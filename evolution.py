# evolution.py
#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json
from pathlib import Path
from typing import Dict, List, Tuple

from google import genai
from google.genai import types

VIEW_ORDER = ["top", "bottom", "front", "back", "left", "right"]

EVOLVE_INSTRUCTION = (
    "You are given: (A) the original target media (image or video), "
    "(B) six rendered views of two candidate CAD models, and (C) the original user prompt.\n"
    "Produce ONE improved CadQuery program that better matches the target.\n"
    "Output rules:\n"
    "- Return ONLY executable Python (no markdown), using `import cadquery as cq` and assign to `result`."
)

def _image_part(path: str):
    return types.Part.from_bytes(data=Path(path).read_bytes(), mime_type="image/png")

def _pick_top2(critique_dir: Path) -> List[Tuple[str, int]]:
    scored = []
    for p in sorted(critique_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            score = int(data.get("score", 0))
            scored.append((p.stem, score))
        except Exception:
            pass
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:2]

def _build_contents_for_evolution(
    source_media,                     # image Part or video File
    prompt_text: str,
    varA: Tuple[str, Dict],           # (name, {code_file, images})
    varB: Tuple[str, Dict],
) -> List:
    parts: List = [source_media]      # media first
    def add_variant(label: str, item: Tuple[str, Dict]):
        name, meta = item
        parts.append(f"{label} code ({name}):")
        parts.append(Path(meta["code_file"]).read_text(encoding="utf-8"))
        imgs = meta["images"]
        for v in VIEW_ORDER:
            parts.append(f"{label} image {v}:")
            parts.append(_image_part(imgs[v]))
    add_variant("Variant A", varA)
    add_variant("Variant B", varB)
    parts.append("Original prompt text:")
    parts.append(prompt_text)
    parts.append(EVOLVE_INSTRUCTION)
    return parts

async def _one_call(client: genai.Client, model: str, contents, attempt: int) -> str:
    cfg = types.GenerateContentConfig(response_mime_type="text/plain")
    print(f"[evolve][{attempt:02d}] generating improved variant…")
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=cfg)
    return (resp.text or "").strip()

async def evolve_from_top2(
    client: genai.Client,
    model: str,
    source_media,               # NEW: image Part or video File
    prompt_text: str,
    manifest: Dict[str, Dict],
    renders_dir: Path,
    critiques_dir: Path,
    out_dir: Path,
    num: int,
    concurrency: int = 8,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    top2 = _pick_top2(critiques_dir)
    if len(top2) < 2:
        raise RuntimeError(f"Need >=2 critiques to evolve, found: {top2}")

    def pack(name: str) -> Tuple[str, Dict]:
        return (name, manifest[name])

    itemA = pack(top2[0][0])
    itemB = pack(top2[1][0])
    shared_contents = _build_contents_for_evolution(source_media, prompt_text, itemA, itemB)

    sem = asyncio.Semaphore(concurrency)
    async def bounded(i: int):
        async with sem:
            return await _one_call(client, model, list(shared_contents), i)
    tasks = [asyncio.create_task(bounded(i)) for i in range(1, num + 1)]
    texts = await asyncio.gather(*tasks)

    raw_path = out_dir / "raw_evolve_responses.json"
    raw_path.write_text(json.dumps(texts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[evolve] wrote raw responses -> {raw_path}")
    return {f"candidate_{i:02d}": t for i, t in enumerate(texts, 1)}
