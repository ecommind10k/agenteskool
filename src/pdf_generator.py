"""
PDF generator for lesson summaries.

Produces one PDF per lesson with:
  - Branded header with course / module / lesson info
  - Formatted sections from the markdown summary
  - Footer with page number and generation date
"""

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .summarizer import LessonSummary


# ------------------------------------------------------------------ #
# Color palette                                                        #
# ------------------------------------------------------------------ #
BRAND_DARK = colors.HexColor("#1a1a2e")
BRAND_ACCENT = colors.HexColor("#e94560")
BRAND_LIGHT = colors.HexColor("#16213e")
BODY_GRAY = colors.HexColor("#374151")
LIGHT_BG = colors.HexColor("#f9fafb")
RULE_COLOR = colors.HexColor("#e5e7eb")


# ------------------------------------------------------------------ #
# Page template helpers                                                #
# ------------------------------------------------------------------ #
def _make_header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4

    # Header bar
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, height - 2 * cm, width, 2 * cm, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(2 * cm, height - 1.1 * cm, doc.course_name)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, height - 1.6 * cm, f"Módulo: {doc.module_name}")

    # Footer
    canvas.setFillColor(RULE_COLOR)
    canvas.rect(0, 0, width, 1.2 * cm, fill=1, stroke=0)
    canvas.setFillColor(BODY_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 0.45 * cm, f"Generado el {doc.gen_date}")
    canvas.drawRightString(
        width - 2 * cm, 0.45 * cm, f"Página {doc.page}"
    )

    canvas.restoreState()


# ------------------------------------------------------------------ #
# Main PDF class                                                       #
# ------------------------------------------------------------------ #
class PDFGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, summary: LessonSummary) -> Path:
        """Generate a PDF file for the lesson summary; returns the file path."""
        filename = self._safe_filename(summary)
        filepath = self.output_dir / filename

        doc = _SkoolDoc(
            str(filepath),
            course_name=summary.course_name,
            module_name=summary.module_name,
            lesson_title=summary.lesson_title,
        )

        styles = _build_styles()
        story = []

        # Title block
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(summary.lesson_title, styles["lesson_title"]))
        story.append(Spacer(1, 0.3 * cm))
        story.append(HRFlowable(width="100%", thickness=2, color=BRAND_ACCENT))
        story.append(Spacer(1, 0.5 * cm))

        # Parse and render markdown sections
        sections = _parse_markdown(summary.content)
        for kind, text in sections:
            if kind == "h2":
                story.append(Spacer(1, 0.4 * cm))
                story.append(Paragraph(text, styles["section_header"]))
                story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR))
                story.append(Spacer(1, 0.15 * cm))
            elif kind == "bullet":
                story.append(Paragraph(f"• &nbsp; {_esc(text)}", styles["bullet"]))
            elif kind == "numbered":
                story.append(Paragraph(_esc(text), styles["numbered"]))
            elif kind == "body":
                story.append(Paragraph(_esc(text), styles["body"]))
            elif kind == "blank":
                story.append(Spacer(1, 0.2 * cm))

        # Metadata footer box
        story.append(Spacer(1, 0.8 * cm))
        meta_data = [
            ["Curso", summary.course_name],
            ["Módulo", summary.module_name],
            ["Lección", summary.lesson_title],
            ["Longitud de transcripción", f"{summary.transcript_length:,} caracteres"],
            ["Modelo IA", summary.model_used],
        ]
        table = Table(meta_data, colWidths=[4 * cm, 12 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), LIGHT_BG),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (-1, -1), BODY_GRAY),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_BG, colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.5, RULE_COLOR),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        print(f"  [PDF] Saved: {filepath}")
        return filepath

    @staticmethod
    def _safe_filename(summary: LessonSummary) -> str:
        def clean(s: str) -> str:
            s = re.sub(r'[^\w\s-]', '', s)
            s = re.sub(r'[\s]+', '_', s.strip())
            return s[:60]

        course = clean(summary.course_name)
        module = clean(summary.module_name)
        title = clean(summary.lesson_title)
        return f"{course}__{module}__{title}.pdf"


# ------------------------------------------------------------------ #
# ReportLab document subclass (holds metadata for header/footer)      #
# ------------------------------------------------------------------ #
class _SkoolDoc(BaseDocTemplate):
    def __init__(self, filename, course_name, module_name, lesson_title, **kwargs):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
            **kwargs,
        )
        self.course_name = course_name
        self.module_name = module_name
        self.lesson_title = lesson_title
        self.gen_date = datetime.now().strftime("%d/%m/%Y %H:%M")

        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="main",
        )
        template = PageTemplate(
            id="main",
            frames=[frame],
            onPage=_make_header_footer,
        )
        self.addPageTemplates([template])


# ------------------------------------------------------------------ #
# Style definitions                                                    #
# ------------------------------------------------------------------ #
def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "lesson_title": ParagraphStyle(
            "lesson_title",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=BRAND_DARK,
            leading=24,
            alignment=TA_LEFT,
        ),
        "section_header": ParagraphStyle(
            "section_header",
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=BRAND_ACCENT,
            leading=18,
            spaceBefore=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=BODY_GRAY,
            leading=15,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Helvetica",
            fontSize=10,
            textColor=BODY_GRAY,
            leading=15,
            leftIndent=16,
            spaceAfter=2,
        ),
        "numbered": ParagraphStyle(
            "numbered",
            fontName="Helvetica",
            fontSize=10,
            textColor=BODY_GRAY,
            leading=15,
            leftIndent=16,
            spaceAfter=2,
        ),
    }


# ------------------------------------------------------------------ #
# Markdown parser (lightweight, covers the sections Claude produces)  #
# ------------------------------------------------------------------ #
def _parse_markdown(text: str) -> list[tuple[str, str]]:
    """
    Parse markdown into a list of (kind, content) tuples.
    Kinds: h2, bullet, numbered, body, blank
    """
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            result.append(("blank", ""))
        elif stripped.startswith("## "):
            result.append(("h2", stripped[3:].strip()))
        elif stripped.startswith("# "):
            result.append(("h2", stripped[2:].strip()))
        elif re.match(r'^[-*] ', stripped):
            result.append(("bullet", stripped[2:].strip()))
        elif re.match(r'^\d+\. ', stripped):
            # Keep the number prefix
            result.append(("numbered", stripped))
        else:
            # Inline bold (**text**) → just strip asterisks for simplicity
            result.append(("body", stripped))
    return result


def _esc(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("**", "")  # strip bold markers
            .replace("*", "")
    )
