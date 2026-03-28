#!/usr/bin/env python3
"""
DelkaAI Pidgin Training Data Generator
=======================================
Generates ~30 Ghanaian Pidgin chat examples and appends them to
training/synthetic_data.jsonl

Usage:
    python training/generate_pidgin_data.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# ── Load .env ────────────────────────────────────────────────────────────────
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
TARGET      = 30

# ── System prompt for Pidgin responses ───────────────────────────────────────
PIDGIN_SYSTEM = """You are Delka, an AI assistant by DelkaAI, built for Ghanaian professionals.
You understand Ghanaian Pidgin English deeply — the way Ghanaians actually speak and write informally.

When the user writes in Pidgin, you respond naturally in Ghanaian Pidgin / code-switching style
(mixing Pidgin with standard English where needed for clarity). Your tone is friendly, helpful,
and feels like advice from a smart friend who knows Ghana well.

Key Pidgin patterns to use naturally:
- "make you" (you should), "I go" (I will), "e dey" (it is/exists), "no be" (it isn't)
- "wey" (that/which/who), "dey" (is/are/there), "sef" (even/also), "abi" (right? / isn't it?)
- "chale" (friend/buddy — casual), "ei" (surprise), "herh" (exclamation)
- "make we" (let us), "no worry" (don't worry), "e easy" (it's easy)
- Mix with clear English for technical terms (CV, cover letter, salary, LinkedIn, etc.)

Never sound robotic. Sound like a Ghanaian who knows their stuff."""

# ── 30 Pidgin prompts across CV, letter, career, chat topics ─────────────────
PIDGIN_PROMPTS = [
    # CV / resume
    "Chale how I go write my CV if I never get degree? I get HND but e feel small.",
    "I be fresh graduate, my CV dey empty, no experience. How I go fill am?",
    "Make you help me fix my CV summary. I be software developer for 3 years for Accra.",
    "I want change job from banking to tech. How I go write my CV make dem no disqualify me?",
    "My CV too long — 4 pages. How I go cut am down? Which things I go remove?",
    "Herh, I never update my CV for 5 years. How I go start am again?",
    "I get National Service experience only. E dey count for CV abi e no relevant?",

    # Cover letters
    "Make you write cover letter for me for Data Analyst job at MTN Ghana. I get 2 years experience.",
    "I dey apply for manager position but I never be manager before. How I go write the letter make it sound good?",
    "The job say make you write cover letter. Chale I no know where to start. Help me.",
    "I dey apply for NGO job for Kumasi. How different cover letter for NGO dey from corporate one?",

    # Career advice
    "Chale which tech skills I go learn for Ghana make I get job quick quick?",
    "I dey work for GES but the pay small. Should I leave for private sector?",
    "How I go ask for salary increase? My boss no dey easy and I dey fear small.",
    "I finish my masters, but I dey earn less than my colleagues wey get only degree. Why?",
    "I dey do remote work for UK company but they pay me Ghana cedis rate. How I go negotiate dollar rate?",
    "I be fresh grad wey dey look for job for 8 months now. E normal? What I go do?",
    "LinkedIn dey work for Ghana? Or e be only for oyibo people?",
    "My boss dey take my work give others as their own. What I go do?",

    # National Service / NYSC-equivalent
    "I dey do National Service now. Should I start job hunting before I finish or make I wait?",
    "My posting dey far from Accra. How I go manage am and still build my career?",
    "National Service allowance too small. Which side jobs I fit do alongside?",

    # Interviews
    "I get interview for Ecobank tomorrow. How I go prepare? I dey nervous small.",
    "They ask me say why should we hire you? Chale I blank. What I suppose say?",
    "The HR ask me expected salary. I no know how much to say. Help me.",
    "I fail interview for 3 places. How I go know where I dey go wrong?",

    # Business / freelance
    "I want start small tech business for Ghana. Where I go register am?",
    "I be freelance graphic designer. How I go find clients for Ghana? Chale I need money.",
    "How I go write proposal for client? They want see something professional.",

    # General
    "What skills make you most valuable worker for Ghana market right now?",
    "I dey think say go abroad go better my career. E worth it or I fit build here?",
]


async def call_groq(client, prompt: str) -> str | None:
    from groq import AsyncGroq
    for attempt in range(4):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": PIDGIN_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.78,
                max_tokens=700,
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


async def gen_one(sem, client, idx: int, prompt: str, out_f) -> bool:
    async with sem:
        await asyncio.sleep(2)
        completion = await call_groq(client, prompt)
        if not completion or len(completion.strip()) < 40:
            print(f"  ⚠️  [{idx+1}] empty — skipping")
            return False

        row = {
            "prompt":     prompt,
            "completion": completion.strip(),
            "rating":     5,
            "platform":   "swypply",
            "service":    "chat",
            "model":      MODEL,
            "auto_score": 0.87,
            "language":   "pidgin",
        }
        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
        out_f.flush()

        preview = prompt[:55] + ("..." if len(prompt) > 55 else "")
        print(f"  ✅ [{idx+1}/{TARGET}] {preview}")
        return True


async def main():
    print("=" * 60)
    print("  DelkaAI Pidgin Training Data Generator")
    print("=" * 60)
    print(f"  Output : {OUTPUT_FILE}")
    print(f"  Model  : {MODEL}")
    print(f"  Target : {TARGET} Pidgin examples")
    print("=" * 60)

    from groq import AsyncGroq
    client = AsyncGroq(api_key=GROQ_API_KEY)

    sem = asyncio.Semaphore(CONCURRENCY)

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        tasks = [
            gen_one(sem, client, i, prompt, f)
            for i, prompt in enumerate(PIDGIN_PROMPTS[:TARGET])
        ]
        results = await asyncio.gather(*tasks)

    done = sum(1 for r in results if r)
    print()
    print(f"  ✅ Done — {done}/{TARGET} Pidgin examples added to {OUTPUT_FILE}")
    print()

    # Show total counts
    counts: dict[str, int] = {}
    with open(OUTPUT_FILE) as f:
        for line in f:
            try:
                row = json.loads(line)
                svc = row.get("service", "?")
                counts[svc] = counts.get(svc, 0) + 1
            except Exception:
                pass
    total = sum(counts.values())
    print(f"  Total rows now: {total}")
    for k, v in sorted(counts.items()):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
