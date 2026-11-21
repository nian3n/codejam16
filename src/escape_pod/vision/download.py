# Owner: Teammate 3 (Vision and retrieval)
"""Download the word-sign model once (spec §6.3). After that, recognition works offline.

    uv run download-models
"""
from __future__ import annotations

import urllib.request

from escape_pod import config

REPO = "https://huggingface.co/sign/kaggle-asl-signs-1st-place/resolve/main"
FILES = {"model.tflite": 11_242_036, "sign_to_prediction_index_map.json": None}


def main():
    config.ISLR_DIR.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        dest = config.ISLR_DIR / name
        if dest.exists() and (size is None or dest.stat().st_size == size):
            print(f"ok      {dest}")
            continue
        print(f"get     {REPO}/{name}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(f"{REPO}/{name}", tmp)
        if size is not None and tmp.stat().st_size != size:
            tmp.unlink()
            raise SystemExit(f"{name}: expected {size} bytes, got a different size. Try again.")
        tmp.replace(dest)
        print(f"saved   {dest}")


if __name__ == "__main__":
    main()
