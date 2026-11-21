# Owner: Teammate 4 (Puzzles and brain)
"""Dynamic answer key: how to solve the modules of ONE drawn bomb.

The static manual (manual/build.py) says what to do in general. This sheet takes a
real draw (seed + level) and walks every rule against the module's facts, so you can
see which condition is true, which rule fires, and the exact instruction.

    uv run answer-key --seed 7 --level intermediate
"""
from __future__ import annotations

import argparse
import random

from escape_pod import config
from escape_pod.puzzles.engine import Module, cond_holds, draw
from escape_pod.puzzles.phrase import condition, phrase, word


def facts_text(m: Module) -> str:
    f = m.facts
    w = m.spec.widget
    if w == "dial":
        return f"pictures {', '.join(word(g) for g in f['options'])}; the needle points at the {word(f['needle'])}"
    if w == "switches":
        return ", ".join(f"{word(s['label'])} ({s['state']})" for s in f["switches"])
    return ", ".join(word(g, m.spec) for g in m.widget.items(f))


def signs_to_make(m: Module) -> list[str]:
    """What the defuser should sign so the expert can find the page and the rule.

    Dial: every picture in reading order, then the needle's picture again last.
    Switch states (on/off) have no sign yet; the expert has to ask. Open question.
    """
    items = m.widget.items(m.facts)
    if m.spec.widget == "dial":
        return items + [m.facts["needle"]]
    return items


def solve_module(m: Module) -> dict:
    derived = m.widget.derive(m.facts)
    rules = []
    for r in m.spec.rules:
        if r.is_else:
            rules.append({"if": None, "conds": [], "matched": True, "then": phrase(r.action(), spec=m.spec)})
            continue
        conds = [{"text": condition(c, m.spec), "holds": cond_holds(c, derived)} for c in r.when]
        rules.append({"if": " and ".join(c["text"] for c in conds), "conds": conds,
                      "matched": all(c["holds"] for c in conds), "then": phrase(r.action(), spec=m.spec)})
    fired = m.fired_rule()
    return {
        "id": m.spec.id,
        "title": m.spec.title,
        "facts": facts_text(m),
        "signs": [g.upper() for g in signs_to_make(m)],
        "rules": rules,
        "fired": fired + 1,
        "solution": m.solution().to_json(),
        "instruction": phrase(m.solution(), m),
    }


def sheet_markdown(modules: list[Module], header: str = "") -> str:
    lines = ["# Answer key", ""]
    if header:
        lines += [header, ""]
    for i, m in enumerate(modules, 1):
        s = solve_module(m)
        lines += [f"## Module {i}: {s['title']} (`{s['id']}`)", "",
                  f"- **On the module:** {s['facts']}",
                  f"- **Signs to make:** {' · '.join(s['signs'])}", "", "Rule check:", ""]
        for j, r in enumerate(s["rules"], 1):
            mark = "fires" if j == s["fired"] else ("true" if r["matched"] else "false")
            if r["if"] is None:
                lines.append(f"{j}. Otherwise: {r['then']} → **{mark}**")
            else:
                parts = " and ".join(f"{c['text']} ({'yes' if c['holds'] else 'no'})" for c in r["conds"])
                lines.append(f"{j}. If {parts}: {r['then']} → **{mark}**")
        lines += ["", f"**Do this:** {s['instruction']}", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--level", choices=list(config.LEVELS), default="intermediate")
    a = ap.parse_args()
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Windows consoles default to cp1252
    mods = draw(random.Random(a.seed), config.LEVELS[a.level])
    print(sheet_markdown(mods, f"Seed {a.seed}, level {a.level}."))


if __name__ == "__main__":
    main()
