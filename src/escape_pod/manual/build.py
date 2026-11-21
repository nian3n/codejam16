# Owner: Teammate 4 (Puzzles and brain)
"""Static manual: puzzle rules -> English pages (spec §5.4).

The manual never changes during a game: it is built only from puzzles/data/*.json,
the same rules the engine uses (spec design rule 2, one source of truth).

    uv run build-manual             # writes docs/manual/<id>.md and MANUAL.md
"""
from __future__ import annotations

from escape_pod import config
from escape_pod.puzzles.engine import WIDGETS, load_pool
from escape_pod.puzzles.models import PuzzleSpec
from escape_pod.puzzles.phrase import condition, phrase, word

WIDGET_NAMES = {"wires": "Wires", "keypad": "Keypad", "icons": "Picture buttons",
                "dial": "Dial", "switches": "Switches", "big_button": "Big button"}


def page(spec: PuzzleSpec, number: int | None = None) -> dict:
    """One manual page as data. The web app renders this; page_markdown() prints it."""
    rules = []
    for r in spec.rules:
        act = phrase(r.action(), spec=spec)
        if r.is_else:
            rules.append({"if": None, "then": act})
        else:
            rules.append({"if": " and ".join(condition(c, spec) for c in r.when), "then": act})
    return {
        "id": spec.id,
        "number": number,
        "title": spec.title,
        "topic": spec.topic,
        "widget": spec.widget,
        "widget_name": WIDGET_NAMES[spec.widget],
        "hard": spec.hard,
        "looks_like": spec.looks_like,
        "words": [word(g, spec) for g in spec.pool],
        "glosses": list(spec.pool),
        "reading_order": WIDGETS[spec.widget].reading_order,
        "rules": rules,
    }


def page_markdown(p: dict) -> str:
    num = f"{p['number']}. " if p["number"] else ""
    lines = [
        f"# {num}{p['title']}",
        "",
        f"**Topic:** {p['topic']} · **Widget:** {p['widget_name']}" + (" · **Hard**" if p["hard"] else ""),
        "",
        "## How to recognize it",
        "",
        p["looks_like"],
        "",
        f"Words you can see on it: {', '.join(p['words'])}.",
        "",
        p["reading_order"],
        "",
        "## Rules",
        "",
        "Read the rules in order. Do the first rule that is true.",
        "",
    ]
    for i, r in enumerate(p["rules"], 1):
        lines.append(f"{i}. **Otherwise:** {r['then']}" if r["if"] is None
                     else f"{i}. **If** {r['if']}: {r['then']}")
    return "\n".join(lines) + "\n"


def all_pages() -> list[dict]:
    return [page(s, i) for i, s in enumerate(load_pool().values(), 1)]


def build() -> list[str]:
    out = config.MANUAL_PAGES_DIR
    out.mkdir(parents=True, exist_ok=True)
    pages = all_pages()
    for p in pages:
        (out / f"{p['id']}.md").write_text(page_markdown(p), encoding="utf-8")
    index = ["# Keep Moving and Nobody Explodes: field manual", "",
             "Find the page whose words match what the field agent signs. Each page has one topic.", ""]
    index += [f"{p['number']}. [{p['title']}]({p['id']}.md): {p['topic']}" for p in pages]
    full = "\n".join(index) + "\n\n---\n\n" + "\n---\n\n".join(page_markdown(p) for p in pages)
    (out / "MANUAL.md").write_text(full, encoding="utf-8")
    return [p["id"] for p in pages]


def main():
    ids = build()
    print(f"Wrote {len(ids)} pages and MANUAL.md to {config.MANUAL_PAGES_DIR}")


if __name__ == "__main__":
    main()
