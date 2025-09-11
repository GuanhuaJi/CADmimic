#!/usr/bin/env python3
# critique.py
from __future__ import annotations
import asyncio, json, platform
from pathlib import Path
from typing import Dict, List, Tuple

from google import genai
from google.genai import types

# Renders we expect per variant
VIEW_ORDER = ["top", "bottom", "front", "back", "left", "right"]

# Strict JSON output (schema-enforced)
CRITIQUE_PROMPT = (
    "You are given a short video of the target object and six rendered views of a CAD model "
    "(top, bottom, front, back, left, right). Critique how well the model matches the target and "
    "how to improve it.\n"
    "Return ONLY JSON with this shape:\n"
    '{\n'
    '  "good": ["point 1", "point 2", ...],\n'
    '  "bad": ["issue 1", "issue 2", ...],\n'
    '  "score": 1\n'
    '}\n'
    "Rules:\n"
    "- Under 8 bullets each for good/bad.\n"
    "- score is an integer 1-10 where 1 = not like at all, 10 = exactly the same.\n"
    "- No extra keys, no extra commentary."
)

def _is_success_variant(log_path: Path, image_map: Dict[str, str]) -> tuple[bool, str]:
    # 1) Must have all six views
    missing_keys = [v for v in VIEW_ORDER if v not in image_map]
    if missing_keys:
        return False, f"missing keys: {missing_keys}"

    # 2) All six PNGs must exist on disk
    missing_files = [v for v in VIEW_ORDER if not Path(image_map[v]).is_file()]
    if missing_files:
        return False, f"missing files: {missing_files}"

    # 3) Log must exist
    if not log_path.is_file():
        return False, "no render log"

    txt = log_path.read_text(errors="ignore")
    lines = txt.splitlines()

    # 4) No per-view failures in this run (match per line)
    any_render_fail = any(("View=" in ln and "failed" in ln) for ln in lines)
    if any_render_fail:
        return False, "per-view failure present in log"

    # 5) Must have a positive completion line from this run
    wrote_six = any("Wrote 6 image(s)" in ln for ln in lines)
    if not wrote_six:
        return False, "no 'Wrote 6 image(s)' line"

    return True, "ok"


def _image_part(path: str):
    from google.genai import types
    data = Path(path).read_bytes()
    return types.Part.from_bytes(data=data, mime_type="image/png")

def _build_contents(video_file, images: Dict[str, str]):
    # Media first (video + 6 images), instruction last (recommended pattern)
    # Docs show using file handle (Files API) + bytes parts for images. 
    # (Video via Files API: ai.google.dev/api/files; Images via bytes: ai.google.dev/.../image-understanding)
    parts = [video_file]
    for name in VIEW_ORDER:
        parts.append(f"View: {name}")
        parts.append(_image_part(images[name]))
    parts.append(CRITIQUE_PROMPT)
    return parts

def _critique_config() -> types.GenerateContentConfig:
    # Enforce JSON and a simple object schema (SDK Schema subset)
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "good":  types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                "bad":   types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                "score": types.Schema(type=types.Type.INTEGER, minimum=1, maximum=10),
            },
            required=["good", "bad", "score"],
            # propertyOrdering is supported in this Schema subset and can improve stability
            property_ordering=["good", "bad", "score"],
        ),
    )

async def _one_variant(
    client: genai.Client,
    model: str,
    video_file,       # Files API handle from your upload step
    variant_name: str,
    images: Dict[str, str],
    out_dir: Path,
) -> Tuple[str, Dict]:
    contents = _build_contents(video_file, images)
    cfg = _critique_config()
    print(f"[critique] {variant_name}: sending {len(contents)} parts (video + 6 images + instruction)")
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=cfg)
    data = json.loads(resp.text)  # strict JSON per schema
    out_path = out_dir / f"{variant_name}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[critique] {variant_name}: score={data.get('score')} -> {out_path}")
    return variant_name, data

async def critique_variants(
    client: genai.Client,
    model: str,
    video_file,           # ACTIVE Files API handle
    manifest: Dict[str, Dict],
    renders_root: Path,   # <out>/renders
    out_dir: Path,        # <out>/critiques
    concurrency: int = 4,
) -> Dict[str, Dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    tasks = []

    for variant, info in manifest.items():
        v_dir = renders_root / variant
        log_path = v_dir / f"{variant}_render.log"
        images = info.get("images", {})

        ok, why = _is_success_variant(log_path, images)
        if ok:
            async def _bound(v=variant, ims=images):
                async with sem:
                    return await _one_variant(client, model, video_file, v, ims, out_dir)
            tasks.append(asyncio.create_task(_bound()))
        else:
            print(f"[critique] {variant}: skipped ({why})")

    results = await asyncio.gather(*tasks) if tasks else []
    return {k: v for k, v in results}
