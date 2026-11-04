# Islamic Fiqh Chatbot — Backend

Flask backend that wraps the BM25 + MiniLM hybrid RAG pipeline and serves both
the web frontend and a WhatsApp channel from one place. Answers are grounded in
the local datasets and generated with Gemini under a strict, citation-only prompt.

## Layout
```
backend/
  app.py            Flask server: /ask, /health, /whatsapp
  rag_engine.py     the RAG pipeline (loads data, hybrid retrieval, Gemini)
  requirements.txt
  .env.example
  data/             fiqh + quran + hadith + topic_examples
  models/           (optional) islamic_minilm/  fine-tuned embedder
```

## Setup
```bash
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env and add your GEMINI_API_KEY
```

Drop the two large datasets into `data/` if they aren't already there:
`quran_trilingual_clean.json` and `sahih_bukhari_muslim.json`.
(The expanded YAMLs are included.)

Optional: to use the fine-tuned embedder, unzip `islamic_minilm/` into
`backend/models/` (or set `MINILM_DIR`). Without it, the base MiniLM is used.

## Run
On Windows, use `../start_fiqhbot.cmd` for the normal local workflow. It opens
the interface on an available loopback port after the RAG engine is ready.

The launcher checks for a runnable 64-bit Python 3.11, preserves a broken virtual
environment as `venv.backup-*`, and installs/checks dependencies in a fresh `venv`
when needed. Set `FIQHBOT_PYTHON` to select a Python executable explicitly.
Use `../start_fiqhbot.cmd --setup-only` for dependency setup, or `--check` for an
offline runtime/import check. Neither option starts the server or calls Gemini.
See the project README for PowerShell examples and retry behavior.

For a manual fixed-port start:
```bash
python app.py          # serves on http://localhost:5000
```
The first start builds and caches embeddings. Later starts load the cache.
`/health` reports `engine_ready: true` when warm.

## Endpoints
- `GET /health` → `{ status, engine_ready }`
- `POST /ask` → body `{ "question": "...", "madhab": "Hanafi" }`
  returns `{ ok, mode, answer, confidence_percent, confidence_label, consensus, sources }`
- `GET /whatsapp` → Meta webhook verification
- `POST /whatsapp` → Meta Cloud API inbound messages

### Test /ask
```bash
curl -s http://localhost:5000/ask -H "Content-Type: application/json" \
  -d '{"question":"Can I combine Zuhr and Asr while travelling?","madhab":"Hanafi"}' | python -m json.tool
```

## WhatsApp (free for customer-initiated messages)
1. Create a Meta app → add WhatsApp → get a test number, `WA_PHONE_NUMBER_ID`, and a token.
2. Expose the server publicly (e.g. `ngrok http 5000`).
3. In the Meta dashboard set the webhook callback URL to
   `https://<your-tunnel>/whatsapp` and the verify token to `WA_VERIFY_TOKEN`.
4. Subscribe to the `messages` field. Message the test number; replies are free
   (service conversations within the 24-hour window).

Voice notes are acknowledged but not yet transcribed — STT (Whisper) and TTS
(edge-tts) are added in the voice step.

## Notes
- The frontend should POST to `/ask` instead of calling Gemini directly; the
  Gemini key now lives only here, server-side.
- Topics tagged `scholar_review: pending` are surfaced in `sources.fiqh[].scholar_review`
  so the UI can show a "pending scholarly review" badge if desired.
