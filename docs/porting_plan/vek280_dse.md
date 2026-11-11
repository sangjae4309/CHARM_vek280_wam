# VEK280 resource model for CHARM DSE

Subsequent implementation: [connected ImageWAM mapping](imagewam_graph_mapping.md)
adds optional grouped workloads, region geometry limits and an explicitly
AIE-only service-cycle objective. The single-GEMM system-model results below
remain historical evidence, not results from the new objective.

Date: 2026-11-10. Scope: user-authorized adaptation of the CHARM search to
VEK280 resources. Status: implemented and host-tested; no vendor compiler,
simulator, synthesis or board run. This is resource-aware candidate selection,
not a calibrated VEK280 performance predictor or a packed INT4 implementation.

## Interface and compatibility

```python
final_config = cdse_top(lhs, rhs, device="vek280")
# Also supported through charm(...).cdse(lhs, rhs, device="vek280").
final_config, model = cdse_top(lhs, rhs, device="vek280", return_details=True)
```

The default remains `vck190`. The result retains 22 columns; since 2026-11-11,
column 14 contains a [family name](named_kernel_families.md) and the array uses
`dtype=object`, rather than an all-numeric family-ID configuration.
`CDSE/devices.py` holds hardware capacities and software budgets separately.
The VEK280 path currently accepts matching INT8 operands, corresponding to the
ported packet kernel family. Unsupported operand types are rejected rather
than treated as a valid mixed-precision or FP32 target port.

Optional `resource_limits` can reduce the AIE, BRAM, URAM or PLIO budgets.
Optional `compute_cycles` replaces the fixed kernel-cycle estimate, and
`bandwidth_scale` scales the inherited DDR bandwidth assumptions. A caller
must supply compatible model units; these knobs do not automatically calibrate
clock domains, DMA timing or the remaining pipeline/communication model.
`return_details=True` records the assumptions and selected resource estimates.

## Verified resources versus policies

| Item | VEK280 model | Basis |
| --- | ---: | --- |
| Compute tiles | 304 | VE2802, DS950 |
| Compute array | 38 col x 8 row | DS950; installed platform reports 38 cols and 8 compute rows |
| Local data memory / compute tile | 64 KiB | AM020 |
| Memory tiles | 76 x 512 KiB | DS950 38 cols x 2 rows; AM020 size |
| BRAM capacity | 600 blocks | DS950 Table 4 |
| URAM capacity | 264 blocks | DS950 Table 4 |
| BRAM / URAM search budgets | 500 / 221 | Capacity minus inherited software reserves of 100 / 43 |
| PL interface tiles | 28 | DS950 array interface table |
| Aggregate 128-bit PLIO ceilings | 112 input / 84 output | 28 * (8/2) input and 28 * (6/2) output channels |
| PLIO search budgets | 100 input / 80 output | Inherited conservative software limits below aggregate ceilings |

The reserves and port budgets are policies, not measured platform overhead.
Aggregate PLIO counts do not prove routing or channel-frequency feasibility;
the target mapper still has to assign legal channels. Memory-tile capacity is
recorded separately and is **not** added to private local memory or PL BRAM/URAM
budgets. This CHARM schedule does not allocate memory tiles.

Sources inspected:

- [AMD DS950](https://docs.amd.com/api/khub/documents/BY0FMkLH05y85Nwu4GmWsw/content),
  downloaded document identifies v2.11, August 3, 2026. Copy/text under the case's
  `sources/` directory. VE2802 resource and array-interface tables.
- [AM020 tile architecture](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-Tile-Architecture).
- [AM020 PL interfaces](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-to-Programmable-Logic-Interface)
  for channel widths and pairing; device counts are taken from DS950.
- Installed Vitis 2025.2 platform
  `xilinx_vek280_base_202520_1/hw/aie_primitive.json`: AIEML, 38 columns,
  `AIE_TILE_ROW=3:8`, `MEM_TILE_ROW=1:2`. These encode physical row start/count;
  ADF compute placement continues using logical row 0 through 7.

## Search and memory changes

The enumeration, array footprint rejection and centered placement now use the
selected device's columns/rows/tile budget instead of constants 50/8/400.
BRAM/URAM and PLIO rejection use the selected budgets. Search, broadcast rules,
buffer selection, tiling hierarchy and original cost formula are retained.

For VEK280, the existing INT8 kernel's actual retained addresses are checked:
A at 0x0000/0x2000, B at 0x4000/0x6000, C at 0x5000/0x7000, stack at 0x3000
(1024 bytes, matching case compiler settings). The conservative union accounts
for neighboring-tile A buffers and rejects overlaps as well as capacity
overflow. At 64x64x64, that union reserves 25,600 bytes and ends at address
0x8000. This does not establish bank contention freedom or target compilation.
It also catches M=128 at the retained addresses: A pong overlaps the stack,
even though an isolated capacity-only calculation might fit within 64 KiB.

Kernel shape remains 64x64x64. Enlarging the shape or consuming the extra upper
32 KiB would require new placement/scheduling and a corresponding cost model.
No kernel arithmetic, data layout, output precision or generated kernel source
was changed by this DSE adaptation.

The fixed 2600-cycle INT8 estimate and DDR constants remain inherited CHARM
assumptions by default. The port's compatibility MAC implementation has not
been profiled, so theoretical AIE-ML throughput is not substituted as its actual
speed. Results explicitly carry `performance_calibrated: false`.

## Execution evidence

Case: `sim/tmp_imagewam_charm_dse_vek280/`.

```sh
./run.sh
python3 analyze.py
PYTHONDONTWRITEBYTECODE=1 python3 check_dse.py
```

The 417x3072x3072 INT8/INT8 search completed with exit 0:

- Kernel M/K/N: 64/64/64; A/B/C: 7/4/4 = **112 compute kernels**.
- Broadcast A_BRO/C_BRO: 2/1; PACK_IN/PACK_OUT: 2/2.
- X/Y/Z: 1/2/2; system tile M/K/N: 448/512/512.
- Outer TX/TY/TZ: 1/6/6; padded workload: 448x3072x3072.
- Placement: col 5, row 0, footprint 28 cols x 4 rows (cols 5..32).
- Model allocations: BRAM 448/500, URAM 176/221, PLIO input 84/100,
  output 14/80. Per-kernel scheduled iterations: 144.

This candidate differs from the old 256-kernel result because available
resources and placement limits changed. It is not evidence that 112 kernels
are faster on hardware. Full-K accumulation still relies on CHARM's existing
system schedule; this remains a PL/DDR-aware model, not an AIE-only objective.

Checks passed: full legacy search reproduces its saved 22-column result;
VEK280 capacities/placement constraints; rejection of over-budget resource
requests, overlapping/out-of-range local-memory layouts, unsupported VEK280
dtypes and a resource budget with no valid packet-array candidate.
Evidence: `host_checks.log`, `host_checks.json`, `result.json`, `mapping.json`
and `exit_status.txt`. Existing baseline result files were preserved.

Remaining work: measured VEK280 timing model, INT8-activation/INT4-weight
packing and arithmetic costs, optional memory-tile scheduling, target compile
and routing checks. The full CACG PL/host/platform flow and original shim
constraint generator are not newly validated by this DSE result.

## Whole ImageWAM inventory and independent searches

On 2026-11-10 the user requested expressing the detailed ImageWAM workload in
`run_dse.py`. The initial whole-workload runner described prefill setup, five double blocks,
twenty single blocks, and ten complete action-denoising iterations followed by
denormalization. Named non-MM operations and stage-local dependencies are
included, but receive no GEMM DSE allocation. Conditioning/modulation SiLU
replacement remains unresolved; the MLP gate uses the agreed HardSwish name.
See [full workload dimensions](../imagewam_aie.md).

The inventory uses separate Q/K/V and G/U projections and groups identical
GEMM shapes, retaining all operation use sites and repetition counts. This gives
31 distinct shapes, 1,817 Linear invocations and 13,200 per-head attention MM
invocations per observation plus its ten-step action chunk. Shape reuse is not
weight sharing, fusion, a global schedule or a simultaneous graph allocation.

Executed from `sim/tmp_imagewam_charm_dse_vek280/`:

```sh
./run.sh
```

All 31 independent INT8/INT8 searches completed with exit 0. No vendor tools
were invoked. Outputs are under `imagewam/`; the previous root-level baseline
files are preserved. `workload.json` contains the hierarchical inventory;
`budget_304/mapping.md` has shape and operation tables, and per-shape JSON/NumPy
files retain configurations. `validation.json` records host checks of operation
counts/dependencies, resource/placement bounds, padding, saved configurations,
and reproduction of the earlier 112-kernel result. The report was regenerated
from the completed results after adding its operation-level tables.

| Shape M/K/N | A/B/C | Compute kernels |
| --- | --- | ---: |
| 417/3072/3072 | 7/4/4 | 112 |
| 417/3072/9216 | 7/4/4 | 112 |
| 417/12288/3072 | 7/4/4 | 112 |
| 417/128/417, prefill QK per head | 7/2/4 | 56 |
| 417/417/128, prefill PV per head | 7/4/2 | 56 |
| 16/1024/3072 | 1/2/6 | 12 |
| 16/128/433, action QK per head | 1/2/8 | 16 |
| 16/433/128, action PV per head | 1/8/2 | 16 |
| 16/7168/1024 | 1/4/8 | 32 |

Every search independently receives the device budget. Replicating the selected
prefill head MM 24 times needs 1,344 compute tiles; the action head MM needs 384.
Both exceed 304 before accounting for nonlinear operations. Consequently these
are not valid 24-head concurrent allocations. The runner now executes all shapes directly with the VEK280 defaults; CLI
parsing and selection/budget options were removed at the user's request on
2026-11-10. Workload changes belong directly in the script, with no try/except
wrappers. This preference is recorded in the repository's `AGENTS.md`.
No reduced-budget run was executed here. The simplification was syntax-checked
and its workload compared with the saved inventory; DSE was not rerun.
INT4 support, wide full-K partial sums, routing and calibrated timing remain
unresolved; the table does not establish full-model correctness or latency.

### Subsequent simplification: direct NumPy construction

On 2026-11-10 the user additionally requested removing helper functions,
unnecessary prints, JSON structures and file-based workload construction.
`run_dse.py` now directly creates NumPy arrays and invokes `cdse_top` for the
same 31 distinct shapes. Results remain in named variables. It contains no
functions, parser, try/except, JSON handling or file I/O. `run.sh` directly
executes it. Nonessential progress/banner/blank-line prints were removed from
`CDSE/cdse.py`; search arithmetic and validation remain unchanged.

The earlier inventory, reports and result files above are preserved historical
artifacts, not inputs or outputs of the current runner. A host check substituted
only the DSE call to inspect constructed operand shapes and confirmed all 31
match the saved inventory. Python/shell syntax checks passed; DSE and vendor
tools were not rerun for this simplification. The preference is in `AGENTS.md`.

### Scope correction: whole-model accelerator composition

Source-inspected on 2026-11-10 after the user clarified that the objective is
mapping the full ImageWAM architecture, not independent GEMMs. The existing
`CDAC/cdac.py:cdac_top(MODEL_IN, DATA_TYPE, num_acc)` accepts multiple
`[M,K,N,count]` workload rows. It sorts by per-operation M*K*N, explores group
partitions for a caller-selected accelerator count, apportions resources, and
returns workload assignments and accelerator configurations. `test_cdac.py`
provides existing model examples. This is the relevant original CHARM path to
investigate before inventing a new model-level optimizer.

The VEK280 adaptation above affects `CDSE/`, not the separate `CDAC/` search.
CDAC still uses 400 compute tiles and its inner search retains 50-col placement
limits. Its input contains no dependency edges, nonlinear operators, KV-cache
lifetime or a 24-head concurrency constraint. Its multi-accelerator objective
uses the maximum group cost; it must not be presented as full ImageWAM
dependency-aware latency or a connected AIE graph. Whole-model resource
composition, legal joint placement, dependency scheduling and numerical
interfaces remain distinct unresolved requirements. No CDAC execution or
implementation changes were made during this inspection.
