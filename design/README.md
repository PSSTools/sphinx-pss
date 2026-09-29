# Design and delivery notes

Working documents: the design, the phased build plan, and the upstream
`pssparser` work items. They record how decisions were reached, including the
ones that were later reversed, and they are updated as work lands.

**These are not published documentation.** They live outside `docs/` so the
Sphinx build cannot reference them: they are addressed to whoever is working on
this project, they cite line numbers in other repositories, and they carry
conclusions that are wrong on purpose — struck through and annotated with what
replaced them, because the reasoning is the useful part. None of that belongs
in a manual. User-facing documentation is `docs/`.

| Document | What it is |
|---|---|
| [`sphinx-pss-design.md`](sphinx-pss-design.md) | The approach, the object model, and the domain design |
| [`implementation-plan.md`](implementation-plan.md) | Phases, work items, and their status |
| [`activity-diagrams-design.md`](activity-diagrams-design.md) | UML activity-diagram rendering (design §9.3): the parser spike, the `A1`–`A5` upstream gaps, the IR, and the UML mapping |
| [`programming-steps-design.md`](programming-steps-design.md) | Step tables and flowcharts from `/// Step:` markers in functions and `exec` blocks (proposed §9.9): research, marker syntax, semantics, and parser dependencies |
| [`programming-steps-plan.md`](programming-steps-plan.md) | The implementation, test and doc plan for programming steps: readiness evidence, decisions, and milestones `S0`–`S5` |
| [`generic-constraints-design.md`](generic-constraints-design.md) | PSS 3.1 generic constraints (design §9.7 / `P4-IMPL-3`): the spike, the `C1`–`C3` upstream gaps, the model mapping, and the reference index |
| [`pssparser-enhancement-plan.md`](pssparser-enhancement-plan.md) | The upstream `pssparser` doc-comment work (Releases A–C) |
| [`pssparser-followup-plan.md`](pssparser-followup-plan.md) | Integration gaps found in Phase 1, dependency pinning, and the lexer decision |
| [`pssparser-fixes-plan.md`](pssparser-fixes-plan.md) | The `F0`–`F5`/`G1` fix plan, and what implementing it changed |
| [`pssparser-activity-gaps.md`](pssparser-activity-gaps.md) | The `A1`–`A6` activity-construction defects: evidence, root causes, and fixes |
