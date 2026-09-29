# Islamic FiqhBot 🕌

An applied AI, multilingual Islamic guidance assistant engineered around a hybrid **BM25 + MiniLM** retrieval-augmented generation (RAG) pipeline with **Gemini synthesis**, local authentic primary sources (Qur'an, Hadith, curated fiqh rulings across schools of thought), and WhatsApp integration.

---

## 🌟 Overview

* **Hybrid RAG Retrieval**: Combines keyword-level precision (BM25) with semantic embeddings (MiniLM) to retrieve authentic sources with high precision.
* **School of Thought (Madhab) Specificity**: Answers grounded according to specific schools of jurisprudence (Hanafi, Shafi'i, Maliki, Hanbali) or comparative consensus.
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
    ├── script.js           # Chat client state & streaming
    └── config.js           # API connection configuration
```

---

## 🚀 Quick Start

### 1. Backend Setup

```bash
cd backend

# Create & activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # Linux/macOS: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

### 2. Run Backend

```bash
python app.py
```
Backend starts on `http://localhost:5000`. Test health status at `http://localhost:5000/health`.

### 3. Run Frontend

Open `frontend/index.html` in your browser or serve via any static HTTP server.

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
