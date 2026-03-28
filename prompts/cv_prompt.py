from prompts.global_rules_prompt import GLOBAL_RULES_PROMPT
from schemas.cv_schema import CVRequest

_DOCUMENT_RULES = """
DOCUMENT RULES:
- Use ONLY the information provided. Never add, invent, or embellish.
- Do not add skills, companies, or qualifications not mentioned by the user.
- Dates must be preserved exactly as given.
- Bullet points must be action-oriented, starting with strong past-tense verbs.
""".strip()

_CV_PERSONA = """
You are an expert professional CV writer with 20 years of experience crafting executive-level resumes.
You write concise, impactful, ATS-optimised CVs that get interviews.
""".strip()

CHAIN_OF_THOUGHT_CV = """
Before writing the CV, reason through these questions inside <thinking> tags:

1. What career level is this person? (entry / mid / senior)
2. What industry and role are they targeting?
3. What are their 3 strongest selling points?
4. What CV format suits their background? (chronological / functional / hybrid)
5. What tone is appropriate? (corporate / startup / academic / government)
6. What would make a recruiter stop scrolling?
7. Are there gaps or weaknesses to address carefully?

Format: <thinking>your reasoning here</thinking>
Then output ONLY the JSON CV.
""".strip()

SELF_CRITIQUE_PROMPT = """
After drafting the CV, review your own output:
- Is every bullet achievement-focused, not task-focused?
- Are there clichés? ("team player", "hard worker", "passionate", "results-driven")
- Is the summary punchy and specific — not generic?
- Does the CV clearly match the target role?
- Would a recruiter be impressed in 6 seconds?

If anything fails — rewrite that section before outputting the final JSON.
""".strip()

CV_OUTPUT_CONTRACT = """
OUTPUT CONTRACT — NEVER VIOLATE:
Return EXACTLY this JSON structure. Every field must be present even if empty ("" or []).
No markdown. No code fences. No explanation. Raw JSON only.

{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "summary": "2-4 sentences, specific and punchy",
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string",
      "end_date": "string",
      "bullets": ["starts with strong past-tense action verb, quantified where possible"]
    }
  ],
  "education": [{"school": "", "degree": "", "field": "", "year": ""}],
  "skills": ["string"]
}

QUALITY RULES:
- summary: 2-4 sentences, specific and punchy — never generic
- bullets: 3-6 per role, must start with a strong past-tense action verb
- skills: minimum 3 items
- No bullets starting with "Responsible for" or "Helped with"
- No clichés anywhere: "team player", "hard worker", "passionate", "results-driven", "dynamic"
""".strip()


def build_cv_prompt(data: CVRequest, language_instruction: str) -> tuple[str, str]:
    system = "\n\n".join([
        GLOBAL_RULES_PROMPT,
        _DOCUMENT_RULES,
        _CV_PERSONA,
        f"OUTPUT LANGUAGE: {language_instruction}",
    ])

    experience_text = ""
    for exp in data.experience:
        bullets = "\n".join(f"  - {b}" for b in exp.bullets)
        experience_text += (
            f"\nCompany: {exp.company}\n"
            f"Title: {exp.title}\n"
            f"Dates: {exp.start_date} – {exp.end_date}\n"
            f"Responsibilities:\n{bullets}\n"
        )

    education_text = ""
    for edu in data.education:
        education_text += (
            f"\nSchool: {edu.school}\n"
            f"Degree: {edu.degree}"
            + (f" in {edu.field}" if edu.field else "")
            + f"\nYear: {edu.year}\n"
        )

    skills_text = ", ".join(data.skills) if data.skills else "Not provided"

    user = "\n\n".join([
        CHAIN_OF_THOUGHT_CV,
        SELF_CRITIQUE_PROMPT,
        CV_OUTPUT_CONTRACT,
        f"""Generate a CV for the following person:

PERSONAL INFO:
Full Name: {data.full_name}
Email: {data.email}
Phone: {data.phone or 'Not provided'}
Location: {data.location or 'Not provided'}
LinkedIn: {data.linkedin or 'Not provided'}
Website: {data.website or 'Not provided'}

PROFESSIONAL SUMMARY:
{data.summary}

WORK EXPERIENCE:
{experience_text.strip()}

EDUCATION:
{education_text.strip()}

SKILLS:
{skills_text}""",
    ])

    return system, user
