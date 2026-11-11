# ImageWAM independent measurement cases

Date: 2026-11-10. Scope: user-approved split of the ImageWAM block into five
cases. Sources: the user-provided diagram, current CHARM INT8 templates,
isolated INT16 nonlinear sources, and conversation decisions.

## Agreed boundaries and sizes

All paths below have prefix `sim/tmp_imagewam_fork_join_`.

| Suffix | Workload | Included/excluded |
| --- | --- | --- |
| `gu_linear` | Two `(417,3072) @ (3072,9216)` | G and U projections; input LayerNorm/modulation excluded |
| `qkv_linear` | Three `(417,3072) @ (3072,3072)` | Q, K, V projections; head split excluded |
| `mlp_branch` | HardSwish(G) times U on `(417,9216)` | G/U already available; projections excluded |
| `headsplit_rope` | Q/K/V `(417,3072)` to `(24,417,128)` | Q/K RMSNorm across 128 features and RoPE; V split/pass-through |
| `self_attention` | `(417,128) @ (128,417)`, ConSmax, `(417,417) @ (417,128)` | Exactly one head; Q/K RMSNorm/RoPE excluded |

The user answered yes to these boundaries. The temporary INT4 instruction was
corrected to INT8. The previously chosen isolated INT16 nonlinear arithmetic
remains the source baseline. Inputs/weights are available at the measurement
boundary; this does not establish actual memory residency or transport timing.
LayerNorm, modulation, final feature concat and Out Linear are outside these
five cases. The five isolated times do not constitute a full-block measurement.

## Parameter ownership

Each case has `config.json` for fixed shapes and `parameters.json` for values
to be supplied later. No learned coefficients, quantization policy, part number
or PL clock is silently chosen. Missing fields are null and validation fails
before generating a numerical workload. `input_npz` points to a user-supplied
NumPy archive; relative paths resolve against the case directory.

- MM inputs and weights: signed INT8. Reference accumulators use INT32 because
  the maximum accumulation at these shapes is within INT32 range.
- MLP inputs G/U: signed INT16 `[417,9216]`. HardSwish has an explicit Q format
  and truncating division; gate requantization specifies multiplier, shift,
  rounding and overflow policy.
- Head split inputs Q/K/V: signed INT16 `[417,3072]`. Also supply `gamma_q` and
  `gamma_k` as INT16 `[24,128]`, and `rope_cs` as INT16 `[417,128]` containing
  adjacent cos/sin values in Q7, matching the selected upstream RoPE module.
  Norm scale/shift/bias are explicit; integer sqrt and epsilon behavior are
  inherited from the inspected isolated norm source, not a floating model.
- Single-head attention: Q/K/V are INT8 `[417,128]`; mask is bool `[417,417]`
  with true meaning keep. Supply a nonnegative INT16 `consmax_lut[65536]`
  indexed by signed INT16 score plus 32768. The table includes the requested
  ConSmax transform; base, beta, gamma, scales and table provenance are explicit.
  This table interface does not establish a final hardware LUT architecture.
  A separate conversion specifies INT8 P for the next MM. Masked weights are
  zero before conversion. Table shape/range validation is not model validation.
- Requantization: integer multiplier and right shift, `floor` or `toward_zero`
  rounding, and `saturate` or `reject` overflow. No implicit wrap is used.

The user explicitly requested the ability to insert correct parameters later.
No test fixture is selected as the actual model. References retain INT32 sums
for inspection; this does **not** mean the AIE output interface has been changed.

## Current implementation and remaining work

Status is deliberately separate by artifact:

| Artifact | Status |
| --- | --- |
| Five case directories, exact shapes, parameter files and plans | Generated |
| Input validation and integer host reference functions | Implemented; small independent arithmetic checks passed |
| MLP HardSwish/gating HLS source, testbench and launch script | Prepared; requires explicit inputs/parameters/part/clock; not compiled or simulated |
| Head split upstream RMSNorm and RoPE snapshots | Copied unchanged with SHA256 provenance; integrated HLS wrapper pending |
| GU/QKV and single-head AIE MM graphs | Generated through actual CHARM generator, retaining INT8 output; target compilation pending |
| Connected PL+AIE timing harness | Not implemented or measured |

The existing CHARM INT8 graph narrows each final cascade result to INT8. For
K=3072, a proposed reusable chain of eight K=64 kernels would need six partial
passes per output tile. Narrowing each pass to INT8 would lose information.
The proposed measurement-only INT32 partial output must be agreed before
modifying kernel templates or interfaces. Default INT8 production behavior has
not been modified. The output accumulator reduction, final requantization and
their timing must be included before calling the result a full Linear latency.

`aie_manifest.json` records the generated 32x64x32 tile and up to eight cascade
kernels. Placement is source-generated, not target-compiled or measured.
M/N tails are padded to 448 where applicable, but logical output dimensions
remain 417. Padding masks and trimming must be checked in hardware validation.

## Commands and evidence

In any case:

```sh
python3 reference.py plan
python3 reference.py validate
python3 reference.py reference
```

The last two commands require explicit inputs and parameters. Host reference
wall time is never reported as accelerator latency. For the MLP case only:

```sh
python3 reference.py prepare-pl
./run_pl.sh
```

The script records the command, vendor exit status and log. It runs C simulation,
HLS synthesis and RTL cosimulation, from the case directory. The source processes
120,096 512-bit beats, each containing 32 INT16 lanes, per full invocation.
The requested II=1 is a synthesis target, not a verified result. RTL cosimulation
latency excludes a real AIE connection, DDR/NoC, host startup and board transport.
Do not substitute a requested clock for a verified achievable clock.

No vendor tools were invoked during preparation. Host checks are recorded in
`sim/tmp_imagewam_fork_join/preparation_checks.json`: five shape plans, missing
parameter rejection, HardSwish boundaries/interior, identity RoPE, integer
RMSNorm, signed rounding and overflow rejection. Shell syntax was checked.
No AIE, RTL cosimulation or board latency number exists yet.

## Actual AIE generator entry points (2026-11-10)

The user clarified that case preparation must include real CHARM AIE sources,
as in `tmp_kernel5_vek280`. GU, QKV and self-attention now contain
`generate_aie.py`, `compile.sh`, `run.sh`, `prepare_inputs.py`, and the generated
`aie/` tree. The former `case.py` helper is renamed `reference.py` in all five
cases so it cannot be mistaken for the AIE generator. MLP and head split are
PL-only under the agreed partition and do not receive artificial AIE kernels.

The production generator now accepts optional per-layer input paths and
simulation iteration counts. Existing callers retain input0/input1 and four
iterations. No default kernel output type or arithmetic was changed.
GU graphs each run 24,192 iterations; QKV graphs each run 8,064; the independent
QK and PV probes run 196 and 56 respectively. Each input packet carries a
32x64 or 64x32 INT8 tile in the original CHARM layout. Signed-byte packing and
packet header fields follow the inspected PL `generateHeader()` source.

Source generation completed for all three cases (exit 0; case-owned
`generate.log`). Host checks passed for generated iteration/path settings,
preserved kernel5 defaults and signed packet/header round trips; shell syntax
checks passed. Evidence: `sim/tmp_imagewam_fork_join/aie_generation_checks.json`.
No compiler, simulator or board run was performed. Full-K partial accumulation
and the ConSmax link are still absent: independent MM completion must not be
reported as measured full-operator completion.
