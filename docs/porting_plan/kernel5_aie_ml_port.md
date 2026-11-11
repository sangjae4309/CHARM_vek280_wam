# kernel5: initial AIE-ML source port

Date: 2026-11-09. Target: VEK280 / AIE-ML, installed Vitis 2025.2 headers.
Status: templates edited; host-only schedule/math checks passed. No vendor
compilation or AIE simulation was run for these changes. The user owns execution.

The user authorized starting the port while preserving CHARM's overall design.
The previous original-source baseline failed on `input_stream_acc48` and
`output_stream_acc48`. Variable renaming alone cannot address the architecture's
different accumulator interfaces and multiply-accumulate instructions.

## Preserved behavior

- K=32 and the configured h1/w2 dimensions (48/48 in the current case).
- Original i/j loops, 16-row by 2-col output blocks, and unrolled K-pair order.
- Names and logical sizes of `buf_matA0/A1`, `buf_matB0/B1`, and `acc0/acc1`.
- Every A/B window read, pointer increment/decrement, preload and buffer-reuse
  position in the source schedule.
- kernel0 starts the sum; kernel1 adds to it; kernel2 finishes and converts to
  INT16; kernel3 performs standalone computation.
- Col-major matrix storage, packet splitting/merging, window sizes and shift=0
  output conversion. No new saturation or rounding setting is introduced.
- Cascade lane order: acc0 low 8, acc0 high 8, acc1 low 8, acc1 high 8.

Source operation order is preserved; instruction scheduling and cycle counts are
not. The compiler must schedule the replacement operations. No performance
equivalence or improvement is claimed.

## Differences and changes

| Original | AIE-ML port | Reason |
| --- | --- | --- |
| `input/output_stream_acc48` | `input_cascade<acc64>` / `output_cascade<acc64>` | acc48 stream aliases are absent on AIE-ML; the graph compiler also rejects acc64 stream aliases for cascade ports. |
| `v16acc48` | `aie::accum<acc64,16>` | Use an explicit native AIE-ML accumulator width, not the INT16 multiply default of acc32. |
| `v32int16`, `v16int16` | `aie::vector<int16,32/16>` | Express vector sizes independently of architecture-specific aliases. |
| `chess_storage(xa/xb/wc0/wc1)` | No fixed register binding | AIE-ML has x0..x11 and wl/wh registers instead; renaming alone would impose an unverified allocation. |
| `upd_w` / `upd_v` | `vector.insert()` | Replace the same vector slice at the same point in the source. |
| `window_read_v16/v8` | `window_read_v<16/8>` | AIE API supplies an AIE-ML implementation for the 128-bit B reads. |
| Fixed-selector `mac16` | `mm5_mac_pair<Z>` with two `aie::mac` calls | Explicitly implement the two K terms without AIE1 selector hardware. |
| `concat(readincr_v8(...), readincr_v8(...))` | Two sequenced reads and inserts | Preserve low/high lane order explicitly; avoid depending on C++ argument evaluation order. |
| `writeincr_v8` / `ext_lo/hi` | `writeincr` / `extract<8>` | Send eight acc64 lanes per 512-bit cascade transfer. |
| `srs(acc,0)` | `acc.to_vector<int16>(0)` | Retain shift=0 INT16 conversion; target mode behavior still requires execution checks. |
| Odd-row east-to-west cascade | West-to-east on every row | AIE-ML cascade directions differ from the AIE checkerboard arrangement. |

Legacy window interfaces remain to limit the scope; the compiler reports them
as warnings. Dedicated `input_cascade`/`output_cascade` interfaces are now used.
Correction to the first pass: the installed headers retain deprecated accumulator
stream overloads, but the 2025.2 graph compiler rejects those interfaces with
77-6489. Header availability alone did not establish graph compatibility. Installed AIE API headers require C++20
for kernel compilation; graph declarations remain in `para.h` without exposing
API implementation bodies. Kernel compiler language-mode compatibility remains
part of the pending target build.

## MAC replacement

All 32 calls per kernel use the same original selector pattern:
`xstart=0`, `xoffsets=0x73727170/0x77767574`, `xsquare=0x3120`,
`zoffsets=0/0`, `zstep=1`.

For a particular K pair and output col, each lane r computes:

```text
acc[r] += buf_matA[r]    * buf_matB[Z]
        + buf_matA[16+r] * buf_matB[Z+1]
```

`kernel5_mac_pair.inc` is a Jinja include rendered directly into each kernel
source. It is not a generated C++ include dependency and does not require changes
to CHARM's file-copy/generation routines. It implements only this fixed pattern,
not a general replacement for arbitrary `mac16` selectors.

The installed AIE API `detail/aie2/mul_acc64.hpp` implements INT16 x INT16 acc64
MACs and scalar/vector overloads. `aie::mac` inherits acc64 from the supplied
accumulator. Using the default multiply accumulator would instead risk acc32.

## Numerical scope

For signed INT16, the largest positive product is 2^30. With K=32 and at most
4095 cascade stages, the worst-case positive sum is below 2^47. A static assertion
enforces that bound, so widening the accumulator does not remove an acc48 wrap
that would otherwise occur within supported configurations. The actual three-
stage case has only 96 products per output value.

This bound concerns AIE cascade accumulation, not later PL accumulation or INT16
output overflow. The output rounding/saturation state is not explicitly changed.
Host checks do not validate target conversion modes, API code generation, or
compiler treatment of the original nested cascade-read expressions.

## Graph placement

`aie_graph.h` retains each chain's footprint. On odd rows the supplied anchor
was the right edge, so `first_col = COL_OFFSET - NUM_KERNEL + 1`; kernels are now
placed at `first_col+i` on every row. The row-0 test case remains at cols 6,7,8.

Buffer/stack offsets are retained. Coordinates follow the corrected chain;
the final output uses the preceding col, or its own col for a standalone kernel.
The existing B=1 selection bug is corrected to select kernel3 instead of kernel0.
B=1 is not covered by the current three-packet simulation fixture.

Retained bank/address constraints require AIE-ML compiler validation. The generic
PLIO placement generator still has original-platform assumptions (cols 6..44),
and larger arrays, odd base rows and full-system placement remain unvalidated.
The port does not claim all CHARM configurations are VEK280-compatible.

## Files and regeneration

Changes are in `templates/aie/kernel_int16_packet/aie/`, not only in generated case files.
Other kernel templates and CHARM generator code are untouched. These kernel5
templates now target AIE-ML; this is not a dual-target AIE1/AIE-ML implementation.

The currently generated `sim/tmp_kernel5_vek280/aie/` files have not been rewritten
in this turn. Regenerate before compiling:

```bash
cd sim/tmp_kernel5_vek280
python test_kernel5.py
# Or generate, compile, simulate and compare in sequence:
./sim.sh
```

## Verification performed

`sim/tmp_kernel5_vek280/check_kernel5_port.py` and `port_host_checks.log` record:

- Exact matching of original and ported A/B read, pointer-move and K-pair call
  sequences for all four kernel roles, using the Git HEAD source as baseline.
- A host interpreter of those actual source schedules, checked against matrix
  multiplication for 16x32x2, 32x32x4 and 48x32x48 cases, signed random and INT16
  extreme inputs, and incoming partial sums for kernel1/2.
- In-memory Jinja rendering for all kernel sources and B=1/2/3 declarations/graph.

These are host-only structural and arithmetic checks. They do not execute the
AIE API, prove original intrinsic lane semantics on silicon, verify graph
placement, measure performance, or replace compiler/simulator testing.

## Sources

- [AM020 register files](https://docs.amd.com/r/en-US/am020-versal-aie-ml/Register-Files): vector register naming and accumulator organization.
- [AM020 array architecture](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-Array-Architecture): west-to-east and north-to-south cascade directions.
- [AIE API 2025.2 arithmetic](https://download.amd.com/docnav/aiengine/xilinx2025_2/aiengine_api/aie_api/doc/group__group__arithmetic.html): vector/scalar arithmetic and accumulator defaults.
- [UG1603 data types](https://docs.amd.com/r/2025.2-English/ug1603-ai-engine-ml-kernel-graph/Data-Types): distinction between API accumulator tags and graph interface types.
- [AIE1 INT16 MAC intrinsics](https://download.amd.com/docnav/aiengine/xilinx2025_1/aiengine_intrinsics/intrinsics/group__vect__mult__16x16.html): two products per lane and selector meanings.
- [UG1079 intrinsic matrix multiplication](https://docs.amd.com/r/2025.2-English/ug1079-ai-engine-kernel-coding/Coding-with-Intrinsics): matching selector pattern and interleaved load/MAC schedule.
- Installed Vitis 2025.2 headers: `adf/stream/types.h`, `aie_api/adf/window.hpp`,
  `aie_api/adf/stream.hpp`, `aie_api/detail/aie2/mul_acc64.hpp`.


## Follow-up: graph API errors reported by the user

The user's next compilation rejected two obsolete APIs:

1. Error 77-6489: `input_stream<acc64>` / `output_stream<acc64>` on cascade ports.
   Declarations in `para.h` and definitions in kernel0/1/2 now use
   `input_cascade<acc64>` / `output_cascade<acc64>`. The installed AIE API provides
   matching `readincr_v<8>` and `writeincr` overloads, so lane ordering, accumulator
   arithmetic and cascade graph connections are unchanged.
2. Error 77-6560: `adf::simulation::platform` is obsolete. The shared
   `templates/aie/aie_top.cpp` now creates a graph wrapper for each layer, owning
   `adf::input_plio` / `adf::output_plio` objects and the existing compute graph.
   All PLIO creation and connections are inside that wrapper's constructor.

Global graph instance names remain `mm_graph0`, `mm_graph1`, etc. PLIO logical
names, input/output file names, 128-bit width, configured frequency, broadcast
connections, output numbering and four simulation iterations are retained.
The nested compute graph adds a hierarchy component (`compute`); target placement
and any external hierarchy-based constraints still require compiler validation.
The existing placement generator addresses PLIO logical names, which are retained.

The top template is shared by all kernel types: this is a Vitis graph API
migration, not another kernel algorithm change. Old toolchain compatibility is
not claimed. No PL implementation, window-buffer conversion or system linking
was added. The window warnings (77-5890) are not the reported fatal errors.

Verification: `check_graph_api_port.py` rendered the old/new shared top templates
for a 3-PLIO single layer, a 40-PLIO broadcast/multiple-packet-group layer and a
43-PLIO two-layer composition. It compared PLIO names, data files, widths,
frequencies and every logical input/output connection. All checks passed; the
log is `sim/tmp_kernel5_vek280/graph_api_checks.log`. Dedicated cascade declarations
were also checked in all rendered kernel sources. No vendor tools were run.
Generated files in the case remain unchanged until the user regenerates them.

Additional sources:
- [AMD 2025.2 PLIO configuration](https://docs.amd.com/r/2025.2-English/ug1079-ai-engine-kernel-coding/Configuring-input_plio/output_plio).
- [AMD 2025.2 graph class example](https://docs.amd.com/r/2025.2-English/Vitis-Tutorials-AI-Engine-Development/Define-the-Graph-Class).
- Installed `aie_api/adf/stream.hpp`: dedicated accumulator cascade overloads.
- User-supplied Vitis 2025.2 diagnostics 77-6489, 77-6560 and 77-5890.

## Follow-up: PLIO placement failure and buffer-bank warnings

The user reported AIE-PRE-MAPPER-40 for `LHS_in0_L0`: the specified channel
cannot satisfy the adjacent-channel requirement for a registered 128-bit PLIO.
The generated `.aiecst` fixes LHS to col 6/channel 2, RHS to col 6/channel 4,
and output to col 6/channel 2 (input/output channel directions are distinct).
The original generator uses `((chl_num+1)*2)%8` for channel selection. This
allocation has not been ported to the VEK280 registered-PLIO constraints.

The case-local `sim.sh` now omits `--constraints=...aie_top_all_aie_mapped.aiecst`.
The file contains only PLIO shim location constraints in this case. Omitting it
allows automatic PLIO placement; the graph's explicit kernel and buffer/stack
locations remain active. PLIO names, widths, frequency and data connections are
unchanged. The generated constraint file remains available for inspection but
is not supplied to this compile command. This is an AIE-only case workaround,
not a completed VEK280 placement-generator or PL/system integration port.

AIE-PRE-MAPPER-43 reports a separate nonfatal issue: each ping/pong pair is
constrained to the same programmer-visible bank. AM020 describes four logical
16-KB banks (eight physical 8-KB banks, interleaved in pairs). The retained
addresses 0x0000/0x2000 share one logical bank; 0x4000/0x6000 and 0x4C00/0x6C00
share another. These constraints need an AIE-ML-aware layout review to avoid
bank conflicts; simply changing one offset could overlap other buffers or the
stack. No buffer/stack addresses were changed for this diagnostic.

The final 77-6231 message is the placer failure following the fatal PLIO check.
The intermediate "AIE Initial Checker Successful" line does not negate that
failure. Shell syntax was checked after editing; target placement has not been
rerun by the assistant.

Sources:
- User-supplied AIE-PRE-MAPPER-40/-43 and aiecompiler 77-6231 diagnostics.
- `CACG/gen_aie/gen_plio_place.py` and this case's generated `.aiecst`.
- [AM020 AIE-ML tile architecture](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-Tile-Architecture).

## Follow-up: host readelf dependency (2026-11-09)

The user-reported build completed core compilation but failed during ELF debug
line extraction: the Vitis-bundled `readelf` could not load `libdebuginfod.so.1`.
The installed `aiecompiler` wrapper prepends `aietools/tps/lnx64/gcc/bin` to
`PATH`; generated `Work/aie/8_0.elfgen.Makefile` invokes bare `readelf` using
`SHELL=/bin/bash`. Dependency inspection confirmed the missing library for the
bundled executable. `/usr/bin/readelf --debug-dump=decodedline` successfully read
the generated core 8_0 ELF in a read-only check.

With user approval, case-local `sim.sh` now exports a Bash `readelf` function
that calls `/usr/bin/readelf` explicitly before invoking `aiecompiler`. This
selects the system tool in inheriting Bash shells despite the wrapper's PATH
change, without modifying shared tool installations or system libraries.
Shell syntax was checked; propagation through the full vendor build remains
unverified. The assistant did not rerun compilation or simulation. Full graph
build success and numerical simulation results remain pending.
