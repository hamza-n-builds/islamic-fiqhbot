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

- 2026-11-04, F01 canonical source records: reproduced four failing source-route
  regressions against `72384fd`. Found mixed numbering and 348 duplicate legacy-key
  groups (702 extra rows), including nonempty wrong-narration hits. Matched all
  38 currently mapped identities to complete normalized Arabic on their published
  pages; pinned the existing owner-provided local rows. Changed seven Muslim
  reference numbers to explicit canonical variants, preserving every ruling/review
  and both original corpus files. Retrieval and text API share the resolver.
  Publisher-reported Shadh record is generation-held. Final: 97 Python tests,
  four frontend VM tests, eight real HTTP/startup checks passed; structural
  reference audit has no missing/textless mappings. Semantic/scholarly review
  remains pending; no live Gemini evaluation, push or deployment.
