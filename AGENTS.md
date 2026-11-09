# CHARM VEK280 working guide

## Scope and collaboration

- This repository is being studied for a VCK190 AIE to VEK280 AIE-ML port.
  INT16 is the first agreed data type. The user has authorized starting kernel5
  porting while preserving original CHARM code and calculation order. Start with
  original-source compilation and minimal compatibility fixes; do not redesign
  the computation for AIE-ML resources. Explain any required numerical or
  interface changes before applying them.
- The user subsequently authorized kernel5 source changes based on AMD docs.
  Preserve CHARM tiling, buffer order and cascade roles; record required API,
  accumulator and placement differences in English under docs/porting_plan/.
- The user now owns compiler/simulator execution. Prepare scripts and docs, but
  do not launch or wait for vendor tools again unless explicitly requested.
- Explain code and discuss the reason, proposed change, affected files, and
  verification method before asking the user to agree to implementation.
- Treat requests to understand code, inspect files, or plan as read-only work.
  Do not interpret them as permission to edit kernels, generate designs, or run
  compilers and simulators. Once a concrete scope is approved, stay within it.
- Explicit requests to edit instructions, maintain notes, or create a visualization
  authorize those specific artifacts, not implementation or toolchain experiments.
- Explain in Korean unless requested otherwise. Follow the user's pace when
  walking through code; answer the current question before advancing.
- Write Markdown documentation in English. Korean is for conversation with the
  user; use English for new or revised documentation.
- Use English `row` / `col` for matrix directions, including Korean explanations
  and new documentation. Avoid translating these direction terms into Korean.
- Do not start background work or delegate execution without an agreed scope.
  Stop task-owned processes when the user cancels or the task ends; preserve
  unrelated processes and files.

## Repository work

- Inspect the working tree and relevant source before editing. Preserve user
  changes, editor swap files, the existing `sim` symlink, and unrelated artifacts.
- Modify generator templates when implementing generated behavior; avoid treating
  generated examples as the only source of truth.
- Preserve numerical behavior, data layout, and interfaces unless the user agrees
  to a change. Do not silently choose overflow, rounding, saturation, precision,
  or performance trade-offs.
- Distinguish board name, architecture, vector type, C++ variable name, register
  storage specifier, kernel role, graph instance, and matrix tile.
- Write newly requested HTML in English, including controls and accessible labels.
  Do not rewrite existing artifacts merely to enforce this rule.
- Use checks proportional to the approved changes. Documentation-only changes
  do not authorize vendor tool invocation or hardware work.

## Porting knowledge

- Read `docs/porting_plan/README.md` and the relevant linked notes before
  substantial porting discussion or implementation. Source is authoritative for
  the current implementation; correct stale notes when source differs.
- Keep durable VEK280 porting findings under `docs/porting_plan/`. Update them
  during code walkthroughs when a new fact, correction, unresolved question, or
  agreed decision would otherwise need to be rediscovered in a later session.
- Keep terminology in `docs/TERMINOLOGY.md`; keep implementation details in the
  porting notes. Link rather than duplicate detailed explanations.
- For each material finding record its scope, source, date, verification status,
  and porting implication. Separate source-inspected facts, architecture-document
  facts, user decisions, proposals, and actual compiler/simulator/board results.
- Revise incorrect entries rather than appending contradictory claims. Do not
  describe conversational examples as hardware results, or a proposed port as
  implemented. Record actual tested tool versions and board revisions when known.
- Keep unresolved decisions explicit. Do not invent ADRs, board facts, performance
  numbers, or an approval that the user has not given.

## Experiments, when approved

- Put every case under `sim/tmp_<pattern>/` without a random suffix. The user
  explicitly authorized clearing the same case on rerun. Preserve case-owned
  scripts and the repository symlink; remove generated run artifacts only.
  Keep generated sources, configuration, working files, temporary files, logs,
  actual outputs, references, and comparisons inside that case directory.
- Run tools from the case directory and use its temporary directory where the
  tool permits. Never remove a different case or bypass the existing `sim` symlink.
- Record exact commands, configuration, exit status, and validation outcome.
  Distinguish prepared, running, failed, stopped, and verified results.
- Preserve failed-case evidence unless the user requests removal. A reference-data
  check is not a passing AIE simulation; a passing simulation is not board validation.
- Explain environment problems before proposing fixes. Do not change shared
  installations, licenses, shell startup files, or system libraries as an incidental
  part of a porting experiment.
