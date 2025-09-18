# siglip_recursive_similarity_rank.py
import os
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, SiglipModel

# ─────────── config ───────────
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if device == "cuda" else torch.float32
MODEL_ID = "google/siglip-so400m-patch14-384"
BATCH_SIZE = 16  # tweak for your 8GB 3070 if needed (8–32 usually fine)

# target image and the root dir to search (recursively)
target_path = "/home/jojo/CADmimic/assets/Screenshot 2025-09-16 at 22-40-45 Serta Comfort Series Ergonomic Bonded Leather Mid Back Executive Office Chair Cognac - Office Depot.png"
root_dir    = "/home/jojo/CADmimic/output/2025-09-16_22-41-53"  # <-- search here recursively
out_txt     = str(Path(root_dir) / "siglip_cosine_ranking.txt")

# which files count as images
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# ─────────── setup model/processor ───────────
image_processor = AutoImageProcessor.from_pretrained(MODEL_ID, use_fast=True)
model = SiglipModel.from_pretrained(MODEL_ID, torch_dtype=dtype).to(device).eval()

def find_all_images(root: str) -> list[str]:
    root_p = Path(root)
    # recursively collect all image files
    paths = [str(p) for p in root_p.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
    paths.sort()
    return paths

def load_pixel_values(paths: list[str]) -> tuple[torch.Tensor, list[str]]:
    """Load a batch of images, return (pixel_values, good_paths). Skips unreadable files."""
    imgs, good_paths = [], []
    for p in paths:
        try:
            imgs.append(Image.open(p).convert("RGB"))
            good_paths.append(p)
        except Exception:
            # skip unreadable image
            pass
    if not imgs:
        return torch.empty(0), []
    pixel_values = image_processor(images=imgs, return_tensors="pt").pixel_values
    return pixel_values.to(device=device, dtype=dtype), good_paths

def iter_batches(seq: list[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]

with torch.inference_mode():
    # --- target embedding ---
    tgt_px, good = load_pixel_values([target_path])
    if tgt_px.numel() == 0:
        raise RuntimeError(f"Failed to load target image: {target_path}")
    tgt_feat = model.get_image_features(pixel_values=tgt_px)         # [1, D]
    tgt_feat = F.normalize(tgt_feat, dim=-1)                         # [1, D]

    # --- source images (recursive) ---
    all_imgs = find_all_images(root_dir)
    if not all_imgs:
        raise SystemExit(f"No images found under: {root_dir}")

    results: list[tuple[str, float]] = []  # (path, score)
    for batch_paths in iter_batches(all_imgs, BATCH_SIZE):
        src_px, good_paths = load_pixel_values(batch_paths)
        if src_px.numel() == 0:
            continue
        src_feats = model.get_image_features(pixel_values=src_px)    # [N, D]
        src_feats = F.normalize(src_feats, dim=-1)
        sims = (src_feats @ tgt_feat.T).squeeze(1)                   # [N]
        scores = sims.float().cpu().tolist()
        results.extend(zip(good_paths, scores))

    if not results:
        raise SystemExit("No valid images loaded to compare.")

    # sort high → low and write out
    results.sort(key=lambda x: x[1], reverse=True)
    out_path = Path(out_txt)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# target: {target_path}\n")
        f.write(f"# searched_root: {root_dir}\n")
        f.write("rank\tscore\tpath\n")
        for rank, (p, s) in enumerate(results, 1):
            f.write(f"{rank}\t{s:.6f}\t{p}\n")

    print(f"Wrote {len(results)} rankings to {out_path}")
    # optional: show top-5 in console
    for i, (p, s) in enumerate(results[:5], 1):
        print(f"{i:>2}. {s:.4f}  {p}")
