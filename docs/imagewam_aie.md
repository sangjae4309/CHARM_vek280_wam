# ImageWAM operations and AIE mapping

Date: 2026-11-10. Source: [detailed architecture diagram](imagewam-detailed.png),
read together with the current CHARM sources and the porting notes linked below.
Status: diagram-derived workload inventory and mapping proposal. This document
does not implement kernels, allocate a complete graph, or report measured latency.

## Scope and conventions

Batch is 1. Matrices below omit the batch dimension and use
`[M,K] @ [K,N] -> [M,N]`; weight dimensions are logical multiplication order,
not an assertion about checkpoint storage order. Token positions are matrix
rows; features are cols. Head tensors use `[heads,tokens,head_width]`.

The detailed diagram extends the previous single-block scope to two workloads:

| Workload | Tokens | Residual width | Attention | Blocks | Execution frequency |
| --- | ---: | ---: | --- | --- | --- |
| Image/text-state prefill | Image 288 + text/state 129 = 417 | 3072 | 24 heads, width 128 | 5 double + 20 single | Once per observation |
| Action denoising | 16 | 1024 | 24 heads, width 128; 433 keys | 5 double + 20 single | Each of 10 steps |

**Action residual width 1024 does not make attention width 1024.** Its Q/K/V
projections produce 3072 features, still split into 24 heads of width 128.
Action attention reads 417 cached prefix tokens and 16 current action tokens.

The latest weight assumption is packed INT4 for learned Linear weights, with
INT8 activations at MM boundaries. This is a target assumption, not current
CHARM support: the existing port/DSE uses INT8 operands on both sides. Earlier
isolated measurement cases retain their INT8 configuration. Intermediate
precision, scales and narrowing must be specified separately; INT4 weights do
not imply INT4 scores, probabilities, caches or accumulators.

## 1. Prefill matrix multiplications

### Input and conditioning projections

| Operation | Matrix multiplication | Count per observation |
| --- | --- | ---: |
| Image input | `[288,128] @ [128,3072] -> [288,3072]` | 1 |
| Text/state input | `[129,7680] @ [7680,3072] -> [129,3072]` | 1 |
| Time embedding, first Linear | `[1,256] @ [256,3072] -> [1,3072]` | 1 |
| Time embedding, second Linear | `[1,3072] @ [3072,3072] -> [1,3072]` | 1 |
| Image double-block modulation | `[1,3072] @ [3072,18432] -> [1,18432]` | 1 |
| Text double-block modulation | `[1,3072] @ [3072,18432] -> [1,18432]` | 1 |
| Single-block modulation | `[1,3072] @ [3072,9216] -> [1,9216]` | 1 |

The diagram computes time conditioning at `t=0`. Double-block modulation splits
into six width-3072 coefficient vectors per stream; single-block modulation
splits into three. The diagram explicitly reuses these over 5 and 20 blocks,
respectively. They are broadcast across tokens, not multiplied as dense
`3072 x 3072` matrices. Fixed sinusoidal embedding and the intervening activations
are separate operations. No prefill output head is drawn; the final hidden
tensor is marked as not used by action.

### Double-stream blocks: five layers

Apply the following per block, separately for `T=288` image tokens and `T=129`
text/state tokens. These streams have distinct projections; token concatenation
does not authorize sharing their learned weights.

| Operation | Matrix multiplication | Count per stream per block |
| --- | --- | ---: |
| Q, K, V projections | `[T,3072] @ [3072,3072] -> [T,3072]` | 3 |
| Attention output projection | `[T,3072] @ [3072,3072] -> [T,3072]` | 1 |
| G, U FFN projections | `[T,3072] @ [3072,9216] -> [T,9216]` | 2 |
| FFN down projection | `[T,9216] @ [9216,3072] -> [T,3072]` | 1 |

The drawn FFN input Linear combines G/U as
`[T,3072] @ [3072,18432] -> [T,18432]`, then splits the output cols.
Combined and separate descriptions represent the same logical projections;
they must not be counted twice. Bias handling and physical weight packing must
follow the model when choosing a fused implementation.

Q/K receive RMSNorm per 128-feature head. The two streams join along token rows
in text/state-then-image order before joint attention. Q/K receive RoPE; V does
not. Attention returns `[417,3072]`, split into 129 and 288 token rows before
the separate output projections and FFNs.

### Single-stream blocks: twenty layers

| Operation | Matrix multiplication | Count per block |
| --- | --- | ---: |
| Q, K, V projections | `[417,3072] @ [3072,3072] -> [417,3072]` | 3 |
| G, U projections | `[417,3072] @ [3072,9216] -> [417,9216]` | 2 |
| Output projection after feature concat | `[417,12288] @ [12288,3072] -> [417,3072]` | 1 |

The single block has no separate attention output projection followed by a
separate FFN down projection. It concatenates attention's 3072 features and
the gated MLP's 9216 features, then applies the width-12288 projection.

### Attention in every prefill block

| Operation | Per-head multiplication | Heads per block |
| --- | --- | ---: |
| Score QK transpose | `[417,128] @ [128,417] -> [417,417]` | 24 |
| Weighted value PV | `[417,417] @ [417,128] -> [417,128]` | 24 |

There are 25 attention blocks per observation, hence 600 head instances of
each multiplication. This is an invocation count, not 600 simultaneously
allocated physical engines. The user requests concurrency across the 24 heads
within a block; the dependent layers execute in sequence.

QK transpose and PV multiply dynamic tensors, not learned INT4 weights.
Between them are score scaling by `1/sqrt(128)`, masking and the selected
ConSmax approximation. P's quantization is an explicit interface decision.

## 2. Action-denoising matrix multiplications

### Input, conditioning and output: each denoising step

| Operation | Matrix multiplication | Count per step |
| --- | --- | ---: |
| Action input | `[16,14] @ [14,1024] -> [16,1024]` | 1 |
| Time embedding, first Linear | `[1,256] @ [256,1024] -> [1,1024]` | 1 |
| Time embedding, second Linear | `[1,1024] @ [1024,1024] -> [1,1024]` | 1 |
| Final-head modulation | `[1,1024] @ [1024,2048] -> [1,2048]` | 1 |
| Double-block modulation | `[1,1024] @ [1024,6144] -> [1,6144]` | 1 |
| Single-block modulation | `[1,1024] @ [1024,3072] -> [1,3072]` | 1 |
| Velocity projection | `[16,1024] @ [1024,14] -> [16,14]` | 1 |

Time conditioning changes each step. The modulation outputs split into 2, 6
and 3 width-1024 coefficient vectors; the latter two are reused over the 5 and
20 blocks within that step. Final LayerNorm/modulation precedes velocity
projection. Euler update operates on `[16,14]`; the diagram places FP32
denormalization after step 9. These are not additional GEMMs.

### Action blocks: five double and twenty single per step

| Block | Operation | Matrix multiplication | Count per block |
| --- | --- | --- | ---: |
| Double | Q, K, V | `[16,1024] @ [1024,3072] -> [16,3072]` | 3 |
| Double | Attention output | `[16,3072] @ [3072,1024] -> [16,1024]` | 1 |
| Double | G, U | `[16,1024] @ [1024,4096] -> [16,4096]` | 2 |
| Double | FFN down | `[16,4096] @ [4096,1024] -> [16,1024]` | 1 |
| Single | Q, K, V | `[16,1024] @ [1024,3072] -> [16,3072]` | 3 |
| Single | G, U | `[16,1024] @ [1024,4096] -> [16,4096]` | 2 |
| Single | Output after concat | `[16,7168] @ [7168,1024] -> [16,1024]` | 1 |

The double-block diagram combines G/U in a `1024 -> 8192` Linear, then splits
into two width-4096 tensors. The single block concatenates attention width 3072
and gated MLP width 4096 to get 7168, not 5120 or 12288.

### Attention in every action block

| Operation | Per-head multiplication | Heads per block |
| --- | --- | ---: |
| Score QK transpose | `[16,128] @ [128,433] -> [16,433]` | 24 |
| Weighted value PV | `[16,433] @ [433,128] -> [16,128]` | 24 |

For each layer, concatenate its read-only prefix cache of 417 K/V tokens with
the current step's 16 action K/V tokens. Action K is normalized/rotated before
joining; cached K has already received those operations. Do not apply them
again to cached K. There are `10 * 25 * 24 = 6000` head instances of each MM
per action chunk. The cache remains length 417 across steps; it does not grow
by 16 on every denoising iteration.

## 3. Non-GEMM operations required around AIE MM

These operations are part of the dependency graph even when isolated MM timing
excludes them. An AIE-only implementation would need corresponding vector,
reduction or data-layout kernels. Existing HLS/RTL modules are references, not
already ported AIE implementations; see [nonlinear source review](imagewam.md).

| Operation | Shape / reduction domain | AIE mapping implication |
| --- | --- | --- |
| LayerNorm | Per token over 3072 features in prefill; 1024 in action | Whole-feature reduction; an individual N tile cannot normalize independently |
| Modulation | `(1+scale)*x + shift`, coefficient vectors broadcast across token rows | Vector operation after norm; preserve coefficient order and scale |
| Q/K RMSNorm | Per token/head over 128 features | Keep one head's reduction together; V bypasses |
| RoPE | Q/K pairs: 64 pairs per 128-feature head | Pairwise rotation with position tables; separate prefill/action positions |
| Head split/merge | `T x 3072 <-> 24 x T x 128` | Reshape plus stream reorder/transpose; not necessarily free data movement |
| Score scale and mask | `417 x 417` or `16 x 433` per head | Mask logical padding before attention weights contribute to PV |
| ConSmax | Same score shapes | Requires model parameters and explicit P representation; not implemented by ordinary softmax automatically |
| G activation and G*U | `T x 9216` prefill; `16 x 4096` action | User-selected HardSwish replaces MLP SiLU; elementwise product and requantization |
| Gated residual addition | `T x 3072` or `16 x 1024` | Preserve residual until the dependent branch returns |
| Token/feature concat and split | 129+288 token rows; 3072+9216 or 3072+4096 feature cols | Preserve diagram ordering and downstream tiled layout |
| Time embedding and modulation activations | Fixed sinusoidal width 256; width-3072/1024 activations | Small-vector work; not large GEMMs |
| Euler update / denormalization | `16 x 14` | Vector/scalar arithmetic; final FP32 path is outside the current INT8 MM port |
| Quantization / INT4 unpack | Operator and tile boundaries | Define signed packing, scales, rounding and saturation before implementation |

The confirmed HardSwish choice concerns the MLP gate. Whether to replace the
additional conditioning/modulation SiLU nodes likewise remains to be confirmed.
ConSmax parameters and exponential base must come from the chosen model;
the earlier REATA review did not establish an explicit base-e to base-2 formula.
No arbitrary parameter values are selected here.

## 4. Mapping onto CHARM and VEK280

### Existing mapping mechanics

CHARM maps one GEMM using kernel dimensions `(h1,w1,w2) = (Mtile,Ktile,Ntile)`.
Its `A/B/C` factors are parallel M partitions, K cascade stages and parallel N
partitions. The physical compute-kernel count is `A*B*C`, with `A*C` output
chains of length B. `X/Y/Z` are scheduled repeats, not extra physical kernels.
Broadcast shares the LHS across appropriate N consumers and the RHS across M
consumers; it does not allow unrelated layers to share learned weights.

The current VEK280 DSE has 304 compute tiles in 38 cols x 8 rows, 64 KiB local
data memory per tile, and fixed INT8 kernel dimensions `64 x 64 x 64`.
See [VEK280 resource model and evidence](porting_plan/vek280_dse.md) and
[`CDSE/devices.py`](../CDSE/devices.py). Memory tiles are not automatically
used as extra local buffers by this generator.

The initial executed VEK280 search among these workload shapes was
`[417,3072] @ [3072,3072]`, using INT8/INT8:

| Mapping item | Existing result |
| --- | --- |
| A/B/C | 7 / 4 / 4 |
| Physical kernels | 112 = 28 output chains, each with 4 cascade stages |
| X/Y/Z | 1 / 2 / 2 |
| System M/K/N tile | 448 / 512 / 512 |
| Outer M/K/N repeats | 1 / 6 / 6 |
| Placement candidate | col 5..32, row 0..3 |

This is a resource-model result, not a compiled placement or an INT4 result.
The timing model still includes inherited PL/DDR costs and uncalibrated kernel
cycles; it is not an AIE-only optimizer. A four-stage cascade covers K=256 per
pass, not all 3072. Repetition and partial-result accumulation are essential.

### Proposed allocation strategy, pending search and implementation

1. **Reuse CHARM GEMM arrays across layers and projections.** Begin with a shared
   projection array and schedule Q/K/V and G/U operations through it. Load the
   corresponding weight tiles as needed. Do not allocate a complete physical
   copy for every logical Linear. Three copies of the existing 112-kernel Q/K/V
   candidate alone would require 336 tiles, exceeding 304.
2. **Search large prefill and small action workloads separately.** Prefill M is
   129, 288 or 417; action M is 16 and conditioning M is 1. A 64-row tile uses
   at most 25% of its M lanes for action and 1/64 for conditioning. First record
   current-template baselines; a smaller M kernel is a subsequent template/cost
   model change, not a shape the current DSE already optimizes.
3. **Reserve 24 concurrent head groups for attention.** Each group owns its
   Q/K/P/V tiles and runs QK, ConSmax and PV in dependency order. QK and PV may
   reuse that group's MM resources if a compatible graph is implemented.
   A head group is not necessarily one tile. The MM count, norm/ConSmax kernels,
   buffers and routing must jointly fit the device. A budget equation is
   `24 * tiles_per_head_group + shared_tiles <= 304`; it does not determine the
   unknown per-head allocation. Do not multiply 112 by 24: that candidate is
   for a different GEMM shape.
4. **Place data-related kernels together.** Preserve the generator's K cascade
   adjacency for MM, then evaluate nearby head-local RMSNorm/RoPE and attention
   processing. Plan split/merge routes around head groups. No absolute tile
   coordinates for this larger graph are established by the existing search.
5. **Schedule the fork/join explicitly.** A shared projection array can run GU
   and QKV in sequence while preserving their outputs, then execute the
   dependent MLP/attention branches. Concurrent branch arrays are a later
   budgeted search option. Both branches must complete before single-block
   concat and output projection. LayerNorm and residual storage also consume
   resources; the diagram's fork does not prove hardware concurrency.

Independent DSE runs for every operator must not each consume the full device
budget and then be combined as if those mappings coexist. A fixed full-workload
graph needs jointly compatible placements and interfaces; temporal reuse needs
explicit schedules and data paths. Neither follows automatically from finding
a good array for one shape.

### Padding, reduction and memory constraints

- With 64-sized MM dimensions, token dimensions 129/288/417 round up to
  192/320/448 before any extra array-level padding. Attention's 433-key
  dimension rounds up to 448. Zero-pad reduction inputs, mask padded score
  cols, and discard padded output rows/cols. Action input K=14 and output N=14
  also need tail handling. Physical padding does not alter logical model sizes.
- AIE-only execution of long-K products needs a defined owner and wide storage
  for partial sums across cascade passes. Existing isolated AIE probes narrow
  their final cascade output to INT8 and do not implement full-K accumulation.
  They cannot yet establish full Linear correctness or latency. See
  [split-case implementation limits](porting_plan/imagewam_split_measurements.md).
  An accumulator/interface change requires agreement; this document does not
  choose one or substitute a new reduction architecture for CHARM.
- Packed INT4 reduces weight storage, but unpacked operands, ping/pong buffers,
  partial sums, stack and residuals still need space. A `3072 x 3072` weight is
  4.5 MiB packed; a `3072 x 9216` weight is 13.5 MiB. Neither fits a single
  tile's 64 KiB. The existing kernel does not consume packed INT4 directly.
- Prefill writes one K and one V tensor `[24,417,128]` for each of 25 layers.
  This is 64,051,200 elements total: about 61.08 MiB at INT8, or 122.17 MiB at
  INT16, excluding metadata. Cache precision is unresolved. Even INT8 exceeds
  all 38 MiB of memory-tile storage, before other buffers; full-cache residency
  there cannot be assumed. This is a capacity observation, not a new PL design.
- Full score storage per head is 173,889 elements for prefill and 6,928 for
  action. Prefill scores already exceed one tile's local capacity at INT8.
  Blockwise score/ConSmax/PV processing is therefore a candidate to evaluate,
  not a currently implemented FlashAttention kernel. Preserve approximation
  semantics and accumulation precision when choosing a tiled schedule.

## 5. Open decisions and validation boundary

Before assigning final AIE counts, resolve packed INT4 layout/dequantization,
partial-sum precision and ownership, MM/nonlinear interfaces, cache precision,
and learned nonlinear/quantization parameters. Confirm bias terms and the
scope of HardSwish outside MLP gates from model sources. The diagram supplies
shapes, but not those numerical contracts.

The workload is now constructed as a connected operator graph in
[`run_dse.py`](../example/ImageWAM/run_dse.py). A grouped CHARM
search gives each shared array one fixed configuration, and an outer scheduler
compares serial versus fork/join execution with 24 head engines. See
[implemented graph mapping, changes and verification](porting_plan/imagewam_graph_mapping.md)
for the eight executed MM-only candidates and their limits. The independent
system-objective results above remain historical; they use a different cost model.

The new graph includes nonlinear/layout dependencies, but does not allocate
those operations or model their duration. Cache lifetimes are recorded without
choosing physical storage. INT4 support, partial-sum correctness, nonlinear
resources, routing and calibrated timing remain unresolved. Compiler, simulator
and board validation remain user-run steps; none were run for this implementation.
No whole-block or action-chunk hardware latency is established here.

The same runner now also generates real CHARM INT8 MM kernel/cascade/array
sources and explicit placement/dispatch artifacts. See
[AIE source generation](porting_plan/imagewam_aie_generation.md) for file paths,
verification and the distinction between generated compute graphs and a
transport-bound, numerically complete ImageWAM implementation.
