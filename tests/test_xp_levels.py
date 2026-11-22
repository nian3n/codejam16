# Owner: Teammate 1 (Game, scenes, widgets)
"""Levels from an XP total (static/xp_levels.js), run in Node."""
import json
import shutil
import subprocess

import pytest

from escape_pod import config

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
URL = (config.STATIC_DIR / "xp_levels.js").as_uri()


def _js(expr: str):
    script = f'import * as X from "{URL}"; console.log(JSON.stringify({expr}));'
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_level_steps():
    assert _js("X.levelFor(0)") == {"level": 1, "title": "Beginner", "into": 0, "need": 250}
    assert _js("X.levelFor(249).level") == 1
    assert _js("X.levelFor(250)") == {"level": 2, "title": "Beginner", "into": 0, "need": 350}
    four = _js("X.levelFor(250 + 350 + 450 + 10)")
    assert four == {"level": 4, "title": "Developing", "into": 10, "need": 550}


def test_titles_never_run_out():
    assert _js("[5, 9, 10, 40].map(X.titleFor)") == ["Practiced", "Skilled", "Accomplished", "Accomplished"]
    assert _js("X.SIGN_XP") == 5
