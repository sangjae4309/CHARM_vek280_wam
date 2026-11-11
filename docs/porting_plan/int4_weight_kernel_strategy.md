# AIE-only INT4 weight reuse proposal

Date: 2026-11-10. Status: planning only, no source implementation, target build,
simulation or performance measurement. The user requested packed INT4 weights
for this discussion and then explicitly excluded PL design. Activation INT8
is an assumption carried forward from the existing workload, not a newly
selected quantization scheme. Existing generated INT8 kernels remain unchanged.

## Scope and source facts

Consider `[M,3072] @ [3072,3072]`, with M=1 for a single vector or M=417 for
ImageWAM. Packed weight storage is 4.5 MiB, excluding quantization metadata.
The full matrix cannot reside in one compute tile's 64 KiB data memory.
[AMD AM020](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-Tile-Architecture)
documents local memory capacity; [local-memory communication](https://docs.amd.com/r/en-US/am020-versal-aie-ml/AIE-ML-to-AIE-ML-Data-Communication-via-Local-Memory)
describes neighboring-tile sharing. This is not an unrestricted shared cache.

Source inspection of `kernel_int8_packet` shows a fixed K=64 schedule and
retained 4 KiB B/C buffer regions. The proposal below therefore requires a new
kernel schedule, packing/layout support and buffer placement; it is not a
configuration-only enlargement of the current generated examples.

## Candidate: keep a full-K weight column strip resident

Assign a kernel 16 output cols. Retain packed `W[3072,16]` (24 KiB) while
processing all available token rows. For each batch of up to eight token rows,
retain `A[8,3072]`, visit K in 48 chunks of 64, and finish the entire reduction
before final output conversion. Decode only a small weight chunk to signed
INT8 if that implementation path is selected, rather than expanding the whole
resident weight strip. An INT4 execution/API path must be selected and measured;
packed storage alone does not imply twice the MAC throughput.

Illustrative local data budget, not a compiler allocation:

| Allocation | KiB |
| --- | ---: |
| One resident packed INT4 W[3072,16] | 24 |
| One INT8 A[8,3072] block | 24 |
| One expanded INT8 W[64,16] scratch chunk | 1 |
| INT32 partial storage for [8,16], if spilled | 0.5 |
| Two final INT8 output [8,16] buffers, if that interface is retained | 0.25 |
| Total, before stack/metadata/alignment | 49.75 |

This budget deliberately has single buffers for A and the resident W strip;
it does not promise overlapping their refills. Do not double-buffer everything
and reuse the same total. Live microtile sums can reside in accumulator
registers, with spills only as required by the schedule. For unscaled signed
INT8 x signed INT4 products, the conservative absolute sum bound is
3072*128*8 = 3,145,728, fitting INT32. This does not settle bias, zero-point,
group-scale or requantization arithmetic. K-group quantization scales may
require separate group sums and scaling before combination.

There are 192 logical column strips. With eight physical kernels, assign eight
different strips per wave and execute 24 waves. Share/broadcast the same A
block through the AIE graph; each kernel owns different weights and distinct
output cols, so no inter-kernel reduction is needed for this partition.
For M=417, each resident strip is reused for 53 blocks of up to eight rows
(last block has one valid row). The 24 waves require replay of activation data;
the source/residency and replay mechanism remain unspecified in this AIE-only
discussion. No claim is made that all 4.5 MiB of weights are already resident.

For M=1 there is no reuse across token rows. Keeping the 3 KiB activation vector
while streaming weight chunks is then a simpler alternative, and may support
wider output-col blocks. Larger row batching is proposed specifically for the
417-token workload. Wider N strips and K-split cascade variants remain options
after validating a full-K kernel; no optimal tile size or kernel count is known.

## Next decisions and checks

Confirm whether the first benchmark targets one vector or all 417 token rows.
Specify nibble ordering, signed encoding and quantization metadata; select
packed-weight compute/unpacking strategy and final output scale/type. Then
validate arithmetic against an independent reference and check actual buffer
placement, stack, register pressure, bank contention and cycle counts.
No PL module or external partial-sum accumulator is part of this proposal.
