"""fastpath.try_fastpath — keyword bypass for the Ollama LLM call.

Pure logic, no Ollama/mic needed. Only unambiguous single-clause phrasings must
match; anything else must fall through to the LLM (None).
"""

import pytest

from tello_control.voice.commands import Command
from tello_control.voice.fastpath import try_fastpath


@pytest.mark.parametrize(
    "text, expected",
    [
        ("start", [Command("takeoff", None)]),
        ("hebe ab", [Command("takeoff", None)]),
        ("lande", [Command("land", None)]),
        ("notstopp", [Command("emergency", None)]),
        ("stopp", [Command("emergency", None)]),
        ("vor", [Command("forward", 100)]),
        ("vor 200 cm", [Command("forward", 200)]),
        ("vor 2 m", [Command("forward", 200)]),
        ("zurück", [Command("back", 100)]),
        ("links", [Command("left", 100)]),
        ("rechts", [Command("right", 100)]),
        ("hoch", [Command("up", 100)]),
        ("runter", [Command("down", 100)]),
        ("dreh dich links", [Command("rotate_ccw", 90)]),
        ("dreh dich rechts um 45 grad", [Command("rotate_cw", 45)]),
    ],
)
def test_fastpath_matches_simple_commands(text, expected):
    assert try_fastpath(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "flieg vor und dann lande",          # multi-clause -> LLM
        "flieg einen halben meter nach vorne",  # German number words -> LLM
        "irgendwas unverständliches",
        "vor 5000 cm",                        # out of SDK range -> LLM decides
    ],
)
def test_fastpath_falls_through_to_llm(text):
    assert try_fastpath(text) is None
