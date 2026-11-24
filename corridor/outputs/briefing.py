"""Two-page briefing note: docs/templates/briefing_note.md is filled from results/ into docs/briefing_note.md,
which is then typeset to outputs/briefing_note.pdf with a small Markdown subset (headings, paragraphs,
bullets, numbered lists, quotes, tables, bold and code)."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import config, docs
from . import rel

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.6, leading=10.8, alignment=TA_LEFT, spaceAfter=3)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=9.6, leading=12, spaceBefore=4, spaceAfter=2,
                    keepWithNext=1)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.6, leading=9.2, spaceAfter=0)
QUOTE = ParagraphStyle("quote", parent=BODY, fontSize=7.8, leading=9.6, backColor=colors.HexColor("#f0efec"),
                       borderColor=colors.HexColor("#c3c2b7"), borderWidth=0.5, borderPadding=4, spaceBefore=2, spaceAfter=7)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=9, bulletIndent=1, spaceAfter=1.5)
CAPTION = ParagraphStyle("caption", parent=BODY, fontSize=7.2, leading=8.8, textColor=colors.HexColor("#52514e"))
IMAGE = re.compile(r"^!\[(.*?)\]\((.+?)\)$")


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', t)
    return t


def _table(lines: list[str]):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    rows = [r for i, r in enumerate(rows) if i != 1]          # drop the |---| separator
    data = [[Paragraph(inline(c), CELL) for c in r] for r in rows]
    n = len(rows[0])
    width = A4[0] - 30 * mm - 14
    first = 0.30 if n > 3 else 0.34
    widths = [width * first] + [width * (1 - first) / (n - 1)] * (n - 1)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e1e0d9")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3c2b7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _image(path: str, caption: str):
    from reportlab.lib.utils import ImageReader
    p = config.ROOT / path
    w, h = ImageReader(str(p)).getSize()
    width = A4[0] - 30 * mm - 14
    return KeepTogether([Image(str(p), width=width, height=width * h / w), Paragraph(inline(caption), CAPTION)])


def flowables(md: str) -> list:
    out, para, table = [], [], []
    lines = [ln for ln in md.splitlines() if not ln.startswith("<!--") or ln.strip() == "<!-- pagebreak -->"]

    def flush():
        nonlocal para, table
        if para:
            out.append(Paragraph(inline(" ".join(para)), BODY))
            para = []
        if table:
            out.extend([_table(table), Spacer(0, 3)])
            table = []

    for ln in lines:
        s = ln.rstrip()
        if s.strip() == "<!-- pagebreak -->":
            flush()
            out.append(PageBreak())
            continue
        m = IMAGE.match(s.strip())
        if m:
            flush()
            out.append(_image(m.group(2), m.group(1)))
            continue
        if s.startswith("|"):
            if para:
                out.append(Paragraph(inline(" ".join(para)), BODY))
                para = []
            table.append(s)
            continue
        if table:
            flush()
        if not s.strip():
            flush()
        elif s.startswith("# "):
            flush()
            out.append(Paragraph(inline(s[2:]), TITLE))
        elif s.startswith("## "):
            flush()
            out.append(Paragraph(inline(s[3:]), H2))
        elif s.startswith("> "):
            flush()
            out.append(Paragraph(inline(s[2:]), QUOTE))
        elif s.startswith("- "):
            flush()
            out.append(Paragraph(inline(s[2:]), BULLET, bulletText="•"))
        elif re.match(r"^\d+\. ", s):
            flush()
            num, rest = s.split(". ", 1)
            out.append(Paragraph(inline(rest), BULLET, bulletText=f"{num}."))
        elif s.startswith("  ") and out and isinstance(out[-1], Paragraph) and out[-1].style is BULLET:
            prev = out.pop()
            out.append(Paragraph(prev.text + " " + inline(s.strip()), BULLET, bulletText=prev.bulletText))
        else:
            para.append(s.strip())
    flush()
    return out


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor("#52514e"))
    canvas.drawString(15 * mm, 8 * mm, "ILLUSTRATIVE: fictional corridor. Personal portfolio desk study on public data; "
                                       "not affiliated with LTA, SLA or URA; not legal advice.")
    canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page} of 2")
    canvas.restoreState()


def render_markdown() -> str:
    tmpl = (config.DOCS / "templates" / "briefing_note.md").read_text(encoding="utf-8")
    return docs.render(tmpl, docs.load_results())


def make(pdf_path: Path) -> dict:
    md = render_markdown()
    docs.write_if_changed(config.DOCS / "briefing_note.md", md)
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm,
                            bottomMargin=14 * mm, title="Briefing note: fictional corridor IL-1",
                            author="Wenjie Luo (LUOaini1213)", subject="Land screening of a fictional rail corridor",
                            creator="sg-rail-corridor-land-screening", invariant=1)
    doc.build(flowables(md), onFirstPage=_footer, onLaterPages=_footer)
    from pypdf import PdfReader
    pages = len(PdfReader(str(pdf_path)).pages)
    return {"path": rel(pdf_path), "markdown": "docs/briefing_note.md", "pages": pages}
