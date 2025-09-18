# clip_recursive_similarity_rank.py
import os
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image, UnidentifiedImageError
import clip

# ───────── config ─────────
device = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_NAME = "ViT-B/32"  # change to "ViT-L/14" or "ViT-L/14@336px" if you like
BATCH_SIZE = 32          # adjust if you hit VRAM limits
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# paths
target_path = "/home/jojo/CADmimic/assets/Screenshot 2025-09-16 at 22-40-45 Serta Comfort Series Ergonomic Bonded Leather Mid Back Executive Office Chair Cognac - Office Depot.png"
root_dir    = "/home/jojo/CADmimic/output/2025-09-16_22-41-53"  # <-- search here recursively
out_txt     = str(Path(root_dir) / "clip_cosine_ranking.txt")

# ───────── setup model ─────────
model, preprocess = clip.load(MODEL_NAME, device=device)
model.eval()

def find_all_images(root: str) -> list[str]:
    root_p = Path(root)
    paths = [str(p) for p in root_p.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
    paths.sort()
    return paths

def load_preprocessed(paths: list[str], preprocess, device, dtype) -> tuple[torch.Tensor, list[str]]:
    """Load + preprocess a batch of images. Skips unreadable files."""
    tensors, good_paths = [], []
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
        except (UnidentifiedImageError, OSError):
            continue
        tensors.append(preprocess(im))
        good_paths.append(p)
    if not tensors:
        return torch.empty(0, dtype=dtype, device=device), []
    batch = torch.stack(tensors, 0).to(device=device, dtype=dtype)
    return batch, good_paths

def iter_batches(seq: list[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]

with torch.inference_mode():
    # --- target embedding ---
    tgt_batch, ok = load_preprocessed([target_path], preprocess, device, model.dtype)
    if tgt_batch.numel() == 0:
        raise RuntimeError(f"Failed to load target image: {target_path}")
    tgt_feat = model.encode_image(tgt_batch)          # [1, D]
    tgt_feat = F.normalize(tgt_feat, dim=-1)          # [1, D]

    # --- gather sources recursively ---
    all_imgs = find_all_images(root_dir)
    if not all_imgs:
        raise SystemExit(f"No images found under: {root_dir}")
    print(f"Found {len(all_imgs)} images under {root_dir}")

    # --- score in batches ---
    results: list[tuple[str, float]] = []  # (path, cosine)
    for batch_paths in iter_batches(all_imgs, BATCH_SIZE):
        src_batch, good_paths = load_preprocessed(batch_paths, preprocess, device, model.dtype)
        if src_batch.numel() == 0:
            continue
        src_feats = model.encode_image(src_batch)     # [N, D]
        src_feats = F.normalize(src_feats, dim=-1)    # [N, D]
        sims = (src_feats @ tgt_feat.T).squeeze(1)    # [N]
        scores = sims.float().cpu().tolist()
        results.extend(zip(good_paths, scores))

    if not results:
        raise SystemExit("No valid images were loaded to compare.")

    # --- sort & write output ---
    results.sort(key=lambda x: x[1], reverse=True)
    out_path = Path(out_txt)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# model: {MODEL_NAME}\n")
        f.write(f"# target: {target_path}\n")
        f.write(f"# searched_root: {root_dir}\n")
        f.write("rank\tscore\tpath\n")
        for rank, (p, s) in enumerate(results, 1):
            f.write(f"{rank}\t{s:.6f}\t{p}\n")

    print(f"Wrote {len(results)} rankings to {out_path}")
    print("Top-5:")
    for i, (p, s) in enumerate(results[:5], 1):
        print(f"{i:>2}. {s:.4f}  {p}")
