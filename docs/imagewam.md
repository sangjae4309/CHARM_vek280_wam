# ImageWAM nonlinear modules and CHARM integration

Inspected: 2026-11-10. Source repository: `~/workspace/wam-modules`, resolved to
`/localssd/spa315/workspace/wam-modules`, commit
`11fbc9bacae04d019ef3a7a34d19cd7f79102d85` (clean working tree at inspection).
Sources and saved reports were read; no synthesis, compiler, simulation or
board execution was performed. Links below assume the repositories are siblings.

## Agreed workload

The user selected INT8 matrix multiplication, latency from LayerNorm start to
the final Out Linear output, pre-prepared input/weights, and 24 concurrent
attention heads. On 2026-11-10 the user selected separate operation-specialized
INT16 nonlinear modules from `isolated_lut_only` as the source baseline. This
does not impose LUT-only resource mapping on VEK280; fixed-point scales remain
open. The user subsequently
selected HardSwish as the replacement for the diagram's SiLU; this decision
does not approve reusing the existing quadratic approximation unchanged.
FP32 **AIE matrix-multiply porting** is deferred.

The user subsequently selected **ConSmax** as the softmax replacement
(2026-11-10), citing REATA (TRETS 2026). This supersedes the ordinary/online
softmax baseline below; existing module descriptions remain a source inventory.
No ConSmax implementation or timing result has been produced in this project.

The [block diagram](../sim/tmp_imagewam_fork_join/imagewam-fork-join.png) has
batch 1, 417 tokens, hidden width 3072, MLP width 9216, and 24 heads of width 128.
See [block scope and timing assumptions](porting_plan/imagewam_block_scope.md)
for the complete MM shapes and latency-estimation discussion.

## Repository organization and provenance

| Source area | What it contains | Interpretation |
| --- | --- | --- |
| [`original/nonlinear`](../../wam-modules/original/nonlinear/) | INT16 HLS elementwise module and separate normalization module | Runtime operation selection; integer shifts/scales are part of the interface |
| [`original/nonlinear-FP`](../../wam-modules/original/nonlinear-FP/) | Floating-point HLS variants | Default lane type is `half` (FP16); `USE_BF16` selects `ap_float<16,8>`; normalization statistics are `float` |
| [`original/sidecar`](../../wam-modules/original/sidecar/) | RTL vector sidecar and online-softmax/weighted-value accumulator | Different protocols, opcodes and normalization scope from HLS |
| [`isolated_lut_only`](../../wam-modules/isolated_lut_only/) | Operation-specialized sources, generated RTL, scripts and saved reports | Separate fixed INT16 and FP16 cases, plus RTL cases; source op is made constant so unused branches can disappear |

The original HLS README mentions Vitis/Vivado 2025.2 and ZCU102/VEK385 targets.
The **isolated saved results** instead identify Vitis HLS/Vivado 2023.2,
`xczu7ev-ffvc1156-2-e` (ZU7EV), and a 3.3 ns clock target. Neither is evidence
of a VEK280 build. Metadata's historical source commit differs from the current
repository HEAD; both are recorded, not assumed equivalent.

The [isolated metadata](../../wam-modules/isolated_lut_only/metadata.json)
explicitly states `functional_simulation_performed: false` and
`place_and_route_performed: false`. Its 20 verified cases concern resource
checks. All 33 source hashes listed in the current
[summary](../../wam-modules/isolated_lut_only/summary.json) matched their case
source files during this read-only inspection. Hash agreement establishes source
identity, not functional correctness or achieved frequency.

## Mapping the diagram to available modules

| Diagram operation | Available source | Fit or gap |
| --- | --- | --- |
| LayerNorm over 3072 features | HLS `norm`, `OP_LNORM` | Whole-row statistics span 96 vectors of 32 lanes; not the RTL sidecar's single-vector RMSNorm |
| `(1+scale)*x + shift` | HLS `OP_FMA` | Can express vector modulation with appropriately prepared operands; scale/shift broadcast and Q formats need definition |
| Q/K RMSNorm over 128 features | HLS `norm`, `OP_RMSNORM` | Four 32-lane blocks per head/token; gamma stream and precision must match the model |
| Q/K RoPE | HLS or RTL `OP_ROPE` | Adjacent even/odd pairs; sine/cosine values are supplied externally |
| SiLU(G), replaced by user-selected HardSwish(G) | Existing operation is named `OP_GELU` | Standard HardSwish is not the existing quadratic; an implementation matching the chosen fixed-point scale is required |
| Elementwise activation(G) times U | HLS `OP_FMA` with zero additive input/bias | Candidate composition, not an existing wired SwiGLU block; product shift and saturation need agreement |
| Score scaling by `1/sqrt(128)` | Integer requant/scale machinery is a candidate | Not built into the online-softmax input interface; score representation must be specified |
| Pad mask and user-selected ConSmax | No ConSmax found in inspected sources | Existing `rgemm_online_softmax` uses a different algorithm and cannot be reused unchanged |
| Head merge/transpose and feature concat | External data movement | Not implemented by these arithmetic modules; include buffers, ordering and backpressure in integration |
| Conversion to next INT8 MM | Integer requant is a starting point | Existing requant output saturates to INT16, not INT8; adapters and quantization policy are still needed |

## Integer elementwise arithmetic

Source: [`original/nonlinear/nonlinear.cpp`](../../wam-modules/original/nonlinear/nonlinear.cpp)
and [`nonlinear.h`](../../wam-modules/original/nonlinear/nonlinear.h).
The isolated INT16 variants retain these formulas with a constant selected op.

- 32 lanes, `ap_int<16>` data and `ap_int<48>` arithmetic helper type.
- `lane_mask_i` disables lanes by writing zero.
- `shift_i` is unsigned 5-bit and means an arithmetic **right shift**.
- `clip16` saturates to [-32768, 32767]. No INT8 saturation is provided here.
- HLS requests `PIPELINE II=1` and unrolls the lane loop. This directive is not
  proof of achieved system throughput.

| Operation | Source behavior |
| --- | --- |
| Requant | `clip16((x*scale_i + bias_i) >> shift_i)`; scalar scale and bias |
| ReLU | `max(x,0)` |
| Activation named GELU | `0` for x <= -512; x for x >= 512; otherwise `clip16((x*(x+512)) >> 10)` |
| RoPE even | `clip16((x_even*cos_q7 - x_odd*sin_q7) >> 7)` |
| RoPE odd | `clip16((x_even*sin_q7 + x_odd*cos_q7) >> 7)` |
| FMA | `clip16(x + ((aux*aux2) >> shift_i) + bias_i)` |

The integer activation is a piecewise quadratic in source-described “Q8-like”
units. The README labels it a GELU/SiLU approximation, but this does not establish
its approximation error or equivalence to the user-selected HardSwish. The floating-point
variant instead evaluates a tanh-based GELU approximation; it is not the same
function as the integer approximation and is not a dedicated SiLU either.

### User decision: HardSwish instead of SiLU

Confirmed 2026-11-10. Use `HardSwish(G) * U` for the MLP gate, replacing the
SiLU shown in the diagram. The mathematical operation is:

```
HardSwish(x) = x * clamp(x + 3, 0, 6) / 6
            = 0                 when x <= -3
            = x*(x+3)/6         when -3 < x < 3
            = x                 when x >= 3
```

For a signed integer encoding X with real value x = X/S and the same output
scale S, the interior integer expression is `X*(X+3*S)/(6*S)`, with thresholds
`-3*S` and `3*S`. Its rounding, intermediate width and final saturation must be
specified before implementation. With S=256, for example, the thresholds are
±768 and the divisor is 1536. This is an illustrative scale, not an agreed one.
The existing activation instead uses ±512 and divisor 1024; at S=256 it has
±2 boundaries. It must be adapted rather than silently relabeled HardSwish.

Status: algorithm choice recorded; no HardSwish RTL/HLS source was added or
changed during this documentation task. Gating multiplication by U remains a
separate operation unless explicitly fused during implementation.

RoPE expects aux lanes `[cos0,sin0,cos1,sin1,...]`. Angle generation, position IDs,
frequency base and any multidimensional ImageWAM position mapping are external.
A compatible adapter must preserve pair alignment and masks.

For modulation, one possible operand assignment is `x=shift`, `aux=normalized`,
`aux2=1+scale`, with zero scalar bias and correctly encoded fixed-point unity.
This is a proposed composition, not evidence that the repository already wires
ImageWAM AdaLN in this way. For gating, `x=0`, `aux=activation(G)`, `aux2=U`
provides a multiply through the same formula after choosing its shift.

## Normalization and reduction scope

Source: [`original/nonlinear/norm.cpp`](../../wam-modules/original/nonlinear/norm.cpp).
The active synthesis script selects this file. The older `norm_const_ite.cpp`
contains softmax-related experiments but is not selected by the inspected
`norm_csynth.tcl`; it is not treated as a ready softmax implementation.

The integer normalization module has three dataflow tasks:

1. Accumulate masked sum, sum of squares and active count over `num_blks`
   32-lane vectors. Forward x, gamma and masks through an internal FIFO.
2. Compute integer mean and mean-square. RMSNorm uses mean-square; LayerNorm
   uses `max(mean_square - mean*mean, 0)`. Compute integer square root of that
   quantity plus **1**, clamp root to at least 1, and form
   `inv = (1u << (2*scale_i)) / root`.
3. Apply `clip16((((x-mean)*gamma*inv) >> shift_i) + bias_i)`; RMSNorm uses
   mean=0. Masked lanes produce zero.

This is integer arithmetic with truncating divisions, an integer-domain `+1`
regularizer and 48-bit intermediate assignments. It must not be described as
floating LayerNorm with an arbitrary model epsilon. The legal scale range also
needs explicit control: the source uses a 32-bit `1u` left shift even though
`scale_i` accepts five bits. Values leading to a shift of 32 or more cannot be
assumed valid.

For the diagram, LayerNorm can be expressed as `num_ites=417`, `num_blks=96`.
Head-width RMSNorm uses `num_blks=4`; each head processes 417 rows for Q and 417
for K. These are proposed invocation sizes inferred from the diagram, not tested
configurations. Header constants mention 256 iterations, but current integer
`norm.cpp` uses dynamic loop bounds rather than a fixed 256-entry frame array.
Therefore 417 must be checked with buffering/control tests, not declared either
supported or impossible merely from the constant's name.

The FIFO carrying x/gamma/masks has depth `MAX_NORM_BLKS+256 = 352` vectors.
Output waits for row statistics; this creates startup latency and buffer demand.
Runtime row/block counts leave top-level HLS latency and interval as `?` in the
isolated reports. “32 lanes” does not imply one entire normalization row per cycle.

The floating variant uses FP16 (or optional BF16) lanes, float statistics, an
extra `FPAcc` stage, and `1/sqrt(max(value,0)+1e-6)`. It writes back to the lane
format. It has no equivalent integer shift/scale controls and no beta addition
in its inspected normalization apply stage.

The RTL vector sidecar's RMSNorm reduces only the active lanes of its current
32-lane vector. Sending four head chunks independently would perform four
separate normalizations, not RMSNorm over 128 features. HLS multi-block norm is
therefore the closer structural match.

## Selected softmax replacement: ConSmax

Decision and source review date: 2026-11-10. The user selected ConSmax and
reported its use in [REATA](https://doi.org/10.1145/3779444). The publisher page
returned HTTP 403, but the user subsequently supplied
[`REATA.pdf`](../sim/tmp_imagewam_fork_join/REATA.pdf).
Its section 4.2, PDF pages 16–17, explicitly uses ConSmax in Equation 9 and
describes local AIE attention processing. The extracted text contains no
explicit base-e to base-2 replacement formula; therefore that replacement is
**not confirmed** by this inspection. No base-2 policy is inferred for our
measurement cases. PDF SHA256:
`b116a3bf950aa75ae4071eb5bf9388f405ff430639b27d21ebb06142491a0df8`.

The [ConSmax paper, Equation 2](https://arxiv.org/html/2402.10930v3) defines
`ConSmax(s_i) = exp(s_i - beta) / gamma`. Parameters are learned during training
and fixed during inference, with head-specific values. This removes the score
row maximum and denominator-sum reductions. Outputs need not sum to one.
This is a replacement function, not the running normalization used in online
softmax or exact FlashAttention.

Proposed partition: `AIE QK^T -> PL score scaling / mask / ConSmax -> AIE P*V`,
where P denotes attention weights, not necessarily normalized probabilities.
Elementwise ConSmax can emit weights without waiting for a whole score row;
actual overlap still depends on CHARM tile order and buffers. Masked entries
must contribute zero weight. The P*V reduction remains necessary.

Open: ImageWAM beta/gamma values, quantization and LUT representation, and
REATA-specific modifications. Placeholder parameters for a latency experiment
would not establish model accuracy. The INT16 module baseline alone does not
select a validated INT16 ConSmax implementation. No implementation was found by
a case-insensitive ConSmax/REATA search of the inspected local Markdown, C++,
headers and Verilog sources.

The user requested five independent measurement cases and explicitly asked
that model-dependent parameters be replaceable later. See
[the split measurement preparation](porting_plan/imagewam_split_measurements.md).
Unknown values remain null and block execution; they are not filled with
unapproved test defaults. A transient INT4 request was corrected to INT8.

## The repository's online-softmax module is an attention accumulator

Source: [`rgemm_online_softmax.v`](../../wam-modules/original/sidecar/rgemm_online_softmax.v),
also copied into the isolated `rtl_softmax_zu7` case.

- Defaults: TILE=16, 16-bit score/value data, 32-bit running sum/output.
- Input contains 16 scores and 16 values for **one query row and one V channel**.
- Maintains running maximum, denominator and weighted V numerator across tiles;
  rescales prior state when the maximum changes.
- Exponential weights are an integer step approximation: delta >=0 gives 256;
  thresholds -2, -4, -8, -16 and -32 give 220, 188, 128, 64 and 16; lower values
  give zero. Score scaling is consequently essential to its meaning.
- `normalized_o` is a clipped scaled weighted result,
  `(running numerator << 8) / denominator`, not a vector of probabilities P.
- `start_i` resets row state; `valid_i` and masks control updates. There is no
  ready/backpressure input. Output may update after each valid tile; external
  control must identify the last tile of a query row.

417 keys require 27 tiles, with one valid element in the final tile. A 128-wide
V result requires replication, scheduling or a redesigned shared-state datapath;
the reported single-value-channel module is not a complete 128-wide head.
Likewise, 24 concurrent heads are not automatically provided by this module.

Using it would move weighted-value computation into PL and change the proposed
`PL softmax -> AIE P*V` partition. Keeping the original diagram partition requires
a probability-output softmax design. This earlier comparison is superseded for
the target workload by the user's ConSmax selection above.

Online softmax incrementally updates normalization statistics across score tiles;
the term alone does not require weighted-V accumulation. This particular RTL
also maintains that weighted numerator. In exact arithmetic, rescaling old
statistics when the running maximum changes preserves full-row normalization;
it is not independent softmax within each tile.

[FlashAttention](https://arxiv.org/abs/2205.14135) combines tiled attention and
incremental normalization to reduce transfers between memory levels without
materializing full score/probability matrices in external memory. The inspected
RTL shares the running-statistics idea, but is not a complete FlashAttention
implementation: it receives precomputed scores, handles only one V channel per
instance, and uses an approximate exponential LUT. Selecting separate nonlinear
modules does not select a FlashAttention architecture or approve this numerical
approximation. This comparison is an algorithm/source interpretation recorded
on 2026-11-10, not a hardware verification result.

## Interfaces and differences that matter for CHARM

- INT16 vectors carry 512 data bits per 32 lanes; masks and auxiliary vectors
  add separate information. Current CHARM PLIOs are 128-bit. Packing, rate
  matching, packet headers/TLAST, and control adapters are not supplied by these
  nonlinear function signatures.
- Elementwise HLS functions expose vector arguments; normalization uses
  `hls::stream` interfaces. An `hls::stream` declaration alone does not specify
  the final AXI4-Stream wrapper, packet protocol or XRT kernel control.
- Original RTL and HLS opcodes differ. RTL RoPE is op 4 while integer HLS RoPE
  is op 3; RTL has OP_SCHED while HLS adds a second vector input for OP_FMA.
- Original RTL's signed shift means positive=left, negative=right. Integer HLS
  uses unsigned right-only shift. Controls cannot be copied verbatim.
- Current CHARM INT8 final kernels convert their accumulator to INT8. Widening
  that result to INT16 cannot recover discarded information. A decision is
  needed on MM output scaling and whether the PL boundary should receive INT8
  or a wider result; changing the latter would be an additional AIE interface
  change, not merely connecting a cable.

## Saved synthesis evidence: not VEK280 performance

The following values are copied from the isolated summary. Each HLS elementwise
case covers 32 lanes. LUT means reported total LUTs, including LUT memory where
present. DSP/BRAM/URAM are zero in these saved cases; LUTRAM/SRL/FF are allowed.

| Isolated INT16 case | LUT | FF | HLS latency cycles | HLS interval cycles |
| --- | ---: | ---: | ---: | ---: |
| Requant | 13,121 | 2,167 | 2 | 1 |
| ReLU | 480 | 0 | 0 | 1 |
| GELU approximation | 10,435 | 2,210 | 2 | 1 |
| RoPE | 19,266 | 2,081 | 1 | 1 |
| FMA | 13,684 | 3,225 | 2 | 1 |
| RMSNorm | 98,348 | 21,001 | unknown | unknown |
| LayerNorm | 106,023 | 28,026 | unknown | unknown |
| RTL online softmax, 16 keys / 1 value channel | 8,641 | 92 | not an HLS result | not an HLS result |

Saved FP16 GELU/RoPE/FMA HLS latencies are 59/7/7 cycles, each with reported
interval 1. These are different arithmetic implementations and cannot be
substituted for the INT16 latency entries.

The softmax synthesized timing report has **WNS -66.8 ns** at the 3.3 ns target.
A register-to-register update in RTL is not evidence that this logic meets a
3.3 ns clock. The integer LayerNorm HLS timing estimate is 3.587 ns against a
3.3 ns target, and its top-level latency is unknown. HLS and post-synthesis
reports describe different analysis stages; neither is routed VEK280 timing.

The original `norm.md` separately reports cosimulation results (for example,
256x3072 latency 24,948 cycles and interval 24,604). These are repository-reported
historical results, not independently rerun here, not the isolated LUT-only
case's measurement, and not a 417x3072 VEK280 result. Keep this evidence separate.

## Consequences for the latency study

Derived traffic counts, assuming one 32-lane datapath and the diagram's axes:
LayerNorm has 417*96 = 40,032 vectors; Q and K head-width RMSNorm together have
2*24*417*4 = 80,064 vectors; Q/K RoPE has the same vector count; each full-width
MLP activation or gating pass has 417*288 = 120,096 vectors. These are work counts,
not cycle estimates. Replication, achieved II, reduction startup, stalls and
fork/join buffering determine elapsed latency.

The saved modules provide useful starting points for a representative PL
microbenchmark, but do not yet supply an integrated ImageWAM nonlinear pipeline.
LUT-only implementation is an existing experiment choice, not an agreed VEK280
constraint. It must not silently become a requirement when allocating 24 heads.

## Open decisions

Questions submitted to the user during this inspection:

1. **Resolved (2026-11-10):** use separate isolated INT16 modules as the source
   baseline. LUT-only resource mapping is not an agreed VEK280 constraint.
2. **Resolved:** the user selected HardSwish instead of SiLU. Implement its
   standard formula at the agreed scale; the existing quadratic is not
   automatically accepted as equivalent. Fixed-point scaling remains open.
3. **Updated (2026-11-10):** the user selected ConSmax. The existing combined
   online-softmax accumulator is not the selected normalization algorithm.
   A separate PL ConSmax followed by AIE P*V is the proposed partition;
   parameters and concrete implementation remain open.

Additional unresolved integration details: nonlinear Q scales and internal precision,
INT8 narrowing/rounding/saturation rules, learned parameters and modulation
broadcast shape, model epsilon, RoPE tables and pairing convention, attention
mask values, weight/input memory residency, MLP/attention overlap, instance count,
clock domains and buffering. These remain open; no hardware or numerical policy
has been inferred from the repository name or diagram alone.
