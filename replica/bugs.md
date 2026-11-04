# Startup bug record

### STARTUP-001: An existing but broken Python exe bypasses setup

- Severity: S1 for the local start flow (core flow blocked).
- Flow/case: F00 / F00-E1.
- Reproduced before changes on 2026-11-04.
- Steps: run the existing `backend/venv/Scripts/python.exe`, then inspect the
  launcher condition which checks only whether that file exists.
- Expected: use a runnable Python environment or provide recoverable setup.
- Actual: Python exits with `No Python at '"C:\Program Files\Python311\python.exe'`;
  the old launcher skips dependency setup because the exe file still exists.
- Cause: a copied environment points at a missing base Python installation.
- Fix: execution/version/prefix checks, preserved environment backup, fresh
  creation, dependency verification and retryable setup.
- Regression: `backend/tests/test_local_startup.py`.
- Status: fixed in the `fix: restore reliable local startup` commit; verified by
  33 regression tests, the launcher runtime check and the real startup smoke test.

### STARTUP-002: Missing NLTK resources prevent knowledge-base warm-up

- Severity: S1 for F00; reproduced by the first real warm-up check.
- Expected: setup prepares the tokenizer and stopwords required by the app.
- Actual: fresh Python packages installed, but `punkt` was missing; warm-up failed.
- Fix: provision `punkt`, `punkt_tab`, `stopwords` during setup in the backend's
  ignored cache and make the RAG initializer use that local resource location.
- Evidence: `evidence/local-startup.json` now passes real model/data warm-up with
  external networking blocked. Failed resource setup cannot mark a runtime ready.
- Status: fixed in the same startup commit.

Existing answer authenticity, chat-state and other readiness findings are outside
this startup fix. Their implementation has not been completed by this batch.

### SOURCE-001: Unprovided references survive curated generation

- Severity: S1 for citation integrity.
- Reproduction: stub the provider with a synthetic answer containing an absent
  `[Quran 999:999]` or fabricated topic tag. The original curated path displays it.
- Related general-path failure: removing the invalid tag retains the same claim.
- Fix: shared context-membership gate rejects the entire generated answer,
  including unknown topic tags, malformed references and uncited output.
- Status: fixed in the citation/provenance commit.
- Evidence: `tests/test_citation_integrity.py`, `evidence/citation-verification.json`.

### SOURCE-002: Browser-supplied prior answer is trusted for rephrasing

- Severity: S1 for answer provenance.
- Reproduction: submit a language instruction with arbitrary `prev_answer` text;
  the original route forwards it to the provider without server provenance.
- Fix: signed exact-answer/citation/source fingerprint, expiry and unchanged-source
  verification before rephrasing. Translation cannot add/drop reference identities.
- Status: fixed in the citation/provenance commit. Historical messages without
  proof require asking the original question again.
- Evidence: receipt, real Flask route and frontend VM tests; real HTTP smoke rejects
  invalid history with all external networking blocked.

### SOURCE-003: Missing context/refusal can fall through to general generation

- Severity: S1 for source constraints.
- Reproduction: no candidate references still invokes general generation; a
  grounded refusal invokes a second, less-constrained general response.
- Fix: no-context requests and grounded refusals yield fixed referrals; general
  prompts prohibit facts/rulings from memory. The legacy shortcut uses the same gate.
- Status: fixed for routing/citation membership. Semantic support still requires
  separate verification and qualified review.

### DATA-001: Two topic mappings point to a missing local hadith record

- Severity: S2 for corpus completeness; open.
- Topics: `zakat_salary`, `zakat_debt`; mapped Sahih Bukhari #1395 is not in the
  local lookup. Do not guess replacement numbers or infer religious correctness.
- Runtime mitigation: absent records cannot enter citation context.
- Evidence: `evidence/source-record-audit.json`; audit command currently exits 1.

### DATA-002: A referenced hadith lacks the English text used by prompts

- Severity: S2 for corpus completeness; open.
- Topic: `five_daily_prayers`; mapped Sahih Muslim #11 has no English text locally.
- Runtime mitigation: textless prompt records are excluded even when an ID exists.
- Evidence: same source audit. All 77 topics additionally have pending (49) or
  unspecified (28) scholar review. Membership checks and HMAC proof do not approve
  these rulings or validate claim-to-source entailment.
