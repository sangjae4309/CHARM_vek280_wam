# Remaining AIE template families

Date: 2026-11-10. Current decision: the user explicitly deferred FP32 and
authorized INT8 only. The INT8 implementation and host checks are recorded in
[the INT8 port note](int8_aie_ml_port.md); target execution remains pending.
The FP32 discussion below is a deferred proposal, not active implementation.

The initial request covered all remaining families with the INT16 preservation
constraints. It was subsequently narrowed to INT8 ordinary/packet families,
including the extra standalone INT8 test. FP32 in both `aie` and `aie1` remains
unchanged. PL/system integration remains a separate task.

## Source-inspected facts

- FP32 sources use `fpmac`, native vector aliases and accumulator stream
  interfaces. Inputs and output order must remain as currently implemented.
- INT8 sources use a different fixed `mac16` selector pattern from INT16:
  `0x11101110`, `0x3120`, and B selectors `0x88880000`/`0xCCCC4444`.
  The INT16 two-product helper cannot be reused without deriving INT8 lanes.
- INT8 ordinary-stream fixture files are absent in the current repository.
- `mm7_kernel4.cc` is a separate fixed 64x64 test function named `mm_test`;
  the production `gen_krnl()` loop renders roles 0 through 3 only.
- Installed Vitis 2025.2 `aie_api/detail/aie2/mul_acc32_fp.hpp` contains
  float/float multiplication support with an `accfloat` accumulator.

## Numerical decision required before FP32 implementation

AMD UG1603 2025.2 describes FP32 multiplication on AIE-ML as emulated using
bfloat16. It exposes safe, fast (default), and low accuracy modes. Safe is
described as similar to FP32 precision, not bitwise identity with AIE1.
XAPP1406 documents discrepancies including subnormal flushing and accumulator
effects. Preserving source MAC order alone cannot guarantee original FP32 bits.

Proposal: retain FP32 storage and interfaces, preserve each source MAC position,
and explicitly select safe emulation. Do not silently accept numerical errors
through a loose tolerance. Measure absolute/relative/ULP differences and special
values separately; acceptance criteria remain unresolved pending user agreement.
The emulation accuracy choice has not yet been approved.

INT8 now uses acc64 cascade/accumulators with an enforced acc48-range bound.
Lane ordering, shift, rounding/saturation state and transport are preserved.
See the implementation note for selector derivation and verification evidence.

## Original proposed verification scope

Edit family templates and graph placement/interfaces; prepare per-family fixed
cases under `sim/tmp_<pattern>/` with generation, compilation, simulation and
comparison scripts. User runs vendor tools. Host verification must check source
load/MAC order, selector-to-matrix correspondence, generated graphs, signed and
extreme integer inputs, and FP32 reference behavior. Target correctness remains
unverified until compiler and simulator results are available.

Sources:
- Current family `para.h`, `mm*_kernel*.cc` and `aie_graph.h` files.
- `CACG/gen_aie/gen_kernel.py`.
- [UG1603 floating-point operations](https://docs.amd.com/r/2025.2-English/ug1603-ai-engine-ml-kernel-graph/Floating-Point-Operations).
- [XAPP1406 summary](https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Summary).

Porting implication: FP32 needs an explicit numerical policy in addition to API
migration; integer families require independent selector derivation.
