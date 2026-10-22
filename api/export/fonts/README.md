# Fonts embedded in the PDF export

| File | Source | Licence |
|---|---|---|
| `NotoSans-Regular.ttf`, `NotoSans-Bold.ttf` | <https://github.com/notofonts/notofonts.github.io/tree/main/fonts/NotoSans/hinted/ttf> (Noto Project, `latin-greek-cyrillic`) | SIL OFL 1.1 |
| `NotoSansDevanagari-Regular.ttf`, `NotoSansDevanagari-Bold.ttf` | <https://github.com/notofonts/notofonts.github.io/tree/main/fonts/NotoSansDevanagari/hinted/ttf> (Noto Project, `devanagari`) | SIL OFL 1.1 |

Downloaded 2026-10-22. `OFL.txt` is the licence text (both families use the same OFL 1.1 text from the Noto Project Authors).
The OFL allows embedding and redistribution with the software. The PDFs embed subsets of these fonts.

The Devanagari font has no Latin letters, so `export/pdf.py` sets Devanagari runs in Noto Sans Devanagari and everything
else in Noto Sans. `export/shaping.py` shapes them with HarfBuzz (`uharfbuzz`) through ReportLab.
