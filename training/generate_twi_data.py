#!/usr/bin/env python3
"""
DelkaAI Twi Training Data Generator
=====================================
Generates Twi/Twi-English training examples using:
  1. Verified Twi-English vocabulary pairs (from the provided CSV, cleaned)
  2. Groq to generate natural conversational completions

Three example types:
  A. Translation Q&A: "How do I say X in Twi?" → correct Twi answer
  B. Conversational Twi: user greets/asks in Twi → Delka responds in Twi
  C. Code-switching: user mixes Twi+English → natural bilingual response

Usage:
    python training/generate_twi_data.py

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

# ── Verified Twi vocabulary (correct characters, semantically valid only) ────
# Source: user-provided CSV + plugin spec, cleaned and encoding-fixed
# Format: (twi, english)

GREETINGS = [
    ("Maakye", "Good morning"),
    ("Maaha", "Good afternoon"),
    ("Maadwo", "Good evening"),
    ("Wo ho te sɛn?", "How are you?"),
    ("Me ho yɛ", "I am fine"),
    ("Meda wo ase", "Thank you"),
    ("Meda wo ase paa", "Thank you very much"),
    ("Yɛbɛhyia bio", "See you again"),
    ("Ɛte sɛn?", "What's up?"),
    ("Wo din de sɛn?", "What is your name?"),
    ("Me din de Delka", "My name is Delka"),
    ("Me ho yɛ, na wo nso ɛ?", "I am fine, and you?"),
    ("Ɛhe na worekɔ?", "Where are you going?"),
    ("Mɛba ɔkyena", "I will come tomorrow"),
    ("Yɛ!", "Great! / Well done!"),
    ("Mɛboa wo", "I will help you"),
    ("Mɛboa wo ma wosua Twi no yie", "I will help you learn Twi well"),
]

# Semantically valid verb+object pairs only (not every combo)
VALID_SENTENCES = [
    # Eating and drinking
    ("Me di aduane", "I eat food"),
    ("Wo di aduane", "You eat food"),
    ("Ɔno di aduane", "He/She eats food"),
    ("Me nom nsuo", "I drink water"),
    ("Wo nom nsuo", "You drink water"),
    ("Ɔno nom nsuo", "He/She drinks water"),
    # Going places
    ("Me kɔ sukuukuu", "I go to school"),
    ("Wo kɔ sukuukuu", "You go to school"),
    ("Me kɔ fie", "I go home"),
    ("Wo kɔ fie", "You go home"),
    ("Ɔno kɔ adwumakɔ", "He/She goes to work"),
    # Coming
    ("Me ba fie", "I come home"),
    ("Wo ba fie", "You come home"),
    # Learning
    ("Me sua", "I am learning"),
    ("Me sua Twi", "I am learning Twi"),
    ("Wo sua adwuma no yie", "You are learning the work well"),
    # Working
    ("Me yɛ adwuma", "I work / I am working"),
    ("Wo yɛ adwuma", "You work"),
    ("Ɔno yɛ adwuma", "He/She works"),
    # Preferences
    ("Me pɛ aduane", "I like food"),
    ("Me pɛ nnwom", "I like music"),
    ("Me pɛ film", "I like movies"),
    ("Me pɛ agorɛ", "I like games"),
    ("Me pɛ nwoma", "I like books / I like reading"),
    ("Wo pɛ sɛ yɛkɔ he?", "Where do you want to go?"),
    # Watching / listening
    ("Me hwɛ film", "I watch a movie"),
    ("Me tie nnwom", "I listen to music"),
    ("Me tie wo", "I am listening to you"),
    # Speaking
    ("Ka kyerɛ me", "Tell / explain to me"),
    ("Me ka asɛm", "I am speaking"),
    ("Mesrɛ wo", "Please / I beg you"),
    # Plurals
    ("Yɛn kɔ sukuukuu", "We go to school"),
    ("Yɛn yɛ adwuma", "We work"),
    ("Wɔn di aduane", "They eat food"),
    ("Wɔn nom nsuo", "They drink water"),
]

# Career-specific Twi vocabulary
CAREER_TWI = [
    ("Adwuma", "Job / Work"),
    ("Adwumakɔ", "Workplace"),
    ("Adwumayɛfo", "Worker / Employee"),
    ("Adwumawura", "Employer / Boss"),
    ("Akontaabu", "Accounting / Finance"),
    ("Nhyehyɛe nwoma", "CV / Resume"),
    ("Mpaebɔ nwoma", "Cover letter"),
    ("Sika", "Money"),
    ("Mfaso", "Salary / Benefit"),
    ("Nnwuma nkosuo", "Career development"),
    ("Ano bɔ", "Interview"),
    ("Wɔpɛ sɛ wofa wo", "They want to hire you"),
    ("Adwuma pa", "Good job / Well-paying job"),
    ("Me pɛ adwuma foforo", "I want a new job"),
    ("Merebɛn wo ano", "I am applying (coming to your office)"),
]

# ── System prompt for Twi responses ──────────────────────────────────────────
TWI_SYSTEM = """You are Delka, an AI assistant by DelkaAI, built for Ghanaian professionals.
You are fluent in Asante Twi and speak it naturally.

IMPORTANT TWI RULES:
- Use correct Asante Twi characters: ɛ (epsilon), ɔ (open-o), ŋ as needed
- Keep it natural — speak like an educated Ghanaian who knows Twi well
- For career/professional topics: respond in Twi with English in parentheses for technical terms
- For greetings/small talk: respond fully in Twi
- For code-switching (Twi+English): respond naturally in the same mix
- NEVER invent Twi words — if unsure, use the English term in brackets

VERIFIED TWI VOCABULARY TO USE NATURALLY:
Greetings: Maakye (good morning), Maaha (good afternoon), Maadwo (good evening)
How are you: Wo ho te sɛn? → Me ho yɛ, na wo nso ɛ?
Thank you: Meda wo ase / Meda wo ase paa
Name: Wo din de sɛn? → Me din de Delka
Yes: Aane | No: Daabi | Please: Mesrɛ wo | Sorry: Kafra
Good: Ɛyɛ / Papa | Great: Yɛ! | Help: Mɛboa wo
Work: Adwuma / yɛ adwuma | Job: Adwuma | Salary: Mfaso
CV: Nhyehyɛe nwoma | Cover letter: Mpaebɔ nwoma | Interview: Ano bɔ
I like: Me pɛ | I want: Me pɛ sɛ | I will: Mɛ... | I am: Me yɛ
Going: kɔ | Coming: ba | Eating: di | Drinking: nom | Learning: sua

BEHAVIOR:
- If user speaks Twi → respond in Twi
- If user speaks English → respond in English but add Twi phrases naturally
- If mixed → match the mix
- Ask natural follow-up questions in Twi when appropriate
- For translation requests: give the Twi, pronounce it simply, give a usage example"""

# ── Conversation prompts ───────────────────────────────────────────────────────
# Type A: Translation requests
TRANSLATION_PROMPTS = [
    ("How do I say 'Good morning' in Twi?", "greeting"),
    ("What is 'Thank you' in Twi?", "greeting"),
    ("How do you say 'I am fine' in Twi?", "greeting"),
    ("How do I say 'I want a new job' in Twi?", "career"),
    ("What is 'Cover letter' in Twi?", "career"),
    ("How do I say 'I am a software developer' in Twi?", "career"),
    ("How do you say 'See you tomorrow' in Twi?", "greeting"),
    ("What is 'Salary' in Twi?", "career"),
    ("How do I say 'I am learning' in Twi?", "learning"),
    ("How do you greet someone in the afternoon in Twi?", "greeting"),
    ("What does 'Mesrɛ wo' mean?", "vocab"),
    ("How do I say 'My name is...' in Twi?", "greeting"),
    ("What is 'I work at MTN' in Twi?", "career"),
    ("How do I say 'I am going to work' in Twi?", "career"),
    ("What is 'Interview' in Twi?", "career"),
]

# Type B: Conversational Twi (user writes in Twi)
TWI_CONVERSATION_PROMPTS = [
    "Maakye! Wo ho te sɛn?",
    "Me din de Kofi. Wo nso de sɛn?",
    "Me pɛ adwuma foforo. Boa me.",
    "Me pɛ sɛ mesua CV bɔ. Yɛ ɛte sɛn?",
    "Meda wo ase paa. Wo boa me paa.",
    "Me yɛ accountant. Me pɛ adwuma wɔ Accra.",
    "Mɛba ɔkyena ma ano bɔ. Mesrɛ wo boa me.",
    "Wo din de sɛn? Yɛ adwuma wɔ he?",
    "Me pɛ sɛ mekɔ abroad. Ɛyɛ papa?",
]

# Type C: Code-switching (Twi + English mixed)
CODESWITCHING_PROMPTS = [
    "Me pɛ adwuma sɛ frontend developer. Wo wɔ experience wɔ frontend anaa?",
    "I want to write my CV. Mesrɛ wo boa me.",
    "Me finish KNUST. Now me pɛ job for tech sector.",
    "My interview yɛ ɔkyena at Ecobank. Boa me prepare.",
    "Me wɔ 3 years experience in data analysis. How I write my CV summary?",
    "Me pɛ salary increase. How I go talk to my boss?",
    "I be fresh graduate. Me pɛ National Service posting wɔ Accra.",
    "Me yɛ software developer for 5 years. Me pɛ sɛ me change career to product management.",
]

ALL_PROMPTS = (
    [(p, "translation") for p, _ in TRANSLATION_PROMPTS] +
    [(p, "twi_chat")    for p in TWI_CONVERSATION_PROMPTS] +
    [(p, "codeswitching") for p in CODESWITCHING_PROMPTS]
)


# ── Groq caller ───────────────────────────────────────────────────────────────
async def call_groq(client, prompt: str) -> str | None:
    for attempt in range(4):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": TWI_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
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


async def gen_one(sem, client, idx: int, total: int,
                  prompt: str, ptype: str, out_f) -> bool:
    async with sem:
        await asyncio.sleep(2)
        completion = await call_groq(client, prompt)
        if not completion or len(completion.strip()) < 20:
            print(f"  ⚠️  [{idx}/{total}] empty — skipping")
            return False

        row = {
            "prompt":     prompt,
            "completion": completion.strip(),
            "rating":     5,
            "platform":   "swypply",
            "service":    "chat",
            "model":      MODEL,
            "auto_score": 0.88,
            "language":   f"twi_{ptype}",
        }
        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
        out_f.flush()

        preview = prompt[:55] + ("..." if len(prompt) > 55 else "")
        print(f"  ✅ [{idx}/{total}] [{ptype}] {preview}")
        return True


def add_vocab_rows(out_f) -> int:
    """Add direct translation pairs as training rows (no Groq needed)."""
    count = 0
    all_pairs = GREETINGS + VALID_SENTENCES + CAREER_TWI

    for twi, english in all_pairs:
        # Example 1: English → Twi translation
        row = {
            "prompt":     f"How do I say '{english}' in Twi?",
            "completion": f"In Twi, '{english}' is: **{twi}**\n\nExample: \"{twi}\" — {english}.",
            "rating":     5,
            "platform":   "swypply",
            "service":    "chat",
            "model":      "verified",
            "auto_score": 0.95,
            "language":   "twi_vocab",
        }
        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")

        # Example 2: Twi → English understanding
        row2 = {
            "prompt":     f"What does '{twi}' mean in English?",
            "completion": f"**{twi}** means: \"{english}\"",
            "rating":     5,
            "platform":   "swypply",
            "service":    "chat",
            "model":      "verified",
            "auto_score": 0.95,
            "language":   "twi_vocab",
        }
        out_f.write(json.dumps(row2, ensure_ascii=False) + "\n")
        count += 2

    return count


async def main():
    total_conversational = len(ALL_PROMPTS)

    print("=" * 60)
    print("  DelkaAI — Twi Training Data Generator")
    print("=" * 60)
    print(f"  Vocab pairs (direct) : {len(GREETINGS + VALID_SENTENCES + CAREER_TWI)} × 2 = {len(GREETINGS + VALID_SENTENCES + CAREER_TWI)*2} rows")
    print(f"  Conversational (Groq): {total_conversational} rows")
    print(f"  Output: {OUTPUT_FILE}")
    print("=" * 60)

    from groq import AsyncGroq
    client = AsyncGroq(api_key=GROQ_API_KEY)
    sem = asyncio.Semaphore(CONCURRENCY)

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        # Step 1: Add vocab pairs directly (no API call needed)
        print(f"\n📚 Writing {len(GREETINGS + VALID_SENTENCES + CAREER_TWI)*2} verified vocab pairs…")
        vocab_count = add_vocab_rows(f)
        print(f"  ✅ {vocab_count} vocab rows written")

        # Step 2: Generate conversational examples via Groq
        print(f"\n💬 Generating {total_conversational} conversational Twi examples via Groq…")
        tasks = [
            gen_one(sem, client, i + 1, total_conversational,
                    prompt, ptype, f)
            for i, (prompt, ptype) in enumerate(ALL_PROMPTS)
        ]
        results = await asyncio.gather(*tasks)

    done = sum(1 for r in results if r)
    print()
    print(f"  ✅ Vocab rows   : {vocab_count}")
    print(f"  ✅ Groq rows    : {done}/{total_conversational}")
    print(f"  ✅ Total added  : {vocab_count + done}")

    # Final counts
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
    print(f"  Dataset total: {sum(counts.values())} rows")
    for k, v in sorted(counts.items()):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
