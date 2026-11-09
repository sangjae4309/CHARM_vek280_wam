# kernel5 generation and simulation

Updated: 2026-11-09.

The user requested a specific generation script in the style of `test_c*.py`,
not a general simulation framework. The entrypoint is now
`sim/tmp_kernel5_vek280/test_kernel5.py`. The previous `aie_sim.py` framework and
JSON configuration were removed.

The script contains explicit `AIE_config` and `placement` arrays and calls the
actual CHARM `CACG.gen_aie.gen_aie_design.gen_aie_top()` function. It generates
AIE sources, top/layer graphs, constraints and the existing packet inputs. It
does not install packages, compile or run simulation. NumPy/Jinja2 must be
available in the selected Python, as required by the existing CHARM generator.

```bash
cd sim/tmp_kernel5_vek280
python3 test_kernel5.py
```

The case now has two independent entrypoints. The former `sim.sh` was removed.

```bash
./compile.sh  # Generate and compile; no simulator or checker.
./run.sh      # Simulate the existing build; no generation or compilation.
python3 check_output.py 2>&1 | tee check.log  # Optional separate check.
```

`compile.sh` retains the exported system-readelf function. `run.sh` requires
`Work/` and `libadf.a`, preserves both, and clears prior simulation/check results.
Both scripts use the case directory regardless of the caller's working directory.

`check_output.py` compares the four output packets with the three-stage INT16
matrix-product reference computed from the existing input packets. It checks
all 9,216 values, rejects missing packets or mismatches, and refuses to infer
saturation/wrap behavior if the reference exceeds INT16 range. It is specific
to the current 48x32x48, B=3 fixture. The original positive-valued data does not
cover all signed-input or overflow cases.

All outputs stay in fixed `sim/tmp_kernel5_vek280/`. Reruns clear generated
artifacts while preserving case-owned scripts and the `repo` link. There are
no random case suffixes, automatic dependency installation, or imposed timeout
in the simplified workflow.

The user owns execution. On 2026-11-09 the user reported successful Vitis 2025.2
compilation with 7 warnings, 0 errors, and hand-off archive `libadf.a` generated.
Simulation then failed at startup with `GLIBC_2.28 not found`, required by the
Vitis-bundled `libpython3.13.so.1.0`. Local `getconf GNU_LIBC_VERSION` reports
2.27 and `/etc/os-release` identifies Ubuntu 18.04.6. This is a host runtime
compatibility issue, not a kernel compilation or Python virtualenv issue.

AMD's [Vitis System Design OS support table](https://www.amd.com/en/support/adaptive-socs-and-fpgas/installer-info-general.html)
should be used to select a supported OS environment. A supported newer host or
an appropriately configured container is the proposed resolution; replacing
system libc in place is not proposed. Container use requires tool/case paths,
dependencies, and license access to be available inside it. Docker is present
on PATH, but daemon access and container execution have not been verified.
No container, library, or system configuration was changed. Only shell syntax
was checked for the split scripts; no vendor tools were invoked by the assistant.
Simulation and numerical verification remain pending.

See the [case README](../../sim/tmp_kernel5_vek280/README.md) for the local layout.

## Shared Python environment

On 2026-11-09, the user requested a reusable environment at
`/localhdd/sangjae/python-env`. It was created with system Python 3.6.9 and
NumPy 1.19.5 / Jinja2 3.0.3. The user's `.bashrc` activates it after existing
environment setup. The old case-local `python-deps/` was deleted on request.
Open a new Bash terminal or source the shared environment before running scripts.
