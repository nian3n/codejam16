# Owner: Teammate 2 (Sign vocabulary and media)
"""The glossary clips: one per game word, credited, and served by the game server."""
import json

from fastapi.testclient import TestClient

from escape_pod import config
from escape_pod.signs.fetch_popsign import CREDIT, game_glosses
from escape_pod.web.server import app

client = TestClient(app)
INDEX = json.loads((config.SIGN_CLIPS_DIR / "index.json").read_text(encoding="utf-8"))


def test_every_game_word_has_a_clip():
    # A new word in a puzzle pool needs `uv run fetch-signs` before it ships.
    missing = [g for g in game_glosses()
               if g not in INDEX["clips"] or not (config.SIGN_CLIPS_DIR / f"{g}.mp4").exists()]
    assert not missing, f"no clip for: {missing}. Run: uv run fetch-signs"


def test_numbers_and_letters_are_not_from_popsign():
    assert not {"0", "7", "a", "q"} & set(game_glosses())


def test_clips_are_small():
    # The repo and every page load carry these files: keep each one small.
    assert all(c["bytes"] < 200_000 for c in INDEX["clips"].values())


def test_credit_names_popsign_and_the_license():
    assert INDEX["credit"] == CREDIT
    assert "PopSign" in CREDIT and "CC BY 4.0" in CREDIT


def test_server_serves_the_index_and_a_clip():
    assert client.get("/signs/index.json").json()["credit"] == CREDIT
    r = client.get("/signs/cat.mp4")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"


PICTURES = config.SIGN_CLIPS_DIR / "pictures"


def test_every_glossary_picture_exists_and_has_its_credit():
    """signs/clips/pictures/index.json: still pictures for the digits (see the README there)."""
    pics = json.loads((PICTURES / "index.json").read_text(encoding="utf-8"))["pictures"]
    for gloss, p in pics.items():
        assert gloss in "0123456789" and len(gloss) == 1, f"{gloss}: pictures are for the digits"
        assert (PICTURES / p["file"]).is_file(), f"{gloss}: {p['file']} is not in {PICTURES}"
        assert p["file"].lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        assert p.get("license") and p.get("source"), f"{gloss}: add the license and the source"
        assert (PICTURES / p["file"]).stat().st_size < 500_000, f"{gloss}: make the picture smaller"
    assert TestClient(app).get("/signs/pictures/index.json").status_code == 200
