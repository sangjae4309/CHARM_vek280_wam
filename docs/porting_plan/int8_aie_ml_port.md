# INT8 AIE-ML source port

Date: 2026-11-10. Scope: `kernel_int8_stream`, `kernel_int8_packet`, including
all four production roles and the historical `mm_test` source. User decision:
port INT8 only; leave FP32 unchanged. Status: implemented source port with
host-only validation. Target compilation, AIE simulation and board validation
remain pending. No vendor tools were run.

## Preserved computation

Original production sources unroll K=64, despite exposing a configurable `w1`.
Each output block has 8 rows and 4 cols. A uses `[M/8][K][8]`, B uses
`[K/16][N][16]`, and output uses `[M/8][N][8]`. The historical extra test uses
`[K/8][N][8]` for B and fixed 64x64x64 dimensions; it remains outside production
graph selection. All source load, pointer movement, MAC and write positions
are retained, as are ordinary-stream versus packet connections and broadcasts.

Source-inspected facts: each original INT8 `mac16` computes eight products per
lane, using X offsets `0x11101110`, X step 16, X square `0x3120`, Z step 2 and
identity Z square `0x3210`. Applying AMD's full-lane addressing rules gives:

```
for lane r in 0..15 and term t in 0..7:
    x_index = 8*t + r%8
    z_index = 2*((ZOffsets >> (4*((r/4)*2+r%2))) & 15) + t
    acc[r] += A[x_index] * B[z_index]
```

Production Z selectors are `0x88880000` and `0xCCCC4444`; the extra test uses
`0x44440000` and `0xCCCC8888`. The helper retains these original selector values
and performs the eight terms in increasing order at each original MAC position.
This is a fixed-selector compatibility implementation, not a new mmul tiling.

## API, numerical and placement differences

- Replace architecture-specific vector types/updates with `aie::vector`,
  `insert`, `get` and `set`; remove fixed register bindings.
- Use `aie::accum<acc64,16>` and dedicated `input_cascade<acc64>` /
  `output_cascade<acc64>` ports. Cascade low/high groups remain sequenced
  groups of eight lanes. Original nested reads are made explicitly sequential.
- Each selected signed INT8 operand is exactly sign-extended to INT16 inside
  the helper. Installed AIE API `detail/aie2/mul_acc64.hpp` supports INT16
  elementwise MAC with acc64. Storage and external interfaces remain INT8.
- Replace `bsrs(acc,0)` with `acc.to_vector<int8>(0)`. No rounding or saturation
  mode is set or changed. Target overflow/conversion behavior remains untested.
- The largest positive INT8 product is 16384. Require
  `cascade_length * 64 * 16384 < 2^47` to stay inside original acc48 range.
  Reject K other than 64 rather than silently generate a different computation.
  Require positive M divisible by 8 and N divisible by 4.
- Cascade placement goes west-to-east on every row, retaining chain footprint
  and the original odd-row right-edge anchor convention used by the layer graph.
  Original bank offsets are retained (A 0x0000/0x2000, B 0x4000/0x6000,
  C 0x5000/0x7000, stack 0x3000). Static checks reject tiles exceeding their
  reserved regions. Same-logical-bank ping/pong warnings and larger-array
  placement still require target review, as with INT16.
- Fix ordinary-stream cascade output window size from `M*N*4` to `M*N*Byte`.
  The original declaration was inconsistent with INT8 output and the top graph.
- Select the standalone role for packet B=1, as already done in the INT16 port.
  Ordinary streams require PACK_IN=1; packet PACK_IN must divide the chain
  length and be at most 32. These guards expose unsupported settings.

The shared generator accepts optional `input_data_dir` for case-owned fixtures;
existing callers retain their default paths. No PL kernel or FP32 source was
changed. Ordinary-stream INT8 has no original fixture directory, so the new
cases supply their own data instead of fabricating a generic template fixture.

## Prepared execution cases

### Tile enlargement discussion (2026-11-10)

Architecture fact: [AMD AM020](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-Tile-Architecture)
increases per-compute-tile data memory from AIE's 32 KiB to AIE-ML's 64 KiB.
Source-inspected constraints in the current INT8 `para.h` still fix K=64 and
reserve at most 8 KiB for each A buffer and 4 KiB for each B/C buffer. The
ImageWAM 32x64x32 choice is not a demonstrated hardware maximum or optimum.
A 64x64x64 tile passes these size/divisibility guards with INT8 output: A/B/C
are 4 KiB each, or 24 KiB in aggregate with ping-pong buffers (distributed by
the graph, not necessarily all in one tile). This is a candidate only: bank
placement, code generation and performance have not been target-tested.
Increasing M/N may improve operand reuse but leaves the eight-kernel K span
at 512; six partial passes for K=3072 remain. Increasing K requires changing
the unrolled kernel schedule, not just a configuration number. No tile-size
implementation change or numerical/interface change is authorized by this
discussion. INT32 output would require recalculating output buffer sizes.

All paths are relative to the repository. Each case has `test_int8.py`,
`compile.sh`, `run.sh`, `check_output.py` and a README.

| Case | Purpose |
| --- | --- |
| `sim/tmp_int8_stream_vek280/` | Ordinary stream, three cascade stages |
| `sim/tmp_int8_packet_vek280/` | Packet stream, three cascade stages |
| `sim/tmp_int8_stream_single_vek280/` | Ordinary stream, standalone role |
| `sim/tmp_int8_packet_single_vek280/` | Packet stream, standalone role |
| `sim/tmp_int8_extra_vek280/` | Historical `mm_test`, separate test graph |

The first four use M=16, K=64, N=12 and four graph iterations. The extra test
uses its original 64x64x64 shape. Signed sparse A and signed dense B fixtures
keep every final value in INT8 range. Packet stages receive distinct data;
ordinary-stream stages share the same fixture, following the existing top
wrapper's file mapping. Shared support lives in `sim/tmp_int8_port_checks/`.

Run from a chosen case:

```sh
./compile.sh
./run.sh
python3 check_output.py
```

Generation alone has completed. Compilation uses Vitis 2025.2 and the VEK280
platform path from the INT16 case, overridable with `PLATFORM`. Generated PLIO
constraints are not passed to the compiler, retaining the INT16 workaround.
The 128-bit/230-MHz PLIO settings and four-iteration top wrapper are unchanged.
`run.sh` preserves the generated reference. No actual PL logic is attached.

## Verification evidence and limits

Host tools: Python 3.10, system g++ with `-std=c++17 -O1`; no AIE compiler was
invoked. Scripts, original snapshots and host executables are under
`sim/tmp_int8_port_checks/`.

- `python3 check_port.py` (exit 0): execute actual rendered old/new production
  source bodies using a small host API model for all four roles, both families,
  shapes 8x64x4, 16x64x12 and 64x64x64, eight input trials per role. Compare
  independently against matrix multiplication. Includes signed random inputs,
  -128/127 extremes for accumulator-output roles, incoming cascade values, and
  bounded final outputs. Evidence: `host_checks.log`.
- `python3 check_extra.py` (exit 0): execute old/new `mm_test` with its distinct
  B layout and compare with matrix multiplication. Evidence: `extra_checks.log`.
- `python3 check_structure.py` (exit 0): match load/MAC/write schedules in all
  nine sources; render B=1/2/3 graphs, check row-parity placement arithmetic;
  test signed output parsing and rejection of corrupted/truncated output.
- Five `python3 test_int8.py` generation runs completed (exit 0), with logs in
  each case. Shell syntax and Python syntax checks completed without vendor tools.

The original-source host model implements the documented AIE1 mini-permutation
independently of the new helper. It sequences original nested cascade reads
low-first explicitly; C++ argument evaluation order is not treated as proof of
original hardware behavior. The host model does not implement saturation/wrap;
final-output tests reject out-of-range values. It cannot validate actual AIE API
code generation, cycle counts, resource use, placement or hardware conversion.
The new helper favors source-order fidelity; no performance claim is made.

During host harness development, combining multiple translation units exposed
helper redefinition in the harness; including the helper only once fixed that
harness issue. Inspection of installed headers also corrected the model/helper
`vector.set(value,index)` argument order. Final checks above use the corrected
files. These were host-harness failures, not vendor compiler results.

## Sources

- Original snapshots in `sim/tmp_int8_port_checks/original/` and current INT8
  templates, particularly `int8_mac8.inc`, `para.h` and `aie_graph.h`.
- [AMD AIE1 INT8 MAC definitions](https://download.amd.com/docnav/aiengine/xilinx2025_1/aiengine_intrinsics/intrinsics/group__vect__mult__8x8.html).
- [AMD full-lane addressing](https://download.amd.com/docnav/aiengine/xilinx2025_1/aiengine_intrinsics/intrinsics/group__vect__mult__intrinsics__explained.html).
- Installed Vitis 2025.2 `aie_api/vector.hpp`, `utils.hpp`,
  `detail/aie2/mul_acc64.hpp`, and `adf/window.hpp` / `adf/stream.hpp`.
- [Existing INT16 port and architecture references](kernel5_aie_ml_port.md).

Porting implication: INT8 source/API migration is prepared for target testing;
passing host checks is not successful AIE simulation or full CHARM integration.
