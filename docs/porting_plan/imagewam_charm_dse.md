# Original CHARM mapping for 417x3072x3072

Subsequent implementation: [VEK280 DSE resource model](vek280_dse.md).
This document retains the original VCK190-model baseline and its evidence.

Date: 2026-11-10. User requested executing CHARM's own search, rather than
manually selecting a tile/array. Case: `sim/tmp_imagewam_charm_dse/`.
Status: original Python DSE completed, exit 0, host runtime 75.956 seconds.
No vendor compiler, simulator or board execution. No kernel or DSE source
was modified for this experiment.

## Model scope

The original `CDSE/cdse.py` requires equal operand dtypes and supports INT8,
INT16 and FP32. It does not model INT8 activation with packed INT4 weights.
This run is an explicitly labeled INT8/INT8 baseline for the requested shape,
not a VEK280/INT4 optimization result. Source hashes are in `result.json`.

The search hardcodes 400 AIEs, a 50x8 placement region, 867 BRAM blocks,
420 URAM blocks, 100 input PLIOs, 80 output PLIOs and profiled DDR bandwidth
constants. INT8 per-kernel dimensions are fixed at 64x64x64, with a fixed
2600-cycle compute estimate. A/B/C, X/Y/Z and buffer selection are searched;
broadcast factors follow source rules. PL/DDR costs are part of the objective.
This is the original algorithm's selected candidate, not proof of a global
optimum under a new architecture or different kernel.

## Selected mapping

| Field | Result | Meaning |
| --- | --- | --- |
| h1,w1,w2 | 64,64,64 | One kernel's M,K,N tile |
| A,B,C | 4,8,8 | Parallel M blocks, K cascade stages, parallel N blocks |
| Physical kernels | 256 | A*B*C, arranged as 32 chains of 8 |
| A_BRO,C_BRO | 4,2 | A shared across four N consumers; B across two M consumers |
| PACK_IN,PACK_OUT | 2,2 | Two packet IDs per input split/output merge |
| X,Y,Z | 2,1,1 | Repeats along M,K,N within a system tile |
| PL buffer selection | BRAM,BRAM,URAM | A,B,C respectively |
| Placement | col 9, row 0, width 32, height 8 | Original model footprint, cols 9–40 |
| PLIOs | 32 A + 64 B input; 16 output | Model port accounting |
| Resource estimate | 768 BRAM, 256 URAM | Analytical, not synthesized utilization |

One array iteration covers `(256,512) @ (512,512)` and produces `[256,512]`
partials. X=2 expands the system tile to M/K/N=`512/512/512`. The logical
problem needs TX/TY/TZ=`1/6/6`, giving padded M/K/N=`512/3072/3072`.
There are 95 padded M rows; K and N divide exactly. Each kernel has
1*6*6*2*1*1 = 72 iterations for this system schedule.

The K=3072 reduction includes six K=512 system chunks; it is not a full-K
result from a single eight-kernel cascade. Existing CHARM PL templates contain
partial-result accumulation (`receiveC`, Y loop and C buffers, plus TY-controlled
output scheduling in `compute.cpp`). This contrasts with the earlier isolated
ImageWAM AIE-only probes, which omitted that PL path. INT8 output/narrowing
semantics remain inherited and must not be equated to a new wide-precision
INT8/INT4 reference without numerical review.

The original model reports 1,016,314 estimated cycles in its own objective.
This is not measured AIE latency and is not converted to VEK280 time. The
returned mapping has not been compiled and should not be passed to the VEK280
generator as an already valid target mapping.

## Reproduction and evidence

```sh
cd sim/tmp_imagewam_charm_dse
./run.sh
python3 analyze.py
```

`dse.log`, `exit_status.txt`, `result.json`, `final_config.npy`, `mapping.json`
and `mapping.log` retain the actual run and derived geometry. The initial runner observed the original function's return event to capture
diagnostics without altering the search. At the user's subsequent request,
the runner was simplified to input setup, a direct DSE call and result saving.
Profiling, hashes, timers and exception/status handling were removed. The
existing run artifacts preserve the original evidence; subsequent runs write
a smaller result schema, supported by `analyze.py`. This cleanup was syntax
checked without rerunning the DSE. Input values are zeros;
only shape/dtype are read by the DSE. `analyze.py` checks the selected resource
constraints and derives padded dimensions, ports and iteration counts.

Porting implication: establish VEK280 resource/placement and measured kernel
cost models, plus separate activation/weight storage widths, before claiming
that CHARM has selected a VEK280 mixed INT8/INT4 design. Those changes are not
part of this baseline run.
