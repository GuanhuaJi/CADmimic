"""Utilities for rendering iteration summaries into a single image."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

VIEW_NAMES: Tuple[str, ...] = ("top", "bottom", "front", "back", "left", "right")


@dataclass
class VariantDisplay:
    iteration: str
    variant: str
    mean_score: float
    best_view: str
    best_image_path: Path
    view_scores: Dict[str, float]


class ScoreLoader:
    """Collect SigLIP scores for rendered images."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._global_img_scores = self._load_global_ranking(run_dir / "siglip_cosine_ranking.txt")

    @staticmethod
    def _load_global_ranking(rank_file: Path) -> Dict[Path, float]:
        if not rank_file.exists():
            return {}
        scores: Dict[Path, float] = {}
        with rank_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) != 3:
                    continue
                _rank, score_str, path_str = parts
                try:
                    score = float(score_str)
                except ValueError:
                    continue
                scores[Path(path_str)] = score
        return scores

    def load_iteration_scores(self, iter_dir: Path) -> Dict[str, Dict[str, float]]:
        by_variant: Dict[str, Dict[str, float]] = {}

        iter_score_file = iter_dir / "siglip_scores.json"
        if iter_score_file.exists():
            data = json.loads(iter_score_file.read_text(encoding="utf-8"))
            for variant, payload in data.items():
                view_scores = payload.get("view_scores") or {}
                if view_scores:
                    by_variant[variant] = {str(view): float(score) for view, score in view_scores.items()}

        return by_variant

    def score_from_manifest(
        self,
        variant: str,
        manifest_entry: Dict,
        existing_scores: Dict[str, Dict[str, float]],
    ) -> Dict[str, float]:
        siglip_blob = manifest_entry.get("siglip")
        if isinstance(siglip_blob, dict):
            view_scores = siglip_blob.get("view_scores")
            if isinstance(view_scores, dict) and view_scores:
                return {str(view): float(score) for view, score in view_scores.items()}

        if variant in existing_scores:
            return existing_scores[variant]

        images = manifest_entry.get("images") or {}
        collected: Dict[str, float] = {}
        for view, img_path in images.items():
            score = self._global_img_scores.get(Path(img_path))
            if score is not None:
                collected[str(view)] = float(score)
        return collected


def load_iteration_data(
    run_dir: Path,
    view_order: Sequence[str] = VIEW_NAMES,
) -> Dict[str, List[VariantDisplay]]:
    score_loader = ScoreLoader(run_dir)

    iteration_data: Dict[str, List[VariantDisplay]] = {}
    iter_dirs = [p for p in run_dir.iterdir() if p.is_dir()]
    iter_dirs.sort(key=lambda p: int(p.name) if p.name.isdigit() else p.name)

    for iter_dir in iter_dirs:
        manifest_path = iter_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        iter_scores = score_loader.load_iteration_scores(iter_dir)

        displays: List[VariantDisplay] = []
        for variant, entry in manifest.items():
            images: Dict[str, str] = entry.get("images") or {}
            if not images:
                continue

            view_scores = score_loader.score_from_manifest(variant, entry, iter_scores)
            if not view_scores:
                continue

            ordered_scores = [view_scores.get(view) for view in view_order if view in view_scores]
            if not ordered_scores:
                continue
            mean_score = sum(ordered_scores) / len(ordered_scores)

            best_view, _best_score = max(view_scores.items(), key=lambda kv: kv[1])
            best_path = images.get(best_view)
            if not best_path:
                best_path = next(iter(images.values()))

            displays.append(
                VariantDisplay(
                    iteration=iter_dir.name,
                    variant=variant,
                    mean_score=mean_score,
                    best_view=best_view,
                    best_image_path=Path(best_path),
                    view_scores=view_scores,
                )
            )

        if displays:
            displays.sort(key=lambda item: item.mean_score, reverse=True)
            iteration_data[iter_dir.name] = displays

    return iteration_data


def render_iteration_grid(
    iteration_data: Dict[str, List[VariantDisplay]],
    output_path: Path,
    top_p: int,
    thumbnail_size: Tuple[int, int] = (256, 256),
    column_spacing: int = 40,
    row_spacing: int = 40,
) -> None:
    if not iteration_data:
        raise RuntimeError("No iteration data with scores was found to render.")

    ordered_iterations = sorted(iteration_data.keys(), key=lambda name: int(name) if name.isdigit() else name)
    max_rows = max(len(iteration_data[name]) for name in ordered_iterations)

    thumb_w, thumb_h = thumbnail_size
    frame_thickness = 6
    top_text_space = 70
    bottom_text_space = 70
    header_height = 90

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        placeholder_path = tmp_dir / "placeholder.png"
        if not placeholder_path.exists():
            subprocess.run(
                [
                    "convert",
                    "-size",
                    f"{thumb_w}x{thumb_h}",
                    "xc:white",
                    "-gravity",
                    "center",
                    "-pointsize",
                    "36",
                    "-fill",
                    "#cc0000",
                    "-annotate",
                    "+0+0",
                    "missing",
                    str(placeholder_path),
                ],
                check=True,
            )

        column_images: List[Path] = []

        for iter_name in ordered_iterations:
            column_data = iteration_data[iter_name]
            highlight_cutoff = min(top_p, len(column_data)) if top_p > 0 else 0

            tile_paths: List[Path] = []
            tile_dimensions: Optional[Tuple[int, int]] = None
            for row, variant in enumerate(column_data):
                highlight = row < highlight_cutoff
                tile_path = tmp_dir / f"tile_{iter_name}_{row:02d}.png"
                base_image = variant.best_image_path if variant.best_image_path.exists() else placeholder_path
                _create_tile_image(
                    base_image=base_image,
                    tile_path=tile_path,
                    label_text=f"{variant.variant} ({variant.best_view})",
                    caption_text=f"mean {variant.mean_score:.3f}",
                    thumbnail_size=thumbnail_size,
                    frame_thickness=frame_thickness,
                    highlight=highlight,
                    top_text_space=top_text_space,
                    bottom_text_space=bottom_text_space,
                )
                if tile_dimensions is None:
                    tile_dimensions = _image_dimensions(tile_path)
                tile_paths.append(tile_path)

            if tile_dimensions is None:
                continue

            width, height = tile_dimensions
            blank_tile_path = tmp_dir / "blank_tile.png"
            if not blank_tile_path.exists():
                subprocess.run(
                    [
                        "convert",
                        "-size",
                        f"{width}x{height}",
                        "xc:white",
                        str(blank_tile_path),
                    ],
                    check=True,
                )

            while len(tile_paths) < max_rows:
                tile_paths.append(blank_tile_path)

            column_body = tmp_dir / f"column_body_{iter_name}.png"
            montage_cmd = ["montage"] + [str(p) for p in tile_paths]
            montage_cmd += [
                "-tile",
                f"1x{len(tile_paths)}",
                "-geometry",
                f"{width}x{height}+0+{row_spacing}",
                "-background",
                "white",
                str(column_body),
            ]
            subprocess.run(montage_cmd, check=True)

            header_path = tmp_dir / f"header_{iter_name}.png"
            subprocess.run(
                [
                    "convert",
                    "-size",
                    f"{width}x{header_height}",
                    "xc:white",
                    "-gravity",
                    "center",
                    "-pointsize",
                    "32",
                    "-fill",
                    "black",
                    "-annotate",
                    "+0+0",
                    f"Iteration {iter_name}",
                    str(header_path),
                ],
                check=True,
            )

            column_path = tmp_dir / f"column_{iter_name}.png"
            subprocess.run(
                [
                    "convert",
                    str(header_path),
                    str(column_body),
                    "-append",
                    str(column_path),
                ],
                check=True,
            )

            column_images.append(column_path)

        if not column_images:
            raise RuntimeError("No columns were generated for the visualization.")

        geometry = f"+{column_spacing}+0"
        montage_columns_cmd = ["montage"] + [str(p) for p in column_images]
        montage_columns_cmd += [
            "-tile",
            f"{len(column_images)}x1",
            "-geometry",
            geometry,
            "-background",
            "white",
            str(output_path),
        ]
        subprocess.run(montage_columns_cmd, check=True)


def _create_tile_image(
    base_image: Path,
    tile_path: Path,
    label_text: str,
    caption_text: str,
    thumbnail_size: Tuple[int, int],
    frame_thickness: int,
    highlight: bool,
    top_text_space: int,
    bottom_text_space: int,
) -> None:
    thumb_w, thumb_h = thumbnail_size
    frame_color = "#2ecc71" if highlight else "#cccccc"

    cmd = [
        "convert",
        str(base_image),
        "-resize",
        f"{thumb_w}x{thumb_h}",
        "-background",
        "white",
        "-gravity",
        "center",
        "-extent",
        f"{thumb_w}x{thumb_h}",
        "-bordercolor",
        frame_color,
        "-border",
        str(frame_thickness),
        "-background",
        "white",
        "-gravity",
        "north",
        "-splice",
        f"0x{top_text_space}",
        "-pointsize",
        "24",
        "-fill",
        "black",
        "-annotate",
        "+0+20",
        label_text,
        "-gravity",
        "south",
        "-splice",
        f"0x{bottom_text_space}",
        "-pointsize",
        "24",
        "-fill",
        "black",
        "-annotate",
        "+0+20",
        caption_text,
        str(tile_path),
    ]
    subprocess.run(cmd, check=True)


def _image_dimensions(image_path: Path) -> Tuple[int, int]:
    result = subprocess.run(
        ["identify", "-format", "%w %h", str(image_path)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    width_str, height_str = result.stdout.strip().split()
    return int(width_str), int(height_str)


def build_and_save_grid(
    run_dir: Path,
    output_path: Path,
    top_p: int,
    thumbnail_size: Tuple[int, int] = (256, 256),
) -> None:
    iteration_data = load_iteration_data(run_dir)
    render_iteration_grid(
        iteration_data,
        output_path,
        top_p=top_p,
        thumbnail_size=thumbnail_size,
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render iteration-by-iteration summary grid.")
    parser.add_argument("run_dir", type=Path, help="Path to a run directory (e.g. output/<timestamp>)")
    parser.add_argument("--top_p", type=int, default=2, help="Number of top variants to highlight per iteration")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the figure. Defaults to <run_dir>/iteration_summary.png",
    )
    parser.add_argument(
        "--thumb",
        type=int,
        default=256,
        help="Maximum edge size (pixels) for thumbnails inside the grid",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    run_dir: Path = args.run_dir.resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    output_path: Path
    if args.output is None:
        output_path = run_dir / "iteration_summary.png"
    else:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    thumb_size = (args.thumb, args.thumb)
    build_and_save_grid(run_dir, output_path, top_p=args.top_p, thumbnail_size=thumb_size)
    print(f"Saved iteration summary figure to {output_path}")


if __name__ == "__main__":
    main()
