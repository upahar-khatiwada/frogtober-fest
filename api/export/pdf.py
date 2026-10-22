"""PDF export of the bid package (ReportLab + HarfBuzz shaping), with embedded Noto fonts (spec section 10.1).

Devanagari must render correctly (conjuncts, reph, the ि matra before its consonant) and read back as the same
Unicode text. `export.shaping` makes ReportLab shape it with HarfBuzz and mark each shaped cluster with /ActualText;
this module sets every Devanagari run in Noto Sans Devanagari and everything else in Noto Sans (the Devanagari font
has no Latin letters), both embedded as subsets (fonts/README.md). Everything goes through `Paragraph` with
`shaping=1`; the footer is Latin-only canvas text.
"""

import io
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from export import shaping
from export.content import BidPackage, Block, Inline

FONT_DIR = Path(__file__).resolve().parent / "fonts"
LATIN, LATIN_BOLD = "TenderlySans", "TenderlySans-Bold"
DEVA, DEVA_BOLD = "TenderlyDeva", "TenderlyDeva-Bold"
# Devanagari block + Vedic extensions + ZWNJ/ZWJ (they join conjuncts, so they stay inside the Devanagari run).
_DEVANAGARI = re.compile(r"[ऀ-ॿ꣠-ꣿ᳐-᳿‌‍]+")


@lru_cache
def register_fonts() -> None:
    """Register the four embedded fonts and their bold mappings, and install the shaping hooks (once)."""
    shaping.install()
    for name, file in ((LATIN, "NotoSans-Regular.ttf"), (LATIN_BOLD, "NotoSans-Bold.ttf"),
                       (DEVA, "NotoSansDevanagari-Regular.ttf"), (DEVA_BOLD, "NotoSansDevanagari-Bold.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    # No italic faces are embedded: italic text is set upright (the note style is grey instead).
    pdfmetrics.registerFontFamily(LATIN, normal=LATIN, bold=LATIN_BOLD, italic=LATIN, boldItalic=LATIN_BOLD)
    pdfmetrics.registerFontFamily(DEVA, normal=DEVA, bold=DEVA_BOLD, italic=DEVA, boldItalic=DEVA_BOLD)


def markup(text: str, *, bold: bool = False) -> str:
    """Escape for Paragraph markup and put Devanagari runs in the Devanagari font (bold for bold styles)."""
    font = DEVA_BOLD if bold else DEVA
    return _DEVANAGARI.sub(lambda m: f'<font name="{font}">{m.group(0)}</font>', escape(text))


def inline_markup(parts: list[Inline], *, bold: bool = False) -> str:
    out = []
    for part in parts:
        text = markup(part.text, bold=bold or part.bold)
        if part.bold:
            text = f"<b>{text}</b>"
        if part.italic:
            text = f"<i>{text}</i>"
        out.append(text)
    return "".join(out)


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=LATIN, fontSize=10, leading=15, alignment=TA_LEFT, shaping=1, spaceAfter=4)
    return {
        "p": base,
        "title": ParagraphStyle("title", parent=base, fontName=LATIN_BOLD, fontSize=18, leading=26, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName=LATIN_BOLD, fontSize=14, leading=21, spaceBefore=6, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base, fontName=LATIN_BOLD, fontSize=11.5, leading=17, spaceBefore=8, spaceAfter=4),
        "note": ParagraphStyle("note", parent=base, fontSize=8.5, leading=13, textColor=colors.HexColor("#555555")),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=12.5, spaceAfter=0),
        "head": ParagraphStyle("head", parent=base, fontName=LATIN_BOLD, fontSize=8.5, leading=12.5, spaceAfter=0),
    }


def _table(block: Block, width: float, styles: dict[str, ParagraphStyle]) -> Table:
    header = len(block.rows[0]) > 2  # key/value tables have no header row
    data = [[Paragraph(markup(cell, bold=header and r == 0), styles["head" if header and r == 0 else "cell"]) for cell in row]
            for r, row in enumerate(block.rows)]
    widths = [width * w for w in block.widths] if block.widths else None
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")))
    else:
        style.append(("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F5F5")))
    table.setStyle(TableStyle(style))
    return table


def _flowables(blocks: list[Block], width: float) -> list:
    styles = _styles()
    out: list = []
    pending: list[tuple[str, Block]] = []  # consecutive bullet / number items -> one list

    def flush() -> None:
        if not pending:
            return
        kind = pending[0][0]
        items = [ListItem(Paragraph(inline_markup(b.inlines), styles["p"]), leftIndent=14) for _, b in pending]
        out.append(ListFlowable(items, bulletType="bullet" if kind == "bullet" else "1", start=None if kind == "bullet" else 1,
                                bulletFontName=LATIN, bulletFontSize=9, leftIndent=14))
        pending.clear()

    for block in blocks:
        if block.kind in ("bullet", "number"):
            if pending and pending[0][0] != block.kind:
                flush()
            pending.append((block.kind, block))
            continue
        flush()
        if block.kind == "pagebreak":
            out.append(PageBreak())
        elif block.kind == "table":
            out += [_table(block, width, styles), Spacer(1, 6)]
        elif block.kind in ("title", "h1", "h2"):
            out.append(KeepTogether([Paragraph(inline_markup(block.inlines, bold=True), styles[block.kind])]))
        else:
            out.append(Paragraph(inline_markup(block.inlines), styles.get(block.kind, styles["p"])))
    flush()
    return out


def render_pdf(package: BidPackage, *, generated: datetime) -> bytes:
    """The package as PDF bytes (A4)."""
    register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=package.title, author="Tenderly (prepared, not submitted)",
                            subject=package.file_stem, creator="Tenderly", lang="ne-NP" if package.language == "ne" else "en")
    footer = f"{package.file_stem} - generated {generated:%Y-%m-%d %H:%M} - prepared with Tenderly, not submitted"

    def on_page(canvas, _doc):
        canvas.saveState()
        canvas.setFont(LATIN, 7.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(18 * mm, 10 * mm, footer)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(_flowables(package.blocks, doc.width), onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
