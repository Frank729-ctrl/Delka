from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

_env = Environment(
    loader=FileSystemLoader("templates/"),
    autoescape=select_autoescape(["html"]),
)


def render_cv_to_pdf(cv_data: dict, template_name: str, color: dict) -> bytes:
    template = _env.get_template(f"cv/{template_name}.html")
    rendered = template.render(cv=cv_data, color=color)
    return HTML(string=rendered).write_pdf()


def render_letter_to_pdf(
    letter_text: str,
    meta: dict,
    template_name: str,
    color: dict,
) -> bytes:
    paragraphs = [p.strip() for p in letter_text.split("\n\n") if p.strip()]
    template = _env.get_template(f"cover_letter/{template_name}.html")
    rendered = template.render(letter={"paragraphs": paragraphs, **meta}, color=color)
    return HTML(string=rendered).write_pdf()
