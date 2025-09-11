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
    "You are given: (A) the original target video, (B) six rendered views of two candidate CAD models, "
    "and (C) the original user prompt. Produce ONE improved CadQuery program that better matches the target, "
    "guided by the visual differences you observe.\n\n"
    "Output rules:\n"
    "- Return ONLY executable Python source code (no markdown fences, no commentary).\n"
    "- Use:  import cadquery as cq\n"
    "- Create geometry and assign it to a variable named `result` (Workplane/Shape/Assembly) "
    "  or call show_object(result_like) at the end.\n"
    "- Prefer simple, robust features (sketch -> extrude, cut/extrude, fillet where needed)."
)

def _image_part(path: str):
    from google.genai import types
    return types.Part.from_bytes(data=Path(path).read_bytes(), mime_type="image/png")  # inline image bytes are supported. :contentReference[oaicite:0]{index=0}

def _pick_top2(critique_dir: Path) -> List[Tuple[str, int]]:
    scored = []
    for p in sorted(critique_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            score = int(data.get("score", 0))
            variant = p.stem  # e.g., variant_09
            scored.append((variant, score))
        except Exception:
            continue
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:2]

def _build_contents_for_evolution(
    uploaded_video_file,            # ACTIVE Files API handle (video)
    prompt_text: str,
    varA: Tuple[str, Dict],         # (variant_name, {"code_file":..., "images":{view->png}})
    varB: Tuple[str, Dict],
) -> List:
    # Recommended order with media: put media parts before text parts. :contentReference[oaicite:1]{index=1}
    parts: List = [uploaded_video_file]

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
    # Force plain text so .text is populated; tools can be added if you want search/URL. :contentReference[oaicite:2]{index=2}
    cfg = types.GenerateContentConfig(response_mime_type="text/plain")
    print(f"[evolve][{attempt:02d}] generating improved variant…")
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=cfg)
    return (resp.text or "").strip()

async def evolve_from_top2(
    client: genai.Client,
    model: str,
    uploaded_video_file,    # ACTIVE File (video) — reuse from your upload step. :contentReference[oaicite:3]{index=3}
    prompt_text: str,
    manifest: Dict[str, Dict],   # your existing manifest mapping
    renders_dir: Path,           # <out>/renders
    critiques_dir: Path,         # <out>/critiques
    out_dir: Path,               # <out>/evolve_iter
    num: int,
    concurrency: int = 8,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) pick top-2 from critiques
    top2 = _pick_top2(critiques_dir)
    if len(top2) < 2:
        raise RuntimeError(f"Need >=2 critiques to evolve, found: {top2}")
    varA, varB = top2[0][0], top2[1][0]

    # 2) gather their code + images from manifest
    def pack(name: str) -> Tuple[str, Dict]:
        meta = manifest[name]
        # defensive: ensure 6 images exist
        _ = [renders_dir / name / Path(meta["images"][v]).name for v in VIEW_ORDER]
        return (name, meta)

    itemA = pack(varA)
    itemB = pack(varB)

    # 3) build shared multimodal contents (video + both variants + prompt + instruction)
    shared_contents = _build_contents_for_evolution(uploaded_video_file, prompt_text, itemA, itemB)

    # 4) fire num parallel requests
    sem = asyncio.Semaphore(concurrency)
    async def bounded(i: int):
        async with sem:
            return await _one_call(client, model, list(shared_contents), i)

    tasks = [asyncio.create_task(bounded(i)) for i in range(1, num + 1)]
    texts = await asyncio.gather(*tasks)

    # 5) save raw responses
    raw_path = out_dir / "raw_evolve_responses.json"
    raw_path.write_text(json.dumps(texts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[evolve] wrote raw responses -> {raw_path}")
    return {f"candidate_{i:02d}": t for i, t in enumerate(texts, 1)}
