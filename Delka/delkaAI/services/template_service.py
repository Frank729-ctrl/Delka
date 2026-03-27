import random

CV_TEMPLATES: list[str] = [
    "modern_sidebar",
    "minimal_clean",
    "bold_header",
    "timeline_style",
    "executive_classic",
]

LETTER_TEMPLATES: list[str] = [
    "letterhead_style",
    "modern_block",
    "clean_minimal",
]

COLOR_SCHEMES: dict[str, dict] = {
    "professional_blue": {
        "primary": "#1a3c5e",
        "secondary": "#2980b9",
        "accent": "#e8f4fd",
        "text": "#2c3e50",
        "border": "#aed6f1",
    },
    "forest_green": {
        "primary": "#1e4d2b",
        "secondary": "#27ae60",
        "accent": "#eafaf1",
        "text": "#1a252f",
        "border": "#a9dfbf",
    },
    "burgundy": {
        "primary": "#6d1f2b",
        "secondary": "#c0392b",
        "accent": "#fdf2f2",
        "text": "#2c3e50",
        "border": "#f5b7b1",
    },
    "charcoal": {
        "primary": "#2c3e50",
        "secondary": "#7f8c8d",
        "accent": "#ecf0f1",
        "text": "#2c3e50",
        "border": "#bdc3c7",
    },
    "navy_gold": {
        "primary": "#1a2744",
        "secondary": "#d4a017",
        "accent": "#fdf9ed",
        "text": "#1a2744",
        "border": "#f0d090",
    },
    "muted": {
        "primary": "#4a4a4a",
        "secondary": "#8e8e8e",
        "accent": "#f5f5f5",
        "text": "#333333",
        "border": "#d0d0d0",
    },
}


def pick_random_cv_template() -> tuple[str, dict]:
    name = random.choice(CV_TEMPLATES)
    color_key = random.choice(list(COLOR_SCHEMES.keys()))
    return name, COLOR_SCHEMES[color_key]


def pick_random_letter_template() -> tuple[str, dict]:
    name = random.choice(LETTER_TEMPLATES)
    color_key = random.choice(list(COLOR_SCHEMES.keys()))
    return name, COLOR_SCHEMES[color_key]
