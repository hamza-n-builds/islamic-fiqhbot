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

Pending work includes source/citation validation, scholarly review, response
contracts, mobile UI, chat reliability, provider budgets/timeouts, dependency
pinning and production serving. This startup change does not certify production
readiness or authorize publication.
