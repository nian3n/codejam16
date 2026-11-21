# Owner: Teammate 2 (Sign vocabulary and media)
"""Fetch one short demonstration clip per game word from PopSign ASL v1.0.

    uv run fetch-signs                 # every word in the puzzle pools that lacks a clip
    uv run fetch-signs cat dog --force # only these words, and replace existing clips

PopSign serves one tar per sign and split (hundreds of MB each), never single
videos. A tar is a plain sequence of files, so we stream it, keep the first
CANDIDATES clips, and close the connection: a few MB per word instead of the
whole archive. The clip with the median length wins (the first one is sometimes
an atypical take with long empty stretches), and ffmpeg shrinks it to a small,
silent, web-friendly MP4 in signs/clips/<gloss>.mp4.

License: CC BY 4.0. CREDIT below must show wherever the clips show (glossary,
README, credits screen). The digits 0-9 are not in PopSign; they use our own
handshape model (spec 6.4).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from escape_pod.puzzles.engine import load_pool

from escape_pod import config

CLIPS_DIR = config.SIGN_CLIPS_DIR
INDEX_FILE = CLIPS_DIR / "index.json"
URL = "https://signdata.cc.gatech.edu/data/popsign_v1_0/game/{split}/{sign}.tar"
SPLIT = "test"          # the smallest split (about 550 MB per sign); we read only its start
CANDIDATES = 3
# Our gloss -> PopSign's file name, where they differ (PopSign keeps the label map's "TV").
POPSIGN_NAME = {"tv": "TV"}
HANDSHAPE_PUZZLES = {"numbers"}
CREDIT = ("Sign videos: PopSign ASL v1.0 (Starner, Sridhar, So, Deshpande et al., "
          "Georgia Tech and DPAN), CC BY 4.0, https://signdata.cc.gatech.edu")


def game_glosses() -> list[str]:
    pool = load_pool()
    words = {g for s in pool.values() if s.id not in HANDSHAPE_PUZZLES for g in s.pool}
    return sorted(words | set(config.CORE_SIGNS))  # YES/NO/FINISH run the sign capture (spec 6.2)


def stream_candidates(sign: str, out: Path) -> tuple[list[Path], int]:
    """Download the first CANDIDATES mp4 members of the sign's tar. Returns (files, bytes read)."""
    name = POPSIGN_NAME.get(sign, sign)
    req = urllib.request.Request(URL.format(split=SPLIT, sign=name), headers={"User-Agent": "kmne-glossary/1"})
    got: list[Path] = []
    with urllib.request.urlopen(req, timeout=60) as resp:
        counted = _Counter(resp)
        with tarfile.open(fileobj=counted, mode="r|") as tar:  # type: ignore[call-overload]  # stream mode needs only read()
            for m in tar:
                if not (m.isfile() and m.name.lower().endswith(".mp4")):
                    continue
                f = tar.extractfile(m)
                if f is None:
                    continue
                path = out / f"{len(got)}.mp4"
                path.write_bytes(f.read())
                got.append(path)
                if len(got) >= CANDIDATES:
                    break  # leaving the with-blocks closes the connection: the rest is never downloaded
    return got, counted.n


class _Counter:
    """File-like wrapper that counts the bytes read (to report the real download size)."""
    def __init__(self, f):
        self.f, self.n = f, 0

    def read(self, size=-1):
        b = self.f.read(size)
        self.n += len(b)
        return b


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def shrink(src: Path, dst: Path) -> None:
    # 360 px tall portrait, 24 fps, no audio, H.264 for every browser, faststart so it plays while loading.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", "-vf", "scale=-2:360,fps=24",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(dst)], check=True)


def fetch(sign: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        files, nbytes = stream_candidates(sign, Path(tmp))
        if not files:
            raise RuntimeError("no mp4 in the tar")
        timed = sorted((duration(f), f) for f in files)
        secs, best = timed[len(timed) // 2]
        dst = CLIPS_DIR / f"{sign}.mp4"
        shrink(best, dst)
    return {"file": dst.name, "seconds": round(secs, 2), "bytes": dst.stat().st_size,
            "source": f"popsign_v1_0/game/{SPLIT}/{POPSIGN_NAME.get(sign, sign)}.tar", "downloaded": nbytes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch one PopSign clip per game word.")
    ap.add_argument("signs", nargs="*", help="default: every word in the puzzle pools")
    ap.add_argument("--force", action="store_true", help="replace clips that already exist")
    a = ap.parse_args(argv)
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ffmpeg and ffprobe must be on PATH.", file=sys.stderr)
        return 2
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8")) if INDEX_FILE.exists() else {"credit": CREDIT, "clips": {}}
    index["credit"] = CREDIT
    todo = a.signs or game_glosses()
    failed = []
    for i, sign in enumerate(todo, 1):
        if sign in index["clips"] and (CLIPS_DIR / f"{sign}.mp4").exists() and not a.force:
            continue
        try:
            entry = fetch(sign)
        except Exception as e:  # one bad sign must not stop the other 130
            failed.append(sign)
            print(f"[{i}/{len(todo)}] {sign}: FAILED ({e})", flush=True)
            continue
        index["clips"][sign] = entry
        INDEX_FILE.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")  # save as we go
        print(f"[{i}/{len(todo)}] {sign}: {entry['seconds']} s, {entry['bytes'] // 1024} KB "
              f"(read {entry['downloaded'] / 1e6:.1f} MB)", flush=True)
    if failed:
        print("Failed:", " ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
