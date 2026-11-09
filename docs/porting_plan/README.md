# VEK280 porting notes

Updated: 2026-11-09. This directory records inspected behavior, architectural
differences, decisions and open questions for porting CHARM from VCK190 AIE to
VEK280 AIE-ML. Conversation is in Korean; new and revised Markdown is in English.

## Current agreement

- INT16/kernel5 is the first target. Preserve CHARM computation and data order.
- The user subsequently authorized the initial kernel5 AIE-ML source port after
  the acc48 graph-interface error. See the implementation notes below; the user reported successful target compilation; simulation is blocked at
  startup by host glibc compatibility.
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
  No successful simulation or board run has been established.
- HTML illustrations explain behavior; they are not hardware validation.

## Documents

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
