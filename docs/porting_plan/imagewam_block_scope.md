# ImageWAM fork/join block: diagram inspection

Date: 2026-11-10. Source: user-provided
`sim/tmp_imagewam_fork_join/imagewam-fork-join.png`.
Status: diagram-inspected interpretation only; no implementation, compilation,
simulation or timing measurement. The user requested understanding and questions
before mapping this block to CHARM matrix multiplication and PL nonlinear logic.

The diagram shows batch 1, sequence length 417 and hidden size 3072. A shared
LayerNorm/modulation output forks into an MLP branch and an attention branch.
The MLP has two 3072-to-9216 projections and computes SiLU(G) times U. Attention
has three 3072-to-3072 projections, 24 heads of width 128, Q/K RMSNorm and RoPE,
then per-head QK-transpose, mask/softmax and probability-times-V. Head outputs
merge to width 3072, concatenate with MLP width 9216, and pass through a
12288-to-3072 output projection.

Logical matrix products (weight orientation expressed as input-by-output):
- G/U: two `(417,3072) @ (3072,9216)` products.
- Q/K/V: three `(417,3072) @ (3072,3072)` products.
- Per head: `(417,128) @ (128,417)` and `(417,417) @ (417,128)`.
- Output: `(417,12288) @ (12288,3072)`.

Unresolved: normalization/modulation definitions and parameter shapes, biases,
RMSNorm axis/epsilon, RoPE parameters/positions, mask contents and padding,
concat order, integer quantization/scaling and nonlinear precision, weight
residency, resource allocation and scheduling, and timing boundaries/method.
The drawing's parallel heads express logical parallelism, not an agreed
allocation of 24 simultaneous hardware engines. Sequence length 417 needs
explicit tail handling when mapped to CHARM tiles; padded keys must not enter
the original softmax normalization.

Porting implication: no numerical policy, hardware allocation, full-system PL
integration scope, or measured latency can be inferred solely from this image.
The previous INT8 verification cases were deleted at the user's request; their
historical notes do not imply that those case scripts remain available.

## User decisions and simulation feasibility (2026-11-10)

User decisions: INT8 MM, latency from LayerNorm start to final Out Linear output,
inputs and weights already prepared, and all 24 attention heads concurrent.
Nonlinear sources are now reviewed in [docs/imagewam.md](../imagewam.md).
The user selected HardSwish in place of the diagram's SiLU on 2026-11-10;
the user also selected separate isolated INT16 nonlinear modules as the source
baseline. LUT-only resource mapping is not required by this selection.
The user subsequently selected ConSmax to replace softmax, citing REATA
(TRETS 2026). See the source review and unverified REATA details in
[docs/imagewam.md](../imagewam.md). A separate PL ConSmax followed by AIE P*V
is proposed; parameter values and fixed-point scaling remain open.
These are decisions/proposals, not implemented or measured results. Memory residency,
MLP/attention overlap, and simulation-versus-board validation remain unresolved.

Arithmetic derived from diagram shapes, excluding nonlinear work and padding:
52,227,348,480 MACs per block, or approximately 104.45 billion operations when
counting multiplication and addition separately. Linear weights alone contain
122,683,392 INT8 elements (117 MiB). These are size/work counts, not timing results.

The prior small INT16 case reports 699.89 seconds of host simulation wall time
for 76.742401 microseconds of simulated time, including startup/flush (see
`aie_simulation.md`). That ratio must not be extrapolated into an ImageWAM run
time: mapping, INT8 instructions, PL RTL and simulator overhead differ.

Proposal, not implemented: measure representative tiled MM steady-state and
startup/drain behavior; measure PL nonlinear latency and initiation interval
with full reduction widths; combine these with explicit resource/transfer and
fork/join scheduling into a latency estimate. Validate a shortened workload
with the intended concurrent head topology, then consider a full-block run.
Do not shrink softmax key count or normalization width and linearly extrapolate
without a model. A component-based estimate is not measured full-block latency.

AMD describes AIE simulation as cycle-approximate. Hardware emulation combines
PL RTL, the AIE simulator and PS QEMU; NoC/DDR timing is approximate. Full-system
emulation can estimate the requested PL+AIE interval but is not board timing.
Sources: [AIE simulation](https://docs.amd.com/r/2025.2-English/ug1388-acap-system-integration-validation-methodology/AI-Engine-Simulation),
[system performance emulation](https://docs.amd.com/r/2025.2-English/ug1388-acap-system-integration-validation-methodology/Using-Hardware-Emulation-to-Analyze-System-Performance).
