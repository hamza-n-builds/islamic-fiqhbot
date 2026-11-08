# Backend maintenance checklist

Startup batch completed on 2026-11-04. Required Replica build/backend/test
workflow applied to the existing application. No hosting or publication.

- [x] Probe the virtual environment rather than accepting an existing exe file.
- [x] Require Python 3.11 (64-bit), including explicit interpreter selection.
- [x] Preserve a broken environment; never remove application data or models.
- [x] Validate installed dependencies before marking setup complete.
- [x] Validate root version requirements offline and prepare NLTK resources locally.
- [x] Serialize dependency setup and retain failure exit codes.
- [x] Provide setup-only and read-only runtime-check modes.
- [x] Cover setup failure, retry, path quoting and duplicate setup with regressions.
- [x] Complete the real warm-up/HTTP smoke check and record evidence.

Verification: 33 regression tests passed (22 startup + 11 existing API boundary
tests), read-only launcher `--check` passed, and five real warm-up/HTTP smoke checks
passed. See `evidence/local-startup.json` and `evidence/startup-verification.json`.
The smoke server warmed the real datasets/model in 11.62 seconds with external
network blocked. It did not generate an answer. Browser rendering, optional voice
model/FFmpeg, provider credentials and religious correctness remain unverified.

Other readiness areas remain pending; no claim is made that prompt grounding,
citation existence, or a confidence percentage proves a religious ruling correct.
No credentials or private conversations belong in verification artifacts.

## Citation batch completed, 2026-11-04

- [x] Reject whole generated replies on references outside supplied context.
- [x] Reject uncited, malformed or oversized generated replies.
- [x] Resolve candidate IDs against local records and require prompt-language text.
- [x] Skip provider generation without source context; preserve grounded refusals.
- [x] Display only references actually cited in accepted text.
- [x] Sign exact-answer/citation/source-content provenance for rephrasing.
- [x] Reject changed/expired/missing proof and altered source contents.
- [x] Preserve all original citation identities through a valid translation.
- [x] Forward/persist proof in frontend history without exposing a signing secret.
- [x] Verify regression, API and local HTTP flows; record actual limits.
- [x] Resolve two missing hadith mappings and one referenced text gap with reliable evidence (canonical identity batch below).
- [ ] Obtain scholarly review; none of the 77 topics currently has an approved review marker.
- [ ] Verify semantic claim support and translation fidelity; membership alone is insufficient.

Latest evidence: 74 Python tests, four frontend VM checks, six real startup/HTTP
checks passed. Corpus audit exits 1 for the open mapping gaps. No live Gemini
evaluation, browser rendering check, production-ready certification, push or deploy.
See `evidence/citation-verification.json` and `evidence/source-record-audit.json`.

## Canonical identity batch completed, 2026-11-04

- [x] Identify legacy numbering collisions rather than fabricating missing text.
- [x] Match all 38 currently mapped narrations to complete published Arabic text.
- [x] Pin owner-provided corpus rows; preserve both raw corpus files unchanged.
- [x] Resolve canonical labels/variants consistently in retrieval and text lookup.
- [x] Correct seven Muslim reference fields without changing fiqh rulings/reviews.
- [x] Reject duplicate canonical keys and modified/missing source fingerprints.
- [x] Exclude the publisher-reported Shadh record from generation pending review.
- [x] Record known semantic support questions for qualified review.

Structural reference audit passes with no missing or referenced-English-text gaps.
The corpus remains unapproved for production religious guidance: no scholarly
approval was added. See `source-record-review.md` and the source identity evidence.
Final verification: 97 Python tests, four frontend VM checks and eight real
startup/HTTP checks passed. The canonical audit passes with all mapped references
resolved. See `evidence/source-record-verification.json` for preservation checks,
the seven exact reference edits and the remaining review limits.

## Response status batch, 2026-11-08

- [x] Remove public heuristic accuracy percentages and definitive consensus flags.
- [x] Omit dataset consensus/certainty certification from generation prompts.
- [x] Preserve stricter private abstention settings without a consensus bonus.
- [x] Withhold weak/invalid topic matches before either generation path.
- [x] Apply known-consensus wording checks to all generated/translated replies.
- [x] Reject old signed consensus claims before translation generation.
- [x] Display scoped reference checks and incomplete review in web/WhatsApp.
- [x] Ignore old saved confidence/consensus metadata without deleting history.
- [x] Persist check/review status in new history and optional logging.
- [x] Cover actual pipeline, Flask routes, channel formatting and frontend functions.
- [ ] Visually check badge wrapping on mobile/desktop: browser host unavailable.
- [ ] Calibrate retrieval, evaluate claim support/translation, obtain scholarly review.

See `response-status.md` and `evidence/response-status-verification.json`.
No live Gemini generation, source/ruling edits, newly approved reviews, push or
deployment are part of this batch.
