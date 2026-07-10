"""Measure the context cost of orienting in this repo: graphify vs. reading the files.

Run:  python scripts/graphify_benchmark.py

WHY THIS SCRIPT EXISTS
----------------------
The README used to claim graphify answers architecture questions at "roughly 10x lower
token cost". That number had no source. This measures it.

WHAT GRAPHIFY ACTUALLY RETURNS
------------------------------
Neither command returns code. Both return structure:

  graphify query "<q>"   flat list of matching nodes with src= paths. Emits NO edges,
                         so it cannot express a relationship. Truncates its own output
                         at --budget tokens (default 2000), which means any "savings"
                         measured against it are partly an artifact of that flag.
  graphify explain "<X>" one node's neighbours and typed relations (uses / calls /
                         method / contains), tagged EXTRACTED or INFERRED.

So graphify is an *index*, not an oracle. It answers "where is this / what touches it",
never "how does it work" — the implementation detail still requires opening the file.
A token comparison is therefore only meaningful next to a sufficiency grade, which is
why SUFFICIENCY below is filled in by hand and printed alongside every ratio.

BASELINE
--------
ANSWER_FILES is the hand-picked minimal set of files that genuinely contain the answer.
It is a judgement call, written out explicitly rather than derived. It is deliberately
small: a small baseline shrinks the ratio, biasing the result *against* graphify. Using
the files graphify itself cites would be far more flattering, since BFS depth-2 pulls in
most of the repo -- which is exactly why that isn't used.

TOKENIZER
---------
tiktoken cl100k_base: OpenAI's BPE, ~10-15% off Claude's in absolute terms, but applied
identically to both arms so the ratio is stable. Falls back to chars/4 if unavailable.

EXCLUDED: the one-time graph build. `graphify update` is AST-only, but the initial
extract runs a semantic LLM pass. This measures query-time cost only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUDGET = 2000  # graphify query default; bounds the query arm by construction

# Pre-registered: questions, the files that answer them, the best graphify command for
# each, and a hand-graded verdict on whether graphify's output actually suffices.
#   PASS    - contains the answer
#   PARTIAL - locates the answer; you must still read the file
#   FAIL    - does not address the question
CASES: list[dict] = [
    {
        "q": "main modules and their responsibilities",
        "cmd": ["query", "main modules and their responsibilities"],
        "files": [
            "src/tello_control/core/controller.py",
            "src/tello_control/core/mock_tello.py",
            "src/tello_control/gesture/app.py",
            "src/tello_control/voice/app.py",
            "src/tello_control/sim/pybullet_backend.py",
        ],
        # keys on the token "main" and returns main() functions in demo/ps4/build_pdf.
        "sufficiency": "FAIL",
    },
    {
        "q": "how does DroneController select a backend",
        "cmd": ["explain", "DroneController"],
        "files": ["src/tello_control/core/controller.py"],
        # names __init__ and the three backends; the if/elif logic is not in the graph.
        "sufficiency": "PARTIAL",
    },
    {
        "q": "how does PyBulletBackend relate to MockTello",
        "cmd": ["explain", "PyBulletBackend"],
        "files": [
            "src/tello_control/sim/pybullet_backend.py",
            "src/tello_control/core/mock_tello.py",
        ],
        # states the link, but as `uses [INFERRED]`; the true relation is inheritance.
        "sufficiency": "PARTIAL",
    },
    {
        "q": "how does a gesture become a drone command",
        "cmd": ["query", "how does a gesture become a drone command"],
        "files": [
            "src/tello_control/gesture/detector.py",
            "src/tello_control/gesture/command_map.py",
            "src/tello_control/gesture/runner.py",
            "src/tello_control/gesture/app.py",
        ],
        # lists every node in the pipeline, no edges, so the ordering is not recoverable.
        "sufficiency": "PARTIAL",
    },
    {
        "q": "where are voice commands validated",
        "cmd": ["explain", "validate_list"],
        "files": ["src/tello_control/voice/commands.py"],
        # points straight at validate_list/validate_command in commands.py.
        "sufficiency": "PARTIAL",
    },
]


def count_tokens(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except ImportError:
        return len(text) // 4


def graphify_tokens(cmd: list[str]) -> int:
    argv = ["graphify", *cmd]
    if cmd[0] == "query":
        argv += ["--budget", str(BUDGET)]
    out = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=True).stdout
    return count_tokens(out)


def file_tokens(paths: list[str]) -> int:
    return sum(
        count_tokens((REPO / p).read_text(encoding="utf-8", errors="replace"))
        for p in paths
        if (REPO / p).exists()
    )


def main() -> int:
    rows = []
    for case in CASES:
        g_tok = graphify_tokens(case["cmd"])
        f_tok = file_tokens(case["files"])
        rows.append((case["q"], case["cmd"][0], g_tok, f_tok, f_tok / g_tok, case["sufficiency"]))

    print(f"\ngraphify vs. reading the files   |   query --budget {BUDGET}   |   cl100k_base\n")
    hdr = f"{'question':<44} {'cmd':<8} {'graphify':>8} {'files':>7} {'ratio':>7}  {'sufficient?':<8}"
    print(hdr)
    print("-" * len(hdr))
    for q, cmd, gt, ft, ratio, suf in rows:
        print(f"{q[:43]:<44} {cmd:<8} {gt:>8} {ft:>7} {ratio:>6.1f}x  {suf:<8}")
    print("-" * len(hdr))

    useful = [r for r in rows if r[5] != "FAIL"]
    med = sorted(r[4] for r in useful)[len(useful) // 2]
    print(f"{'MEDIAN (excluding the FAIL)':<44} {'':<8} {'':>8} {'':>7} {med:>6.1f}x")

    print(
        "\nRead this table as: graphify costs `graphify` tokens to locate what reading"
        "\n`files` tokens would tell you in full. No row is a clean PASS -- the graph"
        "\nindexes structure, it does not contain code. The FAIL row is the cheapest row,"
        "\nwhich is precisely why token count alone is a bad metric."
        "\n\nOne-time graph build cost excluded."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
