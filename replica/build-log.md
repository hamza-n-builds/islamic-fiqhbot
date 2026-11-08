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

- 2026-11-08, F01/F02 response transparency: reproduced heuristic/fixed accuracy,
  consensus prompt/badges, weak general-route acceptance and WhatsApp `None%`
  against `a1ae80d`. Null public legacy scores/consensus, explicit scoped reference
  checks and incomplete answer/ruling review now replace those claims. Existing
  saved metadata is ignored, history preserved. Weak/invalid matches abstain;
  stricter private legacy cutoffs remain, with no consensus bonus. Known-consensus
  wording is withheld in all generation paths and old signed translation input.
  Final: 113 Python tests, eight frontend VM checks, nine real startup/HTTP checks
  passed. Source audit has zero missing/textless references; all dataset bytes
  match the previous batch and no scholarly approval was added. Browser host
  unavailable, so mobile/desktop visual QA remains pending. Wording checks are
  conservative, not semantic verification. No live provider generation, push or
  deployment. See `evidence/response-status-verification.json`.

- 2026-11-08, F01/F02 three-school RAG: removed the selected-school missing-key
  fallback, scoped the actual primary-topic notes to each available school and
  organized them through one provider-function invocation. Bounded JSON, required
  topic citations, school-specific membership/wording gates and independent
  withholding protect the structured contract. School identity/status/citations
  and exact text/source contents are bound in comparison receipts; old exact-scoped
  history stays compatible. The web opens directly into chat with native answer
  disclosures and scoped sources; pending replies stay in their originating chat.
  Unused direct-browser provider code was removed. Final: 138 Python regressions,
  14 actual frontend-function checks, nine real startup/HTTP checks and three real
  comparison HTTP checks passed. Comparison HTTP uses real retrieval plus a
  synthetic organizer, not Gemini. Twelve specified new-component color pairs
  pass AA. Dataset bytes and all review states are unchanged. Browser host
  unavailable; mobile/desktop visual/keyboard checks, live provider fidelity and
  scholarly/semantic validation remain pending. No push or deployment.

- 2026-11-09, F01 prototype response presentation: inspected the owner's FireShot
  reference and sampled its actual PNG palette. Replaced three answer dropdowns
  with one warm Montserrat response card and always-visible school rows; mobile
  stacks labels above full answers. Outline Listen/Copy utilities and a single
  source disclosure retain exact response text and school reference ownership.
  Missing/withheld notices and review limits remain; no demo percentage is copied.
  Source records now use native keyboard-operable disclosures with lazy content.
  Six frontend failures were recorded before implementation. Final: 18 frontend
  checks, 138 Python regressions, nine actual startup/HTTP checks and 44 specified
  contrast pairs passed. Backend runtime and all dataset byte hashes match the
  previous commit. A local renderer-based synthetic preview is available in
  workspace `.audit/fiqhbot-response-ui-2026-11-09/`. Browser host unavailable:
  visual/device/font/keyboard QA remains pending; no screenshot parity or religious
  accuracy claim. No live provider call, push or deployment.
