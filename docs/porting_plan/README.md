# VEK280 porting notes

Updated: 2026-11-10. This directory records inspected behavior, architectural
differences, decisions and open questions for porting CHARM from VCK190 AIE to
VEK280 AIE-ML. Conversation is in Korean; new and revised Markdown is in English.

## Current agreement

- On 2026-11-10 the user narrowed the next port to INT8 only and deferred FP32.
  Both INT8 transport families and the extra standalone test now have source
  ports and prepared execution cases. Host checks passed; target runs are pending.
- INT16/kernel5 is the first target. Preserve CHARM computation and data order.
- The user subsequently authorized the initial kernel5 AIE-ML source port after
  the acc48 graph-interface error. See the implementation notes below. Target
  compilation and the current four-iteration AIE simulation completed; the
  earlier host glibc startup failure is historical.
- Reuse the actual CHARM AIE generator through `compile.sh`; use `run.sh`
  separately for AIE simulation and `check_output.py` for output comparison.
- Record failures from the original code. Do not silently change computation,
  accumulator precision or interfaces to force a pass (user answer: Q1 yes).
- The user will run tools. Finish scripts/documentation without further compiler
  or simulator invocations unless requested.
- Use fixed `sim/tmp_<pattern>/` directories. The user authorized deleting and
  recreating run artifacts on rerun and removing old temporary cases. Preserve
  the case-owned scripts and repository link requested afterward.
- Previous standalone implementation attempts were canceled and removed. The
  separate `check_original.py` case was also removed during requested cleanup.
- VEK280 compilation succeeded according to the user log (2026-11-09).
  The current simulation log reports success; all 9,216 output values match the
  fixture reference (inspected 2026-11-10). Board validation remains pending.
- HTML illustrations explain behavior; they are not hardware validation.

## Documents

- [Named kernel families](named_kernel_families.md): direct family-name selection
  from DSE through AIE/PL generation; numeric IDs removed and callers migrated.
- [ImageWAM code organization](imagewam_code_organization.md): model-specific
  sources moved to `example/ImageWAM/`; generic CHARM code and existing case
  launch commands preserved.
- [ImageWAM AIE source generation](imagewam_aie_generation.md): actual generated
  CHARM MM kernels and separately controlled graphs, tile/dispatch artifacts,
  host source checks and the remaining transport/nonlinear integration boundary.
- [Connected ImageWAM mapping](imagewam_graph_mapping.md): implemented full
  dependency graph, grouped CHARM array search, eight MM-only placement/schedule
  candidates, host verification and unresolved nonlinear/transport resources.
- [Detailed ImageWAM AIE workload](../imagewam_aie.md): prefill/action matrix
  shapes, non-GEMM dependencies and CHARM mapping proposals with resource limits.
- [VEK280 DSE resources](vek280_dse.md): selectable 304-tile/38x8 resource
  model, local-memory checks, executed search and uncalibrated timing limits.
- [Original CHARM ImageWAM DSE](imagewam_charm_dse.md): actual 417x3072x3072
  baseline search result, chosen array/broadcast/repetition and model limits.
- [ImageWAM split measurements](imagewam_split_measurements.md): five agreed
  case boundaries, replaceable parameters, preparation status and remaining
  INT32 partial-output decision; no measured hardware latency yet.
- [ImageWAM nonlinear source review](../imagewam.md): external module inventory,
  arithmetic/interface differences, saved-report provenance and open decisions.
- [INT8 AIE-ML port](int8_aie_ml_port.md): source/API changes, numerical bounds,
  five prepared execution cases, host verification and target-testing limits.
- [Template directories](template_directories.md): descriptive family names,
  numeric configuration mapping, transport differences and rename verification.
- [Initial kernel5 AIE-ML port](kernel5_aie_ml_port.md): actual changes, AMD sources,
  preserved behavior, host-only checks and pending target verification.
- [Generator-based AIE simulation](aie_simulation.md): scripts, configuration,
  production generation path, test results and limitations.
- [Original INT16 kernels](int16_kernels.md): kernel roles, tiling and cascade.
- [VEK280 compatibility](vek280_compatibility.md): architectural facts and proposals.
- [Terminology](../TERMINOLOGY.md): concepts that must remain distinct.
- [Template TODO](../../templates/aie/README.md): implementation/verification status.

## Recording rules

Keep inspected source facts, official specifications, user decisions, proposals
and actual execution results distinct. Record sources, dates and verification
status for material findings. Correct stale claims instead of adding contradictory
notes. Never treat reference preparation or a compiler exit code alone as a
successful AIE simulation. Record agreed changes without inventing approvals.
