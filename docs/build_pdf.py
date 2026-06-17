#!/usr/bin/env python3
"""
build_pdf.py — render docs/PROJECT.md to docs/PROJECT.pdf, fully offline.

Pipeline:  Markdown --(markdown-it-py)--> styled HTML --(headless Chrome)--> PDF.

No pandoc / LaTeX required; uses only markdown-it-py (a core test/runtime dep here)
and a local Chrome/Chromium install. Run via docs/build_pdf.sh, or directly:

    python docs/build_pdf.py
"""

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "PROJECT.md")
HTML = os.path.join(HERE, "_project.html")
PDF = os.path.join(HERE, "PROJECT.pdf")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
]

CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 11pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 4px;
     margin-top: 28px; page-break-after: avoid; }
h2 { font-size: 15pt; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 18px; page-break-after: avoid; }
p, li { page-break-inside: avoid; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9.5pt;
       background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
pre { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 6px;
      padding: 12px; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 9pt; line-height: 1.35; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 12px 0; }
th, td { border: 1px solid #ccc; padding: 5px 8px; text-align: left;
         vertical-align: top; }
th { background: #f0f0f0; }
img { max-width: 100%; display: block; margin: 12px auto; }
.title-block { text-align: center; margin: 40px 0 30px; }
.title-block .t { font-size: 24pt; font-weight: 700; }
.title-block .s { font-size: 13pt; color: #555; margin-top: 6px; }
.title-block .m { font-size: 11pt; color: #777; margin-top: 14px; }
a { color: #0366d6; text-decoration: none; }
"""


def split_frontmatter(text):
    """Return (meta dict, body) splitting a leading --- YAML block."""
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return meta, text
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end():]


def main():
    chrome = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)
    if chrome is None:
        sys.exit("No Chrome/Chromium found — install Chrome or use pandoc instead.")

    from markdown_it import MarkdownIt

    with open(SRC, encoding="utf-8") as f:
        meta, body = split_frontmatter(f.read())

    md = MarkdownIt("js-default")
    body_html = md.render(body)

    title_block = ""
    if meta.get("title"):
        title_block = (
            '<div class="title-block">'
            f'<div class="t">{meta.get("title", "")}</div>'
            f'<div class="s">{meta.get("subtitle", "")}</div>'
            f'<div class="m">{meta.get("author", "")} &middot; {meta.get("date", "")}</div>'
            "</div>"
        )

    html = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>{title_block}{body_html}</body></html>"
    )
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)

    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={PDF}", "--virtual-time-budget=10000",
         f"file://{HTML}"],
        check=True,
    )
    os.remove(HTML)
    size_kb = os.path.getsize(PDF) / 1024
    print(f"Wrote {PDF} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
