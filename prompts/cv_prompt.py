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

_JSON_SCHEMA_EXAMPLE = """
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "summary": "string (2-3 sentences)",
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string",
      "end_date": "string",
      "bullets": ["string", "string", "string"]
    }
  ],
  "education": [
    {
      "school": "string",
      "degree": "string",
      "field": "string",
      "year": "string"
    }
  ],
  "skills": ["string"]
}
""".strip()


def build_cv_prompt(data: CVRequest, language_instruction: str) -> tuple[str, str]:
    system = "\n\n".join([
        GLOBAL_RULES_PROMPT,
        _DOCUMENT_RULES,
        _CV_PERSONA,
        f"OUTPUT LANGUAGE: {language_instruction}",
        "CRITICAL OUTPUT INSTRUCTION: Return ONLY valid JSON. No markdown. No code fences. No explanation. JSON only.",
        "CRITICAL OUTPUT INSTRUCTION: Do NOT wrap your response in ```json or ``` blocks. Raw JSON only.",
        f"CRITICAL OUTPUT INSTRUCTION: Your entire response must be parseable by json.loads(). No text before or after the JSON object. JSON only.\n\nExpected schema:\n{_JSON_SCHEMA_EXAMPLE}",
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

    user = f"""
Please create a professional CV in JSON format using the following information:

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
{skills_text}

Return the complete CV as a single valid JSON object. No markdown. No fences. No explanation. JSON only.
""".strip()

    return system, user
