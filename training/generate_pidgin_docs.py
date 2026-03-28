#!/usr/bin/env python3
"""
DelkaAI Pidgin CV & Cover Letter Training Data Generator
=========================================================
Generates examples where the USER writes in Pidgin but the OUTPUT
is a proper professional English CV or cover letter.

This teaches the model:
  - Understand informal/Pidgin requests
  - Always produce clean, professional English documents

Usage:
    python training/generate_pidgin_docs.py

Appends to training/synthetic_data.jsonl
"""

import asyncio
import json
import os
import random
import sys
from pathlib import Path

# ── Load .env ─────────────────────────────────────────────────────────────────
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    sys.exit("❌  GROQ_API_KEY not set.")

OUTPUT_FILE = Path(__file__).parent / "synthetic_data.jsonl"
MODEL       = "llama-3.1-8b-instant"
CONCURRENCY = 2

# ── Ghanaian data pools ───────────────────────────────────────────────────────
NAMES = [
    "Kwame Asante", "Abena Mensah", "Kofi Boateng", "Akosua Acheampong",
    "Yaw Darko", "Adwoa Frimpong", "Fiifi Amponsah", "Naa Korkor",
    "Samuel Ofori", "Grace Tetteh", "Daniel Adjei", "Linda Darko",
    "Patrick Antwi", "Rose Ankrah", "Eric Kusi", "Faustina Asare",
    "Nii Armah", "Fatima Alhassan", "Stephen Appiah", "Mary Osei",
]

ROLES = [
    ("Software Developer", "tech", 3), ("Data Analyst", "tech", 2),
    ("Marketing Officer", "marketing", 4), ("Accountant", "finance", 5),
    ("HR Officer", "hr", 3), ("Civil Engineer", "engineering", 6),
    ("Nurse", "health", 4), ("Teacher", "education", 5),
    ("Graphic Designer", "creative", 2), ("Sales Executive", "sales", 3),
    ("Business Developer", "business", 4), ("Procurement Officer", "operations", 5),
    ("Brand Strategist", "marketing", 3), ("Financial Analyst", "finance", 4),
    ("Frontend Developer", "tech", 2), ("Electrical Engineer", "engineering", 7),
    ("Communications Officer", "comms", 3), ("Logistics Officer", "operations", 4),
]

COMPANIES = [
    "MTN Ghana", "Vodafone Ghana", "Ecobank Ghana", "GCB Bank",
    "Standard Chartered Ghana", "Absa Ghana", "Access Bank Ghana",
    "Ghana Health Service", "KNUST", "University of Ghana",
    "Unilever Ghana", "TotalEnergies Ghana", "Tullow Oil Ghana",
    "Hubtel", "Zeepay", "ExpressPay", "Fidelity Bank Ghana",
    "COCOBOD", "GNPC", "Electoral Commission",
]

SCHOOLS = [
    "University of Ghana (Legon)", "KNUST", "University of Cape Coast",
    "Ashesi University", "Ghana Institute of Management and Public Administration (GIMPA)",
    "Accra Technical University", "Ho Technical University",
]

LOCATIONS = ["Accra", "Kumasi", "Takoradi", "Tamale", "Cape Coast", "Sunyani"]

# ── Pidgin request templates ───────────────────────────────────────────────────
CV_PIDGIN_REQUESTS = [
    "Chale make you write my CV for me. I be {role} for {company} for {yoe} years. I study {degree} for {school}. I dey for {location}.",
    "Help me do my CV. I work as {role} at {company} — {yoe} years experience. My school be {school}.",
    "Herh I need CV urgently. I be {role}, {yoe} years for the field. I finish {school}. I dey {location}.",
    "Chale abeg write proper CV for me. I get {yoe} years experience as {role} for {company}. {school} graduate.",
    "Make you create professional CV for this person: {name}, {role} at {company}, {yoe} years exp, {school} graduate, based in {location}.",
    "I want good CV. I be {name}, I work as {role} for {company} for {yoe} years. I dey {location}. {school} alumnus.",
    "Please write my full CV. Role: {role}. Company: {company}. Years: {yoe}. School: {school}. Location: {location}.",
    "Ei help me with my CV! I be {role} for {yoe} years, I work for {company} before, I study for {school}.",
]

LETTER_PIDGIN_REQUESTS = [
    "Make you write cover letter for me. I dey apply for {role} at {company}. I get {yoe} years experience for this field. I be {school} graduate.",
    "Chale I need cover letter for {role} position at {company}. I get {yoe} years experience. Help me write am professional.",
    "Herh the deadline dey tomorrow. Make you write cover letter for {role} job at {company} for me. I get {yoe} years for {role} work.",
    "I dey apply for {role} role at {company}. Abeg write nice cover letter for me. I fit show {yoe} years experience.",
    "Please I need cover letter ASAP. Applying for {role} at {company}. {yoe} years experience, {school} graduate.",
    "Write professional cover letter for my job application. Position: {role}. Company: {company}. My experience: {yoe} years.",
    "Chale make the cover letter sound confident. I be applying for {role} at {company}. {yoe} years experience for the field.",
    "I want apply for {role} at {company}. Can you write the cover letter? I dey experienced — {yoe} years.",
]

# ── System prompts (output must ALWAYS be professional English) ───────────────
CV_SYSTEM = """You are a world-class CV/resume writer specializing in Ghanaian professional standards.

The user may write their request in Ghanaian Pidgin English or informal language.
Regardless of how the request is phrased, your output must ALWAYS be a complete,
polished, professional CV written in proper formal English.

Output ONLY a valid JSON object with these exact fields:
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "title": "string (job title / professional headline)",
  "summary": "string (3-4 sentence professional summary in formal English)",
  "experience": [{"company": "", "title": "", "start_date": "", "end_date": "", "bullets": ["", ""]}],
  "education": [{"school": "", "degree": "", "field": "", "year": ""}],
  "skills": ["skill1", "skill2"],
  "linkedin": "",
  "website": ""
}

No markdown. No code fences. No explanation. Raw JSON only.
Fill in realistic details based on the role and experience mentioned."""

LETTER_SYSTEM = """You are a world-class cover letter writer specializing in Ghanaian professional context.

The user may write their request in Ghanaian Pidgin English or informal language.
Regardless of how the request is phrased, your output must ALWAYS be a complete,
polished, professional cover letter written in proper formal English.

Write exactly 3-4 paragraphs. Open with a strong hook (not "I am writing to express my interest").
End with a confident call to action. No subject line. No address header. No markdown.
Output ONLY the letter body text in formal English."""


def make_cv_prompt() -> tuple[str, str]:
    """Returns (pidgin_request, service_tag)"""
    name = random.choice(NAMES)
    role, _, yoe = random.choice(ROLES)
    company = random.choice(COMPANIES)
    school = random.choice(SCHOOLS)
    location = random.choice(LOCATIONS)
    degree = random.choice(["BSc", "BA", "BEng", "HND", "MBA", "MSc"])
    template = random.choice(CV_PIDGIN_REQUESTS)
    prompt = template.format(
        name=name, role=role, company=company,
        yoe=yoe, school=school, location=location, degree=degree,
    )
    return prompt, "cv"


def make_letter_prompt() -> tuple[str, str]:
    """Returns (pidgin_request, service_tag)"""
    _, role, yoe = random.choice(ROLES)
    role_name, _, yoe = random.choice(ROLES)
    company = random.choice(COMPANIES)
    school = random.choice(SCHOOLS)
    template = random.choice(LETTER_PIDGIN_REQUESTS)
    prompt = template.format(
        role=role_name, company=company, yoe=yoe, school=school,
    )
    return prompt, "letter"


# ── Groq caller ───────────────────────────────────────────────────────────────
async def call_groq(client, system: str, user: str) -> str | None:
    for attempt in range(4):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.65,
                max_tokens=1200,
            )
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                wait = 30 * (attempt + 1)
                print(f"  ⏳ Rate limited — waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"  ❌ Error (attempt {attempt+1}): {err[:80]}")
                await asyncio.sleep(5)
    return None


async def gen_one(sem, client, idx: int, total: int, prompt: str,
                  system: str, service: str, out_f) -> bool:
    async with sem:
        await asyncio.sleep(2)
        raw = await call_groq(client, system, prompt)
        if not raw or len(raw.strip()) < 80:
            print(f"  ⚠️  [{idx}/{total}] {service} — empty, skipping")
            return False

        # strip code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        row = {
            "prompt":     prompt,
            "completion": text,
            "rating":     5,
            "platform":   "swypply",
            "service":    service,
            "model":      MODEL,
            "auto_score": 0.88,
            "language":   "pidgin_input",   # input is Pidgin, output is formal English
        }
        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
        out_f.flush()

        preview = prompt[:60] + ("..." if len(prompt) > 60 else "")
        print(f"  ✅ [{idx}/{total}] {service}: {preview}")
        return True


async def main():
    CV_TARGET     = 20
    LETTER_TARGET = 20
    total         = CV_TARGET + LETTER_TARGET

    print("=" * 60)
    print("  DelkaAI — Pidgin CV & Cover Letter Generator")
    print("=" * 60)
    print(f"  CV examples     : {CV_TARGET}")
    print(f"  Letter examples : {LETTER_TARGET}")
    print(f"  Total           : {total}")
    print(f"  Output          : {OUTPUT_FILE}")
    print("=" * 60)

    from groq import AsyncGroq
    client = AsyncGroq(api_key=GROQ_API_KEY)
    sem = asyncio.Semaphore(CONCURRENCY)

    tasks = []
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        # CV tasks
        print(f"\n📄 Generating {CV_TARGET} Pidgin-request CV examples…")
        cv_tasks = [
            gen_one(sem, client, i + 1, CV_TARGET,
                    make_cv_prompt()[0], CV_SYSTEM, "cv", f)
            for i in range(CV_TARGET)
        ]
        cv_results = await asyncio.gather(*cv_tasks)

        # Letter tasks
        print(f"\n✉️  Generating {LETTER_TARGET} Pidgin-request letter examples…")
        letter_tasks = [
            gen_one(sem, client, i + 1, LETTER_TARGET,
                    make_letter_prompt()[0], LETTER_SYSTEM, "letter", f)
            for i in range(LETTER_TARGET)
        ]
        letter_results = await asyncio.gather(*letter_tasks)

    cv_done     = sum(1 for r in cv_results if r)
    letter_done = sum(1 for r in letter_results if r)

    print()
    print(f"  ✅ CV done     : {cv_done}/{CV_TARGET}")
    print(f"  ✅ Letter done : {letter_done}/{LETTER_TARGET}")

    # Final totals
    counts: dict[str, int] = {}
    with open(OUTPUT_FILE) as f:
        for line in f:
            try:
                row = json.loads(line)
                svc = row.get("service", "?")
                counts[svc] = counts.get(svc, 0) + 1
            except Exception:
                pass

    print()
    print(f"  Total rows now: {sum(counts.values())}")
    for k, v in sorted(counts.items()):
        print(f"    {k}: {v}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
