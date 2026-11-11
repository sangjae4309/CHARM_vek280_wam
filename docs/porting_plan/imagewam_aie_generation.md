# ImageWAM AIE source generation

Date: 2026-11-10. User request: finish the flow so running the ImageWAM script
produces AIE mapping and actual kernel/graph source files, rather than only
in-memory DSE results. This follows the
[connected mapping implementation](imagewam_graph_mapping.md).

Status: implemented and executed. Source generation and host structural checks
passed. No vendor compiler, simulator, synthesis or board execution was launched.
The generated MM compute graphs are not a completed ImageWAM inference design.

## Run and outputs

```sh
cd sim/tmp_imagewam_charm_dse_vek280
python3 run_dse.py
# ./run.sh executes the same flow.
```

This directly constructs the workload, searches the eight mapping/scheduling
candidates, and calls the original CHARM AIE generator for the selected arrays.
It writes actual sources and mapping files and prints one completion line.
No parser, model-file input, JSON configuration or numerical fixture is required.
Reruns regenerate the same case-owned outputs. Unrelated and historical files
are preserved; there is no directory-wide cleanup.

| Artifact inside the case | Contents |
| --- | --- |
| `aie/aie_top_all.cpp` | Separately controllable top-level graph instances `linear`, `head_0` through `head_23` |
| `aie/aie_top_all.h` | Array wrappers with flattened logical ADF packet ports |
| `aie/layer0/` | Projection-array parameters, cascade/array graphs and MM kernel sources |
| `aie/layer1/` through `layer24/` | Corresponding sources for the 24 head arrays |
| `aie/include_paths.txt` | Include directories, relative to the case, for future target integration |
| `mapping.csv` | Array configurations, origins, dimensions, port counts and total kernel iterations |
| `tile_mapping.csv` | One row per compute-kernel instance: col/row, chain, cascade stage, role and actual source path |
| `ports.csv` | All logical input/output port names, packet fan-in/out and unbound status |
| `operations.csv`, `connections.csv` | Full operator inventory and producer/consumer edges |
| `schedule.csv` | Selected arrays and uncalibrated MM-only proxy times for each graph operation |
| `mm_dispatch.csv` | Matrix shapes, transposition, padding, K passes and iterations per dispatched MM/head |
| `imagewam_schedule.hpp` | Standard C++ configuration, operation/dependency and MM dispatch tables; no pretend runtime implementation |
| `tensor_lifetimes.csv`, `candidates.csv` | Value lifetimes and all eight candidate comparisons |
| `design_status.md` | Generated scope, interfaces and unresolved integration requirements |

`python3 -i run_dse.py` additionally keeps `mapping`, `arrays`, `schedule`,
`comparison` and `design` available for inspection after generation.

The subsequent [named-family migration](named_kernel_families.md) replaces
numeric template IDs with strings throughout the input/output configuration.
The generated plan now exposes `Array.kernel_family` and named geometry fields;
its former numeric `Array.config[22]` field is no longer used.

## Source changes

| File | Change |
| --- | --- |
| [`run_dse.py`](../../example/ImageWAM/run_dse.py) | Calls `generate_design(imagewam, mapping, case)` after mapping; prints the source destination and kernel-instance count |
| [`example/ImageWAM/generate_design.py`](../../example/ImageWAM/generate_design.py) | Converts selected arrays into the original CHARM generator configuration; exports exact placement, dispatch and dependency records |
| [`example/ImageWAM/graph_mapping.py`](../../example/ImageWAM/graph_mapping.py) | MM descriptors now retain RHS shape and transposition for correct dispatch metadata |
| [`CACG/gen_aie/gen_aie_design.py`](../../CACG/gen_aie/gen_aie_design.py) | Adds optional `io_mode='ports'`, array names and verbosity; existing default remains PLIO mode |
| [`CACG/gen_aie/gen_combine.py`](../../CACG/gen_aie/gen_combine.py) | Selects the new port-wrapper template and emits separately named array graph instances |
| [`templates/aie/aie_top_ports.h`](../../templates/aie/aie_top_ports.h) | New ADF logical-port wrapper template; preserves separate graph controls |
| [`CACG/gen_aie/gen_array.py`](../../CACG/gen_aie/gen_array.py), [`gen_kernel.py`](../../CACG/gen_aie/gen_kernel.py) | Optional verbosity avoids hundreds of per-file messages; existing defaults remain unchanged |
| [`check_generated.py`](../../sim/tmp_imagewam_charm_dse_vek280/check_generated.py) | Checks rendered source topology, port interfaces, dispatch shapes and iteration counts |

This uses the existing `templates/aie/kernel_int8_packet/` computation,
parameter, graph and placement templates. Kernel arithmetic, buffer ordering,
accumulator type, output width and cascade roles were not redesigned or changed.
There are no empty nonlinear kernels masquerading as implementations.

## Generated mapping

The selected MM-only candidate remains:

- Projection: 208 kernel instances, A/B/C = 1/26/8, col 0..25, row 0..7.
- Heads: 24 arrays of 4 kernel instances each, A/B/C = 1/2/2. Head h starts at
  col `26 + 2*(h//4)`, row `2*(h%4)` and occupies a 2x2 region.
- Total: 25 arrays, 304 distinct in-bounds compute locations, 56 cascade chains.
- Active roles: 56 first-stage kernels, 192 middle-stage kernels and 56 tails.
  CHARM emits four role source files per array (100 `.cc` files); not every role
  is instantiated in every array. Source-file count is not physical-kernel count.
- Projection kernel iterations across the modeled workload: 39,688.
- Each head array's iterations: 3,400.
- Dispatch table: 15,017 per-array jobs linked to 8,428 operation descriptors.

The top retains separate graph instances because the arrays have different
iteration counts and schedules. A single unconditional parent `.run(n)` would
incorrectly give every array the same invocation count. The generated tables
retain dependencies and individual iteration requirements; they are data for a
future runtime, not an implemented DMA/nonlinear execution controller.

The tile CSV includes the packet-array template's logical N-chain permutation
and odd-row anchor adjustment. Validation independently reconstructs locations
from the rendered C++ template instances and compares them with that CSV.

## Why the top exposes logical ports

The selected AIE-only candidate needs 226 logical packet inputs and 28 outputs:
130 inputs for the projection array and 4 per head. A one-to-one binding of all
inputs to 128-bit PLIOs exceeds VEK280's 112 aggregate ceiling. The original
shim-constraint generator also contains original-platform column assumptions.
It would be misleading to emit those constraints as a valid VEK280 transport.

The new port mode therefore generates real packet/cascade/MM graph code with
unbound external ADF ports. It skips shim constraints, text-data fixtures and a
standalone simulation `main()`. No `.aiecst` is generated for this compute top.
The existing PLIO mode is preserved for its existing callers.

An integration must bind these interfaces through a legal transport design,
possibly requiring a different mapping or explicit sharing of interfaces.
This generation does not claim that 226 simultaneous physical PLIOs exist or
that the current source can be compiled as a standalone, fully connected top.
No target compilation command is presented as already valid for that integration.

## Numerical and whole-model limits

- Generated kernels take INT8 operands and retain INT8 cascade partial outputs.
  Packed INT4 weights are not implemented by this source-generation change.
- `K_passes > 1` is explicit in dispatch records. The existing INT8 narrowing
  cannot substitute for a correct wide partial-sum reduction. The output contract
  is labeled `INT8_cascade_partial`; no unapproved overflow/requantization policy
  or INT32 interface change was silently introduced.
- Normalization, modulation, RoPE, HardSwish, ConSmax and other non-MM operations
  remain logical dependency nodes with `source_status=not_generated`. Their
  numerical parameters, source kernels and AIE placement remain separate work.
- All 304 compute tiles are used by this MM candidate. Nonlinear capacity has
  not been reserved or proved sufficient.
- K/V and intermediate lifetimes do not establish physical storage allocation.
- The generated C++ plan is a concrete dispatch/dependency data artifact, not
  an end-to-end runtime, fixture, numerical reference or hardware timing result.

## Verification evidence

Commands executed from the case directory:

```sh
python3 -B run_dse.py
python3 -B check_graph_mapping.py
python3 -B check_generated.py
```

All completed with exit 0. Python 3.10.12 and NumPy 1.21.5 were used.
The graph checks still pass for dependencies, full counts, cache reuse, all
24 heads, source scheduling and the saved original VEK280 system-DSE baseline.
Generated-source checks pass for 25 arrays, 304 unique locations reconstructed
from emitted C++, kernel function/source references, complete Jinja rendering,
port counts, 15,017 dispatches, 8,428 nodes, padding, transpose flags and iteration
counts. The generated non-ADF plan header passed host `g++ -std=c++17 -fsyntax-only`
checks, including static assertions for array/operation/dispatch counts.
This host check does not compile AIE intrinsics or establish target feasibility.

A source-generation regression under `checks/default_io/` verified that the
unchanged default mode still emits PLIO creation, four simulation iterations,
default input filenames and a shim-constraint file. That is a compatibility
check of output generation, not VEK280 validation of the old shim allocator.

No vendor tools were invoked. No full ImageWAM numerical inference or hardware
latency was measured. The generated source and status artifacts are retained
in the case for inspection.
