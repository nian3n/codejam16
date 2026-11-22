# Owner: Teammate 1 (Game, scenes, widgets)
"""Levels from an XP total (static/xp_levels.js), run in Node."""
import json
import shutil
import subprocess

import pytest

import config

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


STORE = (config.STATIC_DIR / "xp_store.js").as_uri()


def _store(body: str):
    """Run `body` with S = xp_store.js and mem = a fake localStorage (length, key, getItem, setItem)."""
    script = f'''import * as S from "{STORE}";
class Mem {{ constructor() {{ this.m = new Map(); this.full = false; }}
  get length() {{ return this.m.size; }} key(i) {{ return [...this.m.keys()][i] ?? null; }}
  getItem(k) {{ return this.m.has(k) ? this.m.get(k) : null; }}
  setItem(k, v) {{ if (this.full) throw new Error("QuotaExceeded"); this.m.set(k, String(v)); }} }}
const mem = new Mem();
console.log(JSON.stringify((() => {{ {body} }})()));'''
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_round_counts_once():
    got = _store('''
      S.saveCredits(mem, "p1", ["r1:case_lock:0", "r1:0"]);
      const round = { round_id: "r1", total: 135, signs_xp: 10 };
      const first = S.saveRoundXp(mem, "p1", round);
      const again = S.saveRoundXp(mem, "p1", round);
      return [first, again, S.totalXp(mem, "p1")];''')
    assert got[0] == {"before": 10, "after": 135, "saved": True}
    assert got[1] == {"before": 10, "after": 135, "saved": False}
    assert got[2] == 135


def test_old_credits_alone_give_xp():
    assert _store('S.saveCredits(mem, "p1", ["a", "b", "c"]); return [S.totalXp(mem, "p1"), S.totalXp(mem, "p2")];') == [15, 0]


def test_full_storage_saves_nothing():
    got = _store('''mem.full = true;
      return [S.saveCredits(mem, "p1", ["a"]), S.saveRoundXp(mem, "p1", { round_id: "r", total: 50, signs_xp: 0 }),
              S.totalXp(mem, "p1")];''')
    assert got == [[], {"before": 0, "after": 0, "saved": False}, 0]


def test_a_practice_word_counts_once():
    got = _store('''S.saveCredits(mem, "p1", [S.practiceCredit("cat")]);
      S.saveCredits(mem, "p1", [S.practiceCredit("cat")]);
      S.saveCredits(mem, "p1", [S.practiceCredit("dog")]);
      return S.totalXp(mem, "p1");''')
    assert got == 10


WIN = '{ label: "Bomb defused", xp: 50 }'


def _round(rid: str, total: int, signs: int, won: bool) -> str:
    parts = f"[{WIN}]" if won else "[]"
    return f'{{ round_id: "{rid}", total: {total}, signs_xp: {signs}, parts: {parts} }}'


def test_history_orders_rounds_by_time():
    got = _store(f'''
      S.saveRoundXp(mem, "p", {_round("b", 200, 0, True)}, 2000);
      S.saveRoundXp(mem, "p", {_round("a", 60, 0, False)}, 1000);
      return [S.history(mem, "p"), S.totalXp(mem, "p")];''')
    hist, total = got
    assert hist["start"] == 0
    assert hist["rounds"] == [{"at": 1000, "gain": 60, "total": 60, "won": False},
                              {"at": 2000, "gain": 200, "total": 260, "won": True}]
    assert total == 260


def test_history_mixes_old_and_new_rounds():
    got = _store(f'''
      mem.setItem("ep:round-xp:p:old", "100");             // a round saved before the history
      S.saveCredits(mem, "p", ["r1:0", "r1:1"]);           // the new round's 2 sign credits (10 XP)
      S.saveRoundXp(mem, "p", {_round("r1", 70, 10, True)}, 5000);
      return [S.history(mem, "p"), S.totalXp(mem, "p")];''')
    hist, total = got
    assert total == 100 + 10 + 60
    assert hist["start"] == 100 and hist["rounds"][-1]["total"] == total and hist["rounds"][0]["gain"] == 70


def test_history_keeps_the_last_30():
    got = _store(f'''
      for (let i = 0; i < 35; i++) S.saveRoundXp(mem, "p", {{ round_id: "r" + i, total: 10, signs_xp: 0, parts: [] }}, 1000 + i);
      return [S.history(mem, "p"), S.totalXp(mem, "p")];''')
    hist, total = got
    assert len(hist["rounds"]) == 30 and hist["start"] == 50
    assert hist["rounds"][0]["at"] == 1005 and hist["rounds"][-1]["total"] == total == 350


def test_corrupt_round_counts_as_zero():
    got = _store('''mem.setItem("ep:round-xp:p:x", "{oops"); mem.setItem("ep:round-xp:p:y", "abc");
      return [S.totalXp(mem, "p"), S.history(mem, "p")];''')
    assert got == [0, {"start": 0, "rounds": []}]


def test_empty_profile_has_no_rounds():
    assert _store('return S.history(mem, "nobody");') == {"start": 0, "rounds": []}
