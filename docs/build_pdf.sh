#!/usr/bin/env bash
# Build docs/PROJECT.pdf from docs/PROJECT.md.
#
# Preferred: pandoc + a LaTeX engine (xelatex) if available — nicest typography.
# Fallback:  fully offline Markdown -> HTML -> headless-Chrome PDF (build_pdf.py),
#            which needs no extra install beyond Chrome.
set -euo pipefail
cd "$(dirname "$0")"

if command -v pandoc >/dev/null 2>&1; then
    echo "Using pandoc + xelatex ..."
    pandoc PROJECT.md -o PROJECT.pdf \
        --pdf-engine=xelatex --toc -V geometry:margin=2.5cm \
        -V mainfont="Helvetica Neue" -V colorlinks=true
else
    echo "pandoc not found — using offline HTML/Chrome fallback ..."
    # Use the project's Python (has markdown-it-py). Prefer the repo venv if present.
    PY="../venv/bin/python"
    [ -x "$PY" ] || PY="python3"
    "$PY" build_pdf.py
fi

echo "Done: $(pwd)/PROJECT.pdf"
