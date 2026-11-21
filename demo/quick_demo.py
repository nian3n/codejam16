# Owner: shared (throwaway demo; NOT part of the spec layout in CLAUDE.md §3)
"""Escape Pod quick demo: an M1-style slice of the spec in one file.

What it shows, end to end:
  type glosses (stands in for webcam signs) -> retrieval vote over the manual
  -> mock "LLM" answer from the manual page -> code verification -> alien reply
  -> player clicks the bomb -> defuse or strike.

Run:  .venv/Scripts/python demo/quick_demo.py [--seed N]
Keys: Tab = bomb/manual, Enter = add sign, Ctrl+Enter = send,
      F2 = toggle a "broken LLM" so you can watch verify() correct it,
      R = new game after the end screen.
"""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Puzzle data (same JSON shape as spec §5.3). Only the 3 M1 puzzles.
# ---------------------------------------------------------------------------
PUZZLES = {
    "colors": {
        "id": "colors", "title": "Wire panel", "widget": "wires", "topic": "colors",
        "looks_like": "A panel with four colored wires.",
        "pool": ["red", "blue", "green", "yellow", "black", "white", "brown", "orange"],
        "setup": {"shown": 4},
        "rules": [
            {"if": [["has:red", "==", True], ["has:blue", "==", True]],
             "then": {"verb": "cut", "target": {"color": "blue"}}},
            {"if": [["has:yellow", "==", False]],
             "then": {"verb": "cut", "target": {"wire": "first"}}},
            {"else": {"verb": "cut", "target": {"wire": "last"}}},
        ],
    },
    "pets_farm": {
        "id": "pets_farm", "title": "Animal panel", "widget": "icons",
        "topic": "pets and farm animals",
        "looks_like": "A panel with four buttons, each showing a pet or farm animal.",
        "pool": ["cat", "dog", "cow", "pig", "horse", "duck", "hen", "donkey"],
        "setup": {"shown": 4},
        "rules": [
            {"if": [["has:cat", "==", True], ["has:dog", "==", True]],
             "then": {"verb": "press", "target": {"icon": "dog"}}},
            {"if": [["has:cow", "==", True]],
             "then": {"verb": "press", "target": {"icon": "cow"}}},
            {"else": {"verb": "press", "target": {"icon": "last"}}},
        ],
    },
    "transport": {
        "id": "transport", "title": "Travel dial", "widget": "dial", "topic": "transport",
        "looks_like": "A dial with four vehicles around it and a needle pointing at one.",
        "pool": ["car", "boat", "airplane", "helicopter"],
        "setup": {"shown": 4},
        "rules": [
            {"if": [["needle", "==", "car"]], "then": {"verb": "turn", "target": {"to": "boat"}}},
            {"if": [["needle", "==", "boat"]], "then": {"verb": "turn", "target": {"to": "helicopter"}}},
            {"else": {"verb": "turn", "target": {"to": "car"}}},
        ],
    },
}
# The other 17 pool entries, shown greyed in the manual index (spec §5.1).
OTHER_TITLES = ["numbers", "alphabet", "wild_animals", "family", "people_jobs", "body",
                "food", "clothes", "weather_sky", "feelings", "actions", "home_things",
                "places", "toys", "school", "opposites", "time_words"]
CORE = {"yes", "no", "finish"}


# ---------------------------------------------------------------------------
# Rule engine (spec §5.2). No eval: conditions are [key, op, value] data.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Action:
    verb: str
    target: tuple  # (key, value) pairs; a tuple so Action stays hashable

    @staticmethod
    def make(verb, target: dict) -> "Action":
        return Action(verb, tuple(sorted(target.items())))

    def t(self) -> dict:
        return dict(self.target)


OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, "<": lambda a, b: a < b,
       "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
       "in": lambda a, b: a in b}


def generate(spec, rng) -> dict:
    items = rng.sample(spec["pool"], spec["setup"]["shown"])
    if spec["widget"] == "wires":
        return {"colors": items}
    if spec["widget"] == "icons":
        return {"icons": items}
    return {"options": items, "needle": rng.choice(items)}  # dial


def items_of(widget, facts) -> list[str]:
    return facts.get("colors") or facts.get("icons") or facts.get("options")


def derive(widget, facts) -> dict:
    items = items_of(widget, facts)
    d: dict[str, object] = {f"has:{g}": True for g in items}
    d.update(first=items[0], last=items[-1], count=len(items))
    if widget == "dial":
        d["needle"] = facts["needle"]
    return d


def resolve(widget, action: Action, facts) -> Action:
    """Symbolic targets ("first", "last") -> concrete topic words (spec §5.1 target_words)."""
    t = action.t()
    items = items_of(widget, facts)
    if widget == "wires" and "wire" in t:
        return Action.make("cut", {"color": items[0] if t["wire"] == "first" else items[-1]})
    if widget == "icons" and t.get("icon") in ("first", "last"):
        return Action.make("press", {"icon": items[0] if t["icon"] == "first" else items[-1]})
    return action


def evaluate(spec, facts) -> Action:
    d = derive(spec["widget"], facts)
    for rule in spec["rules"]:
        if "else" in rule:
            raw = rule["else"]
        elif all(OPS[op](d.get(k, False), v) for k, op, v in rule["if"]):
            raw = rule["then"]
        else:
            continue
        return resolve(spec["widget"], Action.make(raw["verb"], raw["target"]), facts)
    raise ValueError("last rule must be else")


@dataclass
class Module:
    spec: dict
    facts: dict
    defused: bool = False

    def solution(self) -> Action:
        return evaluate(self.spec, self.facts)

    def check(self, action: Action) -> bool:
        return action == self.solution()


def draw_modules(rng) -> list[Module]:
    return [Module(s, generate(s, rng)) for s in PUZZLES.values()]


def phrase(action: Action) -> str:
    t = action.t()
    if action.verb == "cut":
        return f"Cut the {t['color']} wire." if "color" in t else f"Cut the {t['wire']} wire."
    if action.verb == "press":
        return f"Press the {t['icon']}." if t["icon"] not in ("first", "last") else f"Press the {t['icon']} button."
    return f"Turn the dial to the {t['to']}."


def cond_text(k, op, v) -> str:
    if k.startswith("has:"):
        return f"there is {'a' if v else 'no'} {k[4:]}"
    if k == "needle":
        return f"the needle points at the {v}"
    return f"the {k} is {v}" if op == "==" else f"{k} {op} {v}"


def manual_page(spec) -> list[str]:
    """One source of truth: the same rules produce the manual text (spec rule 2)."""
    lines = [spec["title"], "", "How to recognize it:", spec["looks_like"],
             "Words: " + ", ".join(spec["pool"]), "", "Rules (first match wins):"]
    for i, r in enumerate(spec["rules"], 1):
        if "else" in r:
            lines.append(f"{i}. Otherwise: {phrase(Action.make(r['else']['verb'], r['else']['target']))}")
        else:
            conds = " and ".join(cond_text(*c) for c in r["if"])
            lines.append(f"{i}. If {conds}: {phrase(Action.make(r['then']['verb'], r['then']['target']))}")
    return lines


# ---------------------------------------------------------------------------
# Brain: retrieval vote, mock answer, verify (spec §7, §8).
# ---------------------------------------------------------------------------
OWNER = {g: pid for pid, s in PUZZLES.items() for g in s["pool"]}


def retrieve(glosses) -> list[tuple[str, float]]:
    """The --mock-llm path: the gloss vote only. Score = share of glosses the page owns."""
    known = [g for g in glosses if g in OWNER]
    if not known:
        return []
    votes = {}
    for g in known:
        votes[OWNER[g]] = votes.get(OWNER[g], 0) + 1
    return sorted(((p, n / len(glosses)) for p, n in votes.items()), key=lambda x: -x[1])


@dataclass
class Answer:
    page_id: str
    facts: dict
    recast: str
    action: Action
    english: str


def mock_answer(glosses, page_id, broken=False) -> Answer:
    """Stands in for the LLM: reads ONLY the signed glosses and the page's rules."""
    spec = PUZZLES[page_id]
    signed = [g for g in glosses if g in spec["pool"]]
    if spec["widget"] == "dial":
        # The player signs where the needle points.
        facts = {"options": spec["pool"], "needle": signed[-1]}
        recast = f"The needle points at the {signed[-1]}."
    else:
        key = "colors" if spec["widget"] == "wires" else "icons"
        facts = {key: signed}
        recast = "You see " + ", ".join(f"a {g}" for g in signed) + "."
    action = evaluate(spec, facts)
    if broken:  # deliberately wrong pick, to show verify() catching it
        others = [g for g in spec["pool"] if g not in action.t().values()]
        k = next(iter(action.t()))
        action = Action.make(action.verb, {k: others[0]})
    return Answer(page_id, facts, recast, action, phrase(action))


@dataclass
class Verdict:
    kind: str  # ok | ask_sure | ask_more | corrected
    english: str


def verify(ans: Answer, module: Module) -> Verdict:
    """Code decides right and wrong (spec rule 1). Wrong LLM answers are never shown."""
    if ans.page_id != module.spec["id"]:
        return Verdict("ask_sure", "Are you sure? Look again.")
    real = items_of(module.spec["widget"], module.facts)
    said = items_of(module.spec["widget"], ans.facts)
    if module.spec["widget"] == "dial":
        if ans.facts["needle"] != module.facts["needle"]:
            return Verdict("ask_sure", "Are you sure about where the needle points?")
    else:
        wrong = [g for g in said if g not in real]
        if wrong:
            return Verdict("ask_sure", f"Are you sure you see a {wrong[0]}?")
        if len(said) < len(real):
            return Verdict("ask_more", f"Which {'wires' if module.spec['widget'] == 'wires' else 'animals'} do you see? Show me all of them.")
    if ans.action == module.solution():
        return Verdict("ok", f"{ans.recast} {ans.english}")
    return Verdict("corrected", f"{ans.recast} {phrase(module.solution())}")


# ---------------------------------------------------------------------------
# Game (pygame). Scenes: BOMB <-> MANUAL; states SIGNING/THINKING/REPLYING.
# ---------------------------------------------------------------------------
W, H = 1280, 720
COLORS = {"red": (220, 50, 50), "blue": (60, 110, 230), "green": (60, 180, 80),
          "yellow": (240, 210, 50), "black": (25, 25, 25), "white": (240, 240, 240),
          "brown": (130, 80, 40), "orange": (250, 140, 30)}
BG, PANEL, INK, DIM, ACC = (18, 22, 34), (34, 40, 58), (230, 235, 245), (120, 130, 150), (120, 220, 200)


@dataclass
class Game:
    seed: int
    modules: list = field(default_factory=list)
    selected: int | None = None
    scene: str = "BOMB"
    state: str = "SIGNING"
    typed: str = ""
    signs: list = field(default_factory=list)
    reply: str = "Alien: Select a module, then sign what you see."
    timer: float = 300.0
    strikes: int = 0
    end: str | None = None
    think_t: float = 0.0
    pending: "Verdict | None" = None
    open_page: str | None = None
    candidates: list = field(default_factory=list)
    broken_llm: bool = False
    flash: float = 0.0
    log: list = field(default_factory=list)

    def __post_init__(self):
        self.modules = draw_modules(random.Random(self.seed))

    # -- the exchange (spec §1 steps 3-6) ----------------------------------
    def send(self):
        if self.selected is None:
            self.reply = "Alien: Which module? Click one first."
            return
        if not self.signs:
            return
        self.scene, self.state, self.think_t = "MANUAL", "THINKING", 1.6
        mod = self.modules[self.selected]
        hits = retrieve(self.signs)
        self.candidates = [p for p, _ in hits[:3]]
        if not hits:
            v = Verdict("ask_more", "I don't know those signs. Show me more signs.")
            self.open_page = None
        else:
            self.open_page = hits[0][0]
            ans = mock_answer(self.signs, hits[0][0], self.broken_llm)
            v = verify(ans, mod)
            self.log.append({"signs": list(self.signs), "page": ans.page_id,
                             "llm": ans.english, "verdict": v.kind})
        self.pending = v
        self.signs = []

    def act(self, action: Action):
        mod = self.modules[self.selected]
        if mod.check(action):
            mod.defused = True
            self.reply = "Alien: Module defused! Nice signing."
            if all(m.defused for m in self.modules):
                self.end = "ESCAPED"
        else:
            self.strikes += 1
            self.flash = 0.4
            self.reply = f"Alien: STRIKE {self.strikes}! That was not right."
            if self.strikes >= 3:
                self.end = "BOOM"

    def update(self, dt):
        if self.end:
            return
        self.timer -= dt
        self.flash = max(0.0, self.flash - dt)
        if self.timer <= 0:
            self.end = "BOOM"
        if self.state == "THINKING":
            self.think_t -= dt
            if self.think_t <= 0:
                v = self.pending
                tag = {"ok": "", "corrected": " [verify() corrected the LLM]",
                       "ask_sure": "", "ask_more": ""}[v.kind]
                self.reply = f"Alien: {v.english}{tag}"
                self.state, self.think_t = "REPLYING", 2.5
        elif self.state == "REPLYING":
            self.think_t -= dt
            if self.think_t <= 0:
                self.scene, self.state = "BOMB", "SIGNING"


def module_rects():
    return [pygame.Rect(30 + (i % 2) * 415, 80 + (i // 2) * 290, 395, 270) for i in range(3)]


def item_rects(widget, items, r):
    if widget == "wires":
        return [pygame.Rect(r.x + 30, r.y + 60 + i * 48, r.w - 60, 30) for i in range(len(items))]
    if widget == "icons":
        return [pygame.Rect(r.x + 25 + (i % 2) * 175, r.y + 60 + (i // 2) * 95, 165, 80) for i in range(len(items))]
    cx, cy = r.centerx, r.y + 160
    pos = [(0, -80), (130, 0), (0, 80), (-130, 0)]
    return [pygame.Rect(cx + dx - 60, cy + dy - 20, 120, 40) for dx, dy in pos]


def draw_bomb(g: Game, s, F, Fs):
    for i, (m, r) in enumerate(zip(g.modules, module_rects())):
        pygame.draw.rect(s, PANEL, r, border_radius=12)
        pygame.draw.rect(s, ACC if g.selected == i else DIM, r, 3 if g.selected == i else 1, border_radius=12)
        s.blit(F.render(m.spec["title"] + ("  DEFUSED" if m.defused else ""), True, ACC if m.defused else INK), (r.x + 15, r.y + 12))
        w = m.spec["widget"]
        items = items_of(w, m.facts)
        for it, ir in zip(items, item_rects(w, items, r)):
            if w == "wires":
                pygame.draw.rect(s, COLORS[it], ir, border_radius=8)
            elif w == "icons":
                pygame.draw.rect(s, (60, 70, 95), ir, border_radius=10)
                s.blit(F.render(it.upper(), True, INK), F.render(it.upper(), True, INK).get_rect(center=ir.center))
            else:
                hot = it == m.facts["needle"]
                pygame.draw.rect(s, (90, 70, 40) if hot else (60, 70, 95), ir, border_radius=10)
                s.blit(Fs.render(it, True, INK), Fs.render(it, True, INK).get_rect(center=ir.center))
        if w == "dial":
            c = (r.centerx, r.y + 160)
            pygame.draw.circle(s, (80, 90, 115), c, 34)
            tgt = item_rects(w, items, r)[items.index(m.facts["needle"])].center
            pygame.draw.line(s, (250, 90, 60), c, ((c[0] * 2 + tgt[0]) // 3, (c[1] * 2 + tgt[1]) // 3), 6)
    # Right third: the "webcam" panel. In --mock-signs mode it is a text box.
    p = pygame.Rect(870, 80, 380, 560)
    pygame.draw.rect(s, PANEL, p, border_radius=12)
    s.blit(F.render("Webcam (mock: type signs)", True, INK), (p.x + 15, p.y + 12))
    box = pygame.Rect(p.x + 15, p.y + 50, p.w - 30, 40)
    pygame.draw.rect(s, (15, 18, 28), box, border_radius=8)
    s.blit(F.render(g.typed + "_", True, ACC), (box.x + 10, box.y + 8))
    s.blit(Fs.render("Enter = confirm one sign  |  Ctrl+Enter = send", True, DIM), (p.x + 15, p.y + 98))
    s.blit(F.render("You signed:", True, INK), (p.x + 15, p.y + 135))
    s.blit(F.render(" · ".join(x.upper() for x in g.signs) or "-", True, ACC), (p.x + 15, p.y + 165))
    send = pygame.Rect(p.x + 15, p.y + 210, 120, 40)
    pygame.draw.rect(s, ACC if g.signs else DIM, send, border_radius=8)
    s.blit(F.render("Send", True, BG), F.render("Send", True, BG).get_rect(center=send.center))
    if g.selected is not None:
        s.blit(Fs.render("Words for this module (sign cards):", True, DIM), (p.x + 15, p.y + 275))
        pool = g.modules[g.selected].spec["pool"]
        for j, word in enumerate(pool):
            s.blit(Fs.render(word, True, INK), (p.x + 25 + (j % 2) * 170, p.y + 300 + (j // 2) * 24))
    s.blit(Fs.render(f"F2 broken LLM: {'ON' if g.broken_llm else 'off'}", True, (250, 120, 90) if g.broken_llm else DIM), (p.x + 15, p.bottom - 30))
    return send


def draw_manual(g: Game, s, F, Fs):
    if g.open_page and g.state != "THINKING" or (g.state == "THINKING" and g.think_t < 0.6 and g.open_page):
        r = pygame.Rect(200, 80, 880, 440)
        pygame.draw.rect(s, (240, 230, 200), r, border_radius=10)
        for j, line in enumerate(manual_page(PUZZLES[g.open_page])):
            s.blit((F if j == 0 else Fs).render(line, True, (40, 30, 20)), (r.x + 30, r.y + 25 + j * 28))
    else:
        # Index of all 20 pages; retrieval candidates glow while the alien flips.
        ids = list(PUZZLES) + OTHER_TITLES
        flip = int(g.think_t * 10) % len(ids) if g.state == "THINKING" else -1
        for i, pid in enumerate(ids):
            r = pygame.Rect(60 + (i % 5) * 235, 90 + (i // 5) * 105, 215, 85)
            col = PANEL if pid in PUZZLES else (28, 32, 45)
            if pid in g.candidates:
                col = (40, 110, 100)
            if i == flip:
                col = (90, 90, 140)
            pygame.draw.rect(s, col, r, border_radius=10)
            s.blit(Fs.render(pid, True, INK if pid in PUZZLES else DIM), (r.x + 12, r.y + 30))
    msg = {"THINKING": "The alien is flipping through the manual...", "REPLYING": "", "SIGNING": "Manual (Tab to go back)"}[g.state]
    s.blit(F.render(msg, True, ACC), (60, 540))


def run(seed):
    global pygame
    import pygame
    pygame.init()
    s = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Escape Pod - quick demo")
    F, Fs, Fb = pygame.font.SysFont("segoeui", 24), pygame.font.SysFont("segoeui", 19), pygame.font.SysFont("segoeui", 64, bold=True)
    clock = pygame.time.Clock()
    g = Game(seed)
    send_rect = pygame.Rect(0, 0, 0, 0)
    while True:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                return
            if g.end:
                if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                    seed += 1
                    g = Game(seed)
                continue
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_TAB and g.state == "SIGNING":
                    g.scene = "MANUAL" if g.scene == "BOMB" else "BOMB"
                elif e.key == pygame.K_F2:
                    g.broken_llm = not g.broken_llm
                elif g.scene == "BOMB" and g.state == "SIGNING":
                    if e.key == pygame.K_RETURN:
                        if e.mod & pygame.KMOD_CTRL:
                            g.send()
                        elif g.typed.strip():
                            g.signs.append(g.typed.strip().lower())
                            g.typed = ""
                    elif e.key == pygame.K_BACKSPACE:
                        if g.typed:
                            g.typed = g.typed[:-1]
                        elif g.signs:
                            g.signs.pop()
                    elif e.unicode.isalnum():
                        g.typed += e.unicode
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if g.scene == "MANUAL" and g.state == "REPLYING":
                    g.scene, g.state = "BOMB", "SIGNING"
                elif g.scene == "BOMB" and g.state == "SIGNING":
                    if send_rect.collidepoint(e.pos):
                        g.send()
                    for i, (m, r) in enumerate(zip(g.modules, module_rects())):
                        if not r.collidepoint(e.pos) or m.defused:
                            continue
                        if g.selected != i:
                            g.selected = i  # first click selects, later clicks act
                            break
                        w = m.spec["widget"]
                        items = items_of(w, m.facts)
                        for it, ir in zip(items, item_rects(w, items, r)):
                            if ir.collidepoint(e.pos):
                                verb, key = {"wires": ("cut", "color"), "icons": ("press", "icon"), "dial": ("turn", "to")}[w]
                                g.act(Action.make(verb, {key: it}))
        g.update(dt)
        s.fill((90, 20, 20) if g.flash > 0 else BG)
        # Top bar: scene tabs, timer, strikes.
        for k, name in enumerate(["BOMB", "MANUAL"]):
            col = ACC if g.scene == name else DIM
            s.blit(F.render(f"[{name}]", True, col), (30 + k * 130, 25))
        s.blit(F.render(f"Time {int(g.timer // 60)}:{int(g.timer % 60):02d}    Strikes {'X' * g.strikes}{'-' * (3 - g.strikes)}", True, INK), (870, 25))
        if g.scene == "BOMB":
            send_rect = draw_bomb(g, s, F, Fs)
        else:
            draw_manual(g, s, F, Fs)
        pygame.draw.rect(s, PANEL, pygame.Rect(30, 655, 1220, 50), border_radius=10)
        s.blit(F.render(g.reply, True, INK), (45, 666))
        if g.end:
            over = pygame.Surface((W, H), pygame.SRCALPHA)
            over.fill((0, 0, 0, 200))
            s.blit(over, (0, 0))
            txt = "POD LAUNCHED - YOU ESCAPED" if g.end == "ESCAPED" else "BOOM"
            s.blit(Fb.render(txt, True, ACC if g.end == "ESCAPED" else (250, 80, 60)), Fb.render(txt, True, INK).get_rect(center=(W // 2, 260)))
            ok = sum(1 for x in g.log if x["verdict"] == "ok")
            rep = f"Defused {sum(m.defused for m in g.modules)}/3   Strikes {g.strikes}   Exchanges {len(g.log)}   LLM right before verify: {ok}/{len(g.log)}"
            s.blit(F.render(rep, True, INK), F.render(rep, True, INK).get_rect(center=(W // 2, 360)))
            s.blit(F.render("Press R to play again", True, DIM), F.render("Press R to play again", True, DIM).get_rect(center=(W // 2, 420)))
        pygame.display.flip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=random.randrange(10_000))
    run(ap.parse_args().seed)
