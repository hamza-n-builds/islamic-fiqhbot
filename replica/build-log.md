# Build log

- 2026-11-04, F00: existing source checkpoint `d407bfd` preserved before changes.
  Startup recovery, read-only checks, setup serialization and regression coverage
  implemented. Fresh environment setup, local NLTK provisioning, 33 regression
  tests, read-only launcher checks and five real startup/HTTP checks passed.
  Real model/data warm-up: 11.62 seconds. No frontend, ruling-generation or
  deployment changes in this batch; no live provider-generation test performed.

- 2026-11-04, F01 citation boundary: six failing response-path regressions
  reproduced against `f520ba6` before the fix. Added shared fail-closed reference
  checks, local source-text resolution, context-only general prompts and signed
  exact-answer/source-content provenance for rephrasing. Actual frontend functions
  forward and persist proof. Final: 74 Python tests, four frontend VM tests and
  six real startup/HTTP checks passed; no live provider-generation evaluation.
  Existing local server was left running; the smoke test used isolated temporary
  lock/state files. Two missing hadith mappings and one English text gap remain
  open, along with scholarly/semantic validation. No source records were guessed,
  edited or approved, and nothing was pushed or deployed.
