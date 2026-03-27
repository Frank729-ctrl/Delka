from prompts.global_rules_prompt import GLOBAL_RULES_PROMPT
from schemas.cover_letter_schema import CoverLetterRequest

_DOCUMENT_RULES = """
DOCUMENT RULES:
- Use ONLY the information provided. Never fabricate details.
- No clichés: never use "I am writing to express my interest", "I am a hard worker",
  "team player", "passionate about", "results-driven", "dynamic", or "synergy".
- Open with a strong, specific hook that references the role and company.
- Write exactly 3-4 paragraphs: hook, relevant experience, company alignment, confident close.
- The closing paragraph must end with a specific, confident call to action.
- Tone must be professional, direct, and confident — never sycophantic.
""".strip()

_LETTER_PERSONA = """
You are a world-class cover letter writer who crafts letters that hiring managers remember.
Your letters are concise, confident, and tailored — never generic.
""".strip()


def build_letter_prompt(
    data: CoverLetterRequest,
    language_instruction: str,
) -> tuple[str, str]:
    system = "\n\n".join([
        GLOBAL_RULES_PROMPT,
        _DOCUMENT_RULES,
        _LETTER_PERSONA,
        f"OUTPUT LANGUAGE: {language_instruction}",
        "OUTPUT FORMAT: Return the letter body text ONLY. No subject line. No date. No address block. No salutation header. Body paragraphs only.",
    ])

    user = f"""
Write a cover letter body for the following application:

Applicant Name: {data.applicant_name}
Applying For: {data.job_title} at {data.company_name}
Tone: {data.tone}

Job Description:
{data.job_description}

Applicant Background:
{data.applicant_background}

Return the letter body only — no headers, no date, no address, no "Dear" salutation line.
Start directly with the opening paragraph.
""".strip()

    return system, user
