# Name-based kernel-family selection

Date: 2026-11-11. User request: remove numeric-ID template selection, not just
rename template directories. Status: implemented and host-verified. No vendor
compiler, simulator or board execution.

## Configuration contract

A family is now the directory name itself, such as `kernel_int8_packet`.
DSE/CDAC output remains a 22-column configuration, but column 14 (zero-based)
contains the family name. AIE generator configurations use column 11 for the
name; PL generator configurations use column 14. Mixed numeric/name arrays use
NumPy `dtype=object`.

```python
AIE_config = np.array([
    # M, K, N, A, B, C, A_BRO, C_BRO, PACK_IN, PACK_OUT, bytes, family
    [64, 64, 64, 1, 2, 2, 1, 1, 2, 2, 1, "kernel_int8_packet"],
], dtype=object)
```

`gen_aie_top()` directly loads `templates/aie/<family>/aie/` and
`gen_pl_top()` loads `templates/pl_kernel/<family>/`. Their byte-width checks
use named metadata. Numeric family values such as `7` are rejected; there is
no implicit legacy-ID conversion table. Historical numeric result files are
preserved as evidence and must be updated explicitly before being used as new
generator inputs. The legacy DSE runner saves future `.npy` configurations as
string arrays so loading them does not require object-array pickle support.

`CACG/kernel_families.py` now contains `KERNEL_FAMILIES`, keyed by names, with
operand-byte width and a source-symbol prefix. Prefixes such as `mm7` preserve
existing C++ source filenames and function names. They do not select a family
or template directory. Cascade-role suffixes 0/1/2/3 also remain unchanged.

## Changed paths

- `CDSE/cdse.py`, `CDAC/cdse.py`, `CDAC/cdse1.py`: select descriptive family
  strings and use the `_packet` suffix for transport branching instead of ID
  parity. Numeric search and cost calculations are unchanged.
- `CDAC/cdac.py`: preserves strings when assembling multi-array configurations.
- `CACG/kernel_families.py`: replaces the ID-to-directory map with named metadata.
- `CACG/gen_aie/gen_aie_design.py`: removes eight numbered environment slots;
  loads environments by family name and keeps geometry numeric.
- `CACG/gen_aie/gen_kernel.py`: uses the selected family's existing source prefix
  to render role files; removes the unreachable numeric-family special case.
- `CACG/gen_pl/gen_pl_kernel.py`: directly chooses the named family directory.
- `CACG/gen_charm.py`: carries names through both generators, separately casting
  numeric geometry, host settings and buffer selections.
- `test_cacg.py` and active kernel5/ImageWAM case generator scripts: explicit
  family strings in configuration rows.
- `example/ImageWAM/`: preserves family strings through mapping and generation.
  `mapping.csv` now includes `kernel_family`; the generated C++ `Array` contains
  a family string and named numeric fields instead of a numeric `config[22]`
  containing a family ID.

No kernel template arithmetic, data layout, source symbols, placement rule or
matrix dimensions changed. Existing template support is unchanged: FP32 stream
and packet, INT16 packet, INT8 stream and packet. The old CDAC low-resource INT16
stream branch now names `kernel_int16_stream`, but this repository still lacks
that template; generation rejects it rather than silently substituting packet.
This change does not implement a missing kernel family or validate a new target.

## Verification

Case: `sim/tmp_named_templates/`.

```sh
python3 -B check_named_templates.py
```

Exit 0. Generated AIE and PL sources for all five supported named families,
checked default four-iteration top generation, rejected a numeric family input,
exercised the full `gen_charm_top()` generation path and checked that original
CDAC's INT8 stream branch returns `kernel_int8_stream`. An initial test assumed
PL components were separate `.cpp` files; the existing generator appends them
to `dma0.cpp`. The test was corrected without changing that generation behavior.

Case: `sim/tmp_imagewam_charm_dse_vek280/`.

```sh
python3 -B check_graph_mapping.py
python3 -B check_generated.py
```

Exit 0. The eight candidates, 304 kernel placements, 15,017 dispatch records and
iteration counts remain unchanged. Hashes of all existing generated AIE `.cc`,
`.cpp` and `.h` files matched before and after migration. The saved system-DSE
baseline still matches all numeric columns; the family name is asserted
separately. Historical baseline files were not rewritten.

The generated non-ADF `imagewam_schedule.hpp` passed host C++17 syntax checks,
including a static assertion for the `kernel_family` string and named placement
fields. This is not AIE compilation or numerical simulation. Documentation,
Python syntax and updated call sites were checked; source-generated artifacts
remain available in the cases above.
