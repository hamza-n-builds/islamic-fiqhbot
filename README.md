# Islamic FiqhBot 🕌

An applied AI, multilingual Islamic guidance assistant engineered around a hybrid **BM25 + MiniLM** retrieval-augmented generation (RAG) pipeline with **Gemini synthesis**, locally stored Qur'an/hadith records, curated fiqh rulings across schools of thought, and WhatsApp integration. Source resolution and scholarly review are separate requirements.

---

## 🌟 Overview

* **Hybrid RAG Retrieval**: Combines keyword-level precision (BM25) with semantic embeddings (MiniLM) to retrieve authentic sources with high precision.
* **School of Thought (Madhab) Specificity**: Answers grounded according to the three schools currently present in the dataset (Hanafi, Shafi'i, Maliki) or general guidance.
* **Citation Membership Validation**: Context-constrained prompts and server checks reject generated references outside the supplied source records. This does not establish that a claim follows from a source or certify a ruling.
* **Multi-Channel**: Web client and Meta Cloud API WhatsApp webhook integration.

---

## 🏗️ System Architecture

```
FIQHBOT - Islamic Chatbot/
├── backend/
│   ├── app.py              # Flask REST API & WhatsApp Webhook endpoints
│   ├── rag_engine.py       # Hybrid BM25 + MiniLM RAG retrieval pipeline
│   ├── voice.py            # Audio query processing & transcription
│   ├── db.py               # Data models and query caching
│   ├── requirements.txt    # Python dependencies
│   ├── .env.example        # Environment variable template
│   └── data/               # Curated fiqh topics, Quran & Hadith databases
└── frontend/
    ├── index.html          # Web chat user interface
    ├── modern.css          # Responsive design styling
    ├── script.js           # Chat client state and message rendering
    └── config.js           # API connection configuration
```

---

## 🚀 Quick Start

On Windows, double-click `start_fiqhbot.cmd` in this folder. It starts the local
backend, waits for the knowledge base to load, and opens the interface in your
browser. Keep the command window open while using FIQHBOT. The launcher chooses
an available local port, so an old server on port 5000 cannot intercept requests.
Later starts reuse cached embeddings and are faster.

On first use, the launcher creates `backend/venv` and installs dependencies if
needed. It checks that the interpreter can actually run Python 3.11 (64-bit),
not just that `python.exe` exists. If an old/copied environment is broken, it
preserves it as `backend/venv.backup-*` and creates a clean environment. Backups
are ignored by Git; setup never removes your datasets, models or `.env`.

Before starting, copy `backend/.env.example` to `backend/.env` and put your own
`GEMINI_API_KEY` there. Python 3.11 (64-bit) and an internet connection for missing
packages/models are required. The `.env` file stays on this computer and is
ignored by Git. An existing `GEMINI_API_KEY` process environment variable also
works without an `.env` file.

The launcher tries a working project environment, `py -3.11`, `python3.11`, then
`python`. To choose an interpreter explicitly in PowerShell:

```powershell
$env:FIQHBOT_PYTHON = 'C:\path\to\Python311\python.exe'
.\start_fiqhbot.cmd --setup-only
```

Useful launcher options (run from this folder):

```powershell
.\start_fiqhbot.cmd --setup-only  # install/check dependencies; no app or browser
.\start_fiqhbot.cmd --check       # read-only runtime/import check; no installs
.\start_fiqhbot.cmd --no-browser  # run normally without opening the browser
```

`--check` does not read credentials, initialize the knowledge base, call Gemini,
send WhatsApp messages, or verify answer correctness. First setup verifies package
dependencies, core imports and local NLTK tokenizer/stopword resources before
marking the environment ready. NLTK resources stay in `backend/.cache/nltk_data`.
Whisper is still imported lazily by voice features; voice model/FFmpeg readiness
is a separate check. Later launches
reuse it; changed requirements or missing dependencies trigger setup again.
For unattended commands, set `$env:FIQHBOT_NO_PAUSE = '1'` to preserve error exit
codes without waiting for a key press. If installation fails, fix the reported
issue and rerun `--setup-only`; the environment is not marked ready until checks
pass.

Startup verification and remaining scope are recorded in
[`replica/test-plan.md`](replica/test-plan.md) and
[`replica/backend.md`](replica/backend.md). Run the regression suite from `backend`
with `venv\Scripts\python.exe -B -m unittest discover -s tests -v`.

For local use, always open the page launched by `start_fiqhbot.cmd` rather than
double-clicking `frontend/index.html`.

The WhatsApp sidebar shortcut is shown only if `WA_PUBLIC_NUMBER` is configured
in `backend/.env`; a placeholder number is never shown.

The fiqh dataset includes topics with pending or unspecified scholar review.
Treat generated guidance as informational and verify important rulings with a
qualified scholar.

### Citation and follow-up safeguards

The server re-resolves candidate records against the local corpus and excludes
missing records or records without the English source text used by the prompts.
An unsupported/malformed citation or an answer without any supplied reference
withholds the entire generated reply. Its text is not retained after merely
removing a bad tag. Without source context, no generation request is made; a
grounded refusal does not trigger an ungrounded second attempt. The Sources panel
contains only records actually cited in the accepted response.

Accepted responses include an opaque `answer_receipt`. The frontend saves it and
sends `prev_answer_receipt` with translation/rephrasing follow-ups. The proof binds
the exact prior answer, citation identities and cited source contents. Modified,
expired or missing proof, or changed source text, requires asking the original
question again. Valid translations retain all original citation identities.

Receipts expire after seven days. Optionally set a private
`FIQHBOT_RESPONSE_SECRET` of at least 32 bytes in backend configuration to keep
proofs valid across restarts/workers. With it blank, a random process-local secret
is used, so earlier answers cannot be rephrased after a restart. Never put this
secret in frontend config. Existing saved chats without proof remain readable;
their original question must be asked again before a translation follow-up.

These are reference-membership and provenance checks, not a hallucination-free
guarantee. Claim-to-source support, retrieval relevance, translation fidelity,
reviewed wording and scholarly approval remain separate release requirements.
See [`replica/evidence/source-record-audit.json`](replica/evidence/source-record-audit.json)
for unresolved dataset mappings/review status and
[`replica/evidence/citation-verification.json`](replica/evidence/citation-verification.json)
for the exact tests and limitations.

### Manual setup (optional)

```bash
cd backend

# Create a virtual environment using Python 3.11 (64-bit)
py -3.11 -m venv venv

# Install dependencies
venv\Scripts\python.exe -m pip install -r requirements.txt

# Configure environment variables
copy .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

### Manual start

```bash
venv\Scripts\python.exe app.py
```
Open `http://127.0.0.1:5000/` in your browser. Test health status at
`http://127.0.0.1:5000/health`.

---

## 📡 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server status and RAG engine warm-up status |
| `POST` | `/ask` | Submit question with optional madhab selection |
| `GET` | `/whatsapp` | Meta Webhook verification handshake |
| `POST` | `/whatsapp` | Inbound WhatsApp message handler |

---

## 📄 License

MIT License. Designed and engineered by [Hamza Nadeem](https://github.com/hamza-n-builds).
