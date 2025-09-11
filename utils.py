# utils.py
from __future__ import annotations
from pathlib import Path

def ensure_dir(path: Path | str):
    Path(path).mkdir(parents=True, exist_ok=True)

def write_text(path: Path | str, text: str):
    Path(path).write_text(text, encoding="utf-8")
