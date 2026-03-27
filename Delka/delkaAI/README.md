# DelkaAI API v1

A professional, self-hosted AI services API for CV generation, cover letter writing, and customer support chat — built on Ollama + FastAPI.

---

## What is DelkaAI?

DelkaAI is a production-grade REST API that exposes three AI-powered services:

- **CV Generation** — Provide structured career data, receive a professionally designed PDF CV.
- **Cover Letter Generation** — Provide job details and background, receive a tailored PDF cover letter.
- **Support Chat (SSE)** — Real-time customer support chat scoped to your platform (Swypply, Hakdel, Plugged Imports, or generic).

All generation is powered by a locally running Ollama LLM. All output is PDF. No data is stored externally.

---

## Architecture

```
Client
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Application (main.py)                          │
│                                                         │
│  Middleware Chain (outermost → innermost):              │
│  CORS → ContentModeration → Jailbreak → KeyPermission   │
│  → APIKey → HMAC → Sanitize → RateLimit → Metrics       │
│  → Logging → ResponseTime → RequestID → IPBlock         │
│  → SecurityHeaders                                      │
│                                                         │
│  Routers:                                               │
│  /v1/health  /v1/cv/generate  /v1/letter/generate       │
│  /v1/support/chat  /v1/admin/*  /admin/dashboard        │
│                                                         │
│  Services:                                              │
│  OllamaService → LanguageService → TemplateService      │
│  OutputValidator → ExportService (WeasyPrint → PDF)     │
│  WebhookService → JobQueue (asyncio)                    │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌────────────────┐       ┌──────────────────┐
     │  Ollama LLM    │       │  MySQL / Postgres │
     │  llama3.1      │       │  (SQLAlchemy)     │
     └────────────────┘       └──────────────────┘
```

---

## Quick Start

### 1. Install and run Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1
ollama serve
```

### 2. Clone and install

```bash
git clone https://github.com/your-username/delkaai.git
cd delkaai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set DB credentials, SECRET_MASTER_KEY, OLLAMA_BASE_URL
```

### 4. Run

```bash
uvicorn main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs` (development mode only).

---

## API Key Types

DelkaAI uses two key types, both with the format `fd-delka-{type}-{32hex}`.

| Type | Prefix | Access |
|------|--------|--------|
| **Publishable** (`pk`) | `fd-delka-pk-` | `/v1/health`, `/v1/support/chat` only |
| **Secret** (`sk`) | `fd-delka-sk-` | All non-admin endpoints |

Keys are created via the admin API with your master key. Raw keys are shown **once** at creation — save them immediately.

Pass the key on every request:
```
X-DelkaAI-Key: fd-delka-sk-your32hexkeyhere
```

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/health` | None | Health + Ollama status |
| `POST` | `/v1/cv/generate` | SK key | Generate CV as PDF |
| `POST` | `/v1/letter/generate` | SK key | Generate cover letter as PDF |
| `POST` | `/v1/support/chat` | PK or SK | SSE support chat stream |
| `POST` | `/v1/admin/keys/create` | Master key | Create key pair |
| `POST` | `/v1/admin/keys/revoke` | Master key | Revoke a key |
| `GET` | `/v1/admin/keys/list` | Master key | List all keys |
| `GET` | `/v1/admin/keys/{prefix}/usage` | Master key | Key usage stats |
| `GET` | `/v1/admin/metrics` | Master key | System metrics |
| `GET` | `/v1/admin/blocked-ips` | Master key | Blocked IP list |
| `POST` | `/v1/admin/unblock-ip` | Master key | Unblock an IP |
| `GET` | `/v1/admin/jobs/{job_id}` | Master key | Async job status |
| `GET` | `/admin/dashboard` | `?master_key=` | Admin web UI |

---

## Webhook Usage

Pass `webhook_url` in your CV or cover letter request to receive the PDF asynchronously:

```json
POST /v1/cv/generate
{
  "full_name": "Jane Smith",
  "email": "jane@example.com",
  ...
  "webhook_url": "https://your-server.com/hooks/delkaai"
}
```

Response `202`:
```json
{ "status": "success", "message": "CV generation queued.", "data": { "job_id": "uuid" } }
```

Your webhook receives a `POST` with:
```json
{
  "job_id": "...",
  "status": "complete",
  "event": "cv.generated",
  "data": { "pdf_base64": "...", "template": "modern_sidebar" },
  "timestamp": "..."
}
```

The payload is signed — verify with `X-DelkaAI-Signature` header (HMAC-SHA256).

---

## Docker Deployment

```bash
cp .env.example .env
# Fill in production values in .env

docker compose up -d --build
```

The `api` service waits for MySQL to pass its healthcheck before starting.

Logs are mounted to `./logs/` on the host.

---

## GitHub Actions Secrets

For the CI/CD deploy job, set these repository secrets:

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Production server IP or hostname |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_SSH_KEY` | Private SSH key (no passphrase) |
| `DEPLOY_PATH` | Absolute path to project on server |
| `DEPLOY_PORT` | SSH port (default 22) |

---

## ⚠️ Security Notice

**Never commit your `.env` file.** It contains your master key, database password, and HMAC secrets.

The `.gitignore` blocks `.env` and all `*.env` files. Double-check with `git status` before every push.

---

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Write tests for new behaviour.
4. Ensure `pytest tests/ --cov --cov-fail-under=80` passes.
5. Open a pull request against `main`.

Please do **not** open public issues for security vulnerabilities — see `SECURITY.md`.
