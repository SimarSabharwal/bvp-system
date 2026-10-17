---
name: decision-overlap
description: Check Student System project decisions and requested changes against the PRD, logic.md, and current decision records; flag material contradictions before acting.
metadata:
  short-description: Flag conflicting project decisions
---

# Decision Overlap

Use this skill whenever the user makes or changes a product, workflow, data, architecture, implementation-order, or deployment decision for the Student System project. The goal is to catch accidental conflicts early and let the user decide which direction is current.

## Check before acting

1. Read the project-root `logic.md` first. Inspect the relevant source of truth for the decision, such as `PRD.md`, `PHASE_0_DECISIONS.md`, `DATABASE_DESIGN.md`, `TECH_STACK_TRD.md`, or `IMPLEMENTATION_PLAN.md`. Do not rely on memory if the current record is available.
2. Restate the new decision internally as a concrete rule and compare it with current decisions and constraints in the relevant files.
3. Treat a conflict as material when both rules cannot be true for the same scope or when implementing the new rule would violate a recorded invariant. Examples include:
   - asking to include excused attendance in percentages after deciding it is excluded;
   - asking to deploy the API to a provider that cannot support a required connection model;
   - assigning a teacher or room to overlapping sessions after establishing a no-overlap rule;
   - bringing lab subgroups into MVP after recording that they are deferred;
   - moving frontend implementation earlier despite the agreed backend-first phase order.
4. Distinguish a true contradiction from added detail, a narrower scope, or a clearly intentional revision. A newer, explicit user instruction may replace an older choice; do not treat normal iteration as an error.
5. Whenever work is organized into phases, compare each phase's planned tasks and exit criteria with the PRD and `PRD_PHASE_CROSSWALK.md` (if present). Flag requirements that have no phase, phases that promise behavior contrary to the PRD, and scope that is deferred without a recorded decision.

## How to alert the user

- If the user clearly says to replace or revise an earlier decision, acknowledge the old and new values briefly, then proceed with the new direction. Update affected canonical documents and record the superseding decision in `logic.md` when project files change.
- If intent is ambiguous and the conflict materially changes the design or outcome, pause only the work that depends on the choice. Tell the user which new request conflicts with which recorded decision, identify the source files, and state the practical consequence in plain language. Ask whether the new choice should replace the old one or whether the earlier decision should remain.
- Do not silently pick a side, quietly rewrite the previous decision, or implement both incompatible options as if they were compatible.
- Continue independent work that does not depend on the conflict. Avoid interrupting for low-impact differences that can be safely reconciled without changing an agreed invariant.
- After resolution, update all affected records together so the PRD, decision log, database design, technical requirements, and implementation plan do not contradict one another. Preserve decision history in `logic.md`; do not erase the old choice.

## Reporting format

Keep warnings short and specific:

> **Decision conflict:** Your new request says **[new choice]**, while **[file/section]** records **[current choice]**. This affects **[practical consequence]**. Should I replace the recorded choice with the new one?

If there is no material conflict, proceed without announcing a routine consistency check.
