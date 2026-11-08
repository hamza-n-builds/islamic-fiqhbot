# -*- coding: utf-8 -*-
"""
rag_engine.py — Islamic Fiqh RAG pipeline (refactored from the Colab notebook).

Loads the datasets once, builds BM25 + MiniLM hybrid indexes, and exposes a
single clean entry point:  answer_question(query, madhhab) -> dict

The dict is JSON-serialisable and shared by BOTH the web frontend (/ask) and
the WhatsApp webhook, so the two channels always behave identically.
"""
import os, re, time, json, string, hashlib, tempfile, math
import yaml
import numpy as np
from citation_guard import CitationError, ResponseReceipts, validate_citations
from source_records import load_hadith_records, normalize_hadith_source
from response_status import REVIEW_INSTRUCTION, REVIEW_SCOPE, validate_unreviewed_answer
from school_response import (SCHOOLS, SCHEMA as SCHOOL_SCHEMA, MODE as SCHOOL_MODE, NOTICES,
                             parse_school_output, validate_school_wording, flatten_sections, split_sections)

_response_receipts = ResponseReceipts()

# ---------------------------------------------------------------- config
HERE        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.environ.get("DATA_DIR", os.path.join(HERE, "data"))
FIQH_FILE   = os.environ.get("FIQH_FILE",   os.path.join(DATA_DIR, "fiqh_topics_complete_expanded.yaml"))
QURAN_FILE  = os.environ.get("QURAN_FILE",  os.path.join(DATA_DIR, "quran_trilingual_clean.json"))
HADITH_FILE = os.environ.get("HADITH_FILE", os.path.join(DATA_DIR, "sahih_bukhari_muslim.json"))
# Optional supplementary hadith from other authentic collections (Tirmidhi,
# Nasa'i, Abu Dawud) that aren't in the main Bukhari/Muslim corpus. Verified
# and added by the team from Sunnah.com. Loaded if present; ignored if absent.
OTHER_HADITH_FILE = os.environ.get("OTHER_HADITH_FILE", os.path.join(DATA_DIR, "other_hadith.json"))
HADITH_REGISTRY_FILE = os.environ.get("HADITH_REGISTRY_FILE", os.path.join(DATA_DIR, "hadith_identity_registry.json"))

EXAMPLE_FILE= os.environ.get("EXAMPLE_FILE",os.path.join(DATA_DIR, "topic_examples_expanded.yaml"))

# Fine-tuned model folder (from finetune_islamic_minilm.ipynb). Falls back to
# the base MiniLM if the folder is not present — so the server always runs.
FINETUNED_DIR = os.environ.get("MINILM_DIR", os.path.join(HERE, "models", "islamic_minilm"))
# Multilingual base so Urdu/Roman-Urdu/Arabic queries embed meaningfully even if
# the fine-tuned folder is absent. (all-MiniLM-L6-v2 is English-only and mangles
# non-English input, which caused wrong retrieval + wrong-language answers.)
BASE_MODEL    = os.environ.get("BASE_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

ALPHA       = float(os.environ.get("HYBRID_ALPHA", "0.45"))   # BM25 weight; (1-alpha) = semantic
# Minimum similarity for a NON-curated (semantic-search) citation to be shown.
# Curated references from the dataset always pass; only guessed ones are gated.
HADITH_MIN_SCORE = float(os.environ.get("HADITH_MIN_SCORE", "0.50"))
QURAN_MIN_SCORE  = float(os.environ.get("QURAN_MIN_SCORE", "0.45"))
# Hadith citations are only trustworthy when they come from curated, verified
# references. A semantic search over ~15k hadiths can return a same-book-but-WRONG
# hadith (verified case: Bukhari #137 is about passing wind, not bleeding), which
# is unacceptable for a religious citation. So the search fallback is OFF by default.
ENABLE_HADITH_SEARCH = os.environ.get("ENABLE_HADITH_SEARCH", "false").lower() == "true"
# General-knowledge mode grounds its citations in the datasets too (real verses /
# hadith only). These gate how relevant a retrieved reference must be to be offered.
GENERAL_QURAN_MIN  = float(os.environ.get("GENERAL_QURAN_MIN", "0.35"))
GENERAL_HADITH_MIN = float(os.environ.get("GENERAL_HADITH_MIN", "0.45"))
# Below this topic-classifier score, treat the question as general (not a curated
# fiqh edge-case). Raised to 0.65 so weak/ambiguous matches (e.g. Roman-Urdu
# phrasings the classifier isn't sure about) fall to the general path and answer
# correctly, instead of grasping at the wrong curated topic with false confidence.
# Lower it if genuine fiqh questions start slipping into general mode.
GENERAL_IF_BELOW   = float(os.environ.get("GENERAL_IF_BELOW", "0.65"))
# In general-knowledge answers, a matched topic's VERIFIED references become
# citation candidates once its score clears this gate. Lower = more general
# answers can offer a locally resolvable citation candidate. Membership validation
# below does not establish relevance or scholarly correctness.
GENERAL_CITE_MIN   = float(os.environ.get("GENERAL_CITE_MIN", "0.35"))
# Legacy configuration name retained as a PRIVATE abstention-policy cutoff.
# Its heuristic units are not measured answer accuracy and are never returned.
# Consensus flags cannot boost this gate. Higher existing cutoffs stay restrictive.
LOW_CONFIDENCE_PCT = int(os.environ.get("LOW_CONFIDENCE_PCT", "50"))
ISLAMQA_URL        = os.environ.get("ISLAMQA_URL", "https://islamqa.info/en")
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]

# Lazy-initialised globals (filled by init())
_READY = False
fiqh_topics = quran_data = hadith_data = topic_examples = None
quran_lookup = hadith_lookup = None
bm25_fiqh = bm25_hadith = bm25_quran = None
fiqh_texts = hadith_texts = quran_texts = None
embedder = None
fiqh_embeddings = example_embeddings = None
example_topic_ids = None
stop_words = set()
_genai_client = None


# ---------------------------------------------------------------- text utils
def preprocess(text):
    """Lowercase, strip punctuation (keep Arabic), tokenise, drop stopwords."""
    from nltk.tokenize import word_tokenize
    text = (text or "").lower()
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    tokens = word_tokenize(text)
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def fiqh_topic_to_text(topic):
    parts = [
        topic.get("topic_name", ""),
        topic.get("description", ""),
        topic.get("topic_id", "").replace("_", " "),
    ]
    for _m, rd in (topic.get("rulings", {}) or {}).items():
        if isinstance(rd, dict):
            parts.append(rd.get("ruling", ""))
            parts.append(rd.get("explanation", ""))
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------- init
def init(verbose=True):
    """Load data + build indexes. Safe to call multiple times (idempotent)."""
    global _READY, fiqh_topics, quran_data, hadith_data, topic_examples
    global quran_lookup, hadith_lookup, bm25_fiqh, bm25_hadith, bm25_quran
    global fiqh_texts, hadith_texts, quran_texts, embedder
    global fiqh_embeddings, example_embeddings, example_topic_ids, stop_words
    if _READY:
        return

    import nltk
    local_nltk = os.path.join(HERE, ".cache", "nltk_data")
    if local_nltk not in nltk.data.path:
        nltk.data.path.insert(0, local_nltk)
    for pkg, resource in (("punkt", "tokenizers/punkt"),
                          ("punkt_tab", "tokenizers/punkt_tab"),
                          ("stopwords", "corpora/stopwords")):
        try:
            nltk.data.find(resource)
        except LookupError:
            if not nltk.download(pkg, download_dir=local_nltk, quiet=True):
                raise RuntimeError(f"NLTK resource {pkg} is missing and could not be downloaded")
    from nltk.corpus import stopwords
    stop_words = set(stopwords.words("english"))

    if verbose: print("Loading datasets...")
    with open(FIQH_FILE, encoding="utf-8") as f:
        fiqh_topics = yaml.safe_load(f)
    with open(QURAN_FILE, encoding="utf-8") as f:
        quran_data = json.load(f)
    source_corpus = load_hadith_records(HADITH_FILE, OTHER_HADITH_FILE, HADITH_REGISTRY_FILE)
    hadith_data = [record for record in source_corpus.records if record["generation_eligible"]]
    with open(EXAMPLE_FILE, encoding="utf-8") as f:
        topic_examples = yaml.safe_load(f)

    quran_lookup  = {(v["chapter"], v["ayah"]): v for v in quran_data}
    hadith_lookup = source_corpus.lookup
    if verbose:
        print(f"[rag] Loaded {len(source_corpus.records)} canonical identities ({len(hadith_data)} eligible for generation); legacy corpus remains preserved on disk.")

    from rank_bm25 import BM25Okapi
    if verbose: print("Building BM25 indexes...")
    fiqh_texts   = [fiqh_topic_to_text(t) for t in fiqh_topics]
    bm25_fiqh    = BM25Okapi([preprocess(t) for t in fiqh_texts])
    hadith_texts = [h.get("text_en", "") for h in hadith_data]
    bm25_hadith  = BM25Okapi([preprocess(t) for t in hadith_texts]) if hadith_texts else None
    quran_texts  = [v.get("english", "") for v in quran_data]
    bm25_quran   = BM25Okapi([preprocess(t) for t in quran_texts])

    from sentence_transformers import SentenceTransformer
    if os.path.isdir(FINETUNED_DIR):
        if verbose: print(f"Loading fine-tuned MiniLM from {FINETUNED_DIR}")
        embedder = SentenceTransformer(FINETUNED_DIR, local_files_only=True)
    else:
        if verbose: print(f"Fine-tuned model not found — using base {BASE_MODEL}")
        embedder = SentenceTransformer(BASE_MODEL)

    ex_texts, example_topic_ids = [], []
    for tid, exs in topic_examples.items():
        for ex in exs:
            ex_texts.append(ex); example_topic_ids.append(tid)

    # These texts and model weights rarely change. Cache their embeddings so
    # later launches do not encode thousands of examples again.
    model_stamp = BASE_MODEL
    if os.path.isdir(FINETUNED_DIR):
        model_stamp = []
        for root, dirs, files in os.walk(FINETUNED_DIR):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                stat = os.stat(path)
                model_stamp.append((os.path.relpath(path, FINETUNED_DIR), stat.st_size, stat.st_mtime_ns))
    cache_input = json.dumps((model_stamp, fiqh_texts, ex_texts), ensure_ascii=False).encode("utf-8")
    cache_key = hashlib.sha256(cache_input).hexdigest()[:20]
    cache_dir = os.path.join(HERE, ".cache")
    cache_path = os.path.join(cache_dir, f"embeddings-{cache_key}.npz")
    try:
        import torch
        with np.load(cache_path, allow_pickle=False) as cached:
            if len(cached["fiqh"]) != len(fiqh_texts) or len(cached["examples"]) != len(ex_texts):
                raise ValueError("Embedding cache does not match the datasets")
            fiqh_embeddings = torch.from_numpy(cached["fiqh"].copy()).to(embedder.device)
            example_embeddings = torch.from_numpy(cached["examples"].copy()).to(embedder.device)
        if verbose: print("Loaded cached fiqh and example embeddings.")
    except (OSError, ValueError, KeyError):
        if verbose: print("Embedding fiqh topics + topic examples...")
        fiqh_embeddings = embedder.encode(fiqh_texts, convert_to_tensor=True, show_progress_bar=False)
        example_embeddings = embedder.encode(ex_texts, convert_to_tensor=True, show_progress_bar=False)
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".npz", delete=False) as temp:
                temp_path = temp.name
            np.savez(temp_path, fiqh=fiqh_embeddings.cpu().numpy(),
                     examples=example_embeddings.cpu().numpy())
            os.replace(temp_path, cache_path)
        except OSError as error:
            if verbose: print(f"Embedding cache could not be saved: {error}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)

    _READY = True
    if verbose:
        print(f"Engine ready: {len(fiqh_topics)} topics, {len(quran_data):,} ayahs, "
              f"{len(hadith_data):,} hadiths, {len(ex_texts):,} examples.")


# ---------------------------------------------------------------- retrieval
def classify_topic(query, top_n=3):
    from sentence_transformers import util
    q = embedder.encode(query, convert_to_tensor=True)
    sims = util.cos_sim(q, example_embeddings)[0].cpu().numpy()
    scores = {}
    for i, tid in enumerate(example_topic_ids):
        if tid not in scores or sims[i] > scores[tid]:
            scores[tid] = float(sims[i])
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


def retrieve_fiqh_ruling(query, madhhab=None, top_k=3, alpha=ALPHA):
    from sentence_transformers import util
    tokens = preprocess(query)
    bm = bm25_fiqh.get_scores(tokens)
    bm_max = bm.max()
    bm_norm = bm / bm_max if bm_max > 0 else bm
    q = embedder.encode(query, convert_to_tensor=True)
    sem = util.cos_sim(q, fiqh_embeddings)[0].cpu().numpy()
    hybrid = alpha * bm_norm + (1 - alpha) * sem
    ranked = sorted(enumerate(hybrid), key=lambda x: x[1], reverse=True)[:top_k]

    out = []
    for idx, score in ranked:
        topic = fiqh_topics[idx]
        rulings = topic.get("rulings", {}) or {}
        mk = madhhab.lower() if madhhab else None
        if mk == "shafi'i":
            mk = "shafi"
        ruling = ({mk: rulings[mk]} if mk in rulings else {}) if mk else rulings
        out.append({
            "type": "fiqh",
            "topic_id": topic["topic_id"],
            "topic_name": topic["topic_name"],
            "description": topic.get("description", ""),
            "ruling": ruling,
            "consensus": topic.get("consensus", False),
            "references": topic.get("references", {}) or {},
            "scholar_review": topic.get("scholar_review"),  # surfaced for transparency
            "score": float(score),
        })
    return out


def _fiqh_entry_by_id(topic_id, madhhab=None, score=0.0):
    """Build a fiqh-result dict (same shape as retrieve_fiqh_ruling) for one topic."""
    for t in fiqh_topics:
        if t["topic_id"] == topic_id:
            rulings = t.get("rulings", {}) or {}
            mk = madhhab.lower() if madhhab else None
            if mk == "shafi'i":
                mk = "shafi"
            ruling = ({mk: rulings[mk]} if mk in rulings else {}) if mk else rulings
            return {
                "type": "fiqh", "topic_id": t["topic_id"], "topic_name": t["topic_name"],
                "description": t.get("description", ""), "ruling": ruling,
                "consensus": t.get("consensus", False),
                "references": t.get("references", {}) or {},
                "scholar_review": t.get("scholar_review"), "score": float(score),
            }
    return None


def retrieve_hadith(query, top_k=3, bm25_candidates=50, alpha=ALPHA):
    if not hadith_data or bm25_hadith is None:
        return []
    from sentence_transformers import util
    tokens = preprocess(query)
    bm = bm25_hadith.get_scores(tokens)
    top = np.argsort(bm)[::-1][:bm25_candidates]
    bm_max = bm[top[0]] if len(top) else 1
    cand = [hadith_texts[i] for i in top]
    cemb = embedder.encode(cand, convert_to_tensor=True)
    q = embedder.encode(query, convert_to_tensor=True)
    sem = util.cos_sim(q, cemb)[0].cpu().numpy()
    bm_norm = np.array([bm[i] / bm_max if bm_max else 0 for i in top])
    hybrid = alpha * bm_norm + (1 - alpha) * sem
    local = np.argsort(hybrid)[::-1][:top_k]
    out = []
    for li in local:
        h = hadith_data[top[li]]
        out.append({
            "type": "hadith", "source": h["source"], "hadith_no": h["hadith_no"],
            "chapter": h.get("chapter", ""), "text_en": h.get("text_en", ""),
            "text_ar": h.get("text_ar", ""), "score": float(hybrid[li]),
        })
    return out


def retrieve_quran(query, fiqh_refs=None, top_k=3, bm25_candidates=30, alpha=ALPHA):
    from sentence_transformers import util
    direct = []
    if fiqh_refs:
        for ref in fiqh_refs:
            ch, ay = ref.get("chapter"), ref.get("ayah")
            v = quran_lookup.get((ch, ay)) if (ch and ay) else None
            if v:
                direct.append({
                    "type": "quran", "chapter": ch, "ayah": ay,
                    "surah_name_en": v.get("surah_name_en", ""),
                    "arabic": v.get("arabic", ""), "english": v.get("english", ""),
                    "urdu": v.get("urdu", ""), "score": 1.0,
                })
    if direct:
        return direct[:top_k]

    tokens = preprocess(query)
    bm = bm25_quran.get_scores(tokens)
    top = np.argsort(bm)[::-1][:bm25_candidates]
    bm_max = bm[top[0]] if len(top) else 1
    cand = [quran_texts[i] for i in top]
    cemb = embedder.encode(cand, convert_to_tensor=True)
    q = embedder.encode(query, convert_to_tensor=True)
    sem = util.cos_sim(q, cemb)[0].cpu().numpy()
    bm_norm = np.array([bm[i] / bm_max if bm_max else 0 for i in top])
    hybrid = alpha * bm_norm + (1 - alpha) * sem
    local = np.argsort(hybrid)[::-1][:top_k]
    out = []
    for li in local:
        v = quran_data[top[li]]
        out.append({
            "type": "quran", "chapter": v["chapter"], "ayah": v["ayah"],
            "surah_name_en": v.get("surah_name_en", ""), "arabic": v.get("arabic", ""),
            "english": v.get("english", ""), "urdu": v.get("urdu", ""),
            "score": float(hybrid[li]),
        })
    return out


def _topic_match_is_eligible(topic_score):
    """Retrieval similarity is a routing threshold, never a probability of truth."""
    return (isinstance(topic_score, (int, float)) and not isinstance(topic_score, bool)
            and math.isfinite(topic_score) and 0 <= topic_score <= 1
            and topic_score >= max(GENERAL_IF_BELOW, GENERAL_CITE_MIN))


def _retrieval_policy_allows(topic_score, hadith, quran):
    """Retain stricter legacy abstention settings without publishing a score.

    This policy is uncalibrated. A passing result only permits a generation
    attempt; citations, claim support and scholarly approval remain separate.
    Removing the old consensus bonus can only tighten the previous fiqh gate.
    The same minimum topic-match threshold now also protects the general path.
    """
    if not _topic_match_is_eligible(topic_score):
        return False
    policy = 0.62 if topic_score >= 0.70 else 0.50
    policy += 0.08 * bool(quran) + 0.08 * bool(hadith)
    return int(25 + round(policy, 3) * 74) >= LOW_CONFIDENCE_PCT


# ---------------------------------------------------------------- generation
def _client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        if not GEMINI_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _genai_client = genai.Client(api_key=GEMINI_KEY)
    return _genai_client


def gemini_generate(prompt):
    client = _client()
    last = None
    for model in GEMINI_MODELS:
        try:
            r = client.models.generate_content(model=model, contents=prompt)
            return r.text.strip()
        except Exception as e:
            err = str(e); last = e
            if "503" in err or "UNAVAILABLE" in err:
                time.sleep(2); continue
            if "429" in err or "QUOTA" in err.upper():
                continue
            if "404" in err or "NOT_FOUND" in err.upper():
                continue
            raise
    raise RuntimeError(f"All Gemini models unavailable: {last}")


def build_rag_prompt(query, madhhab, fiqh, hadith, quran, target_language=None):
    parts = []
    if fiqh:
        parts.append("=== FIQH RULINGS FROM KNOWLEDGE BASE ===")
        for r in fiqh:
            parts.append(f'\n[{r["topic_name"]}] Topic ID: {r["topic_id"]}')
            parts.append(f'Description: {r["description"]}')
            parts.append('Scholarly review: not completed; dataset notes only.')
            for mn, rd in r["ruling"].items():
                label = "Shafi'i" if mn == "shafi" else mn.capitalize()
                parts.append(f'  [{label}] Dataset ruling: {rd.get("ruling","")}')
                parts.append(f'  Explanation: {rd.get("explanation","")}')
    if quran:
        parts.append("\n=== QURAN REFERENCES ===")
        for v in quran:
            parts.append(f'\n[Quran {v["chapter"]}:{v["ayah"]}] Surah {v["surah_name_en"]}')
            parts.append(f'Arabic: {v["arabic"]}')
            parts.append(f'English: {v["english"]}')
    if hadith:
        with_text = [h for h in hadith if h.get("text_en")]
        if with_text:
            parts.append("\n=== HADITH REFERENCES ===")
            for h in with_text:
                t = h["text_en"][:600] + "..." if len(h["text_en"]) > 600 else h["text_en"]
                parts.append(f'\n[{h["source"]} #{h["hadith_no"]}] Chapter: {h["chapter"]}')
                parts.append(t)
    context = "\n".join(parts)

    madhhab_instruction = ""
    if madhhab and madhhab != "General":
        madhhab_instruction = (f"The user follows the **{madhhab}** school of thought. Focus your answer "
                               f"on the {madhhab} ruling but mention other schools if they differ significantly.")

    lang_directive = ""
    lang_reminder = ""
    if target_language:
        lang_directive = (f"### OUTPUT LANGUAGE (HIGHEST PRIORITY) ###\n"
                          f"The user wrote their question in {target_language}. "
                          f"You MUST write your ENTIRE reply in {target_language}, and in NO other language. "
                          f"This overrides everything else. The reference material below may be in a different "
                          f"language \u2014 ignore its language and still answer in {target_language}. "
                          f"Only bracketed citations like [Quran 4:101] or [Sahih Bukhari #1] stay in Latin letters. "
                          f"Never reply in Hindi or Devanagari. Never say you cannot write a language \u2014 just write it.\n")
        lang_reminder = (f"\n\nFINAL REMINDER: Your entire answer above must be written in {target_language} only "
                         f"(citations in brackets excepted). If any part is in another language, rewrite it in {target_language}.")

    return f"""{lang_directive}You are an Islamic knowledge assistant providing accurate, respectful Islamic guidance.

STRICT RULES YOU MUST FOLLOW:
1. Answer ONLY using the information in the KNOWLEDGE BASE CONTEXT below.
2. Do NOT add any information from outside the provided context.
3. Citations:
   - Cite the FIQH TOPIC name ONCE, the first time you introduce the ruling, e.g. [Combining Prayers During Travel]. Do NOT repeat the same topic tag again in later sentences.
   - Cite Quran verses every time you use them: [Quran 4:101]
   - Cite Hadiths every time you use them: [Sahih Muslim #705] or [Sahih Bukhari #1]
   - Never place the same topic tag in two consecutive sentences.
4. After the first topic citation, support further statements with Quran/Hadith tags rather than repeating the topic name.
5. If the context does not answer the question, respond exactly: "This requires consultation with a qualified scholar." (translated into {target_language or 'the user language'}).
6. Do NOT issue personal fatwas or rulings beyond what the sources state.
7. If scholars disagree (ikhtilaf), clearly state the different positions with their citations.
8. Maintain a respectful, neutral, scholarly tone.
9. Use only the exact citation tags supplied in the context. Do not add URLs,
   unbracketed reference numbers, or other bracketed labels. Keep the reply under 20,000 characters.
10. {REVIEW_INSTRUCTION}
{madhhab_instruction}

--- KNOWLEDGE BASE CONTEXT ---
{context}
--- END OF CONTEXT ---

User Question: {query}
Remember: cite the fiqh topic only once (at first mention), then use Quran/Hadith citations. No repeated topic tags.{lang_reminder}
Answer:"""


# ---------------------------------------------------------------- public API
def _collapse_topic_tags(text):
    """
    Keep each fiqh-TOPIC tag only the first time it appears; drop later repeats.
    Quran tags ([Quran ...]) and Hadith tags (anything containing '#') are NEVER
    touched — those are real sources and are allowed to repeat.
    """
    if not text:
        return text
    seen = set()
    def repl(m):
        inner = m.group(1).strip()
        if inner.lower().startswith("quran") or "#" in inner:
            return m.group(0)          # scripture citation — always keep
        key = inner.lower()
        if key in seen:
            return ""                  # duplicate topic tag — remove
        seen.add(key)
        return m.group(0)
    out = re.sub(r"\[([^\]]+)\]", repl, text)
    out = re.sub(r"[ \t]{2,}", " ", out)        # tidy double spaces
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)   # tidy space before punctuation
    return out.strip()


def _is_refusal(text):
    """True when the model returned only the scholar-referral line (couldn't answer)."""
    if not text:
        return True
    t = text.strip().lower()
    return "requires consultation with a qualified scholar" in t and len(text) < 300


def general_generate(query, madhhab=None):
    """Compatibility wrapper; the old ungrounded generation shortcut is closed."""
    return answer_question(query, madhhab)["answer"]


def _validated_context(fiqh, hadith, quran, madhhab=None):
    """Resolve candidate IDs against local records; require text actually sent to the model.

    Record presence is not a scholarly approval or proof of relevance.
    """
    clean_fiqh, clean_hadith, clean_quran = [], [], []
    def has_text(value):
        return isinstance(value, str) and bool(value.strip())
    seen = set()
    for candidate in fiqh:
        record = _fiqh_entry_by_id(candidate.get("topic_id"), madhhab, candidate.get("score", 0.0))
        if (record and record["topic_id"] not in seen and has_text(record.get("topic_name"))
                and any(isinstance(r, dict) and (has_text(r.get("ruling")) or has_text(r.get("explanation")))
                        for r in record.get("ruling", {}).values())):
            seen.add(record["topic_id"])
            clean_fiqh.append(record)
    seen = set()
    for candidate in quran:
        identity = (candidate.get("chapter"), candidate.get("ayah"))
        record = (quran_lookup or {}).get(identity)
        if record and identity not in seen and has_text(record.get("english")):
            seen.add(identity)
            clean_quran.append({**record, "type": "quran", "score": candidate.get("score", 0.0)})
    seen = set()
    for candidate in hadith:
        identity = (normalize_hadith_source(candidate.get("source", "")), str(candidate.get("hadith_no", "")))
        record = (hadith_lookup or {}).get(identity)
        if (record and identity not in seen and has_text(record.get("text_en"))
                and record.get("generation_eligible", True)):
            seen.add(identity)
            clean_hadith.append({**record, "type": "hadith", "score": candidate.get("score", 0.0)})
    return clean_fiqh, clean_hadith, clean_quran


def _context_tags(fiqh, hadith, quran):
    return ({f'[{r["topic_name"]}]' for r in fiqh}
            | {f'[{h["source"]} #{h["hadith_no"]}]' for h in hadith}
            | {f'[Quran {v["chapter"]}:{v["ayah"]}]' for v in quran})


def _cited_sources(tags, fiqh, hadith, quran):
    return {
        "fiqh": [{"topic_id": r["topic_id"], "topic_name": r["topic_name"],
                  "consensus": None, "scholar_review": r.get("scholar_review")}
                 for r in fiqh if f'[{r["topic_name"]}]' in tags],
        "quran": [{"ref": f'{v["chapter"]}:{v["ayah"]}', "surah": v.get("surah_name_en", ""),
                   "arabic": v.get("arabic", ""), "english": v.get("english", ""), "urdu": v.get("urdu", "")}
                  for v in quran if f'[Quran {v["chapter"]}:{v["ayah"]}]' in tags],
        "hadith": [{"ref": f'{h["source"]} #{h["hadith_no"]}', "chapter": h.get("chapter", ""),
                    "text_ar": h.get("text_ar", ""), "text_en": h.get("text_en", ""),
                    "reference_url": h.get("reference_url"), "source_identity": h.get("source_identity"),
                    "reported_grade": h.get("reported_grade")}
                   for h in hadith if f'[{h["source"]} #{h["hadith_no"]}]' in tags],
    }


def _source_validation_failure(query, reason):
    language = _lang_key(query)
    if "Roman Urdu" in (_requested_target_language(query) or ""):
        language = "roman"
    if reason == "unverified_history":
        messages = {
            "en": "I couldn't verify the earlier answer. Please repeat your original question so I can check its sources again.",
            "roman": "Pehle jawab ki tasdeeq nahi ho saki. Baraye meharbani asal sawal dobara poochhein taake main us ke sources dobara check kar sakoon.",
        }
    else:
        messages = {
            "en": "I couldn't validate a source-backed answer to this question, so I won't provide a ruling. Please clarify your question or consult a qualified scholar.",
            "roman": "Is sawal ke liye sources ke saath jawab ki tasdeeq nahi ho saki, is liye main hukm nahi doon ga. Baraye meharbani sawal wazeh karein ya kisi mustanad aalim se rujoo karein.",
        }
    return {"ok": True, "mode": "low_confidence", "out_of_scope": False,
            "answer": messages.get(language) or _msg("referral", query, url=ISLAMQA_URL),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
            "citation_validation": {"status": "rejected", "reason": reason}}


def _context_fingerprint(tags, fiqh, hadith, quran):
    material = []
    groups = ((fiqh, lambda r: f'[{r["topic_name"]}]'),
              (hadith, lambda h: f'[{h["source"]} #{h["hadith_no"]}]'),
              (quran, lambda v: f'[Quran {v["chapter"]}:{v["ayah"]}]'))
    for records, tag_for in groups:
        for record in records:
            if tag_for(record) in tags:
                material.append({key: value for key, value in record.items() if key not in {"score", "type"}})
    encoded = json.dumps(sorted(material, key=lambda record: json.dumps(record, sort_keys=True)),
                         sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _with_receipt(result, tags, fiqh, hadith, quran):
    result["answer_receipt"] = _response_receipts.issue(
        result["answer"], tags, _context_fingerprint(tags, fiqh, hadith, quran))
    result["citation_validation"] = {"status": "passed", "scope": "provided_reference_membership"}
    # Compatibility fields stay null; neither retrieval nor a dataset flag is
    # measured answer accuracy. A bare topic review flag cannot approve an answer.
    result.update(confidence=None, confidence_percent=None, confidence_label=None,
                  confidence_reason=None, consensus=None)
    result["scholarly_review"] = {"status": "not_completed", "scope": REVIEW_SCOPE}
    return result


def build_general_prompt(query, madhhab, quran, hadith, target_language=None):
    parts = []
    if quran:
        parts.append("=== QURAN VERSES (you may cite these) ===")
        for v in quran:
            parts.append(f'[Quran {v["chapter"]}:{v["ayah"]}] Surah {v["surah_name_en"]}: {v["english"]}')
    if hadith:
        parts.append("\n=== HADITH (you may cite these) ===")
        for h in hadith:
            t = h["text_en"][:400] + ("..." if len(h["text_en"]) > 400 else "")
            parts.append(f'[{h["source"]} #{h["hadith_no"]}]: {t}')
    context = "\n".join(parts) if parts else "(no specific references were retrieved for this question)"
    m = f" The user follows the {madhhab} school of thought." if (madhhab and madhhab != "General") else ""
    lang_directive = ""
    lang_reminder = ""
    if target_language:
        lang_directive = (f"### OUTPUT LANGUAGE (HIGHEST PRIORITY) ###\n"
                          f"The user wrote in {target_language}. Write your ENTIRE reply in {target_language} and no other "
                          f"language. This overrides everything else. The references below may be in another language \u2014 "
                          f"ignore that and still answer in {target_language}. Only bracketed citations stay in Latin letters. "
                          f"Never reply in Hindi/Devanagari. Never claim you cannot write a language \u2014 just write it.\n\n")
        lang_reminder = (f"\nFINAL REMINDER: the entire answer must be in {target_language} only (bracketed citations excepted).")
    return f"""{lang_directive}You are a knowledgeable, careful Islamic assistant answering a general question.{m}
Give a clear, complete and helpful answer (a few sentences; use a short list if it fits).

CITATION RULES (critical):
- You MAY cite ONLY the references listed in the CONTEXT below, using their exact tags, e.g. [Quran 4:103] or [Sahih Bukhari #8].
- Where a listed reference supports part of your answer (for example, a verse commanding the establishment of prayer), DO cite it inline.
- If a listed reference is not relevant, simply don't cite it. NEVER invent or cite anything not in the CONTEXT.
- Answer ONLY from the actual text in CONTEXT. Do not add facts, counts, rulings or principles from memory.
- A source's existence does not mean it answers the question. If it does not support the requested answer, respond: "This requires consultation with a qualified scholar."
- Cite each substantive point with the exact supplied bracketed tag. Do not invent URLs, topic tags or unbracketed reference numbers.
- Do not extrapolate a new ruling from a broadly related passage. If CONTEXT is missing or insufficient, decline instead.
- Keep the answer under 20,000 characters.
- {REVIEW_INSTRUCTION}

--- CONTEXT (the only references you may cite) ---
{context}
--- END CONTEXT ---

Question: {query}
Answer:{lang_reminder}"""


def _curated_candidates(topic_id):
    """Locally resolvable references mapped to a curated topic, as candidates."""
    entry = _fiqh_entry_by_id(topic_id)
    if not entry:
        return [], []
    refs = entry.get("references", {}) or {}
    qcands = []
    for r in (refs.get("quran") or []):
        v = quran_lookup.get((r.get("chapter"), r.get("ayah")))
        if v:
            qcands.append({"type": "quran", "chapter": v["chapter"], "ayah": v["ayah"],
                           "surah_name_en": v.get("surah_name_en", ""), "arabic": v.get("arabic", ""),
                           "english": v.get("english", ""), "urdu": v.get("urdu", ""), "score": 1.0})
    hcands = []
    for r in (refs.get("hadith") or []):
        src, no = normalize_hadith_source(r.get("source", "")), r.get("hadith_no", "")
        h = hadith_lookup.get((src, str(no)))
        if h:
            hcands.append({"type": "hadith", "source": h["source"], "hadith_no": h["hadith_no"],
                           "chapter": h.get("chapter", ""), "text_en": h.get("text_en", ""),
                           "text_ar": h.get("text_ar", ""), "score": 1.0})
        # Missing references are skipped; present records still need text and
        # relevance checks. The lookup also includes the supplementary corpus.
    return qcands, hcands


def _is_ruling_request(query):
    """True when the question asks for a permissibility/fiqh RULING (halal/haram,
    'is it allowed', 'can men/women...', 'is it permissible') rather than a basic
    fact. Used to decide that, without any verified reference, we must refer the
    user to a scholar/IslamQA instead of extrapolating a novel ruling."""
    q = " " + re.sub(r"[^\w\s]", " ", query.lower()).strip() + " "
    ruling_markers = [
        "permissible", "permissable", "impermissible", "allowed", "allow ",
        "halal", "haram", "haraam", "forbidden", "prohibited", "sinful",
        "is it ok", "is it okay", "is it fine", "is it wrong", "is it a sin",
        "can i ", "can we ", "can men ", "can women ", "can a man ", "can a woman ",
        "can muslims", "am i allowed", "are we allowed", "may i ", "should i wear",
        "jaiz", "jayez", "gunah", "napak",
    ]
    return any(m in q for m in ruling_markers)


def _is_sensitive_question(query):
    """True for grave, contested, or highly personal matters that a small
    automated system must NOT rule on \u2014 e.g. violence, sexuality, apostasy,
    takfir, or explicit acts. These are ALWAYS referred to a qualified scholar
    regardless of any weak topic match, because a wrong or oversimplified answer
    here can cause real harm. This is a safety backstop, not a moral judgement."""
    q = " " + re.sub(r"[^\w\s]", " ", (query or "").lower()).strip() + " "
    sensitive = [
        # violence / harm to self or others (English)
        " murder", " kill ", " killing", " suicide", " terroris", " bomb", " jihad ",
        " behead", " stone to death", " honor kill", " honour kill", " violence",
        # sexuality / relationships (English)
        " gay", " lesbian", " homosexual", " lgbt", " transgender", " trans ",
        " zina", " adultery", " fornicat", " sex ", " sexual", " masturbat",
        # creed-critical / interpersonal grave matters (English)
        " apostasy", " apostate", " leave islam", " kafir", " takfir", " kill an apostate",
        " divorce my", " triple talaq", " abortion", " euthanasia",
        # Roman Urdu markers
        " qatal", " khudkushi", " khudkhushi", " samlaingik", " hum jinsi",
        " zina", " talaq", " isqat", " isqaat e haml", " murtad",
        # Urdu / Arabic script markers
        "\u0642\u062a\u0644",            # qatl (murder/killing)
        "\u062e\u0648\u062f\u06a9\u0634\u06cc",  # khudkushi (suicide)
        "\u0632\u0646\u0627",            # zina
        "\u0637\u0644\u0627\u0642",      # talaq (divorce)
        "\u0627\u0633\u0642\u0627\u0637",  # isqat (abortion)
        "\u0645\u0631\u062a\u062f",      # murtad (apostate)
        "\u0627\u0646\u062a\u062d\u0627\u0631",  # intihar (suicide, Arabic)
        "\u0634\u0630\u0648\u0630",      # shudhudh (homosexuality, Arabic)
    ]
    return any(m in q for m in sensitive)


def _general_result(query, madhhab=None, topic_id=None, topic_score=0.0):
    """Answer only from a matched topic's locally resolvable source records."""
    if not _topic_match_is_eligible(topic_score):
        return _low_confidence_result(query, madhhab)
    quran_cands, hadith_cands = [], []

    # A mapped reference still needs relevance and scholarly review separately.
    if topic_id and topic_score >= GENERAL_CITE_MIN:
        quran_cands, hadith_cands = _curated_candidates(topic_id)

    _, hadith_cands, quran_cands = _validated_context([], hadith_cands, quran_cands)
    allowed = _context_tags([], hadith_cands, quran_cands)
    if not allowed:
        return _source_validation_failure(query, "missing_source_context")

    if not _retrieval_policy_allows(topic_score, hadith_cands, quran_cands):
        return _low_confidence_result(query, madhhab)

    prompt = build_general_prompt(query, madhhab, quran_cands, hadith_cands,
                                  target_language=_detect_language(query))
    answer = gemini_generate(prompt)

    try:
        answer, tags = validate_citations(answer, allowed)
        validate_unreviewed_answer(answer)
    except CitationError as error:
        return _source_validation_failure(query, str(error))

    return _with_receipt({
        "ok": True, "mode": "general", "general_knowledge": True,
        "out_of_scope": False,
        "answer": answer,
        "consensus": None,
        "sources": _cited_sources(tags, [], hadith_cands, quran_cands),
    }, tags, [], hadith_cands, quran_cands)


def _lang_key(query):
    """Short language key for selecting fixed (non-LLM) messages: 'ur', 'ar',
    'roman', or 'en'. Mirrors _detect_language but returns a compact code."""
    tl = _detect_language(query)
    if "Urdu script" in tl: return "ur"
    if tl == "Arabic":      return "ar"
    if "Roman Urdu" in tl:  return "roman"
    return "en"


# Fixed messages, localized so a referral/greeting/rephrase reply always matches
# the user's language. Citations/URLs stay as-is (Latin) inside these.
_MSG = {
    "referral": {
        "en": ("I couldn't find a reliable, well-sourced answer to this question in my "
               "knowledge base, so I won't guess \u2014 and some matters genuinely depend on "
               "the person's situation and require a scholar's judgement.\n\n"
               "Please consult a qualified scholar, or look this up on a trusted resource such as {url}"),
        "ur": ("\u0645\u062c\u06be\u06d2 \u0627\u067e\u0646\u06d2 \u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0645\u06cc\u06ba \u0627\u0633 \u0633\u0648\u0627\u0644 \u06a9\u0627 \u0645\u0633\u062a\u0646\u062f \u0627\u0648\u0631 \u0642\u0627\u0628\u0644\u0650 \u0627\u0639\u062a\u0645\u0627\u062f \u062c\u0648\u0627\u0628 \u0646\u06c1\u06cc\u06ba \u0645\u0644\u0627\u060c \u0627\u0633 \u0644\u06cc\u06d2 \u0645\u06cc\u06ba \u0627\u0646\u062f\u0627\u0632\u06c1 \u0646\u06c1\u06cc\u06ba \u0644\u06af\u0627\u0624\u06ba \u06af\u0627\u06d4 \u06a9\u0686\u06be \u0645\u0633\u0627\u0626\u0644 \u0627\u0646\u0633\u0627\u0646 \u06a9\u06d2 \u062d\u0627\u0644\u0627\u062a \u067e\u0631 \u0645\u0646\u062d\u0635\u0631 \u06c1\u0648\u062a\u06d2 \u06c1\u06cc\u06ba \u0627\u0648\u0631 \u0627\u0646 \u06a9\u06d2 \u0644\u06cc\u06d2 \u0639\u0627\u0644\u0645 \u06a9\u06cc \u0631\u0627\u06c1\u0646\u0645\u0627\u0626\u06cc \u0636\u0631\u0648\u0631\u06cc \u06c1\u06d2\u06d4\n\n"
               "\u0628\u0631\u0627\u06c1\u0650 \u06a9\u0631\u0645 \u06a9\u0633\u06cc \u0645\u0633\u062a\u0646\u062f \u0639\u0627\u0644\u0650\u0645\u0650 \u062f\u06cc\u0646 \u0633\u06d2 \u0631\u062c\u0648\u0639 \u06a9\u0631\u06cc\u06ba\u060c \u06cc\u0627 {url} \u062c\u06cc\u0633\u06d2 \u0642\u0627\u0628\u0644\u0650 \u0627\u0639\u062a\u0645\u0627\u062f \u0630\u0631\u06cc\u0639\u06d2 \u067e\u0631 \u062f\u06cc\u06a9\u06be\u06cc\u06ba\u06d4"),
        "ar": ("\u0644\u0645 \u0623\u062c\u062f \u0625\u062c\u0627\u0628\u0629 \u0645\u0648\u062b\u0648\u0642\u0629 \u0648\u0645\u0633\u0646\u062f\u0629 \u0644\u0647\u0630\u0627 \u0627\u0644\u0633\u0624\u0627\u0644 \u0641\u064a \u0642\u0627\u0639\u062f\u0629 \u0645\u0639\u0631\u0641\u062a\u064a\u060c \u0648\u0644\u0646 \u0623\u062e\u0645\u0651\u0646\u060c \u0641\u0628\u0639\u0636 \u0627\u0644\u0645\u0633\u0627\u0626\u0644 \u062a\u0639\u062a\u0645\u062f \u0639\u0644\u0649 \u0638\u0631\u0648\u0641 \u0627\u0644\u0634\u062e\u0635 \u0648\u062a\u062a\u0637\u0644\u0628 \u0631\u0623\u064a \u0639\u0627\u0644\u0650\u0645.\n\n"
               "\u064a\u064f\u0631\u062c\u0649 \u0627\u0633\u062a\u0634\u0627\u0631\u0629 \u0639\u0627\u0644\u0650\u0645 \u0645\u0624\u0647\u0651\u0644\u060c \u0623\u0648 \u0627\u0644\u0631\u062c\u0648\u0639 \u0625\u0644\u0649 \u0645\u0635\u062f\u0631 \u0645\u0648\u062b\u0648\u0642 \u0645\u062b\u0644 {url}"),
        "roman": ("Mujhe apne knowledge base mein is sawal ka mustanad aur qabil-e-etimaad jawab nahi mila, "
                  "is liye main andaza nahi lagaunga. Kuch masail insaan ke halaat par munhasir hote hain "
                  "aur un ke liye aalim ki rahnumai zaroori hai.\n\n"
                  "Baraye meharbani kisi mustanad aalim se rujoo karein, ya {url} jaise qabil-e-etimaad zariye par dekhein."),
    },
    "greeting": {
        "en": "Wa Alaikum Assalam. How can I help you with your Islamic question today?",
        "ur": "\u0648\u0639\u0644\u06cc\u06a9\u0645 \u0627\u0644\u0633\u0644\u0627\u0645\u06d4 \u0645\u06cc\u06ba \u0622\u062c \u0622\u067e \u06a9\u06d2 \u06a9\u0633\u06cc \u062f\u06cc\u0646\u06cc \u0633\u0648\u0627\u0644 \u0645\u06cc\u06ba \u06a9\u06cc\u0633\u06d2 \u0645\u062f\u062f \u06a9\u0631 \u0633\u06a9\u062a\u0627 \u06c1\u0648\u06ba\u061f",
        "ar": "\u0648\u0639\u0644\u064a\u0643\u0645 \u0627\u0644\u0633\u0644\u0627\u0645. \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643 \u0641\u064a \u0633\u0624\u0627\u0644\u0643 \u0627\u0644\u0625\u0633\u0644\u0627\u0645\u064a \u0627\u0644\u064a\u0648\u0645\u061f",
        "roman": "Wa Alaikum Assalam. Main aaj aap ke kisi deeni sawal mein kaise madad kar sakta hoon?",
    },
    "gibberish": {
        "en": ("I couldn't find a clear Islamic question in that. Please type your question in a full "
               "sentence \u2014 for example, \u201cCan I combine prayers while travelling?\u201d \u2014 and I'll do my best to help."),
        "ur": ("\u0627\u0633 \u0645\u06cc\u06ba \u0645\u062c\u06be\u06d2 \u06a9\u0648\u0626\u06cc \u0648\u0627\u0636\u062d \u062f\u06cc\u0646\u06cc \u0633\u0648\u0627\u0644 \u0646\u06c1\u06cc\u06ba \u0645\u0644\u0627\u06d4 \u0628\u0631\u0627\u06c1\u0650 \u06a9\u0631\u0645 \u0627\u067e\u0646\u0627 \u0633\u0648\u0627\u0644 \u0645\u06a9\u0645\u0644 \u062c\u0645\u0644\u06d2 \u0645\u06cc\u06ba \u0644\u06a9\u06be\u06cc\u06ba \u2014 \u0645\u062b\u0644\u0627\u064b \u201c\u06a9\u06cc\u0627 \u0645\u06cc\u06ba \u0633\u0641\u0631 \u0645\u06cc\u06ba \u0646\u0645\u0627\u0632\u06cc\u06ba \u062c\u0645\u0639 \u06a9\u0631 \u0633\u06a9\u062a\u0627 \u06c1\u0648\u06ba\u061f\u201d \u2014 \u062a\u0627\u06a9\u06c1 \u0645\u06cc\u06ba \u0628\u06c1\u062a\u0631 \u0645\u062f\u062f \u06a9\u0631 \u0633\u06a9\u0648\u06ba\u06d4"),
        "ar": ("\u0644\u0645 \u0623\u062c\u062f \u0633\u0624\u0627\u0644\u0627\u064b \u0625\u0633\u0644\u0627\u0645\u064a\u0627\u064b \u0648\u0627\u0636\u062d\u0627\u064b \u0641\u064a \u0630\u0644\u0643. \u0627\u0644\u0631\u062c\u0627\u0621 \u0643\u062a\u0627\u0628\u0629 \u0633\u0624\u0627\u0644\u0643 \u0641\u064a \u062c\u0645\u0644\u0629 \u0643\u0627\u0645\u0644\u0629 \u2014 \u0645\u062b\u0644\u0627\u064b \u00ab\u0647\u0644 \u064a\u062c\u0648\u0632 \u0644\u064a \u0627\u0644\u062c\u0645\u0639 \u0628\u064a\u0646 \u0627\u0644\u0635\u0644\u0627\u062a\u064a\u0646 \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u0633\u0641\u0631\u061f\u00bb \u2014 \u0648\u0633\u0623\u0628\u0630\u0644 \u062c\u0647\u062f\u064a \u0644\u0644\u0645\u0633\u0627\u0639\u062f\u0629."),
        "roman": ("Is mein mujhe koi wazeh deeni sawal nahi mila. Baraye meharbani apna sawal mukammal "
                  "jumle mein likhein \u2014 masalan \u201cKya main safar mein namazein jama kar sakta hoon?\u201d \u2014 "
                  "taake main behtar madad kar sakoon."),
    },
    "ask_lang": {
        "en": "Sure \u2014 ask me your question and I'll answer in that language, in sha' Allah.",
        "ur": "\u0636\u0631\u0648\u0631\u06d4 \u0627\u067e\u0646\u0627 \u0633\u0648\u0627\u0644 \u067e\u0648\u0686\u06be\u06cc\u06ba\u060c \u0645\u06cc\u06ba \u0627\u0633\u06cc \u0632\u0628\u0627\u0646 \u0645\u06cc\u06ba \u062c\u0648\u0627\u0628 \u062f\u0648\u06ba \u06af\u0627\u060c \u0627\u0646 \u0634\u0627\u0621 \u0627\u0644\u0644\u06c1\u06d4",
        "ar": "\u062d\u0633\u0646\u0627\u064b \u2014 \u0627\u0637\u0631\u062d \u0633\u0624\u0627\u0644\u0643 \u0648\u0633\u0623\u062c\u064a\u0628\u064f\u0643 \u0628\u0647\u0630\u0647 \u0627\u0644\u0644\u063a\u0629\u060c \u0625\u0646 \u0634\u0627\u0621 \u0627\u0644\u0644\u0647.",
        "roman": "Zaroor \u2014 apna sawal poochein, main isi zabaan mein jawab doonga, in sha' Allah.",
    },
    "capability": {
        "en": ("You can ask me any Islamic Fiqh (jurisprudence) question \u2014 for example about "
               "prayer, fasting, zakat, hajj, marriage, or purification. I answer with verified "
               "Qur'an and Hadith citations across the Hanafi, Maliki, and Shafi'i schools. "
               "Go ahead and ask your question."),
        "ur": ("\u0622\u067e \u0645\u062c\u06be \u0633\u06d2 \u0641\u0642\u06c1 \u0633\u06d2 \u0645\u062a\u0639\u0644\u0642 \u06a9\u0648\u0626\u06cc \u0628\u06be\u06cc \u0633\u0648\u0627\u0644 \u067e\u0648\u0686\u06be \u0633\u06a9\u062a\u06d2 \u06c1\u06cc\u06ba \u2014 \u0645\u062b\u0644\u0627\u064b \u0646\u0645\u0627\u0632\u060c \u0631\u0648\u0632\u06c1\u060c \u0632\u06a9\u0648\u0629\u060c \u062d\u062c\u060c \u0646\u06a9\u0627\u062d \u06cc\u0627 \u0637\u06c1\u0627\u0631\u062a \u06a9\u06d2 \u0628\u0627\u0631\u06d2 \u0645\u06cc\u06ba\u06d4 \u0645\u06cc\u06ba \u062d\u0646\u0641\u06cc\u060c \u0645\u0627\u0644\u06a9\u06cc \u0627\u0648\u0631 \u0634\u0627\u0641\u0639\u06cc \u0645\u0633\u0627\u0644\u06a9 \u06a9\u06d2 \u0645\u0637\u0627\u0628\u0642 \u0645\u0633\u062a\u0646\u062f \u0642\u0631\u0622\u0646 \u0648 \u062d\u062f\u06cc\u062b \u06a9\u06d2 \u062d\u0648\u0627\u0644\u0648\u06ba \u06a9\u06d2 \u0633\u0627\u062a\u06be \u062c\u0648\u0627\u0628 \u062f\u06cc\u062a\u0627 \u06c1\u0648\u06ba\u06d4 \u0628\u0631\u0627\u06c1\u0650 \u06a9\u0631\u0645 \u0627\u067e\u0646\u0627 \u0633\u0648\u0627\u0644 \u067e\u0648\u0686\u06be\u06cc\u06ba\u06d4"),
        "ar": ("\u064a\u0645\u0643\u0646\u0643 \u0623\u0646 \u062a\u0633\u0623\u0644\u0646\u064a \u0623\u064a \u0633\u0624\u0627\u0644 \u0641\u064a \u0627\u0644\u0641\u0642\u0647 \u0627\u0644\u0625\u0633\u0644\u0627\u0645\u064a \u2014 \u0645\u062b\u0644\u0627\u064b \u0639\u0646 \u0627\u0644\u0635\u0644\u0627\u0629 \u0623\u0648 \u0627\u0644\u0635\u064a\u0627\u0645 \u0623\u0648 \u0627\u0644\u0632\u0643\u0627\u0629 \u0623\u0648 \u0627\u0644\u062d\u062c \u0623\u0648 \u0627\u0644\u0632\u0648\u0627\u062c \u0623\u0648 \u0627\u0644\u0637\u0647\u0627\u0631\u0629. \u0623\u064f\u062c\u064a\u0628 \u0628\u0627\u0644\u0627\u0633\u062a\u0646\u0627\u062f \u0625\u0644\u0649 \u0627\u0644\u0642\u0631\u0622\u0646 \u0648\u0627\u0644\u062d\u062f\u064a\u062b \u0627\u0644\u0645\u0648\u062b\u0651\u0642\u064a\u0646 \u0648\u0641\u0642\u064b\u0627 \u0644\u0644\u0645\u0630\u0627\u0647\u0628 \u0627\u0644\u062d\u0646\u0641\u064a \u0648\u0627\u0644\u0645\u0627\u0644\u0643\u064a \u0648\u0627\u0644\u0634\u0627\u0641\u0639\u064a. \u062a\u0641\u0636\u0651\u0644 \u0628\u0637\u0631\u062d \u0633\u0624\u0627\u0644\u0643."),
        "roman": ("Aap mujh se koi bhi Islamic Fiqh ka sawal pooch sakte hain \u2014 masalan namaz, roza, "
                  "zakat, hajj, nikah, ya taharat ke baare mein. Main Hanafi, Maliki aur Shafi'i "
                  "masalik ke mutabiq mustanad Qur'an aur Hadith ke hawalon ke saath jawab deta hoon. "
                  "Baraye meharbani apna sawal poochein."),
    },
}


def _msg(kind, query, **fmt):
    """Pick a fixed message in the user's detected language, with fallback to English."""
    table = _MSG.get(kind, {})
    text = table.get(_lang_key(query)) or table.get("en", "")
    return text.format(**fmt) if fmt else text


def _low_confidence_result(query, madhhab):
    """Legacy mode name: a fixed referral, without an accuracy assessment."""
    msg = _msg("referral", query, url=ISLAMQA_URL)
    return {
        "ok": True, "mode": "low_confidence", "out_of_scope": False,
        "low_confidence": True,
        "answer": msg,
        "confidence": None, "confidence_percent": None, "confidence_label": None,
        "consensus": None,
        "referral_url": ISLAMQA_URL,
        "sources": {"fiqh": [], "quran": [], "hadith": []},
    }


def _is_vague_question(query):
    """True for short prompts that are grammatical but carry NO real subject to
    answer — e.g. 'what am I', 'who am I', 'help', 'tell me something', 'explain'.
    These have a question/instruction word but no topic noun, so the model just
    rambles ('please provide more details'). We route them to a rephrase prompt.
    Real short questions ('what is zakat', 'how many prayers') are NOT vague
    because they contain a topic word, so they pass through untouched.
    """
    raw = (query or "").strip()
    q = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
    words = q.split()
    if not words:
        return False  # emptiness handled by _is_gibberish
    # Only consider SHORT prompts (long ones are genuine attempts).
    if len(words) > 5:
        return False
    # Script (Urdu/Arabic) input is handled elsewhere; only screen Latin here.
    if any('\u0600' <= ch <= '\u06FF' for ch in raw):
        return False

    # Known vague/contentless phrasings (exact, whole-message match).
    vague_exact = {
        "what am i", "who am i", "what is this", "what is it", "what", "who",
        "why", "how", "when", "where", "help", "help me", "tell me", "tell me something",
        "explain", "explain this", "explain it", "answer", "answer me", "info",
        "information", "something", "anything", "guide me", "assist me", "idk what to ask",
        "what should i ask", "what can you do", "what do you do", "who are you",
        "what are you", "define", "meaning", "kuch batao", "kuch bta", "batao",
    }
    if q in vague_exact:
        return True

    # General case: has a question/instruction word but no recognisable TOPIC.
    lead_words = {
        "what", "who", "why", "how", "when", "where", "which", "am", "is", "are",
        "tell", "explain", "help", "define", "give", "show", "answer", "describe",
    }
    if words[0] not in lead_words:
        return False
    # Reuse the domain vocabulary: if ANY token looks like a topic/subject
    # (a noun that isn't a pure function word), it's a real question.
    function_words = {
        "what", "who", "why", "how", "when", "where", "which", "am", "is", "are",
        "i", "me", "my", "you", "your", "it", "this", "that", "the", "a", "an",
        "do", "does", "can", "to", "of", "in", "on", "for", "about", "tell",
        "explain", "help", "give", "show", "answer", "describe", "define", "should",
        "would", "will", "and", "or", "please", "some", "any", "thing", "something",
        "anything", "us", "we", "them",
    }
    content_tokens = [w for w in words if w not in function_words and len(w) >= 3]
    # No content noun at all -> vague.
    return len(content_tokens) == 0


def _is_gibberish(query):
    """True when the message carries no real question — random tokens in ANY
    language ('yo', 'blah', 'asdf', Urdu 'کہل', Arabic scribble, Roman-Urdu
    'abcd'), single filler words, or no letters at all. Such input must NOT be
    pushed through retrieval (it grabs a random topic and returns a bogus cited
    answer). It is routed to a rephrase prompt instead.

    Strategy: instead of trying to list every possible junk word (impossible
    across four languages), we require SHORT messages to contain at least one
    recognisable signal — a question word or an Islamic-domain word in English,
    Roman Urdu, Urdu script, or Arabic. Long, sentence-like input is assumed to
    be a genuine attempt and passes through.
    """
    raw = (query or "").strip()
    q = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
    words = q.split()
    if not words:
        return True
    # No letters at all (pure numbers/symbols/emoji).
    if not any(ch.isalpha() for ch in q):
        return True

    # Obvious English/Latin filler.
    filler = {
        "yo", "blah", "blahblah", "bla", "asdf", "asdff", "qwerty", "test", "testing",
        "bruh", "bro", "lol", "lmao", "hmm", "hmmm", "meh", "idk", "uh", "um", "erm",
        "abc", "xyz", "aaa", "aaaa", "haha", "hahaha", "nvm", "wtf", "yeah", "yep",
        "nope", "nah", "yup", "sup", "wassup", "wagwan", "huh", "eh", "ok", "okay",
        "bla bla", "blabla", "kk", "k", "hmmmm", "ugh", "oof", "eh", "hey",
    }
    if all(w in filler for w in words):
        return True

    # Repeated single-character run in one token ("aaaaaa", "ھھھھ").
    if len(words) == 1 and len(set(words[0])) <= 1:
        return True

    # --- Cross-language "is there any real signal?" check for SHORT input ---
    # Long input (4+ words) is treated as a genuine attempt and passes through;
    # retrieval + downstream abstention policy handle the rest.
    if len(words) >= 4:
        return False

    # Recognisable signal words across the four supported languages. A short
    # message with NONE of these is almost certainly a random token.
    question_words = {
        # English
        "how", "what", "when", "why", "where", "who", "can", "is", "are", "should",
        "does", "do", "may", "will", "would", "which", "many",
        # Roman Urdu
        "kya", "kaise", "kaisay", "kab", "kahan", "kahaan", "kyun", "kyu", "kiya",
        "kia", "sakta", "sakte", "sakti", "hai", "hain", "ho", "kar", "karna", "krna",
        "kitne", "kitni", "kitna", "kaun", "konsa", "konsi", "kon", "kaunsa",
        "parhna", "parhni", "parhne", "farz", "wajib", "sunnat", "daily", "rozana",
        # (Urdu-script & Arabic question words handled by the domain set below too)
    }
    # Islamic-domain words (roots) in Latin letters (English + Roman Urdu).
    domain_latin = {
        "namaz", "namaaz", "naamaz", "namaz", "namz", "salah", "salat", "salaah",
        "prayer", "prayers", "pray", "wudu", "wuzu", "wudhu", "ablution",
        "roza", "roze", "rozay", "fast", "fasting", "sawm", "saum", "zakat", "zakah",
        "zakaat", "hajj", "haj", "umrah", "umra", "umrah",
        "quran", "qur'an", "koran", "hadith", "hadees", "sunnah", "sunnat", "halal",
        "haram", "haraam", "jaiz", "najaiz", "fiqh", "deen", "deeni", "ibadat", "ibadah",
        "ramadan", "ramzan", "eid", "janaza", "janazah", "nikah", "talaq", "witr",
        "sujood", "sajda", "sajdah", "ruku", "tayammum", "ghusl", "iddah", "mahr",
        "fitr", "qibla", "qiblah", "masjid", "dua", "duaa", "tasbih", "islam",
        "islamic", "muslim", "allah", "nabi", "rasool", "makkah", "madina", "kaaba",
        "tahajjud", "fajr", "dhuhr", "zuhr", "zohar", "asr", "maghrib", "isha",
        "rakat", "rakah", "rakats", "rakaat", "rakaats", "rakah", "interest", "riba",
        "sood", "sood", "qaza", "qada", "farz", "fardh", "wajib", "sunnah", "nafl",
        "namazein", "namazen", "prayers",
    }
    # Urdu/Arabic-script domain & question words (substring match on the raw text).
    domain_script = [
        "\u0646\u0645\u0627\u0632",  # namaz
        "\u0631\u0648\u0632",        # roza
        "\u0648\u0636\u0648", "\u0648\u0632\u0648",  # wudu
        "\u0632\u06a9\u0627", "\u0632\u06a9\u0648\u0629",  # zakat
        "\u062d\u062c",              # hajj
        "\u0639\u0645\u0631\u06c1", "\u0639\u0645\u0631\u0629",  # umrah
        "\u0642\u0631\u0622\u0646", "\u0642\u0631\u0627\u0646",  # quran
        "\u062d\u062f\u06cc\u062b",  # hadith
        "\u062d\u0644\u0627\u0644", "\u062d\u0631\u0627\u0645",  # halal/haram
        "\u0631\u0648\u0632\u06c1", "\u0635\u0648\u0645",  # fasting/sawm
        "\u0646\u06a9\u0627\u062d", "\u0637\u0644\u0627\u0642",  # nikah/talaq
        "\u063a\u0633\u0644", "\u062f\u0639\u0627",  # ghusl/dua
        "\u0627\u0633\u0644\u0627\u0645", "\u0627\u0644\u0644\u06c1", "\u0627\u0644\u0644\u0647",  # islam/allah
        "\u0645\u0633\u062c\u062f", "\u0639\u06cc\u062f", "\u0631\u0645\u0636\u0627\u0646",  # masjid/eid/ramadan
        # question words (Urdu/Arabic)
        "\u06a9\u06cc\u0627", "\u06a9\u06cc\u0633\u06d2", "\u06a9\u0628",  # kya/kaise/kab (Urdu)
        "\u0647\u0644", "\u0645\u0627\u0630\u0627", "\u0643\u064a\u0641", "\u0645\u062a\u0649", "\u0644\u0645\u0627\u0630\u0627", "\u0623\u064a\u0646",  # Arabic Q words
        "\u064a\u062c\u0648\u0632", "\u0635\u0644\u0627\u0629", "\u0635\u0648\u0645", "\u0632\u0643\u0627\u0629",  # yajuz/salah/sawm/zakah
    ]

    latin_has_signal = any(w in question_words or w in domain_latin for w in words)
    script_has_signal = any(tok in raw for tok in domain_script)
    if latin_has_signal or script_has_signal:
        return False

    # Short, and no recognisable question/domain signal in any language -> junk.
    return True


def _force_general(query):
    """Basic-fact questions that are never specific edge-case rulings -> general mode."""
    q = query.lower()
    # "how many ..." is always a basic count question (prayers, rakats, pillars...).
    if "how many" in q:
        return True
    return False


def _is_meta_instruction(query):
    """Bare language/format instructions ('answer in roman urdu', 'in urdu',
    'translate this') aren't questions — they mean 're-express the previous
    answer'. We accept short phrases that reference a language or a
    translate/explain-again instruction, as long as they carry no real question."""
    q = re.sub(r"[^\w\s]", "", query.lower()).strip()
    words = q.split()
    if len(words) > 8:
        return False
    # mentions a language/answering instruction but contains no actual question
    lang_words = ["roman urdu", "urdu", "english", "arabic", "hindi", "language"]
    instruct_words = ["answer", "reply", "respond", "speak", "talk", "write", "say it",
                      "translate", "explain", "rephrase", "convert", "make it", "say that",
                      "in", "to"]
    has_lang = any(w in q for w in lang_words)
    has_instruct = any(w in q for w in instruct_words)
    # A standalone translate/repeat request with no language named still counts
    # (e.g. "translate this", "say that again", "rephrase").
    translate_only = any(w in q for w in
        ["translate", "rephrase", "reword", "say that again", "repeat that", "again"])
    has_question = "?" in query or any(w in q for w in
        ["how", "what", "when", "why", "can i", "is it", "should", "kya", "kaise", "kab"])
    # Guard: a bare "in"/"to" alone shouldn't trigger — require it to co-occur
    # with a language word so plain sentences don't get misread.
    if not has_lang and not translate_only:
        return False
    return (has_lang or translate_only) and has_instruct and not has_question


def _is_capability_question(query):
    """True when the user is asking what the bot can do / what they may ask, e.g.
    'what can I ask', 'what can you do', 'what topics do you cover', and the
    Roman-Urdu / Urdu / Arabic equivalents ('mai kya pooch sakta hu',
    'tum kya karte ho', 'ماذا يمكنني أن أسأل'). These are NOT Fiqh questions, so
    retrieval must not run — we reply with a short capability message instead.

    Guarded to whole/short messages so a real question that merely contains one
    of these words (e.g. 'what can I ask Allah for in dua?') still gets answered.
    """
    raw = (query or "").strip()
    q = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
    q = re.sub(r"\s+", " ", q)
    if not q:
        return False
    words = q.split()
    if len(words) > 7:                     # capability questions are short
        return False

    # 1) Latin (English + Roman Urdu) — match the WHOLE message against a set of
    #    known capability phrasings, plus a couple of tight patterns.
    latin_exact = {
        # English
        "what can i ask", "what can i ask you", "what can you do", "what do you do",
        "what can you help with", "what can you help me with", "what should i ask",
        "what can i ask about", "what topics can i ask", "what topics do you cover",
        "what kind of questions can i ask", "what questions can i ask",
        "what are you for", "what is this for", "what can this do", "how can you help",
        "how can you help me", "what all can i ask", "what can u ask", "what can u do",
        # Roman Urdu
        "mai kya pooch sakta hu", "main kya pooch sakta hu", "mai kya puch sakta hu",
        "mai kya pooch sakta hoon", "main kya pooch sakta hoon", "kya pooch sakta hu",
        "kya pooch sakta hoon", "mai aap se kya pooch sakta hu",
        "main aap se kya pooch sakta hoon", "aap kya karte ho", "tum kya karte ho",
        "tum kya kar sakte ho", "aap kya kar sakte ho", "mujhe kya poochna chahiye",
        "mai kya poochun", "main kya poochun", "kya poochun", "aap kis cheez mein madad karte ho",
        "mai kya sawal pooch sakta hu", "main kya sawal pooch sakta hoon",
    }
    if q in latin_exact:
        return True
    # Tight pattern: "(what/kya) ... (ask/pooch/puch) ..." within a short message,
    # e.g. "what can i ask here", "mai tumse kya pooch sakta hu".
    if len(words) <= 7:
        has_q = any(w in ("what", "kya", "kia") for w in words)
        has_ask = any(w in ("ask", "pooch", "poochun", "puch", "poch", "poochna",
                            "sawal", "questions", "question") for w in words)
        has_cap = any(w in ("can", "sakta", "sakte", "sakti", "chahiye", "karte",
                            "karsakta", "kar") for w in words)
        if has_q and has_ask and has_cap:
            return True

    # 2) Urdu / Arabic script — key phrases.
    #    Urdu:  "میں کیا پوچھ سکتا ہوں", "آپ کیا کر سکتے ہیں", "کیا پوچھوں"
    #    Arabic:"ماذا يمكنني أن أسأل", "ماذا تستطيع أن تفعل", "بماذا يمكنك مساعدتي"
    script_markers = [
        "\u06a9\u06cc\u0627 \u067e\u0648\u0686\u06be",      # kya poochh (Urdu)
        "\u06a9\u06cc\u0627 \u0633\u0648\u0627\u0644",      # kya sawal (Urdu)
        "\u06a9\u06cc\u0627 \u06a9\u0631 \u0633\u06a9\u062a\u06d2",  # kya kar sakte (Urdu)
        "\u0645\u0627\u0630\u0627 \u064a\u0645\u0643\u0646\u0646\u064a",  # matha yumkinuni (Arabic: what can I)
        "\u0645\u0627\u0630\u0627 \u0623\u0633\u0623\u0644",  # matha as'al (Arabic: what do I ask)
        "\u0645\u0627\u0630\u0627 \u062a\u0633\u062a\u0637\u064a\u0639",  # matha tastati' (Arabic: what can you)
        "\u0628\u0645\u0627\u0630\u0627 \u064a\u0645\u0643\u0646\u0643",  # bimatha yumkinuk (Arabic: with what can you)
    ]
    if len(raw) <= 60 and any(m in raw for m in script_markers):
        return True

    return False


def _is_greeting(query):
    """True when the message is ONLY a greeting / pleasantry, not a question.

    Catches English, Roman-Urdu and Urdu-script greetings. If a greeting is
    followed by a real question (e.g. "salam, kya main safar mein namaz jama kar
    sakta hu?"), we do NOT treat it as a greeting — the question wins and goes to
    retrieval. Matching is phrase-based (whole message or clear prefix) rather
    than loose substring, so a greeting word inside a longer question can't
    hijack it.
    """
    raw = (query or "").strip()
    q = raw.lower().strip()
    q_clean = re.sub(r"[^\w\s]", "", q)            # drop punctuation
    q_clean = re.sub(r"\s+", " ", q_clean).strip()
    if not q_clean:
        return False
    words = q_clean.split()
    if len(words) > 6:                             # long messages aren't bare greetings
        return False

    # Whole-message / prefix greeting phrases (English + Roman Urdu).
    greetings = [
        # salutations
        "assalam", "assalamu", "assalam o alaikum", "assalam alaikum",
        "salam", "salaam", "asalam", "asalaam", "asslam", "as salam",
        "walaikum", "wa alaikum", "walekum", "walaikum assalam",
        # English greetings / pleasantries
        "hi", "hello", "hey", "hola", "yo",
        "good morning", "good evening", "good afternoon", "good night",
        "how are you", "how are you doing", "hows it going", "how do you do",
        "thanks", "thank you", "shukran", "jazakallah", "jazak allah", "jazakillah",
        "ok", "okay", "test", "testing",
        # Roman-Urdu greetings / pleasantries
        "kaise ho", "kaise hain", "kaisay ho", "kaisay hain",
        "kaisa hai", "kaise ho bhai", "kaise ho aap", "aap kaise ho", "aap kaise hain",
        "kya haal hai", "kya haal", "kya haal hain", "kya hal hai", "kya hal",
        "sab theek", "sab thik", "sab theek hai", "sab thik hai", "sab khairiyat",
        "theek ho", "thik ho", "theek hain", "khairiyat",
        "kaise ho tum", "kese ho", "kesi ho",
    ]

    # 1) If the WHOLE message (punctuation stripped) is exactly a greeting phrase,
    #    it's a greeting even with a trailing "?" ("kaise ho?").
    if q_clean in greetings:
        return True

    # 2) Otherwise, a "?" or a real question signal means send it to retrieval,
    #    even if it opens with a greeting. (Islamic/topic words are NOT treated as
    #    question signals here — only interrogative structure.)
    if "?" in raw:
        return False
    question_markers = [
        "how many", "how do", "how can i", "what is", "what are", "when", "why",
        "can i", "is it", "should i", "how to", "which",
        # Roman-Urdu interrogatives that indicate a real question follows
        "kya main", "kya mai", "kaise parh", "kaise karu", "kaise karun",
        "kitni", "kitne", "kitna", "kab", "kahan", "kaha", "jaiz hai", "haram hai",
        "kar sakta", "kar sakti", "karna chahiye", "parh sakta",
    ]
    if any(m in q for m in question_markers):
        return False

    # 3) Greeting at the start, remainder isn't a real question -> still a greeting
    #    (e.g. "salam bhai", "assalam o alaikum sheikh").
    for g in greetings:
        if q_clean.startswith(g + " "):
            return True
    return False


_TARGET_LANG_WORDS = {
    "urdu":       "Urdu script (اردو)",
    "roman urdu": "Roman Urdu (Urdu written in Latin letters)",
    "roman":      "Roman Urdu (Urdu written in Latin letters)",
    "arabic":     "Arabic",
    "english":    "English",
}


# Roman-Urdu marker words (Urdu written in Latin letters). Used to tell apart
# English from Roman Urdu, since both use the Latin alphabet.
_ROMAN_URDU_HINTS = {
    # ONLY grammatical/function words that are distinctly Urdu. Islamic terms
    # (wudu, namaz, roza, halal, zakat, hajj...) are deliberately EXCLUDED
    # because English speakers use them too ("is coffee halal", "vomiting and
    # wudu"), which caused English questions to be misread as Roman Urdu.
    "kya", "kaise", "kaisay", "kab", "kahan", "kahaan", "kyun", "kyu", "kiya", "kia",
    "hai", "hain", "ho", "hota", "hoti", "hote", "tha", "thi", "the",
    "karna", "karne", "karta", "karti", "karte", "kar", "krna", "krta", "krte", "kr",
    "sakta", "sakte", "sakti", "krsakta", "krskta",
    "mai", "main", "mein", "meri", "mera", "mere", "mujhe", "mujhko", "hum", "humein",
    "ap", "aap", "tum", "tumhe", "uska", "uski", "unka", "iska", "iski",
    "nhi", "nahi", "nahin", "haan", "acha", "achha", "theek", "thik",
    "batao", "bta", "bata", "batayen", "bataye", "bataiye",
    "chahiye", "chahie", "chaida", "hoga", "hogi", "hoga", "raha", "rahi", "rahe",
    "kaha", "kehte", "kehna", "wala", "wali", "wale", "agar", "lekin", "aur",
    "par", "se", "ka", "ke", "ki", "ko", "ne", "kis", "kaun", "kitna", "kitni",
}


def _detect_language(query):
    """Deterministically detect the input language so we can force the reply to
    match it. Returns one of: 'Urdu script (اردو)', 'Arabic', 'Roman Urdu ...',
    or 'English'. Script-based checks are reliable; Roman-Urdu vs English is a
    heuristic on common Urdu words written in Latin letters."""
    q = query or ""
    # Arabic/Urdu share the Arabic block (U+0600–U+06FF). Distinguish by the
    # Urdu-specific letters that Arabic does not use (ں ہ ے ٹ ڈ ڑ گ چ پ ژ ک).
    has_arabic_block = any('\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F'
                           or '\uFB50' <= ch <= '\uFDFF' or '\uFE70' <= ch <= '\uFEFF'
                           for ch in q)
    if has_arabic_block:
        urdu_specific = set("ںہھیےۓٹڈڑگچپژکﺁآۃ")
        if any(ch in urdu_specific for ch in q):
            return _TARGET_LANG_WORDS["urdu"]
        # Heuristic: if it also has clearly Urdu function words in script, call Urdu.
        return _TARGET_LANG_WORDS["arabic"]
    # Latin script: decide English vs Roman Urdu by marker words.
    words = re.sub(r"[^\w\s]", " ", q.lower()).split()
    if words:
        hits = sum(1 for w in words if w in _ROMAN_URDU_HINTS)
        # Require a genuine signal: at least 2 Urdu function words, OR one strong
        # one in a short phrase where it dominates. A single ambiguous short word
        # ('se', 'ka') in an otherwise-English sentence must NOT flip it to Urdu.
        strong = {"kya", "kaise", "kaisay", "kyun", "kyu", "hai", "hain", "karna",
                  "krna", "sakta", "sakte", "mujhe", "mein", "nahi", "nahin",
                  "batao", "bata", "chahiye", "kitna", "kitni", "kaun", "kahan"}
        strong_hits = sum(1 for w in words if w in strong)
        if strong_hits >= 1 and (hits / len(words)) >= 0.25:
            return _TARGET_LANG_WORDS["roman urdu"]
        if hits >= 2 and (hits / len(words)) >= 0.4:
            return _TARGET_LANG_WORDS["roman urdu"]
    return _TARGET_LANG_WORDS["english"]


def _requested_target_language(query):
    """Return a human-readable target language named in a meta-instruction, or None."""
    q = query.lower()
    # check the more specific 'roman urdu' before 'urdu'
    for key in ("roman urdu", "roman", "urdu", "arabic", "english"):
        if key in q:
            return _TARGET_LANG_WORDS[key]
    return None


def _receipt_context(tags, madhhab=None):
    """Re-resolve signed source identities; missing/empty records invalidate history."""
    fiqh, hadith, quran = [], [], []
    topic_ids = {f'[{topic["topic_name"]}]': topic["topic_id"] for topic in (fiqh_topics or [])}
    for tag in tags:
        if tag in topic_ids:
            fiqh.append({"topic_id": topic_ids[tag], "score": 0.0})
            continue
        verse = re.fullmatch(r"\[Quran ([0-9]+):([0-9]+)\]", tag)
        narration = re.fullmatch(r"\[(.+) #([^\[\]]+)\]", tag)
        if verse:
            quran.append({"chapter": int(verse[1]), "ayah": int(verse[2]), "score": 0.0})
        elif narration:
            hadith.append({"source": narration[1], "hadith_no": narration[2], "score": 0.0})
    context = _validated_context(fiqh, hadith, quran, madhhab)
    return context if _context_tags(*context) == set(tags) else None


def _school_notice(status, query):
    target = _requested_target_language(query) or _detect_language(query)
    language = ("roman" if "Roman Urdu" in target else "ur" if "Urdu script" in target
                else "ar" if target == "Arabic" else "en")
    return NOTICES[status][language]


def _school_section(key, title, status, answer, sources=None):
    section = {"school": key, "title": title, "status": status, "answer": answer,
               "reference_scope": "topic_level_shared",
               "sources": sources or {"fiqh": [], "quran": [], "hadith": []}}
    if status == "available":
        section["citation_validation"] = {"status": "passed", "scope": "provided_reference_membership"}
        section["scholarly_review"] = {"status": "not_completed", "scope": REVIEW_SCOPE}
    return section


def _comparison_digest(sections, evidence):
    rows = []
    for section in sections:
        key = section["school"]
        row = {"school": key, "status": section["status"]}
        if key in evidence:
            tags, context = evidence[key]
            row.update(tags=sorted(tags), source_digest=_context_fingerprint(tags, *context))
        rows.append(row)
    return hashlib.sha256(json.dumps({"schema": SCHOOL_SCHEMA, "sections": rows}, sort_keys=True).encode()).hexdigest()


def _pack_comparison(sections, evidence):
    answer = flatten_sections(sections)
    sources = {"fiqh": [], "quran": [], "hadith": []}
    for kind in sources:
        seen = set()
        for section in sections:
            for record in section["sources"][kind]:
                identity = json.dumps(record, sort_keys=True, ensure_ascii=True)
                if identity not in seen:
                    seen.add(identity)
                    sources[kind].append(record)
    result = {"ok": True, "mode": SCHOOL_MODE, "response_schema": SCHOOL_SCHEMA,
              "answer": answer, "answer_sections": sections, "sources": sources, "out_of_scope": False,
              "confidence": None, "confidence_percent": None, "confidence_label": None,
              "confidence_reason": None, "consensus": None}
    if evidence:
        tags = sorted({tag for item in evidence.values() for tag in item[0]})
        result["answer_receipt"] = _response_receipts.issue(answer, tags, _comparison_digest(sections, evidence))
        result["citation_validation"] = {"status": "passed", "scope": "provided_reference_membership"}
        result["scholarly_review"] = {"status": "not_completed", "scope": REVIEW_SCOPE}
    return result


def _school_prompt(query, contexts, previous=None):
    scopes = {}
    for key, (fiqh, hadith, quran) in contexts.items():
        scopes[key] = {
            "school": dict(SCHOOLS)[key],
            "rulings": [{"topic_tag": f'[{r["topic_name"]}]',
                         "notes": {name: {field: note[field] for field in ("ruling", "explanation") if field in note}
                                   for name, note in r["ruling"].items() if isinstance(note, dict)}} for r in fiqh],
            "topic_level_shared_references": {
                "quran": [{"tag": f'[Quran {v["chapter"]}:{v["ayah"]}]', "text": v["english"]} for v in quran],
                "hadith": [{"tag": f'[{h["source"]} #{h["hadith_no"]}]', "text": h["text_en"]} for h in hadith]},
        }
        if previous:
            scopes[key]["previous_answer"] = previous[key]["answer"]
            scopes[key]["required_citations"] = list(previous[key]["tags"])
    language = _requested_target_language(query) or _detect_language(query)
    task = ("Translate/re-express each previous answer while preserving its exact meaning and every required citation."
            if previous else "Organize the retrieved school notes to answer the question.")
    return f"""You organize retrieved Islamic knowledge-base material; you do not decide or invent rulings.
{task}
Write in {language}. Never use Hindi/Devanagari. Keep citation tags unchanged in Latin letters.
Return ONLY a JSON object with exactly these school keys: {json.dumps(list(contexts))}.
Each value must be an answer string of at most 6,000 characters, or null if the supplied material cannot answer.
No summary, extra keys, school headings or commentary outside the JSON.
Use ONLY the ruling/explanation under that SAME school key and its supplied references.
Do not transfer another school's position into this school. Do not infer a missing position.
Cite the supplied fiqh topic tag at least once in each answer. Use other exact reference tags only when relevant.
References are attached to the topic; they are not independently verified evidence for each school's inference.
Do not add facts from memory, unprovided references, URLs, or unbracketed reference numbers.
{REVIEW_INSTRUCTION}
For translation, retain every required citation in its original school; do not move, add or drop them.

RETRIEVED SCHOOL CONTEXTS:
{json.dumps(scopes, ensure_ascii=False)}

USER QUESTION/INSTRUCTION:
{query}
"""


def _organize_school_contexts(query, contexts, fixed=None, previous=None):
    fixed = fixed or {}
    if not contexts:
        return _pack_comparison([fixed[key] for key, _ in SCHOOLS], {})
    try:
        values = parse_school_output(gemini_generate(_school_prompt(query, contexts, previous)), contexts)
    except CitationError as error:
        return _source_validation_failure(query, str(error))
    sections, evidence = [], {}
    for key, title in SCHOOLS:
        if key in fixed:
            sections.append(fixed[key])
            continue
        context = contexts[key]
        try:
            answer, tags = validate_citations(values[key], _context_tags(*context),
                                               expected=previous[key]["tags"] if previous else None)
            validate_unreviewed_answer(answer)
            validate_school_wording(answer, key)
            if not any(f'[{r["topic_name"]}]' in tags for r in context[0]):
                raise CitationError("missing_school_ruling_citation")
        except CitationError:
            sections.append(_school_section(key, title, "withheld", _school_notice("withheld", query)))
            continue
        sources = _cited_sources(tags, *context)
        for topic in sources["fiqh"]:
            topic["madhhab"] = title
        sections.append(_school_section(key, title, "available", answer, sources))
        evidence[key] = (tags, context)
    return _pack_comparison(sections, evidence)


def _comparison_result(query, topic_id, topic_score):
    # Retain hybrid retrieval plus the existing example-classifier anchor. Only
    # that primary topic supplies school notes; a nearby second topic cannot fill gaps.
    retrieved = retrieve_fiqh_ruling(query, madhhab=None, top_k=2)
    primary = next((r for r in retrieved if r["topic_id"] == topic_id), None)
    primary = _fiqh_entry_by_id(topic_id, score=topic_score) or primary
    references = primary.get("references", {}) if primary else {}
    quran = retrieve_quran(query, fiqh_refs=references.get("quran", []), top_k=2) if primary else []
    quran = [v for v in quran if v.get("score", 0) >= QURAN_MIN_SCORE]
    _, hadith = _curated_candidates(topic_id) if primary else ([], [])
    if not hadith and ENABLE_HADITH_SEARCH and primary:
        hadith = [h for h in retrieve_hadith(query, top_k=2) if h["score"] >= HADITH_MIN_SCORE]
    contexts, fixed = {}, {}
    for key, title in SCHOOLS:
        context = _validated_context([primary] if primary else [], hadith, quran, title)
        note = context[0][0].get("ruling", {}).get(key) if context[0] else None
        if not isinstance(note, dict) or not isinstance(note.get("ruling"), str) or not note["ruling"].strip():
            fixed[key] = _school_section(key, title, "unavailable", _school_notice("unavailable", query))
        elif not _retrieval_policy_allows(topic_score, context[1], context[2]):
            fixed[key] = _school_section(key, title, "withheld", _school_notice("withheld", query))
        else:
            contexts[key] = context
    return _organize_school_contexts(query, contexts, fixed)


def _reexpress_comparison(prev_answer, instruction, receipt):
    proof = _response_receipts.verify(prev_answer, receipt)
    if not proof:
        return _source_validation_failure(instruction, "unverified_history")
    all_tags, fingerprint = proof
    try:
        sections = split_sections(prev_answer)
        contexts, fixed, evidence, previous = {}, {}, {}, {}
        for section in sections:
            key, title = section["school"], section["title"]
            if section["status"] != "available":
                fixed[key] = _school_section(key, title, section["status"], _school_notice(section["status"], instruction))
                continue
            answer, tags = validate_citations(section["answer"], all_tags)
            validate_unreviewed_answer(answer)
            validate_school_wording(answer, key)
            context = _receipt_context(tags, title)
            if context is None or not context[0]:
                raise CitationError("unverified_history")
            contexts[key] = context
            evidence[key] = (tags, context)
            previous[key] = {"answer": answer, "tags": tags}
        if (set(all_tags) != {tag for tags, _ in evidence.values() for tag in tags}
                or _comparison_digest(sections, evidence) != fingerprint):
            raise CitationError("unverified_history")
    except CitationError:
        return _source_validation_failure(instruction, "unverified_history")
    return _organize_school_contexts(instruction, contexts, fixed, previous)


def _reexpress_result(prev_answer, instruction, madhhab=None, prev_answer_receipt=None):
    """
    Re-express only the exact server-issued answer bound to its signed receipt.
    A receipt proves provenance/citation identity, not semantic or scholarly accuracy.
    """
    proof = _response_receipts.verify(prev_answer, prev_answer_receipt)
    tags, fingerprint = proof if proof else ((), None)
    context = _receipt_context(tags, madhhab) if tags else None
    # Older selected-school history remains translatable after the UI switches
    # to all schools. Accept only the exact old scope proven by its fingerprint.
    if tags and madhhab is None and (context is None or _context_fingerprint(tags, *context) != fingerprint):
        for _, title in SCHOOLS:
            candidate = _receipt_context(tags, title)
            if candidate is not None and _context_fingerprint(tags, *candidate) == fingerprint:
                context = candidate
                break
    if context is None or _context_fingerprint(tags, *context) != fingerprint:
        return _source_validation_failure(instruction, "unverified_history")
    fiqh, hadith, quran = context
    try:
        validate_unreviewed_answer(prev_answer)
    except CitationError as error:
        return _source_validation_failure(instruction, str(error))
    # Preserve original source fingerprints, but do not present unreviewed
    # dataset certainty fields as evidence for a translated answer.
    fiqh_notes = []
    for record in fiqh:
        notes = {}
        for school, note in record["ruling"].items():
            if isinstance(note, dict):
                notes[school] = {key: note[key] for key in ("ruling", "explanation") if key in note}
        fiqh_notes.append({"topic_name": record["topic_name"], "ruling": notes})
    source_context = json.dumps({"fiqh": fiqh_notes, "hadith": hadith, "quran": quran}, ensure_ascii=False)
    target = _requested_target_language(instruction) or "the requested language"
    prompt = f"""Re-express the following Islamic answer in {target}.

RULES:
- Keep the meaning EXACTLY the same. Do not add new rulings, verses, or facts.
- Keep every bracketed citation (e.g. [Quran 2:196], [Sahih Bukhari #8]) EXACTLY as written, in Latin letters, unchanged.
- If the target is Urdu script, write fluent natural Urdu (اردو). You ARE capable of writing Urdu — never claim otherwise and never substitute English.
- If the target is Roman Urdu, write Urdu using Latin letters.
- Never use Hindi or Devanagari script.
- Output only the re-expressed answer, nothing else.
- Keep all supplied citation tags. Add no other citations, URLs or unbracketed reference numbers.
- Use the supplied source text only. If you cannot preserve the supported meaning, decline.
- Keep the output under 20,000 characters.
- {REVIEW_INSTRUCTION}

SOURCE CONTEXT:
{source_context}

ANSWER TO RE-EXPRESS:
{prev_answer}
"""
    out = gemini_generate(prompt)
    try:
        out, cited = validate_citations(out, tags, expected=tags)
        validate_unreviewed_answer(out)
    except CitationError as error:
        return _source_validation_failure(instruction, str(error))
    return _with_receipt({
        "ok": True, "mode": "reexpress", "out_of_scope": False,
        "answer": out.strip(),
        # This is the same content as before, just re-expressed — no new scoring.
        "confidence": None, "confidence_percent": None, "confidence_label": None,
        "consensus": None,
        "sources": _cited_sources(cited, fiqh, hadith, quran),
    }, cited, fiqh, hadith, quran)


def answer_question(query, madhhab=None, prev_answer=None, prev_answer_receipt=None, *, compare_schools=False):
    """
    Full pipeline. Returns a JSON-serialisable dict:
      { ok, mode, answer, sources: {fiqh:[...], quran:[...], hadith:[...]},
        citation_validation, scholarly_review, answer_receipt, out_of_scope }

    Legacy confidence/consensus fields remain null; similarity is not accuracy.
    Citation/review status and receipts apply only to accepted generated answers.
    Served defaults enable compare_schools; the default False retains flat
    compatibility for existing Python-library callers and explicit school paths.

    prev_answer: the previous bot answer (optional). When the current message is
    a bare "explain/translate in <language>" instruction, we re-express THIS text
    in the requested language instead of running retrieval (which would otherwise
    grab a random nearby topic).
    """
    if not _READY:
        init(verbose=False)
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "empty_query"}

    # ── Greeting / small-talk gate ───────────────────────────────
    # A greeting is not a question — don't run retrieval and answer something
    # that was never asked. Reply with a short greeting + a prompt to ask.
    if _is_greeting(query):
        return {
            "ok": True, "mode": "greeting", "out_of_scope": False,
            "answer": _msg("greeting", query),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
        }

    # ── Capability / "what can I ask" gate ───────────────────────
    # Questions about what the bot can do ("what can I ask", "mai kya pooch sakta
    # hu", "ماذا يمكنني أن أسأل") are NOT Fiqh questions. Without this, retrieval
    # grabs a nearby topic and returns a random cited ruling. Reply with a short
    # capability message in the user's language instead.
    if _is_capability_question(query):
        return {
            "ok": True, "mode": "capability", "out_of_scope": False,
            "answer": _msg("capability", query),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
        }

    # Bare language/format instruction (e.g. "answer me in roman urdu") — not a
    # question. If we have the previous answer, RE-EXPRESS it in the requested
    # language (that's what "explain in urdu" as a follow-up means). Otherwise
    # just acknowledge and wait for the actual question.
    if _is_meta_instruction(query):
        if prev_answer and prev_answer.strip():
            if compare_schools and prev_answer.startswith("## Hanafi\n"):
                return _reexpress_comparison(prev_answer, query, prev_answer_receipt)
            return _reexpress_result(prev_answer, query, madhhab, prev_answer_receipt)
        return {
            "ok": True, "mode": "greeting", "out_of_scope": False,
            "answer": _msg("ask_lang", query),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
        }

    topic_matches = classify_topic(query, top_n=2)
    top_topic_id    = topic_matches[0][0] if topic_matches else None
    top_topic_score = topic_matches[0][1] if topic_matches else 0.0

    # ── Gibberish / no-real-question gate ────────────────────────
    # Random tokens ("yo", "blah", "asdf") are not questions. Retrieval would
    # still grab a nearest topic and fabricate a cited answer, so we intercept
    # junk input and return an honest low-confidence prompt to rephrase.
    if _is_gibberish(query):
        return {
            "ok": True, "mode": "low_confidence", "out_of_scope": True,
            "answer": _msg("gibberish", query),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
        }

    # ── Vague / contentless question gate ────────────────────────
    # Grammatical but empty prompts ("what am I", "who am I", "help", "explain")
    # have a question word but no topic, so the model just rambles. Ask the user
    # to be specific instead of guessing.
    if _is_vague_question(query):
        return {
            "ok": True, "mode": "low_confidence", "out_of_scope": True,
            "answer": _msg("gibberish", query),
            "confidence": None, "confidence_percent": None, "confidence_label": None,
            "consensus": None, "sources": {"fiqh": [], "quran": [], "hadith": []},
        }
    # Grave, contested, or highly personal matters (violence, sexuality,
    # apostasy, abortion, divorce specifics, etc.) are ALWAYS referred to a
    # qualified scholar. A small automated system must not issue a ruling on
    # these, even if a curated topic weakly matches — the risk of a wrong or
    # oversimplified answer is too high.
    if _is_sensitive_question(query):
        return _low_confidence_result(query, madhhab)

    if not _topic_match_is_eligible(top_topic_score):
        return _low_confidence_result(query, madhhab)

    if compare_schools:
        return _comparison_result(query, top_topic_id, top_topic_score)

    # ── General-knowledge routing (decided up front) ─────────────
    # Basic-fact questions use only the matched topic's local references. Weak
    # matches have already been withheld; this is not a model-memory fallback.
    if _force_general(query):
        return _general_result(query, madhhab, top_topic_id, top_topic_score)

    fiqh = retrieve_fiqh_ruling(query, madhhab=madhhab, top_k=2)

    # ── Classifier anchoring ─────────────────────────────────────
    # The topic classifier anchors the candidate topic; it is not a correctness
    # guarantee. Pure hybrid retrieval on topic text can
    # be fooled by near-identical wudu/fasting topics (e.g. vomiting vs bleeding).
    # When the classifier confidently disagrees with the hybrid top hit, promote
    # the classifier's topic so the ruling, references and sources all align.
    CLASSIFIER_TRUST = 0.50
    if (top_topic_id and top_topic_score >= CLASSIFIER_TRUST
            and (not fiqh or fiqh[0]["topic_id"] != top_topic_id)):
        anchored = _fiqh_entry_by_id(top_topic_id, madhhab, score=top_topic_score)
        if anchored:
            fiqh = [anchored] + [r for r in fiqh if r["topic_id"] != top_topic_id]
            fiqh = fiqh[:2]

    quran_refs, hadith_refs = [], []
    if fiqh:
        refs = fiqh[0].get("references", {}) or {}
        quran_refs  = refs.get("quran", []) or []
        hadith_refs = refs.get("hadith", []) or []

    quran = retrieve_quran(query, fiqh_refs=quran_refs, top_k=2)
    # Curated/direct ayahs score 1.0 and always pass; gate weak fallback matches.
    quran = [v for v in quran if v["score"] >= QURAN_MIN_SCORE]

    hadith = []
    for href in hadith_refs:
        src = normalize_hadith_source(href.get("source", ""))
        hno = href.get("hadith_no", "")
        h = hadith_lookup.get((src, str(hno)))
        if h:
            # curated reference present in the local corpus (full text available)
            hadith.append({"type": "hadith", "source": h["source"], "hadith_no": h["hadith_no"],
                           "chapter": h.get("chapter", ""), "text_en": h.get("text_en", ""),
                           "text_ar": h.get("text_ar", ""), "score": 1.0, "curated": True})
        # References not found in either the Bukhari/Muslim corpus or the
        # supplementary other_hadith.json are skipped (we only cite hadith whose
        # text we can actually display).
    if not hadith and ENABLE_HADITH_SEARCH:
        # Opt-in only. Guessed (search) hadith are gated hard and never trusted by default.
        hadith = [h for h in retrieve_hadith(query, top_k=2) if h["score"] >= HADITH_MIN_SCORE]

    fiqh, hadith, quran = _validated_context(fiqh, hadith, quran, madhhab)
    if madhhab and not fiqh:
        return _source_validation_failure(query, "missing_school_context")
    allowed = _context_tags(fiqh, hadith, quran)
    if not allowed:
        return _source_validation_failure(query, "missing_source_context")

    if not _retrieval_policy_allows(top_topic_score, hadith, quran):
        return _low_confidence_result(query, madhhab)

    prompt = build_rag_prompt(query, madhhab, fiqh, hadith, quran,
                              target_language=_detect_language(query))
    answer = gemini_generate(prompt)
    # A grounded refusal must not trigger a less-constrained second generation.
    if _is_refusal(answer):
        return _source_validation_failure(query, "insufficient_source_context")
    try:
        answer, tags = validate_citations(answer, allowed)
        validate_unreviewed_answer(answer)
    except CitationError as error:
        return _source_validation_failure(query, str(error))
    answer = _collapse_topic_tags(answer)
    sources = _cited_sources(tags, fiqh, hadith, quran)

    return _with_receipt({
        "ok": True, "mode": "fiqh", "out_of_scope": False,
        "answer": answer,
        "sources": sources,
    }, tags, fiqh, hadith, quran)


if __name__ == "__main__":
    init()
    import pprint
    pprint.pprint(answer_question("Can I combine Zuhr and Asr while travelling?", "Hanafi"))
