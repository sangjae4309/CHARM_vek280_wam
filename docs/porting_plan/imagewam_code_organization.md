# ImageWAM code organization

Date: 2026-11-11. User decision: model-specific code belongs under `example/`;
core CHARM directories must contain reusable, model-agnostic functionality.
Status: relocation implemented; numerical code and mapping policies unchanged.

## Moves

| Previous location | Current location |
| --- | --- |
| `CACG/imagewam/aie_case.py` | `example/ImageWAM/aie_case.py` |
| `CACG/imagewam/bench.py` | `example/ImageWAM/bench.py` |
| `CACG/imagewam/generate_design.py` | `example/ImageWAM/generate_design.py` |
| `CDAC/graph_mapping.py` | `example/ImageWAM/graph_mapping.py` |
| `templates/imagewam/` | `example/ImageWAM/templates/` |
| Full workload in the VEK280 case's `run_dse.py` | `example/ImageWAM/run_dse.py` |

The graph mapper moves too because it hardcodes the ImageWAM 24-head policy,
projection-group candidates and scheduling assumptions. It is not a general
CHARM graph compiler merely because its internal class is named `Graph`.

The existing `sim/tmp_imagewam_charm_dse_vek280/run_dse.py` becomes a thin import
launcher. Its output location remains the same case directory. Existing split
case launchers import `example.ImageWAM.aie_case` and `example.ImageWAM.bench`;
their repository-discovery paths and the MLP template lookup were updated.
Documentation links now point to the current code locations. There is no
compatibility shim or duplicate implementation under `CACG/imagewam/`.

## Shared functionality retained

- `CACG/gen_aie/`: parameter-driven kernel/array/graph generation, optional
  logical-port top generation and verbosity control.
- `templates/aie/`: reusable datatype/transport kernel templates and the generic
  `aie_top_ports.h` wrapper template.
- `CDSE/`: device resources, region limits, multi-workload array search and the
  optional AIE-only objective. None depends on ImageWAM operator names or heads.
- `CDAC/`: original general accelerator-composition functions.

The rule is also recorded in the repository's `AGENTS.md`. Generated sources,
inputs, historical evidence and unrelated user changes are preserved. No vendor
compiler or simulator is invoked by the relocation.

## Verification

All checks below passed on 2026-11-11; both case check scripts returned exit 0.
The five isolated-case reference plan commands also returned exit 0.

The existing `check_graph_mapping.py` and `check_generated.py` are run against
the retained case launcher. They check the same eight candidates, dependency
and cache constraints, saved system-DSE baseline, 304 emitted kernel locations,
15,017 dispatches and unchanged iteration counts. Split-case `reference.py plan`
commands verify the relocated reference imports. Template files are checked at
the new lookup path. Python syntax and documentation links are checked separately.
