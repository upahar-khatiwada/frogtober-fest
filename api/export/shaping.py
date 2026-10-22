"""Devanagari in ReportLab PDFs: correct shaping on the page and correct text when the PDF is read back.

ReportLab (>= 4) shapes TrueType text with HarfBuzz (`uharfbuzz`) when a paragraph style has `shaping=1`. That gives
the right glyphs (conjuncts such as क्ष / त्र / प्र, reph र्, the ि matra drawn before its consonant), but three things
go wrong out of the box, and `install()` fixes them:

1. **Mixed-font words are shaped with the first font.** A word such as `रु.` or `भानु,` is a Devanagari run plus a
   Latin run (the Devanagari font has no Latin letters). ReportLab shapes the whole word with the first run's font, so
   the Latin glyph ids are looked up in the wrong font and print as the wrong character. `install()` shapes each font
   run on its own. Latin ligatures (fi, fl) are switched off, so English text extracts letter for letter.
2. **Shaped glyphs lose their text.** Conjunct glyphs have no Unicode code point, so ReportLab gives them private-use
   codes, and the reordered ि sits before its consonant. Copy/paste and text extraction then return garbage. `install()`
   wraps every glyph cluster whose glyphs are not its own source text in a PDF `/ActualText` span (PDF 32000-1
   §14.9.4) holding that cluster's logical Unicode text. Clusters whose glyphs are their text (most Latin, plain
   Devanagari letters) are written as before.
3. **Long words are split character by character.** A word wider than its column (a narrow table cell) is rebuilt
   from single characters, which turns shaped glyphs into bare glyph codes and can cut a conjunct in two.
   `install()` splits shaped words at cluster boundaries instead, and slices keep their source text.

The hooks patch ReportLab internals (`platypus.paragraph.shapeFragWord` / `_splitFragWord`,
`PDFTextObject._formatText`, `ShapedStr.__getitem__`), so the version is pinned in pyproject.toml and `tests/test_export.py` extracts text from a generated PDF to catch a break.
Only text drawn through `Paragraph` with `shaping=1` is shaped; `canvas.drawString` is not (keep it Latin-only).
"""

import unicodedata
from itertools import groupby

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import ShapedFragWord, ShapedStr, makeShapedFragWord
from reportlab.pdfgen import textobject
from reportlab.platypus import paragraph

# HarfBuzz features for every run: kerning yes, optional ligatures no (Devanagari conjuncts come from the required
# script features, which HarfBuzz always applies).
FEATURES = {"kern": True, "liga": False, "clig": False, "dlig": False}

_installed = False
_orig_shape = paragraph.shapeFragWord
_orig_format = textobject.PDFTextObject._formatText
_orig_getitem = ShapedStr.__getitem__
_orig_split = paragraph._splitFragWord


def _shape_word(word, *_args, **_kwargs):
    """Shape each single-font run of a paragraph word separately, remembering the source text of each run."""
    frags = word[1:]
    if isinstance(word, ShapedFragWord) or any(isinstance(text, ShapedStr) for _, text in frags):
        return word  # already shaped (e.g. a split piece re-wrapped on the next page)
    if any(hasattr(f, "cbDefn") for f, _ in frags):  # links/anchors: leave to ReportLab
        return _orig_shape(word, features=FEATURES)
    out, total, changed = [], 0.0, False
    for _, run in groupby(frags, key=lambda frag: (frag[0].fontName, frag[0].fontSize)):
        run = list(run)
        width = sum(pdfmetrics.stringWidth(text, f.fontName, f.fontSize) for f, text in run)
        shaped = _orig_shape([width, *run], features=FEATURES)
        source = "".join(text for _, text in run)
        for _, text in shaped[1:]:
            if isinstance(text, ShapedStr):
                text._source = source
                changed = True
        total += shaped[0]
        out.extend(shaped[1:])
    if not changed:
        return word
    return makeShapedFragWord(word)([total, *out])


def _slice(self, index):
    """A slice of a shaped run keeps its source text, and where the glyph after the slice starts in it."""
    out = _orig_getitem(self, index)
    source = getattr(self, "_source", None)
    if source is not None and isinstance(index, slice) and isinstance(out, ShapedStr):
        stop = index.indices(len(self))[1]
        out._source = source
        out._source_end = self.__shapeData__[stop].cluster if stop < len(self) else getattr(self, "_source_end", len(source))
    return out


def _split_word(word, max_width, max_widths, lineno):
    """Split a word too wide for its line at cluster boundaries, keeping the shaped glyphs (ReportLab rebuilds it
    character by character, which turns shaped glyphs into bare glyph codes and can cut a conjunct in two)."""
    if not any(isinstance(text, ShapedStr) for _, text in word[1:]):
        return _orig_split(word, max_width, max_widths, lineno)
    last = len(max_widths) - 1
    next_width = max_widths[min(last, lineno + 1)]
    pieces, current, line_width = [], [], 0.0

    def close(final: bool) -> None:
        width = sum(w for w, _, _ in current)
        frags = []
        for _, frag, text in current:  # as ReportLab does: each piece gets its own frag carrying its text
            frag = frag.clone()
            if hasattr(frag, "text"):
                frag.text = text
            frags.append((frag, text))
        pieces.append((paragraph._SplitFragH if final else paragraph._SplitFrag)([width, *frags]))

    for frag, text in word[1:]:
        if isinstance(text, ShapedStr):
            data, scale = text.__shapeData__, frag.fontSize / 1000
            units = [(sum(data[i].x_advance for i in g) * scale, g[0], g[-1] + 1)
                     for g in (list(g) for _, g in groupby(range(len(text)), key=lambda i: data[i].cluster))]
        else:
            units = [(pdfmetrics.stringWidth(c, frag.fontName, frag.fontSize), i, i + 1) for i, c in enumerate(text)]
        start = 0
        for width, first, end in units:
            if line_width + width > max_width and (line_width or width <= next_width) and (current or first > start):
                if first > start:
                    current.append((sum(w for w, f0, _ in units if start <= f0 < first), frag, text[start:first]))
                close(final=False)
                current, line_width, start = [], 0.0, first
                lineno += 1
                max_width, next_width = next_width, max_widths[min(last, lineno + 1)]
            line_width += width
        if start < len(text):
            current.append((sum(w for w, f0, _ in units if f0 >= start), frag, text[start:]))
    close(final=True)
    return pieces


def _utf16_hex(text: str) -> str:
    return "FEFF" + text.encode("utf-16-be").hex().upper()


def _units(text: str) -> list[str]:
    """A base character plus the combining marks (and joiners) after it: च्छि -> च्, छि."""
    out: list[str] = []
    for ch in text:
        if out and (unicodedata.category(ch) in ("Mn", "Mc") or ch in "‌‍"):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _format_text(self, text):
    """Write shaped text cluster by cluster; clusters whose glyphs are not their own text get /ActualText.

    A cluster with as many glyphs as base+mark units (च्छि = half-form + ligature: च्, छि) gets one span per glyph:
    text extractors (MuPDF) give the extra characters of a multi-glyph span zero width, and the gap that leaves
    before the next glyph reads as a word or line break. Other clusters (reph र्य, लि) get one span.
    """
    source = getattr(text, "_source", None)
    if source is None:
        return _orig_format(self, text)
    data = text.__shapeData__
    clusters = [list(g) for _, g in groupby(range(len(text)), key=lambda i: data[i].cluster)]
    starts = [data[c[0]].cluster for c in clusters] + [getattr(text, "_source_end", len(source))]
    pieces: list[list] = []  # [first glyph, end glyph, actual text or None]
    for n, cluster in enumerate(clusters):
        actual = source[starts[n]:starts[n + 1]]
        if str(_orig_getitem(text, slice(cluster[0], cluster[-1] + 1))) == actual:
            if pieces and pieces[-1][2] is None:
                pieces[-1][1] = cluster[-1] + 1
            else:
                pieces.append([cluster[0], cluster[-1] + 1, None])
            continue
        units = _units(actual)
        if len(cluster) > 1 and len(units) == len(cluster):
            pieces += [[glyph, glyph + 1, unit] for glyph, unit in zip(cluster, units)]
        else:
            pieces.append([cluster[0], cluster[-1] + 1, actual])
    code = []
    for start, end, actual in pieces:
        self._curSubset = -1  # re-select the font: _formatText's text-rise handling needs a previous operator
        ops = _orig_format(self, _orig_getitem(text, slice(start, end)))
        code.append(f"/Span <</ActualText <{_utf16_hex(actual)}>>> BDC {ops} EMC" if actual is not None else ops)
    return " ".join(code)


def install() -> None:
    """Patch ReportLab once per process (idempotent)."""
    global _installed
    if _installed:
        return
    paragraph.shapeFragWord = _shape_word
    textobject.PDFTextObject._formatText = _format_text
    ShapedStr.__getitem__ = _slice
    paragraph._splitFragWord = _split_word
    _installed = True
