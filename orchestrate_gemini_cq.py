#!/usr/bin/env python3
# orchestrate_gemini_cq.py
import argparse, asyncio, json, os
from pathlib import Path
from typing import List, Dict

from google import genai
from google.genai import types

from gemini_io import upload_video_and_wait_active, async_generate_variants, build_contents
from code_extraction import extract_python_code, write_code_files, sanitize_extrude_centered
from render_six_views import render_six_views
from utils import ensure_dir, write_text

from critique import critique_variants

def parse_args():
    ap = argparse.ArgumentParser(description="Generate N CadQuery variants and render 6 views each.")
    ap.add_argument("--prompt_txt", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api_key", required=True)
    ap.add_argument("--num", type=int, default=10)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top_p", type=float, default=0.95)
    ap.add_argument("--max_output_tokens", type=int, default=1000000)
    ap.add_argument("--image_size", type=int, default=800)
    return ap.parse_args()

async def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    codes_dir = out_dir / "codes"
    renders_dir = out_dir / "renders"
    logs_dir = out_dir / "logs"
    for d in (codes_dir, renders_dir, logs_dir):
        ensure_dir(d)

    print(f"[main] prompt_txt={args.prompt_txt}")
    prompt_text = Path(args.prompt_txt).read_text(encoding="utf-8")
    print(f"[main] prompt length={len(prompt_text)} chars")

    print(f"[main] initializing client; model={args.model}")
    client = genai.Client(api_key=args.api_key)

    print(f"[main] uploading video and waiting ACTIVE: {args.video}")
    uploaded_file = upload_video_and_wait_active(client, args.video)
    print(f"[main] uploaded file: name={getattr(uploaded_file,'name',None)} "
          f"uri={getattr(uploaded_file,'uri',None)} state={getattr(uploaded_file,'state',None)} "
          f"mime={getattr(uploaded_file,'mime_type',None)}")

    contents = build_contents(uploaded_file, prompt_text)

    gen_config = types.GenerateContentConfig(
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
    )
    print(f"[main] gen_config: temp={args.temperature} top_p={args.top_p} max_tokens={args.max_output_tokens}")

    print(f"[main] launching {args.num} async requests (concurrency={args.concurrency})")
    texts = await async_generate_variants(
        client=client,
        model=args.model,
        contents=contents,
        num=args.num,
        gen_config=gen_config,
        concurrency=args.concurrency,
        logs_dir=logs_dir,
    )

    # quick visibility into what we got back
    lens = [len(t or "") for t in texts]
    print(f"[main] received {len(texts)} responses; text lengths={lens}")

    # Extract Python & write code
    code_list: List[str] = [sanitize_extrude_centered(extract_python_code(t)) for t in texts]
    code_paths: List[Path] = write_code_files(code_list, codes_dir)
    print(f"[main] wrote {len(code_paths)} code files to {codes_dir}")

    # Render each .py to 6 views
    manifest: Dict[str, Dict] = {}
    for idx, code_path in enumerate(code_paths, start=1):
        variant_name = f"variant_{idx:02d}"
        v_out = renders_dir / variant_name
        ensure_dir(v_out)
        print(f"[render] {variant_name} -> {v_out}")
        six = render_six_views(
            infile=str(code_path),
            outdir=str(v_out),
            size=args.image_size,
            margin=1.2,
            tilt_eps=1e-3,
        )
        manifest[variant_name] = {"code_file": str(code_path), "images": six}

    write_text(out_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    write_text(out_dir / "raw_responses.json", json.dumps(texts, indent=2, ensure_ascii=False))
    print(f"[done] manifest, raw_responses saved under {out_dir}")
    print("[critique] starting critique pass on working variants")
    crit_dir = out_dir / "critiques"
    # Reuse the already-uploaded video `uploaded_file` from your earlier step
    results = await critique_variants(
        client=client,
        model=args.model,
        video_file=uploaded_file,
        manifest=manifest,
        renders_root=renders_dir,
        out_dir=crit_dir,
        concurrency=args.concurrency,
    )
    # Also save a CSV summary (variant, score)
    import csv
    with open(crit_dir / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variant", "score"])
        for k, v in results.items():
            w.writerow([k, v.get("score")])
    print(f"[critique] wrote {len(results)} critiques -> {crit_dir}")

if __name__ == "__main__":
    asyncio.run(main())


'''
python /Users/jiguanhua/vlmgineer/gemini_evolution/orchestrate_gemini_cq.py --prompt_txt \
    /Users/jiguanhua/vlmgineer/exp2/prompt_1.txt --video /Users/jiguanhua/Downloads/20250902_155806.mp4 \
        --model gemini-2.5-pro --api_key "AIzaSyA2_I5PEg1rn2HNK2mj8tpFWr9xBKvUr3w" --num 10 \
            --out_dir /Users/jiguanhua/vlmgineer/gemini_evolution/output/cq_test --concurrency 10 \
                --image_size 800
'''