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

CHAIN_OF_THOUGHT_LETTER = """
Before writing the letter, think inside <thinking> tags:

1. What is the company's culture? (corporate / startup / NGO / government)
2. What is the single strongest reason to hire this person for this role?
3. What tone fits this application? (formal / professional / enthusiastic)
4. What specific achievement should lead the opening paragraph?
5. What would make this letter memorable compared to 100 generic applications?

Format: <thinking>your reasoning here</thinking>
Then output ONLY the letter body text.
""".strip()

LETTER_OUTPUT_CONTRACT = """
OUTPUT CONTRACT:
Return ONLY the letter body text — no subject line, no date, no address block.

STRUCTURE RULES:
- Opening: strong hook — NEVER start with "I am writing to apply for..."
- Body: 3-4 paragraphs maximum, one clear point each
- Closing: confident and specific, not begging or hollow
- Length: 250-400 words maximum

BANNED PHRASES (never use):
- "passionate", "team player", "hard worker", "results-driven", "dynamic"
- "I am writing to...", "I look forward to hearing from you"
- "I am a fast learner", "I thrive in fast-paced environments"
- Any hollow filler that could apply to any job at any company
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

    user = "\n\n".join([
        CHAIN_OF_THOUGHT_LETTER,
        LETTER_OUTPUT_CONTRACT,
        f"""Write a cover letter body for the following application:

Applicant Name: {data.applicant_name}
Applying For: {data.job_title} at {data.company_name}
Tone: {data.tone}

Job Description:
{data.job_description}

Applicant Background:
{data.applicant_background}

Return the letter body only — no headers, no date, no address, no "Dear" salutation line.
Start directly with the opening paragraph.""",
    ])

    return system, user
