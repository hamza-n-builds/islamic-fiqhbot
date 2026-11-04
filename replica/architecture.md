# Startup architecture

Existing stack retained: Python 3.11, Flask/Werkzeug, local datasets, MiniLM/BM25,
Gemini and the existing HTML/CSS/JavaScript frontend.

`start_fiqhbot.cmd` selects a runnable 64-bit Python 3.11. The standard-library
`backend/bootstrap_local.py` checks the actual virtual-environment interpreter,
serializes setup using an OS file lock, preserves broken environments in a
Git-ignored backup, and creates/installs/checks a clean environment when needed.

Dependency readiness is recorded only after required package presence, root
requirement version validation, `pip check`, core imports and local NLTK resources
pass. The downloader stores tokenizer/stopword files in `backend/.cache/nltk_data`;
the existing RAG initializer now looks there first and downloads missing resources
there instead of a user-global directory. Optional Whisper imports remain lazy.
A requirements digest invalidates the setup marker when
requirements change. Normal launches reuse a healthy environment. Failed setup
does not start the application and can be retried.

After setup, the existing `start_local.py` loads server-side configuration, warms
the knowledge base, binds an available loopback port, records its local URL, and
opens the browser unless `--no-browser` is used. Existing instance reuse remains
in `start_local.py`.

`--setup-only` and `--check` do not start the app or call the model provider.
`--check` does not repair/install anything or import application configuration.
Runtime readiness is distinct from model readiness and answer correctness.

Pending work includes semantic source validation, scholarly review, response
contracts, mobile UI, chat reliability, provider budgets/timeouts, dependency
pinning and production serving. This startup change does not certify production
readiness or authorize publication.

## Citation integrity batch, 2026-11-04

Flask, Gemini, the current UI and retrieval stack are retained. Candidates are
re-resolved against local records before entering prompts; textless/missing
records are excluded. `citation_guard.py` enforces membership in the actual
generation context. Invalid, missing or malformed citations withhold the entire
reply. No-source requests do not call the provider, and grounded refusals cannot
escape into general-knowledge generation. The old generation shortcut now uses
the same guarded pipeline.

`POST /ask` accepts optional `prev_answer_receipt` text up to 8192 characters.
Accepted generated responses return `answer_receipt`; the frontend stores it in
message metadata. HMAC-SHA256 proof binds exact response text, cited identities,
cited record contents and a seven-day expiry. Rephrasing checks the proof and
current source fingerprint before calling Gemini, then requires the identical
set of citations. It returns the cited source metadata as well.

The optional private `FIQHBOT_RESPONSE_SECRET` must be at least 32 bytes and stable
across workers/restarts when persistent history is required. Otherwise a fresh
process-local key safely rejects old proofs. A receipt is provenance, not user
authentication or approval of religious content.

Verification: 74 Python tests, four actual frontend-function VM checks, six real
startup/HTTP checks. No live Gemini generation or browser rendering evaluation.
The source-record audit reports two unresolved hadith mappings and one mapped
hadith without English text. All 77 topics have pending/unspecified scholarly
review; semantic support, reviewed wording and accurate confidence remain open.
