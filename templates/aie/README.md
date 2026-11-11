# AIE templates: VEK280 porting TODO

INT8 update (2026-11-10): `kernel_int8_stream` and `kernel_int8_packet`
have initial AIE-ML source ports, including the historical extra standalone
test. Host checks passed; compiler/simulator execution remains with the user.
See [INT8 port details and execution cases](../../docs/porting_plan/int8_aie_ml_port.md).
FP32 is explicitly deferred and unchanged.

Updated: 2026-11-09.

## Agreed scope

Preserve the original CHARM computation and data order. Start with kernel5
(INT16). Tile enlargement, AIE-ML-specific redesign and replacement with
`aie::mmul` are outside the current scope. Record original-source compatibility
failures before deciding on minimum changes. Explain numerical or interface
changes before applying them.

Use the actual CHARM AIE generator rather than a separately handwritten graph.
The user will run compilation and simulation using the prepared scripts.

## kernel5

- [x] Inspect register bindings: `xa`, `xb`, `wc0`, `wc1`.
- [x] Identify `mac16`, `v16acc48`, acc48 cascade and window API dependencies.
- [x] Confirm installed AIE compiler version: 2025.2.
- [x] Reuse production `gen_aie_top()` from the simulation runner.
- [x] Generate kernels, layer graph, top graph, PLIO constraints and packet inputs.
- [x] Provide case-local `sim.sh`: generation -> compilation -> simulation -> comparison.
- [x] Prepare the reference for the existing kernel5 input fixture.
- [x] Pass five parser/comparison unit checks, including failure detection.
- [x] Verify deterministic case recreation and reproducible source generation.
- [ ] Successfully compile the original kernel0/1/2 graph for VEK280.
- [ ] Record compiler-reported register/type/intrinsic incompatibilities.
- [x] Implement the initial AIE-ML type/API/MAC and cascade-direction changes.
- [x] Check all four source schedules and signed/extreme accumulator arithmetic on the host.
- [x] Replace obsolete accumulator stream ports with dedicated cascade ports.
- [x] Move PLIOs into graph-owned wrappers and remove simulation::platform.
- [x] Verify shared top-template connections for single/multiple-layer cases.
- [ ] Validate the updated port with the target compiler and AIE simulator.
- [ ] Check kernel3 standalone separately.
- [ ] Verify output order, INT16 conversion and cascade partial sums.
- [ ] Pass actual AIE simulation and reference comparison.

## Execution

```bash
./sim.sh
```

Run from `sim/tmp_kernel5_vek280/`. The case is `sim/tmp_kernel5_vek280/`.
A rerun clears generated artifacts; case-owned scripts and the repository link
are preserved. Random suffixes are not used.
See [the simulation guide](../../docs/porting_plan/aie_simulation.md) for
configuration, Python dependencies, evidence files and limitations.

Latest source status: kernel5 templates now contain the initial AIE-ML port.
The original baseline reached an acc48 graph-interface error in the user's run.
The edited port has not been compiled or simulated; host-only checks passed.
Python generator code is unchanged; the shared top C++ template is migrated
to graph-owned PLIOs. Regenerate the case before compiling.
See [the port details](../../docs/porting_plan/kernel5_aie_ml_port.md).

## Later work

- [ ] Select the next kernel after kernel5 verification.
- [ ] Scope full generator, PL and board integration separately.

Background: [porting notes](../../docs/porting_plan/README.md).

The case now uses a short, explicit generation script following `test_c*.py`.
No JSON configuration, automatic package installation or general CLI remains.
The simplified scripts were syntax-checked only; execution belongs to the user.
