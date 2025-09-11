#!/usr/bin/env python3
# orchestrate_gemini_cq.py
import argparse, asyncio, json
from pathlib import Path
from typing import List, Dict

from google import genai
from google.genai import types

from gemini_io import upload_video_and_wait_active, async_generate_variants, build_contents
from code_extraction import extract_python_code, write_code_files, sanitize_extrude_centered
from render_six_views import render_six_views
from critique import critique_variants
from evolution import evolve_from_top2
from utils import ensure_dir, write_text

def parse_args():
    ap = argparse.ArgumentParser(description="Iterative: generate → render → critique → evolve")
    ap.add_argument("--prompt_txt", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api_key", required=True)
    ap.add_argument("--num", type=int, default=10, help="candidates per iteration")
    ap.add_argument("--max_iter", type=int, default=1, help="number of evolution rounds (folders 1..max_iter)")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--concurrency", type=int, default=5, help="parallel requests/renders/critiques")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top_p", type=float, default=0.9)
    ap.add_argument("--max_output_tokens", type=int, default=4096)
    ap.add_argument("--image_size", type=int, default=800)
    return ap.parse_args()

async def generate_initial(
    client: genai.Client,
    model: str,
    uploaded_file,
    prompt_text: str,
    num: int,
    concurrency: int,
    iter_dir: Path,
    image_size: int,
):
    print(f"[iter 0] generating {num} candidates")
    ensure_dir(iter_dir)
    codes_dir = iter_dir / "codes"
    renders_root = iter_dir / "renders"
    critiques_dir = iter_dir / "critiques"
    for d in (codes_dir, renders_root, critiques_dir):
        ensure_dir(d)

    # Build contents (video first, then text)
    contents = build_contents(uploaded_file, prompt_text)

    # (We pass a config, but gemini_io._one_call forces tools + text/plain to stabilize resp.text)
    gen_config = types.GenerateContentConfig(
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
        response_mime_type="text/plain",
    )

    texts = await async_generate_variants(
        client=client,
        model=model,
        contents=contents,
        num=num,
        gen_config=gen_config,
        concurrency=concurrency,
        logs_dir=iter_dir / "logs",
    )
    write_text(iter_dir / "raw_responses.json", json.dumps(texts, indent=2, ensure_ascii=False))

    # Extract + sanitize + save code files
    code_list: List[str] = [sanitize_extrude_centered(extract_python_code(t)) for t in texts]
    code_paths: List[Path] = write_code_files(code_list, codes_dir)
    print(f"[iter 0] wrote {len(code_paths)} code files")

    # Render + manifest
    manifest: Dict[str, Dict] = {}
    for idx, code_path in enumerate(code_paths, start=1):
        variant = f"variant_{idx:02d}"
        v_dir = renders_root / variant
        ensure_dir(v_dir)
        img_map = render_six_views(
            infile=str(code_path),
            outdir=str(v_dir),
            size=image_size,
            margin=1.2,
            tilt_eps=1e-3,
            log_file=str(v_dir / f"{variant}_render.log"),
        )
        manifest[variant] = {"code_file": str(code_path), "images": img_map}
    write_text(iter_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[iter 0] rendered and saved manifest")

    # Critique working variants
    _ = await critique_variants(
        client=client,
        model=model,
        video_file=uploaded_file,
        manifest=manifest,
        renders_root=renders_root,
        out_dir=critiques_dir,
        concurrency=concurrency,
    )
    print(f"[iter 0] critique complete")

async def evolve_round(
    client: genai.Client,
    model: str,
    uploaded_file,
    prompt_text: str,
    prev_dir: Path,
    iter_dir: Path,
    num: int,
    concurrency: int,
    image_size: int,
):
    print(f"[evolve] from {prev_dir.name} → {iter_dir.name}: generating {num}")
    ensure_dir(iter_dir)
    codes_dir = iter_dir / "codes"
    renders_root = iter_dir / "renders"
    critiques_dir = iter_dir / "critiques"
    for d in (codes_dir, renders_root, critiques_dir):
        ensure_dir(d)

    # Load previous manifest
    prev_manifest = json.loads((prev_dir / "manifest.json").read_text(encoding="utf-8"))

    # Evolve top-2 into new candidates
    evolved_map = await evolve_from_top2(
        client=client,
        model=model,
        uploaded_video_file=uploaded_file,
        prompt_text=prompt_text,
        manifest=prev_manifest,
        renders_dir=prev_dir / "renders",
        critiques_dir=prev_dir / "critiques",
        out_dir=iter_dir,
        num=num,
        concurrency=concurrency,   # same as --concurrency
    )

    # Extract + sanitize + save code files for this iteration
    texts_sorted = [evolved_map[k] for k in sorted(evolved_map.keys())]
    code_list: List[str] = [sanitize_extrude_centered(extract_python_code(t)) for t in texts_sorted]
    code_paths: List[Path] = write_code_files(code_list, codes_dir)
    print(f"[{iter_dir.name}] wrote {len(code_paths)} evolved code files")

    # Render + manifest for this iteration
    manifest: Dict[str, Dict] = {}
    for idx, code_path in enumerate(code_paths, start=1):
        variant = f"variant_{idx:02d}"
        v_dir = renders_root / variant
        ensure_dir(v_dir)
        img_map = render_six_views(
            infile=str(code_path),
            outdir=str(v_dir),
            size=image_size,
            margin=1.2,
            tilt_eps=1e-3,
            log_file=str(v_dir / f"{variant}_render.log"),
        )
        manifest[variant] = {"code_file": str(code_path), "images": img_map}
    write_text(iter_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[{iter_dir.name}] render complete")

    # Critique for this iteration
    _ = await critique_variants(
        client=client,
        model=model,
        video_file=uploaded_file,
        manifest=manifest,
        renders_root=renders_root,
        out_dir=critiques_dir,
        concurrency=concurrency,
    )
    print(f"[{iter_dir.name}] critique complete")

async def main():
    global args
    args = parse_args()

    root = Path(args.out_dir)
    ensure_dir(root)

    prompt_text = Path(args.prompt_txt).read_text(encoding="utf-8")
    print(f"[init] prompt len={len(prompt_text)}; model={args.model}")

    client = genai.Client(api_key=args.api_key)
    print(f"[init] uploading video once and waiting ACTIVE: {args.video}")
    uploaded_file = upload_video_and_wait_active(client, args.video)

    # ---- iteration 0 (initial generation) ----
    iter0 = root / "0"
    await generate_initial(
        client=client,
        model=args.model,
        uploaded_file=uploaded_file,
        prompt_text=prompt_text,
        num=args.num,
        concurrency=args.concurrency,
        iter_dir=iter0,
        image_size=args.image_size,
    )

    # ---- evolution rounds 1..max_iter ----
    prev_dir = iter0
    for it in range(1, args.max_iter + 1):
        curr_dir = root / str(it)
        await evolve_round(
            client=client,
            model=args.model,
            uploaded_file=uploaded_file,
            prompt_text=prompt_text,
            prev_dir=prev_dir,
            iter_dir=curr_dir,
            num=args.num,
            concurrency=args.concurrency,   # reuse --concurrency (no extra flag)
            image_size=args.image_size,
        )
        prev_dir = curr_dir

    print(f"[done] pipeline complete under {root}")

if __name__ == "__main__":
    asyncio.run(main())
