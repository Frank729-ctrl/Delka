# DelkaAI API v1

A self-hosted AI API for CV generation, cover letter writing, and support chat — built with FastAPI, Groq, and Ollama.

---

## What it does

- **CV Generation** — Send structured career data, get back a professionally designed PDF CV
- **Cover Letter Generation** — Send job details and background, get back a tailored PDF cover letter
- **Support Chat** — Real-time streaming chat scoped to your platform (SSE)

---

## Stack

- **FastAPI** — API framework
- **Groq** — Primary LLM provider
- **Ollama** — Fallback LLM (local)
- **WeasyPrint** — PDF generation from HTML templates
- **SQLAlchemy** — ORM (MySQL or Postgres)
- **Argon2** — Password / key hashing
- **Jinja2** — HTML templating

---

## Getting Started

```bash
git clone https://github.com/Frank729-ctrl/hakdel.git
cd hakdel/Delka/delkaAI

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your DB credentials, master key, and Groq API key

uvicorn main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`

---

## Usage

All requests require an API key in the header:

```
X-DelkaAI-Key: fd-delka-sk-your32hexkeyhere
```

Keys are created via the admin endpoint using your master key.

### Generate a CV

```bash
curl -X POST http://localhost:8000/v1/cv/generate \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "summary": "Software engineer with 5 years experience.",
    "experience": [{"company": "Acme", "title": "Engineer", "start_date": "2020-01", "end_date": "present", "bullets": ["Built APIs"]}],
    "education": [{"school": "MIT", "degree": "BSc CS", "year": "2019"}],
    "skills": ["Python", "FastAPI"]
  }'
```

Returns a PDF directly, or a `job_id` if a `webhook_url` is provided.

### Generate a Cover Letter

```bash
curl -X POST http://localhost:8000/v1/letter/generate \
  -H "X-DelkaAI-Key: fd-delka-sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "applicant_name": "Jane Smith",
    "applicant_email": "jane@example.com",
    "company_name": "TechCorp",
    "role_title": "Senior Engineer",
    "body_paragraphs": ["I am excited to apply...", "In my previous role..."]
  }'
```

### Support Chat (streaming)

```bash
curl -X POST http://localhost:8000/v1/support/chat \
  -H "X-DelkaAI-Key: fd-delka-pk-..." \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "message": "How do I add a photo to my CV?", "platform": "myapp"}'
```

---

## Tests

```bash
pytest tests/ -q
```
