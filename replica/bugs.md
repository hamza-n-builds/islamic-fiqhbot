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
