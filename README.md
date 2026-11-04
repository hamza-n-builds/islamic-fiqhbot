# Islamic FiqhBot 🕌

An applied AI, multilingual Islamic guidance assistant engineered around a hybrid **BM25 + MiniLM** retrieval-augmented generation (RAG) pipeline with **Gemini synthesis**, local authentic primary sources (Qur'an, Hadith, curated fiqh rulings across schools of thought), and WhatsApp integration.

---

## 🌟 Overview

* **Hybrid RAG Retrieval**: Combines keyword-level precision (BM25) with semantic embeddings (MiniLM) to retrieve authentic sources with high precision.
* **School of Thought (Madhab) Specificity**: Answers grounded according to the three schools currently present in the dataset (Hanafi, Shafi'i, Maliki) or general guidance.
* **Citation-Only Synthesis**: Strict prompt grounding with confidence scores and source attribution.
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
needed. Before starting, copy `backend/.env.example` to `backend/.env` and put
your own `GEMINI_API_KEY` there. Python 3.11 and an internet connection are
required. The `.env` file stays on this computer and is ignored by Git.

For local use, always open the page launched by `start_fiqhbot.cmd` rather than
double-clicking `frontend/index.html`.

The WhatsApp sidebar shortcut is shown only if `WA_PUBLIC_NUMBER` is configured
in `backend/.env`; a placeholder number is never shown.

The fiqh dataset includes topics with pending or unspecified scholar review.
Treat generated guidance as informational and verify important rulings with a
qualified scholar.

### Manual setup (optional)

```bash
cd backend

# Create a virtual environment
python -m venv venv

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
