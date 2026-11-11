# Connected ImageWAM MM mapping and scheduling

Date: 2026-11-10. Scope: user-authorized implementation of a connected ImageWAM
workload and AIE mapping/scheduling exploration, followed by an explicit request
to document the changes. Sources: [detailed diagram](../imagewam-detailed.png),
[operation inventory](../imagewam_aie.md), current CHARM source and host checks.

Status: implemented and host-checked. Eight MM-only mapping/scheduling candidates
were evaluated. The subsequent [source-generation integration](imagewam_aie_generation.md)
now emits actual MM kernels, graph sources and mapping artifacts from the same
runner. No vendor compilation, simulation, synthesis or board execution was
performed. This is not a verified full-model accelerator.

## What changed

The previous runner searched each of 31 GEMM shapes independently. It had no
producer/consumer connections, shared-array configuration or execution schedule.
The current runner constructs the complete operator dependency graph directly in
Python. CHARM chooses one fixed MM configuration for all shapes assigned to an
array, and a scheduler evaluates those arrays against the graph dependencies.

| File | Change |
| --- | --- |
| [`run_dse.py`](../../example/ImageWAM/run_dse.py) | Directly constructs prefill and ten action steps, connects outputs to consumers, then invokes mapping; results remain in named Python variables |
| [`example/ImageWAM/graph_mapping.py`](../../example/ImageWAM/graph_mapping.py) | New small graph representation, grouped CHARM search, rectangular compute-region placement, serial/fork scheduling, tensor lifetime records |
| [`CDSE/cdse.py`](../../CDSE/cdse.py) | Optional multi-shape workload and AIE-only objective; returns per-shape service-cycle estimates; default system search remains available |
| [`CDSE/devices.py`](../../CDSE/devices.py) | Allows reducing `aie_cols` and `aie_rows` as region limits, in addition to the existing resource limits |
| [`check_graph_mapping.py`](../../sim/tmp_imagewam_charm_dse_vek280/check_graph_mapping.py) | Host checks for graph connectivity, counts, cache reuse, dependencies, array reuse, geometry and DSE regression |
| [Case README](../../sim/tmp_imagewam_charm_dse_vek280/README.md) | Current execution and inspection instructions; historical outputs distinguished from current in-memory results |

The runner has no local function definitions, CLI parser, JSON handling,
file-based model input or try/except wrappers. Following the explicit generation
request, it now writes source/mapping artifacts and prints one completion line. It uses
NumPy arrays to specify input/weight shapes. The graph operations and mapping
algorithm live in `example/ImageWAM/graph_mapping.py`; they are necessary to retain connections
and search/schedule arrays, not numerical NumPy inference. `Graph.mm()` returns
a tensor descriptor, while the final mapping stores CHARM configurations.

The original `CDAC/cdac.py:cdac_top` is not called or claimed to have been ported.
Its size-sorted grouping does not preserve ImageWAM branch dependencies. The new
outer mapping uses the existing VEK280-aware `CDSE.cdse_top` enumeration, broadcast
rules, tile shape and compute estimate, extended to evaluate a group of shapes.
This is a bounded candidate exploration, not an exhaustive architecture optimizer.

## Graph connectivity

The graph contains 8,428 nodes, including inputs, control/layout/nonlinear nodes
and 2,367 MM nodes. There are 31 distinct GEMM shapes. The 1,817 learned Linear
invocations are individual nodes; 550 attention MM nodes each represent a
synchronized batch of 24 heads, giving 15,017 total head-expanded MM invocations.

- Prefill executes once: input and time/modulation projections, five double
  blocks with separate text/image streams, token join, then twenty single blocks.
- Every Q/K/V projection feeds head split; Q/K feed RMSNorm and RoPE. QK feeds
  score scaling/masking, ConSmax and then PV with the corresponding V input.
- Single blocks fork from the same normalized input into QKV and G/U.
  `HardSwish(G) * U` joins merged attention before the output projection.
- Double blocks connect attention output projection and gated residual to the
  subsequent FFN normalization, G/U, down projection and residual.
- Prefill records 25 pairs of K/V tensor references. Each action layer reads the
  matching prefill pair in all ten steps. Cache tensors do not grow across steps.
- Each action step includes conditioning, input projection, all 25 blocks,
  velocity head and Euler update. The next step references the preceding Euler
  output. A phase barrier places action after the completed prefill.
- Final denormalization consumes the tenth Euler output.

Position tables, masks, normalization coefficients, quantization parameters and
ConSmax parameters are not numerically evaluated. Non-MM nodes record dependencies
and shapes, not complete arithmetic interfaces. Conditioning SiLU remains as drawn;
its substitution is still unresolved. MLP activation is the agreed HardSwish.

## Grouped CHARM search

`cdse_top(..., workload=rows)` accepts positive `[M,K,N,count]` rows, minimizing
count-weighted costs over one common `A/B/C`, broadcast and `X/Y/Z` configuration.
The result includes `workload_MKN_count` and `cycles_per_invocation`. The internal
candidate table now allocates a cost column for each workload row. With no
`workload`, the ordinary two-operand API remains in use.

This is essential for array reuse: choosing a different A/B/C for every MM and
pretending those configurations are one fixed engine would not establish a
reusable placement. Within a selected region, all assigned projections now use
the same configuration, with operation-specific repetition/padding costs.

### AIE-only objective

The new optional `aie_only=True` path is explicitly narrower than CHARM's system
model. It retains 64x64x64 INT8 kernels, local-memory checks, A/B/C enumeration,
broadcast/packet factors and region geometry. It fixes X/Y/Z to 1 because those
factors aggregate PL system buffers in the original flow. Long dimensions are
handled as repeated kernel-array passes in the cost estimate.

For each shape, the service-cycle proxy is:

```text
AIE_CYCLE = max(Mtile*Ktile/4, Ktile*Ntile/4, inherited_kernel_cycles)
            + (Mtile*Ktile/4)*PACK_IN + (Mtile*Ntile/4)*PACK_OUT
passes = ceil(M/(A*Mtile)) * ceil(K/(B*Ktile)) * ceil(N/(C*Ntile))
MM service cycles = AIE_CYCLE * passes
```

This is the existing CHARM kernel/input/output service estimate applied to array
passes. It is not calibrated for the ported AIE-ML implementation. It excludes
PL/DDR load/store costs, PL buffer allocation and PLIO feasibility rejection.
Model fields record `scope='aie_mm_service_cycles'` and
`pl_resources_allocated=False`. Reported legacy PLIO demand is not a routed port
assignment. Buffer-selection columns in these configs must not be interpreted
as validated PL buffers or fed directly into a complete-system generator.

A preliminary conventional search with a per-head allowance of 20 BRAM, 8 URAM,
4 input PLIOs and 3 output PLIOs found no configuration. This was not treated as
proof that 24-head AIE execution is impossible. The AIE-only path follows the
agreed scope and leaves the excluded transport/buffering problem unresolved.

The default `aie_only=False` path keeps the original PL/DDR-aware objective and
resource checks. No kernel arithmetic, numerical interface or template changed.

## Candidate placement and schedule

Candidate settings are literal Python arguments in the runner:

```python
mapping = map_graph(imagewam, head_budgets=(4, 8), splits=(None, 0.5))
```

- All candidates have 24 simultaneous head engines. Each head engine reuses one
  configuration for prefill/action QK and PV; QK and PV execute in dependency order.
- Head budgets of 4 and 8 tiles are explored. Identical head-array rectangles are
  packed into a region on the right of the 38-col x 8-row device.
- Remaining cols form either one shared projection region (`None`), or two
  equal-width regions (`0.5`) for linear versus MLP projections. CHARM searches
  within each region's col/tile limit. The chosen rectangles cannot overlap.
- Each physical arrangement is evaluated with serial MM execution and with
  dependency/resource-constrained overlap. Both preserve the 24-head batch.
- The scheduler uses construction-order list scheduling. It is not an exhaustive
  schedule search and does not implement tile-level producer/consumer pipelining.
- Non-MM nodes have unknown duration and no allocated engine. Their timestamps
  are dependency propagation points with zero added cost. They are explicitly
  listed in `unplaced_operations`; zero is not a claim about their hardware latency.

### Executed results

The following values are uncalibrated MM service-cycle proxies, not microseconds
or measured full-model latency. All eight cases fit compute-region geometry;
that does not establish communication or complete-graph feasibility.

| Head tile budget | Projection regions | MM scheduling | Occupied compute tiles | Service-cycle makespan |
| ---: | --- | --- | ---: | ---: |
| 4 | Shared | Serial | 304 | 288,517,248 |
| 4 | Shared | Fork/join overlap | 304 | **268,027,488** |
| 4 | Equal split | Serial | 288 | 553,759,200 |
| 4 | Equal split | Fork/join overlap | 288 | 418,473,216 |
| 8 | Shared | Serial | 304 | 529,064,352 |
| 8 | Shared | Fork/join overlap | 304 | 514,266,192 |
| 8 | Equal split | Serial | 288 | 1,016,613,504 |
| 8 | Equal split | Fork/join overlap | 288 | 788,293,296 |

The lowest proxy among the tested candidates is:

| Region | Mapping | Placement |
| --- | --- | --- |
| Shared projection array | A/B/C = 1/26/8; 208 kernels; 8 cascades of length 26 | col 0..25, row 0..7 |
| Each of 24 head arrays | A/B/C = 1/2/2; 4 kernels; 2 cascades of length 2 | 2 cols x 2 rows per head |
| Head h, h=0..23 | 96 kernels total | origin col `26 + 2*(h//4)`, row `2*(h%4)` |

For example, prefill single-block QK can overlap V projection after Q/K are
ready. Its PV can overlap G projection. The final projection waits for both
attention and G/U branches. The host test checks a concrete PV/G overlap and
also checks all producer/consumer and engine-serialization constraints.

**This candidate uses every compute tile for MM. It leaves no allocated capacity
for nonlinear kernels.** It is the best tested MM-only proxy, not a recommendation
for a completed all-AIE ImageWAM implementation. Unknown nonlinear resources and
costs may change both the candidate set and ranking.

## Result inspection and storage requirements

Run from `sim/tmp_imagewam_charm_dse_vek280/`:

```sh
python3 -i run_dse.py
```

The script now generates the artifacts described in the
[source-generation note](imagewam_aie_generation.md). These Python variables
remain available with `-i`:

- `imagewam.nodes`: connected operators and their producer references.
- `comparison`: head budget, projection split, overlap flag, occupied tiles and
  service-cycle makespan for each candidate.
- `arrays`: selected fixed configurations, col/row origins and per-shape costs.
- `schedule`: named operations, inputs, engines and proxy start/end times.
- `buffer_lifetimes`: output shape, element count, production point and last
  consumer completion, including K/V reuse across ten action steps.

Lifetimes identify values that must survive; they do not allocate memory or prove
capacity. No cache precision, shared memory-tile arrangement, INT4 unpacking,
wide partial-sum store or full-K reduction owner is chosen. The cache-capacity
limits in the [workload note](../imagewam_aie.md) still apply. Multi-pass numerical
correctness and intermediate interfaces remain unresolved. `complete_graph_feasible`
and `measured_latency` are `None`; routing and packed-INT4 support are false.

## Verification

Command, executed from the case directory:

```sh
python3 -B check_graph_mapping.py
```

Environment: Python 3.10.12, NumPy 1.21.5. Exit status: 0. The check executes all
eight candidates, verifies operation and
shape counts, actual fork/join edges, layer-matched cache identity across all
action steps, step feedback, simultaneous head-engine assignment, non-overlapping
in-bounds array rectangles, engine serialization, dependency timing, local-memory
bounds, tensor cache lifetime and weighted per-shape costs. It also reproduces
the saved 112-kernel VEK280 **system-objective** baseline and verifies that a
single workload row with count 7 preserves the selected configuration and scales
its objective by 7. The direct runner has no function definitions or try/except.

An initial overlap assertion checked QK against G specifically and failed:
QK actually overlapped V in the selected schedule. Inspection confirmed PV/G
overlap, which the corrected check now asserts. This was a test expectation
correction, not a change to the graph or scheduling algorithm.

No hardware latency, numerical inference correctness, routed graph, nonlinear
placement or INT4 implementation was verified. Existing historical case outputs
were preserved and are not read by the runner.
