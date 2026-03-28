#!/usr/bin/env python3
"""
DelkaAI Synthetic Training Data Generator
==========================================
Generates 300 high-quality Ghanaian-context training examples using Groq.
  - 120 CV generation examples
  -  80 cover letter examples
  - 100 chat / career-advice Q&A pairs

Usage (from project root):
    python training/generate_synthetic_data.py

Output:
    training/synthetic_data.jsonl  — ready to merge with real data for Colab
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

# ── Load .env from project root ─────────────────────────────────────────────
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    sys.exit("❌  GROQ_API_KEY not found in .env — cannot continue.")

OUTPUT_FILE  = Path(__file__).parent / "synthetic_data.jsonl"
MODEL        = "llama-3.1-8b-instant"  # high RPM/TPM limits; good quality for training data
PLATFORM     = "swypply"
CONCURRENCY  = 3        # parallel requests — 8b-instant handles higher concurrency
CV_COUNT     = 120
LETTER_COUNT = 80
CHAT_COUNT   = 100

# ── Ghanaian data pools ──────────────────────────────────────────────────────

MALE_NAMES = [
    "Kwame Asante", "Kofi Mensah", "Yaw Boateng", "Kweku Acheampong",
    "Kwabena Owusu", "Fiifi Aidoo", "Nii Armah", "Alhassan Dramani",
    "Abubakari Sulemana", "Emmanuel Tetteh", "George Ankrah", "Isaac Darko",
    "Joseph Amponsah", "Michael Amoah", "Richard Osei", "Samuel Ofori",
    "Daniel Adjei", "Benjamin Asare", "Frank Frimpong", "Eric Kusi",
    "Patrick Antwi", "Charles Opoku", "Stephen Appiah", "Andrew Baffoe",
    "David Quaye", "Joshua Lartey", "Peter Agyemang", "Paul Akoto",
]
FEMALE_NAMES = [
    "Ama Owusu", "Abena Mensah", "Akua Boateng", "Akosua Asante",
    "Adwoa Acheampong", "Yaa Amponsah", "Afia Asare", "Naa Korkor",
    "Fatima Alhassan", "Grace Tetteh", "Judith Ankrah", "Linda Darko",
    "Mary Adjei", "Nancy Frimpong", "Patricia Kusi", "Rose Antwi",
    "Sandra Opoku", "Theresa Appiah", "Victoria Baffoe", "Wendy Quaye",
    "Janet Lartey", "Cecilia Agyemang", "Beatrice Akoto", "Eunice Osei",
]
ALL_NAMES = MALE_NAMES + FEMALE_NAMES

ROLES = [
    ("Software Engineer",      "Technology"),
    ("Data Analyst",           "Technology"),
    ("Frontend Developer",     "Technology"),
    ("Backend Developer",      "Technology"),
    ("DevOps Engineer",        "Technology"),
    ("Product Manager",        "Technology"),
    ("Accountant",             "Finance"),
    ("Financial Analyst",      "Finance"),
    ("Audit Officer",          "Finance"),
    ("Credit Officer",         "Finance"),
    ("Marketing Manager",      "Marketing"),
    ("Brand Strategist",       "Marketing"),
    ("Digital Marketer",       "Marketing"),
    ("Sales Executive",        "Sales"),
    ("Business Developer",     "Business"),
    ("Project Manager",        "Management"),
    ("Operations Manager",     "Operations"),
    ("HR Officer",             "Human Resources"),
    ("Recruitment Specialist", "Human Resources"),
    ("Nurse",                  "Healthcare"),
    ("Pharmacist",             "Healthcare"),
    ("Clinical Officer",       "Healthcare"),
    ("Doctor",                 "Healthcare"),
    ("Civil Engineer",         "Engineering"),
    ("Electrical Engineer",    "Engineering"),
    ("Mechanical Engineer",    "Engineering"),
    ("Quantity Surveyor",      "Construction"),
    ("Architect",              "Construction"),
    ("Teacher",                "Education"),
    ("Lecturer",               "Education"),
    ("Supply Chain Officer",   "Logistics"),
    ("Procurement Officer",    "Logistics"),
    ("Legal Officer",          "Legal"),
    ("Compliance Officer",     "Legal"),
    ("Communications Officer", "Media"),
    ("Journalist",             "Media"),
]

COMPANIES = [
    # Telecom
    "MTN Ghana", "Vodafone Ghana", "AirtelTigo", "Surfline Communications",
    # Banking
    "GCB Bank", "Ecobank Ghana", "Absa Ghana", "Standard Chartered Ghana",
    "CalBank", "Access Bank Ghana", "Fidelity Bank Ghana", "Consolidated Bank Ghana",
    # Oil & Gas / Energy
    "GNPC", "TotalEnergies Ghana", "Tullow Oil Ghana", "Radiance Energy",
    "BOST", "Ghana Grid Company (GRIDCo)", "Electricity Company of Ghana (ECG)",
    # Healthcare
    "Korle Bu Teaching Hospital", "Komfo Anokye Teaching Hospital",
    "37 Military Hospital", "Ghana Health Service", "Lister Hospital",
    # Tech / Fintech
    "Hubtel", "ExpressPay", "Rancard Solutions", "mPharma", "Farmerline",
    "Zeepay", "Payswitch", "Dream Oval", "Logiciel",
    # Government / Public
    "Ghana Revenue Authority (GRA)", "Electoral Commission",
    "Ghana Immigration Service", "COCOBOD", "Ghana Ports and Harbours Authority",
    "National Petroleum Authority (NPA)",
    # Other
    "Unilever Ghana", "Nestle Ghana", "Guinness Ghana Breweries",
    "Enterprise Group", "SIC Insurance", "GLICO Group",
    "Accra Mall", "Melcom Ghana", "Ghana Airports Company Limited (GACL)",
    "Julius Berger Ghana", "Contracta Construction",
]

SCHOOLS = [
    ("University of Ghana, Legon",                 "BSc Computer Science",     "2019"),
    ("KNUST",                                      "BSc Electrical Engineering","2018"),
    ("University of Cape Coast",                   "BSc Accounting",           "2020"),
    ("Ashesi University",                          "BSc Business Administration","2021"),
    ("GIMPA",                                      "MBA",                      "2022"),
    ("Central University",                         "BSc Marketing",            "2019"),
    ("Ghana Communication Technology University",  "BSc Information Technology","2020"),
    ("Accra Technical University",                 "HND Mechanical Engineering","2018"),
    ("Ho Technical University",                    "HND Accountancy",          "2019"),
    ("Takoradi Technical University",              "HND Civil Engineering",    "2020"),
    ("University of Ghana Business School",        "MBA Finance",              "2022"),
    ("University of Health and Allied Sciences",   "BSc Nursing",              "2020"),
    ("University for Development Studies",         "BSc Agriculture",          "2019"),
    ("Catholic University College of Ghana",       "BSc Administration",       "2021"),
    ("Valley View University",                     "BSc Information Systems",  "2020"),
]

LOCATIONS = [
    "Accra, Greater Accra", "Kumasi, Ashanti Region", "Takoradi, Western Region",
    "Tamale, Northern Region", "Cape Coast, Central Region", "Tema, Greater Accra",
    "Ho, Volta Region", "Sunyani, Bono Region", "Koforidua, Eastern Region",
    "Bolgatanga, Upper East Region",
]

SKILLS_POOL = {
    "Technology":     ["Python", "JavaScript", "React", "Node.js", "FastAPI", "Django", "PostgreSQL",
                       "MySQL", "Docker", "AWS", "Git", "REST APIs", "TypeScript", "Vue.js", "MongoDB"],
    "Finance":        ["Financial Reporting", "Excel", "QuickBooks", "SAP", "IFRS", "Audit", "Taxation",
                       "Budgeting", "Forecasting", "Power BI", "Financial Modelling"],
    "Marketing":      ["Digital Marketing", "Google Analytics", "SEO", "Social Media Management",
                       "Content Marketing", "Email Marketing", "Brand Strategy", "Canva", "Hubspot"],
    "Sales":          ["CRM Systems", "B2B Sales", "Lead Generation", "Salesforce", "Negotiation",
                       "Client Relationship Management", "Pipeline Management"],
    "Healthcare":     ["Patient Care", "Clinical Assessment", "Electronic Health Records",
                       "Infection Control", "Pharmacology", "Diagnostic Skills"],
    "Engineering":    ["AutoCAD", "MATLAB", "Project Management", "Structural Analysis",
                       "Quality Control", "Technical Drawing", "Safety Compliance"],
    "Human Resources":["Recruitment", "HRIS", "Performance Management", "Labour Law Ghana",
                       "Training & Development", "Employee Relations"],
    "default":        ["Microsoft Office", "Communication", "Problem Solving",
                       "Project Management", "Teamwork", "Time Management"],
}

CHAT_TOPICS = [
    # Career advice
    "How do I negotiate a salary increase at a Ghanaian company?",
    "What is the minimum wage in Ghana in 2024?",
    "How do I include National Service on my CV?",
    "Should I put my WASSCE results on my CV?",
    "What is the difference between a CV and a resume in Ghana?",
    "How do I write a professional LinkedIn profile as a Ghanaian?",
    "What are the best companies to work for in Ghana in tech?",
    "How long should a CV be in Ghana?",
    "Should I include a photo on my CV in Ghana?",
    "What do Ghanaian employers look for in a CV?",
    "How do I explain a gap year after university in Ghana?",
    "What is a good starting salary for a software engineer at MTN Ghana?",
    "How do I prepare for an interview at GCB Bank?",
    "What should I wear to a job interview in Accra?",
    "How do I write a professional email to a Ghanaian hiring manager?",
    "What are the best universities in Ghana for computer science?",
    "How does the National Service Scheme work in Ghana?",
    "Can I use my National Service as work experience?",
    "What are the top skills companies in Ghana are hiring for?",
    "How do I find remote work opportunities as a Ghanaian?",
    # Technical / professional
    "How do I register a business in Ghana?",
    "What taxes does a freelancer pay in Ghana?",
    "What is the Ghana Revenue Authority's filing deadline?",
    "How do I open a domiciliary account in Ghana?",
    "What is the best way to send money internationally from Ghana?",
    "How do I apply for a UK visa from Ghana?",
    "What is the NHIS and how does it work?",
    "How do I get a SSNIT number as a new employee?",
    "What are my rights as an employee in Ghana?",
    "How does annual leave work in Ghana?",
    # General knowledge / writing help
    "Write a professional out-of-office email for a Ghanaian company",
    "How do I write a resignation letter professionally?",
    "What is the format for a business proposal in Ghana?",
    "How do I write a complaint letter to GRA?",
    "Help me write a professional bio for a conference in Accra",
    "How do I address a formal letter to a government minister in Ghana?",
    "Write a professional email requesting a meeting with a potential client",
    "What is the difference between a memorandum and a business letter?",
    "How do I write a project proposal for an NGO in Ghana?",
    "Help me write an introduction for a startup pitch in Ghana",
    # Coding / tech help
    "How do I integrate MTN Mobile Money API into my app?",
    "What is the best payment gateway for a Ghanaian e-commerce site?",
    "How do I accept Vodafone Cash payments on my website?",
    "What cloud provider is best for hosting in Ghana?",
    "How do I set up a Ghana Post GPS address for my business?",
    "Explain how to use the GhanaPostGPS API",
    "What is the best stack for building a fintech app in Ghana?",
    "How do I handle Ghana cedis currency formatting in JavaScript?",
    "What are the data protection laws for apps in Ghana?",
    "How do I register a .com.gh domain?",
]

# ── System prompts ───────────────────────────────────────────────────────────

CV_SYSTEM = """You are an expert professional CV writer with 20 years of experience.
You understand Ghanaian professional context: National Service counts as real experience,
WAEC/WASSCE/HND are valid qualifications, major Ghanaian employers (MTN, ECG, GNPC, GCB,
Hubtel, etc.) are well known. You write concise, ATS-optimised CVs in JSON format.

Output ONLY a valid JSON object with these exact fields:
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "title": "string (job title / professional headline)",
  "summary": "string (3-4 sentence professional summary)",
  "experience": [{"company": "", "title": "", "start_date": "", "end_date": "", "bullets": ["", ""]}],
  "education": [{"school": "", "degree": "", "field": "", "year": ""}],
  "skills": ["skill1", "skill2"],
  "linkedin": "",
  "website": ""
}

No markdown. No code fences. No explanation. Raw JSON only."""

LETTER_SYSTEM = """You are a world-class cover letter writer.
You understand Ghanaian professional context and write letters that are concise,
confident, and tailored. No clichés. No "I am writing to express my interest".
Open with a strong hook. Write exactly 3-4 paragraphs. End with a confident call to action.
Output ONLY the letter body text. No subject line. No address header. No markdown."""

CHAT_SYSTEM = """You are Delka, an AI assistant by DelkaAI — a platform built for
Ghanaian professionals and businesses. You are helpful, knowledgeable, and understand
Ghanaian context deeply: local employers, institutions, laws, culture, and language.
You give direct, practical advice. You respond in clear, professional English."""

# ── Profile builder ──────────────────────────────────────────────────────────

def build_cv_profile() -> dict:
    name = random.choice(ALL_NAMES)
    role, industry = random.choice(ROLES)
    company = random.choice(COMPANIES)
    school, degree, year = random.choice(SCHOOLS)
    pool = SKILLS_POOL.get(industry, SKILLS_POOL["default"])
    skills = random.sample(pool, k=min(random.randint(5, 8), len(pool)))
    yoe = random.randint(1, 10)
    end_year = 2024
    start_year = end_year - yoe
    location = random.choice(LOCATIONS)
    first_name = name.split()[0]
    email = f"{name.lower().replace(' ', '.')}{random.randint(10,99)}@gmail.com"
    phone = f"+233 {random.choice(['24','54','55','20','27','50'])} {random.randint(100,999)} {random.randint(1000,9999)}"

    return {
        "full_name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "summary": (
            f"{role} with {yoe} year{'s' if yoe > 1 else ''} of experience at {company}. "
            f"Studied {degree} at {school}. "
            f"Skilled in {', '.join(skills[:3])}."
        ),
        "experience": [
            {
                "company": company,
                "title": role,
                "start_date": str(start_year),
                "end_date": "Present",
                "bullets": [
                    f"Led key projects and delivered measurable results at {company}",
                    f"Collaborated cross-functionally to improve team efficiency",
                    f"Applied {skills[0]} and {skills[1]} to solve complex business problems",
                ]
            }
        ],
        "education": [
            {"school": school, "degree": degree, "field": "", "year": year}
        ],
        "skills": skills,
        "linkedin": "",
        "website": "",
        "webhook_url": "",
    }


def build_letter_profile() -> dict:
    name = random.choice(ALL_NAMES)
    role, industry = random.choice(ROLES)
    company = random.choice(COMPANIES)
    hiring_company = random.choice([c for c in COMPANIES if c != company])
    school, degree, _ = random.choice(SCHOOLS)
    skills = random.sample(SKILLS_POOL.get(industry, SKILLS_POOL["default"]), k=3)
    yoe = random.randint(1, 8)

    return {
        "applicant_name": name,
        "company_name": hiring_company,
        "job_title": role,
        "job_description": (
            f"We are seeking a talented {role} to join our team at {hiring_company}. "
            f"The ideal candidate has {yoe}+ years of experience in {industry} and strong "
            f"{skills[0]} skills. You will work on impactful projects and collaborate with "
            f"cross-functional teams. GHS-competitive salary and benefits offered."
        ),
        "applicant_background": (
            f"{name} is a {role} with {yoe} years at {company}. "
            f"Holds a {degree} from {school}. "
            f"Expert in {', '.join(skills)}."
        ),
        "tone": random.choice(["professional", "professional", "professional", "confident"]),
        "webhook_url": "",
    }

# ── Groq caller ──────────────────────────────────────────────────────────────

async def call_groq(session, system: str, user: str, temperature: float = 0.7) -> str | None:
    from groq import AsyncGroq
    client = AsyncGroq(api_key=GROQ_API_KEY)
    for attempt in range(3):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=temperature,
                max_tokens=2048,
            )
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                wait = 30 * (attempt + 1)
                print(f"  ⏳ Rate limited — waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"  ❌ Groq error (attempt {attempt+1}): {err[:80]}")
                await asyncio.sleep(5)
    return None

# ── Task generators ──────────────────────────────────────────────────────────

async def gen_cv(sem, session, idx: int) -> dict | None:
    async with sem:
        await asyncio.sleep(2)  # throttle between requests
        profile = build_cv_profile()
        user_prompt = (
            f"Generate a professional CV for the following person:\n"
            f"{json.dumps(profile, indent=2, ensure_ascii=False)}"
        )
        raw = await call_groq(session, CV_SYSTEM, user_prompt, temperature=0.65)
        if not raw:
            return None

        # strip fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            completion = json.loads(raw)
        except json.JSONDecodeError:
            # try to extract JSON from response
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    completion = json.loads(raw[start:end])
                except Exception:
                    print(f"  ⚠️  CV {idx}: JSON parse failed")
                    return None
            else:
                print(f"  ⚠️  CV {idx}: no JSON found")
                return None

        print(f"  ✅ CV {idx}: {profile['full_name']} — {profile['experience'][0]['title']} @ {profile['experience'][0]['company']}")
        return {
            "prompt": user_prompt,
            "completion": json.dumps(completion, ensure_ascii=False),
            "rating": 5,
            "platform": PLATFORM,
            "service": "cv",
            "model": MODEL,
            "auto_score": 0.9,
        }


async def gen_letter(sem, session, idx: int) -> dict | None:
    async with sem:
        await asyncio.sleep(2)  # throttle between requests
        profile = build_letter_profile()
        user_prompt = (
            f"Write a cover letter for this application:\n"
            f"Applicant: {profile['applicant_name']}\n"
            f"Applying for: {profile['job_title']} at {profile['company_name']}\n"
            f"Job description: {profile['job_description']}\n"
            f"Applicant background: {profile['applicant_background']}\n"
            f"Tone: {profile['tone']}"
        )
        raw = await call_groq(session, LETTER_SYSTEM, user_prompt, temperature=0.72)
        if not raw or len(raw.strip()) < 100:
            print(f"  ⚠️  Letter {idx}: empty or too short")
            return None

        letter_text = raw.strip()
        print(f"  ✅ Letter {idx}: {profile['applicant_name']} → {profile['job_title']} @ {profile['company_name']}")
        return {
            "prompt": user_prompt,
            "completion": letter_text,
            "rating": 5,
            "platform": PLATFORM,
            "service": "letter",
            "model": MODEL,
            "auto_score": 0.88,
        }


async def gen_chat(sem, session, idx: int) -> dict | None:
    async with sem:
        await asyncio.sleep(2)  # throttle between requests
        question = random.choice(CHAT_TOPICS)
        raw = await call_groq(session, CHAT_SYSTEM, question, temperature=0.75)
        if not raw or len(raw.strip()) < 50:
            print(f"  ⚠️  Chat {idx}: empty response")
            return None

        print(f"  ✅ Chat {idx}: {question[:60]}...")
        return {
            "prompt": question,
            "completion": raw.strip(),
            "rating": 5,
            "platform": PLATFORM,
            "service": "chat",
            "model": MODEL,
            "auto_score": 0.85,
        }

# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    from groq import AsyncGroq

    sem = asyncio.Semaphore(CONCURRENCY)

    # Count existing lines so we can resume
    existing = 0
    existing_services: dict[str, int] = {"cv": 0, "letter": 0, "chat": 0}
    if OUTPUT_FILE.exists():
        for line in OUTPUT_FILE.read_text().splitlines():
            try:
                row = json.loads(line)
                existing += 1
                svc = row.get("service", "")
                if svc in existing_services:
                    existing_services[svc] += 1
            except Exception:
                pass

    cv_need     = max(0, CV_COUNT     - existing_services["cv"])
    letter_need = max(0, LETTER_COUNT - existing_services["letter"])
    chat_need   = max(0, CHAT_COUNT   - existing_services["chat"])
    total_need  = cv_need + letter_need + chat_need

    print("=" * 60)
    print("  DelkaAI Synthetic Training Data Generator")
    print("=" * 60)
    print(f"  Output : {OUTPUT_FILE}")
    print(f"  Model  : {MODEL}")
    print(f"  Concurrency: {CONCURRENCY} parallel requests")
    print()
    print(f"  Existing : {existing} rows")
    print(f"    CV     : {existing_services['cv']}  (need {cv_need} more)")
    print(f"    Letter : {existing_services['letter']}  (need {letter_need} more)")
    print(f"    Chat   : {existing_services['chat']}  (need {chat_need} more)")
    print(f"  Total to generate: {total_need}")
    print("=" * 60)

    if total_need == 0:
        print("\n✅ Already at target. Nothing to generate.")
        return

    start_time = time.time()
    generated = 0

    with OUTPUT_FILE.open("a", encoding="utf-8") as f:

        # ── CVs ──
        if cv_need > 0:
            print(f"\n📄 Generating {cv_need} CV examples…")
            tasks = [gen_cv(sem, None, i + 1) for i in range(cv_need)]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                    generated += 1

        # ── Cover letters ──
        if letter_need > 0:
            print(f"\n✉️  Generating {letter_need} cover letter examples…")
            tasks = [gen_letter(sem, None, i + 1) for i in range(letter_need)]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                    generated += 1

        # ── Chat ──
        if chat_need > 0:
            print(f"\n💬 Generating {chat_need} chat examples…")
            tasks = [gen_chat(sem, None, i + 1) for i in range(chat_need)]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                    generated += 1

    elapsed = time.time() - start_time
    total_rows = existing + generated
    print()
    print("=" * 60)
    print(f"  ✅ Done! Generated {generated} new examples in {elapsed:.0f}s")
    print(f"  📁 Total rows in file: {total_rows}")
    print(f"  📍 Saved to: {OUTPUT_FILE}")
    print()
    print("  Next step:")
    print("  1. Upload training/synthetic_data.jsonl to Google Colab")
    print("  2. Run training/colab_finetune.py")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
