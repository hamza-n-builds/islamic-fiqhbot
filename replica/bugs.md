# FIQHBOT bug record

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

- Severity: S2 for corpus identity; fixed in the canonical source record batch.
- Topics: `zakat_salary`, `zakat_debt`; mapped Sahih Bukhari #1395 is not in the
  local lookup. Do not guess replacement numbers or infer religious correctness.
- Resolution: existing local row labeled 1413 exactly matches published Bukhari
  1395. The canonical resolver pins that row; no translation was generated/imported.
- Evidence: `evidence/source-record-audit.json`; structural audit now passes.

### DATA-002: A referenced hadith lacks the English text used by prompts

- Severity: S2 for corpus identity; fixed in the canonical source record batch.
- Topic: `five_daily_prayers`; mapped Sahih Muslim #11 has no English text locally.
- Resolution: old local 11 is an Introduction record. The mapped narration is
  canonical Muslim 11a, matching the complete existing local row labeled 109.
  The topic now names 11a and resolves its pinned original text.
- Evidence: same source audit. All 77 topics additionally have pending (49) or
  unspecified (28) scholar review. Membership checks and HMAC proof do not approve
  these rulings or validate claim-to-source entailment.

### DATA-003: Nonempty legacy key hits can be the wrong published narration

- Severity: S1 for source identity; fixed in the canonical source record batch.
- Reproduced: `/hadith-text?source=Sahih%20Bukhari&number=5590` returned a goat
  narration from a legacy key, not published Bukhari 5590. Four source-route
  regressions failed against `72384fd` before this fix.
- Cause: mixed numbering and 348 duplicate legacy-key groups, silently overwritten
  by dictionary construction. Thirteen registered identities differ from legacy labels.
- Fix: pin existing row fingerprints, require checked published variant/URL and
  complete normalized Arabic text identity; use the same resolver in RAG/API.
  Both original corpus files remain unchanged. No unregistered legacy key fallback.
- Evidence: source identity tests, registry and `source-record-review.md`.

### DATA-004: A publisher-reported Shadh source was generation-eligible

- Severity: S2 for source review; mitigated by an explicit generation hold.
- Source: Sunan Abi Dawud 2318; reported grade `Shadh (Al-Albani)` on its
  published page. This batch does not assign an independent grade.
- The identity remains inspectable but its text is excluded from generation/search.
  Qualified grade/fiqh support review remains open. The broader support-review
  queue is documented separately; no existing fiqh wording was approved.

### STATUS-001: Heuristics and unreviewed flags imply answer correctness

- Severity: S2 for response transparency; reproduced against `a1ae80d`.
- Flow/cases: F01/F02; response-status and saved-chat regressions.
- Steps: answer using a synthetic pending-review topic with `consensus: true`,
  inspect the public score and model prompt; format a general answer/WhatsApp
  greeting; render a saved chat with old confidence and consensus metadata.
- Expected: no measured-accuracy or agreement claims without supporting review;
  scoped reference-membership status and incomplete review on accepted answers.
- Actual: arbitrary/fixed percentages, `Scholarly Consensus: Yes` in prompts,
  agreement/disagreement badges, and WhatsApp `None%` on non-answer messages.
- Fix: null legacy fields, omit prompt certification, ignore legacy saved-chat
  scores/flags, persist scoped checks, and use the same limited labels on both
  channels. Known consensus wording is withheld on all generation paths.
- Status: fixed in `fix: replace misleading confidence with scoped response status`.
- Evidence: `test_response_status.py`, `test_chat_receipts.cjs`, and
  `evidence/response-status-verification.json`. No semantic/religious certification.

### STATUS-002: Weak topic match bypasses the main gate via general generation

- Severity: S2 for retrieval eligibility; reproduced against `a1ae80d`.
- Steps: call the general response path with a synthetic 0.5 topic match and
  locally resolvable source records; repeat with an invalid/infinite score.
- Expected: withhold before provider generation below the existing topic threshold
  or for invalid scores, regardless of dataset consensus flags.
- Actual: the lower 0.35 candidate threshold enabled general generation and a
  fixed confidence score even though the main fiqh topic threshold was 0.65.
- Fix: finite 0..1 similarity, shared topic threshold, and private conservative
  abstention cutoff without the consensus bonus. No published accuracy score.
- Status: fixed in the same response-status commit.
- Evidence: weak main/general match regressions and strict legacy-cutoff test.
- Remaining: calibrated relevance/ambiguity evaluation and qualified source-support
  review. These thresholds are heuristics, not proof of topical/religious support.
