# Repository working rules

- Tests must exercise meaningful behavior, public contracts, failure handling, or real
  integration boundaries. Do not add tests for import side effects, module layout,
  private implementation details, or assertions that merely repeat the code.

## Handoff workflow

- At the start of each task, read `transcription-assignment-plan.md`, the local
  Git-ignored checklist at `docs/implementation-status.md`, and recent Git status/log.
- Use the next unfinished checklist item as the default scope. Work only on that item
  and direct prerequisites; do not begin later phases without a concrete dependency.
- Preserve existing user changes. Never reset, discard, or rewrite unrelated work.
- Keep the code simple: prefer cohesive modules and explicit boundaries over speculative
  abstractions. Preserve the required domain/application/infrastructure/entrypoint layers.
- Use only user-provided media. Never search for or download recordings independently.
- Keep updates and tool output concise. Batch read-only inspection where practical.
- Verify changes with focused checks and record exact commands, results, limitations, and
  remaining work in `docs/implementation-status.md`. Do not claim unverified behavior.
- Keep `docs/implementation-status.md` local and ignored. Make one coherent Git commit
  when the scoped checklist item reaches a usable checkpoint.
- End each task with the completed checklist item, verification result, commit, and next
  unchecked item. Stop there unless the next item is a direct prerequisite.
