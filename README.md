# DelkaAI API v2

A self-hosted AI API for Ghanaian professionals and businesses — built with FastAPI, multi-provider LLM routing, a full plugin ecosystem, and a disk-based skills system with slash commands.

---

## What it does

| Service | Description |
|---|---|
| **CV Generation** | Send career data or raw text → professionally designed PDF |
| **Cover Letter** | Send job details → tailored PDF cover letter |
| **Chat** | Streaming SSE chat with memory, plugins, web search, skills |
| **Support Chat** | Platform-scoped streaming support chat |
| **Voice** | Full duplex voice pipeline: audio in → STT → LLM → TTS → audio out |
| **OCR** | Extract text from images |
| **Speech-to-Text** | Transcribe audio files (multi-format, Ghana keyterm-biased) |
| **Text-to-Speech** | Generate spoken audio (Ghana English voice) |
| **Translation** | Translate text between 100+ languages |
| **Code Generation** | Write, explain, and auto-run code in any language |
| **Object Detection** | Identify objects in images |
| **Image Generation** | Create images from text prompts |
| **Visual Search** | Search a product image index by image or text |
| **Document Q&A** | Ask questions about uploaded PDFs or text documents |
| **Notebooks** | Interactive cell-by-cell code execution sessions, export to .ipynb |
| **Code Sandbox** | Safe Python/JS execution — auto-verifies generated code works |
| **Document Diff** | Word and section-level diff between two document versions |
| **Workspace** | Per-user cloud file store — upload, read, search, edit across sessions |
| **Scheduled Tasks** | User-defined recurring AI tasks with webhook delivery |

---

## Slash Commands (Skills)

Users type `/skill [input]` directly in chat. Delka resolves the command, runs it through the matching LLM, and returns the result in the same stream.

### Built-in skills (always available)

| Command | Aliases | What it does |
|---|---|---|
| `/help` | — | List all available skills |
| `/summarize [text]` | `/summary`, `/tldr` | Summarize text into key points |
| `/translate [text] to [lang]` | `/tr` | Translate text to any language |
| `/explain [code or concept]` | `/what` | Explain code or a concept simply |
| `/improve [text]` | `/fix`, `/polish` | Fix grammar, clarity, and flow |
| `/email [who, purpose, points]` | `/mail` | Draft a professional email with subject line |
| `/cv [what you need]` | `/resume` | CV coaching for the Ghanaian job market |
| `/debug [code]` | `/fix-code` | Identify and fix bugs in code |
| `/brainstorm [topic]` | `/ideas` | Generate 5 creative, practical ideas |
| `/roast [your work]` | `/critique`, `/feedback` | Brutally honest constructive feedback |

### Ghana-context skills (disk-loaded)

| Command | Aliases | What it does |
|---|---|---|
| `/ghana-news [topic]` | `/news`, `/ghana` | Latest Ghana news — top 3–5 stories summarised |
| `/cover-letter [role] at [company]` | `/letter`, `/cl` | Professional cover letter for job applications |
| `/simplify [text]` | `/plain`, `/eli5`, `/simple` | Rewrite complex text in plain English |
| `/interview-prep [role] at [company]` | `/interview`, `/prep` | 5 likely questions + model answers + what to ask |
| `/salary-negotiation [role, offer, experience]` | `/salary`, `/negotiate`, `/pay` | Script + strategy for salary negotiation |

### How to add custom skills

Drop a `.md` file in the `skills/` directory — it hot-reloads within 60 seconds without restarting the server:

```
skills/
  my-skill.md
```

File format:

```markdown
---
name: my-skill
description: Does something useful
aliases: [ms, myskill]
argument-hint: "[your input here]"
when-to-use: When the user asks about X
model: groq
---

Your prompt template here. Use {args} for user input.
```

Or create a skill via the admin API (no file needed):

```bash
curl -X POST http://localhost:8000/v1/skills \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "my-platform",
    "name": "ui-designer",
    "description": "Get UI design advice and wireframe ideas",
    "prompt_template": "Give UI/UX design advice for: {args}. Focus on mobile-first design for Ghanaian users.",
    "aliases": ["ui", "design", "ux"],
    "argument_hint": "[describe the screen or feature]"
  }'
```

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

## Chat Plugins (auto-triggered, no slash command needed)

| Plugin | Trigger | Source |
|---|---|---|
| **Calculator** | Math expressions | AST-based (no eval) |
| **Date/Time** | "what time", "today" | Ghana time (GMT+0) |
| **Currency** | "GHS rate", "convert cedis" | frankfurter.app |
| **Weather** | "weather in Accra" | wttr.in |
| **Wikipedia** | Facts about people/places | Wikipedia API |
| **Bible** | Scripture references | bible-api.com |
| **YouTube** | "find a tutorial on..." | YouTube Data API |
| **News** | "latest news" | GNews API |
| **Web Search** | Current events, recent info | Tavily AI search |
| **WebFetch** | URLs pasted in chat | Fetches + cleans HTML |
| **Workspace** | "in my files", "my documents" | User's cloud file store |

---

## Cognitive Features

| Feature | What it does |
|---|---|
| **Plan mode** | Auto-detects complex requests, streams a structured plan before responding |
| **Adaptive length** | Detects brief/detailed/bullets/code-only intent from message patterns |
| **User settings** | Learns preferences from chat ("always in French", "use bullet points") |
| **Speculation** | Pre-generates 3 follow-up questions after each reply |
| **Relevant memory** | AI selects which memories are relevant per query (not all memories injected) |
| **Team memory** | Platform-level shared facts injected into every session |
| **Away summary** | Recaps what happened if user returns after 30+ min |
| **Context analytics** | Warns before hitting context window limit, emits SSE event |
| **Auto-compact** | Summarises old history to free context window |
| **Tool attribution** | Appends `Sources: 🌐 Web search · 🌤 Weather` footnote |
| **Tips** | Rotating usage tips shown once per user |
| **Code diagnostics** | Security scan + confidence score on every generated code snippet |
| **LSP feedback** | Streams real-time diagnostic events token-by-token during code generation |
| **Code sandbox** | Auto-runs generated Python/JS to verify it works before returning |
| **Document diff** | Before/after word and section diff on every document rewrite |
| **Isolated contexts** | Each coordinator subtask gets its own memory bubble (no cross-bleed) |
| **Cron tasks** | User-defined recurring AI tasks with webhook delivery |
| **Analytics** | Self-hosted event pipeline, feature flags, hourly metrics dashboard |
| **Cost tracking** | USD cost estimates per request per provider |
| **Policy limits** | Per-platform daily quotas — soft (80%) warn, hard (100%) block |
| **Notifier** | Webhook POST + Resend email + SSE event on async job completion |

---

## Voice

Full duplex voice pipeline — audio in, audio out.

```
User speaks → STT (Groq Whisper) → LLM → TTS (edge-tts Ghana voice) → User hears
```

**Ghana-specific STT keyterm biasing**: Whisper is given 200+ vocabulary hints covering Ghana places, currencies, institutions, job titles, and coding terms so it transcribes Ghanaian speech accurately.

| Endpoint | Description |
|---|---|
| `POST /v1/voice/sessions` | Start a voice session |
| `POST /v1/voice/chat` | Full round trip — returns audio_base64 |
| `POST /v1/voice/chat/stream` | SSE: transcript → tokens → audio_ready → done |
| `GET /v1/voice/audio/{session_id}` | Fetch TTS audio after streaming |
| `POST /v1/voice/transcribe` | STT only (with keyterm biasing + confidence score) |
| `GET /v1/voice/keyterms` | List all Ghana + coding keyterms |

---

## Stack

- **FastAPI** — API framework with SSE streaming
- **Groq** — Primary chat/support LLM + Whisper STT
- **Google Gemini 2.5 Pro** — Primary CV/letter LLM
- **Cerebras** — Primary code generation LLM (Qwen3-235B free)
- **NVIDIA NIM** — OCR, STT, TTS, translation, image gen, safety layer
- **Ollama** — Local fallback LLM
- **Cohere** — Text embeddings (RAG/reranking)
- **edge-tts** — Ghana English TTS voice (Microsoft, free, no key)
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
| `RESEND_API_KEY` | resend.com | Free tier (job notifications) |
| `ASSEMBLYAI_API_KEY` | assemblyai.com | Free tier (STT fallback) |

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

## API Endpoints

### Chat & Voice
| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/chat` | Streaming SSE chat |
| `POST` | `/v1/voice/chat` | Full voice round trip |
| `POST` | `/v1/voice/chat/stream` | Streaming voice (SSE) |
| `POST` | `/v1/voice/transcribe` | STT only |

### Skills
| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/skills` | List all skills |
| `POST` | `/v1/skills` | Create platform skill (DB) |
| `PUT` | `/v1/skills/{name}` | Update skill |
| `DELETE` | `/v1/skills/{name}` | Deactivate skill |
| `POST` | `/v1/skills/reload` | Force hot-reload from disk |
| `POST` | `/v1/skills/{name}/run` | Test-run a skill |

### Documents & Workspace
| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/workspace/files` | Upload file |
| `GET` | `/v1/workspace/files` | List files |
| `GET` | `/v1/workspace/files/{name}` | Read file |
| `PUT` | `/v1/workspace/files/{name}` | Edit file (targeted replace) |
| `DELETE` | `/v1/workspace/files/{name}` | Delete file |
| `GET` | `/v1/workspace/search` | Search across all files |
| `POST` | `/v1/doc/ask` | Ask question about uploaded doc |
| `POST` | `/v1/diff` | Diff two text documents |
| `POST` | `/v1/diff/versions` | Diff two saved CV versions |

### Code
| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/code/generate` | Generate code |
| `POST` | `/v1/code/run` | Execute Python/JS in sandbox |
| `POST` | `/v1/notebook/sessions` | Create notebook session |
| `POST` | `/v1/notebook/sessions/{id}/run` | Run a cell |
| `GET` | `/v1/notebook/sessions/{id}/export` | Export as .ipynb |

### Scheduled Tasks
| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/cron/tasks` | Create recurring task |
| `GET` | `/v1/cron/tasks` | List tasks |
| `DELETE` | `/v1/cron/tasks/{id}` | Delete task |

### Analytics & Admin
| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/admin/analytics/metrics` | Hourly metrics dashboard |
| `GET` | `/v1/admin/analytics/flags/{flag}` | Get feature flag |
| `POST` | `/v1/admin/analytics/flags` | Set feature flag |

---

## Usage Examples

### Use a slash command in chat

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-DelkaAI-Key: fd-delka-pk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "message": "/interview-prep Software Engineer at Hubtel",
    "platform": "delkaai-console"
  }'
```

### Create a custom skill via API

```bash
curl -X POST http://localhost:8000/v1/skills \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "my-app",
    "name": "ui-designer",
    "description": "Get UI design advice and wireframe ideas",
    "prompt_template": "Give mobile-first UI/UX advice for Ghanaian users: {args}",
    "aliases": ["ui", "ux", "design"],
    "argument_hint": "[describe the screen or feature]"
  }'
```

### Full voice round trip

```bash
curl -X POST http://localhost:8000/v1/voice/chat \
  -H "X-DelkaAI-Key: fd-delka-pk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "audio_base64": "<base64-encoded-mp3>",
    "audio_format": "mp3",
    "session_id": "voice-session-1",
    "user_id": "user-123",
    "platform": "delkaai-mobile",
    "language": "en",
    "voice": "en-GH-AmaNewscast"
  }'
```

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

### Run code in sandbox

```bash
curl -X POST http://localhost:8000/v1/code/run \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{"code": "print(sum(range(1, 101)))", "language": "python"}'
```

### Schedule a recurring AI task

```bash
curl -X POST http://localhost:8000/v1/cron/tasks \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "platform": "my-app",
    "prompt": "Summarise the top 3 Ghana business news stories",
    "schedule": "every_morning",
    "webhook_url": "https://myapp.com/hooks/daily-briefing"
  }'
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

## Adding Skills via Disk (hot-reload)

Place any `.md` file in the `skills/` folder. No restart needed — reloads within 60 seconds.

```
skills/
  ghana-news.md          ← /ghana-news, /news, /ghana
  cover-letter.md        ← /cover-letter, /letter, /cl
  simplify.md            ← /simplify, /plain, /eli5
  interview-prep.md      ← /interview-prep, /interview, /prep
  salary-negotiation.md  ← /salary-negotiation, /salary, /negotiate
  your-skill.md          ← /your-skill
```

Or set `SKILLS_DIR=/path/to/your/skills` in `.env` to mount an external directory.

---

## Tests

```bash
pytest tests/ -q
```
