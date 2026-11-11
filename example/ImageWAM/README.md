# ImageWAM example

This directory owns ImageWAM-specific code and assets. Shared CHARM components
under `CACG/`, `CDAC/` and `CDSE/` remain model-agnostic.

| File | Responsibility |
| --- | --- |
| `run_dse.py` | Direct construction of the ImageWAM workload and generation entry point |
| `graph_mapping.py` | ImageWAM's 24-head allocation, projection-region candidates and dependency scheduling |
| `generate_design.py` | Adapts the selected mapping to generic CHARM generation; exports ImageWAM plan artifacts |
| `aie_case.py` | Earlier isolated MM case generation and packet/reference handling |
| `bench.py` | Earlier split-case reference calculations and nonlinear experiment preparation |
| `templates/` | ImageWAM MLP HLS sources and launch template |

Run from the repository root:

```sh
python3 example/ImageWAM/run_dse.py
```

Outputs remain in `sim/tmp_imagewam_charm_dse_vek280/`. The existing case's
`run_dse.py` is a thin launcher for this module, so its previous execution command
also works. `python3 -i` keeps mapping variables available afterward.

The example calls the generic `CACG.gen_aie.gen_aie_top()` with explicit array
configurations and names. Shared AIE kernel templates remain in `templates/aie/`.
No compatibility copy of model code is retained under `CACG/` or `CDAC/`.

[Source generation and limitations](../../docs/porting_plan/imagewam_aie_generation.md) ·
[Mapping and scheduling](../../docs/porting_plan/imagewam_graph_mapping.md)
