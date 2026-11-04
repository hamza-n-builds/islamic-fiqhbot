# Backend maintenance checklist

Current batch: local startup only, 2026-11-04. Required Replica build/backend/test
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
