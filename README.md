# DelkaAI API v2

A self-hosted AI API for Ghanaian professionals and businesses — built with FastAPI, multi-provider LLM routing, and a full plugin ecosystem.

---

## What it does

| Service | Description |
|---|---|
| **CV Generation** | Send career data or raw text → professionally designed PDF |
| **Cover Letter** | Send job details → tailored PDF cover letter |
| **Chat** | Streaming SSE chat with memory, plugins, web search |
| **Support Chat** | Platform-scoped streaming support chat |
| **OCR** | Extract text from images |
| **Speech-to-Text** | Transcribe audio files |
| **Text-to-Speech** | Generate spoken audio |
| **Translation** | Translate text between 100+ languages |
| **Code Generation** | Write and explain code in any language |
| **Object Detection** | Identify objects in images |
| **Image Generation** | Create images from text prompts |
| **Visual Search** | Search a product image index by image or text |

---

## Provider Chain

| Task | Primary | Secondary | Tertiary | Fallback |
|---|---|---|---|---|
| CV / Cover Letter | Gemini 2.5 Pro | Groq llama-3.3-70b | NVIDIA NIM | Ollama |
| Chat / Support | Groq llama-3.1-8b | Cerebras llama-3.3-70b | — | Ollama |
| Code generation | Cerebras Qwen3-235B | Groq llama-3.3-70b | — | Ollama |
| Embeddings (text) | Cohere embed-v4 | — | — | CLIP local |
| Embeddings (image) | CLIP (local) | — | — | — |

---

## Chat Plugins (auto-triggered)

- **Calculator** — safe AST-based math evaluation
- **Date/Time** — Ghana time (GMT+0), day, timezone conversions
- **Currency** — live GHS exchange rates (frankfurter.app)
- **Weather** — current weather for any city (wttr.in)
- **Wikipedia** — factual summaries for people, places, concepts
- **Bible** — scripture lookup by reference (bible-api.com)
- **YouTube** — video and tutorial search
- **News** — latest Ghana and world headlines (GNews)
- **Web search** — real-time Tavily search (auto-triggered for current events)

---

## Stack

- **FastAPI** — API framework with SSE streaming
- **Groq** — Primary chat/support LLM
- **Google Gemini 2.5 Pro** — Primary CV/letter LLM
- **Cerebras** — Primary code generation LLM (Qwen3-235B free)
- **NVIDIA NIM** — OCR, STT, TTS, translation, image gen, safety layer
- **Ollama** — Local fallback LLM
- **Cohere** — Text embeddings (RAG/reranking)
- **WeasyPrint** — PDF generation from HTML templates
- **SQLAlchemy** — ORM (PostgreSQL/MySQL)
- **Argon2** — Password/key hashing

---

## Getting Started

```bash
git clone https://github.com/Frank729-ctrl/hakdel.git
cd hakdel/Delka/delkaAI

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your credentials (see Required API Keys below)

uvicorn main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`

---

## Required API Keys (in `.env`)

| Key | Provider | Free? |
|---|---|---|
| `GROQ_API_KEY` | console.groq.com | Yes |
| `GOOGLE_API_KEY` | aistudio.google.com | Yes |
| `CEREBRAS_API_KEY` | cerebras.ai | Yes |
| `NVIDIA_API_KEY` | build.nvidia.com | Free tier |
| `TAVILY_API_KEY` | tavily.com | Free tier |
| `YOUTUBE_API_KEY` | console.cloud.google.com | Free quota |
| `GNEWS_API_KEY` | gnews.io | Free tier |
| `COHERE_API_KEY` | cohere.com | Free tier |

---

## Authentication

All requests require an API key in the header:

```
X-DelkaAI-Key: fd-delka-sk-your32hexkeyhere
```

- **SK (secret key)** — full access to all endpoints
- **PK (public key)** — restricted to chat, OCR, STT, TTS, translation, code, detection

Keys are created via the admin endpoint using the master key.

---

## Usage Examples

### Generate a CV

```bash
curl -X POST http://localhost:8000/v1/cv/generate \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Kwame Mensah",
    "email": "kwame@example.com",
    "summary": "Software engineer with 5 years experience.",
    "experience": [{"company": "Acme", "title": "Engineer", "start_date": "2020-01", "end_date": "present", "bullets": ["Built APIs"]}],
    "education": [{"school": "UG", "degree": "BSc CS", "year": "2019"}],
    "skills": ["Python", "FastAPI"]
  }'
```

Or send raw text and let the AI parse it:

```bash
curl -X POST http://localhost:8000/v1/cv/generate \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{"raw_text": "Kwame Mensah, kwame@example.com. Software engineer at Acme since 2020..."}'
```

### Chat (streaming SSE)

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-DelkaAI-Key: fd-delka-pk-..." \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "message": "What is the weather in Accra?", "platform": "delkaai-console"}'
```

### Code Generation

```bash
curl -X POST http://localhost:8000/v1/code/generate \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a FastAPI endpoint that validates a Ghanaian phone number", "language": "python"}'
```

### Translation

```bash
curl -X POST http://localhost:8000/v1/translate/ \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, how are you?", "target_lang": "ak"}'
```

---

## Fine-tuning (Ollama custom model)

The `train/` directory contains scripts to fine-tune llama-3.1-8b on 56K curated examples built from the included parquet datasets.

```bash
# 1. Prepare 56K training examples from all parquet datasets
python train/prepare_data.py --out train/delka_train.jsonl

# 2. Train LoRA on GPU (requires unsloth + CUDA — use Colab or RunPod)
python train/train_delka.py

# 3. Export to GGUF and register with Ollama
python train/export_to_ollama.py
ollama create delkaai -f models/Modelfile
```

Datasets included: Anthropic RLHF, Constitutional AI, Claude Reasoning, CodeAlpaca, OpenHermes, SlimOrca, WizardLM, UltraChat, UltraFeedback — all processed with the Delka system prompt injected.

---

## Tests

```bash
pytest tests/ -q
```
