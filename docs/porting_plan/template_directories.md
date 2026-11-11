# AIE template directories

Inspected: 2026-11-10. Scope: `templates/aie/`, `templates/aie1/` and the
production generator. Status: source-inspected facts; no compiler or simulator
execution was performed for this comparison.

- `CACG/gen_charm.py:33-44` selects `templates/aie/` and passes it to
  `gen_aie_top()`. This directory contains the five descriptive template families listed below.
  Kernel5 is the current INT16 AIE-ML port target.
- `templates/aie1/` contains only `kernel_fp32_stream`, the FP32 output-stream variant. The description in
  `templates/description.txt` calls it the stream variant. Inspection of
  `kernel_fp32_stream/aie/para.h`, `mm0_kernel2.cc`, `mm0_kernel3.cc` and `aie_graph.h`
  confirms that A/B inputs remain windows, while final results use an ordinary
  float stream instead of an output window. Intermediate cascade roles remain.
- The two kernel0 variants also differ in output layout: the window variant
  declares C as `[W2][H1]`; the stream variant declares
  `[W2/2][H1/8][2][8]` and writes the two output-col vectors consecutively.
  Graph output-buffer constraints and stack addresses also differ.
- No Python or shell template-path selection for `templates/aie1/` was found
  in the repository search. The production generator selects `aie/` explicitly;
  its fixture-copy path expects `data/kernel_<dtype>_<transport>`, whereas `aie1/` stores fixtures
  directly under `data/`.

Porting implication: these directory names do not select AIE versus AIE-ML.
Continue the agreed INT16 work in `templates/aie/kernel_int16_packet/aie/`.
The historical reason for the name `aie1` is not established by this inspection.

## Kernel family identifiers

Inspected: 2026-11-10. Status: source-inspected classification, not target
compatibility validation. Sources: `templates/description.txt`, each family's
`aie/para.h`, `aie/aie_graph.h`, `aie/aie_top.h`, and
`CACG/gen_aie/gen_aie_design.py`.

| Directory | Operand type | Graph transport outside kernel windows |
| --- | --- | --- |
| `kernel_fp32_stream` | FP32 | Ordinary stream |
| `kernel_fp32_packet` | FP32 | Packet stream with split/merge |
| `kernel_int16_packet` | INT16 | Packet stream with split/merge |
| `kernel_int8_stream` | INT8 | Ordinary stream |
| `kernel_int8_packet` | INT8 | Packet stream with split/merge |

The current tree has no `templates/aie/kernel2`, `kernel3` or `kernel4`
directories. Their intended historical meanings are not established here.
As of 2026-11-11, the generator selects these directories directly by family
name. The earlier eight numeric slots and `kernel_type` ID selection were
removed; see [name-based selection](named_kernel_families.md).

Family names are distinct from the role suffix in a source filename. For example,
`kernel_int16_packet/aie/mm5_kernel0.cc` retains the historical `mm5` prefix and implements its initial
cascade role 0. Roles 1 and 2 continue and finalize the cascade respectively;
role 3 computes a standalone result. See the kernel5 port note for current
implementation details. Porting implication: family selection and cascade role
selection must remain separate when discussing or changing the generator.

### Broadcast is separate from packet selection

Inspected: 2026-11-10. Status: source-inspected graph connectivity, not a new
simulation result. Both `kernel_fp32_stream/aie/aie_top.h:27-40` (ordinary stream) and
`kernel_int16_packet/aie/aie_top.h:52-65` (packet stream) reuse input-port indices across
multiple compute graphs according to `A_BRO` and `C_BRO`. Both therefore express
broadcast connectivity. Ordinary streams are not restricted to one-to-one
connections. Kernel5 additionally uses `pktsplit` within each receiving graph
to distribute packets to kernel windows. Broadcast replicates the same data;
packet selection distributes packets according to their IDs. Porting implication:
preserve both mechanisms independently when changing graph transport.

### INT16 transport choice

Inspected: 2026-11-10. Sources: the family inventory above,
`kernel_int16_packet/aie/para.h`, `kernel_int16_packet/aie/aie_top.h`, and the matching
`templates/pl_kernel/kernel_int16_packet/` template family. Status: source-inspected facts
and an explicitly limited inference; no performance measurements.

The current tree provides only the packet-based INT16 family. No inspected
source explains why a non-packet INT16 family was omitted; this is not evidence
of a data-type restriction. Kernel5 groups `PACK_IN` kernel destinations per
packet input, giving `B/PACK_IN` input groups per compute graph, and groups
outputs using `PACK_OUT`. Reduced interface count is therefore a structural
benefit when these grouping factors exceed one. Whether that benefit motivated
the original authors is unverified. No throughput advantage is established.
Porting implication: introducing ordinary-stream INT16 would require coordinated
graph, PL transport and generator review, rather than only a scalar-type edit;
it is outside the currently agreed computation-preserving kernel5 port.

## Descriptive directory rename

Date: 2026-11-10. Status: user-requested and implemented directory rename.
Scope: AIE and PL family directories, existing AIE fixture directories, and
`aie1/kernel_fp32_stream`. Sources: `CACG/kernel_families.py`,
`CACG/gen_aie/gen_aie_design.py`, and `CACG/gen_pl/gen_pl_kernel.py`.

| Historical configuration ID | Previous directory | Current directory |
| --- | --- | --- |
| 0 | `kernel0` | `kernel_fp32_stream` |
| 1 | `kernel1` | `kernel_fp32_packet` |
| 5 | `kernel5` | `kernel_int16_packet` |
| 6 | `kernel6` | `kernel_int8_stream` |
| 7 | `kernel7` | `kernel_int8_packet` |

`stream` means ordinary stream transport; `packet` means packet stream
transport. Compute kernels retain their existing window interfaces. The `aie1`
FP32 variant still differs from the `aie` FP32 variant in final output interface
and layout, as described above. The host template `templates/host/kernel0` is
not a data-type/transport family and was not renamed.

At the directory-rename stage, numeric configuration IDs, C++ filenames and
symbols, calculation schedules, and generated output paths were unchanged.
The subsequent 2026-11-11 migration replaces the IDs with names; C++ symbols
and numerical behavior remain unchanged. Existing notes that say kernel5
refer to configuration family 5, now `kernel_int16_packet`. Git HEAD baseline
paths in the host checker intentionally retain the historical path until that
baseline is updated separately.

Verification: Python-only AIE and PL generation for all five families produced
byte-identical file inventories and contents before and after the rename.
Evidence: `sim/tmp_template_rename/check_generation.py`, `before.json`, and
`after.json`. The pre-existing absence of INT8 ordinary-stream fixture data
causes a fixture-copy diagnostic in both runs; generated AIE/PL sources match,
but this check does not validate that family's missing input fixture. No vendor
compiler, simulator or board execution was performed.

Porting implication: template paths now expose the data type and transport;
the original rename retained numeric compatibility, but current generation
requires explicit names as documented in [name-based selection](named_kernel_families.md).
