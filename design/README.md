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
| [`pssparser-enhancement-plan.md`](pssparser-enhancement-plan.md) | The upstream `pssparser` doc-comment work (Releases A–C) |
| [`pssparser-followup-plan.md`](pssparser-followup-plan.md) | Integration gaps found in Phase 1, dependency pinning, and the lexer decision |
| [`pssparser-fixes-plan.md`](pssparser-fixes-plan.md) | The `F0`–`F5`/`G1` fix plan, and what implementing it changed |
