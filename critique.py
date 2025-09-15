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
    "You are given a target (image or video) and six rendered views of ONE CAD model "
    "(top, bottom, front, back, left, right). Provide CONSTRUCTIVE feedback only.\n\n"
    "Return ONLY JSON with this shape (no extra keys):\n"
    '{\n'
    '  "keep":    ["what to keep because it matches the target", ...],\n'
    '  "improve": ["specific, actionable changes to better match the target", ...],\n'
    '  "score":   1\n'
    '}\n\n'
    "Coverage (be concise, max ~8 bullets per list):\n"
    "- Overall form & silhouette; proportions (hood/cabin/trunk or equivalent); alignment between parts;\n"
    "- Key features & placements (lights/grille/wheels/handles/etc. or domain analogs);\n"
    "- Curvature, fillets/chamfers, thickness/robustness; joints/clearances; color/material cues.\n\n"
    "Scoring rubric (1–10). Use the FULL scale:\n"
    "1  = almost no resemblance (blocky/incorrect silhouette, features missing/misplaced).\n"
    "3  = coarse resemblance; silhouette partially wrong; many major features missing.\n"
    "5  = basic silhouette recognizable; several major features present but proportions off.\n"
    "7  = good silhouette; most major features present; minor proportion/placement issues.\n"
    "9  = near-match; small cosmetic gaps (e.g., fillets, minor offsets, color tone).\n"
    "10 = essentially indistinguishable in all views.\n"
    "Typical scores for reasonable models fall in 3–9. Avoid giving all 1s unless truly warranted.\n"
)


def _is_success_variant(log_path: Path, image_map: Dict[str, str]) -> tuple[bool, str]:
    missing = [v for v in VIEW_ORDER if v not in image_map or not Path(image_map[v]).is_file()]
    if missing:
        return False, f"missing images: {missing}"
    if not log_path.is_file():
        return False, "no render log"
    txt = log_path.read_text(errors="ignore")
    lines = txt.splitlines()
    if any(("View=" in ln and "failed" in ln) for ln in lines):
        return False, "per-view failure present"
    if not any("Wrote 6 image(s)" in ln for ln in lines):
        return False, "no completion line"
    return True, "ok"

def _image_part(path: str):
    data = Path(path).read_bytes()
    return types.Part.from_bytes(data=data, mime_type="image/png")

def _build_contents(source_media, images: Dict[str, str]):
    # Media (image or video File) first, then six PNGs, then instruction. :contentReference[oaicite:6]{index=6}
    parts: List = [source_media]
    for name in VIEW_ORDER:
        parts.append(f"View: {name}")
        parts.append(_image_part(images[name]))
    parts.append(CRITIQUE_PROMPT)
    return parts

def _critique_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "keep":    types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                "improve": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                "score":   types.Schema(type=types.Type.INTEGER, minimum=1, maximum=10),
            },
            required=["keep", "improve", "score"],
            property_ordering=["keep", "improve", "score"],
        ),
    )

async def _one_variant(
    client: genai.Client,
    model: str,
    source_media,       # File (video) or Part (image)
    variant_name: str,
    images: Dict[str, str],
    out_dir: Path,
) -> Tuple[str, Dict]:
    contents = _build_contents(source_media, images)
    cfg = _critique_config()
    print(f"[critique] {variant_name}: sending {len(contents)} parts (media + 6 images + instruction)")
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=cfg)
    data = json.loads(resp.text)
    allowed = {"keep", "improve", "score"}
    data = {k: v for k, v in data.items() if k in allowed}
    data["keep"]    = [str(x) for x in (data.get("keep") or [])]
    data["improve"] = [str(x) for x in (data.get("improve") or [])]
    data["score"]   = max(1, min(10, int(data.get("score", 0))))
    out_path = out_dir / f"{variant_name}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[critique] {variant_name}: score={data.get('score')} -> {out_path}")
    return variant_name, data

async def critique_variants(
    client: genai.Client,
    model: str,
    source_media,         # NEW: image Part or video File
    manifest: Dict[str, Dict],
    renders_root: Path,
    out_dir: Path,
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
                    return await _one_variant(client, model, source_media, v, ims, out_dir)
            tasks.append(asyncio.create_task(_bound()))
        else:
            print(f"[critique] {variant}: skipped ({why})")
    results = await asyncio.gather(*tasks) if tasks else []
    return {k: v for k, v in results}