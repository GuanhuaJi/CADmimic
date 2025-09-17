"""SigLIP similarity scoring across six rendered views."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, SiglipModel

VIEW_ORDER: Tuple[str, ...] = ("top", "bottom", "front", "back", "left", "right")
DEFAULT_MODEL_ID = "google/siglip-so400m-patch14-384"
DEFAULT_BATCH_SIZE = 16


def _default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _default_dtype(device: str) -> torch.dtype:
    return torch.float16 if device.startswith("cuda") else torch.float32


@dataclass
class SiglipResult:
    view_scores: Dict[str, float]
    average: float


class SiglipScorer:
    def __init__(
        self,
        target_image_path: str,
        model_id: str = DEFAULT_MODEL_ID,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str | None = None,
        dtype: torch.dtype | None = None,
    ) -> None:
        self.target_image_path = str(target_image_path)
        self.model_id = model_id
        self.batch_size = batch_size
        self.device = device or _default_device()
        self.dtype = dtype or _default_dtype(self.device)

        print(f"[siglip] loading model={self.model_id} device={self.device} dtype={self.dtype}")
        self.processor = AutoImageProcessor.from_pretrained(self.model_id, use_fast=True)
        self.model = SiglipModel.from_pretrained(self.model_id, torch_dtype=self.dtype)
        self.model = self.model.to(self.device).eval()

        with torch.inference_mode():
            target_px, loaded = self._load_images([("target", self.target_image_path)])
            if target_px.numel() == 0:
                raise RuntimeError(f"Failed to load target image: {self.target_image_path}")
            self.target_feat = self._encode(target_px)
            print(f"[siglip] target embedding ready ({len(loaded)} image)")

    def _load_images(self, items: Iterable[Tuple[str, str]]) -> Tuple[torch.Tensor, List[Tuple[str, str]]]:
        pil_images: List[Image.Image] = []
        loaded: List[Tuple[str, str]] = []
        for name, path in items:
            if not path:
                continue
            try:
                pil_images.append(Image.open(path).convert("RGB"))
                loaded.append((name, path))
            except Exception as exc:  # pragma: no cover - logging only
                print(f"[siglip] skip {path}: {exc}")
        if not pil_images:
            return torch.empty(0), []
        pixel_values = self.processor(images=pil_images, return_tensors="pt").pixel_values
        pixel_values = pixel_values.to(device=self.device, dtype=self.dtype)
        return pixel_values, loaded

    def _encode(self, pixel_values: torch.Tensor) -> torch.Tensor:
        feats = self.model.get_image_features(pixel_values=pixel_values)
        return F.normalize(feats, dim=-1)

    def score_views(
        self,
        images: Dict[str, str],
        view_order: Sequence[str] = VIEW_ORDER,
    ) -> SiglipResult:
        items = [(name, images.get(name)) for name in view_order]
        with torch.inference_mode():
            pixel_values, loaded = self._load_images(items)
            if pixel_values.numel() == 0:
                raise RuntimeError("No valid views to score.")
            feats = self._encode(pixel_values)
            sims = (feats @ self.target_feat.T).squeeze(-1)
        scores: Dict[str, float] = {}
        for (view_name, path), score in zip(loaded, sims.float().cpu().tolist()):
            scores[view_name] = float(score)
        if not scores:
            raise RuntimeError("All views failed during scoring.")
        average = sum(scores.values()) / len(scores)
        return SiglipResult(view_scores=scores, average=float(average))

    def score_manifest(
        self,
        manifest: Dict[str, Dict],
        view_order: Sequence[str] = VIEW_ORDER,
    ) -> Dict[str, SiglipResult]:
        results: Dict[str, SiglipResult] = {}
        for variant, info in manifest.items():
            try:
                res = self.score_views(info.get("images", {}), view_order=view_order)
                results[variant] = res
            except Exception as exc:  # pragma: no cover - logging only
                print(f"[siglip] {variant}: scoring failed ({exc})")
        return results
