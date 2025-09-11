# render_six_views.py
from __future__ import annotations
import base64
import importlib.util
import math
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import cadquery as cq
from cadquery.vis import show  # supports screenshot/position/roll/interact args

# ---- helpers ----------------------------------------------------------------

def _placeholder_png(path: Path, size: int, msg: str):
    try:
        from PIL import Image, ImageDraw, ImageFont
        im = Image.new("RGB", (size, size), (240, 240, 240))
        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        draw.multiline_text((10, 10), f"Render error:\n{msg}", fill=(180, 0, 0), font=font, spacing=4)
        im.save(path)
    except Exception:
        tiny = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
        )
        path.write_bytes(tiny)

def _log(log_path: Path, stage: str, msg: str, exc: BaseException | None = None):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{stage}] {msg}\n")
        if exc is not None:
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write("\n")

def _load_module_and_collect(infile: str):
    spec = importlib.util.spec_from_file_location("user_model", infile)
    mod = importlib.util.module_from_spec(spec)
    captured = []
    def _capture(obj, *_, **__):
        captured.append(obj)
    mod.show_object = _capture
    sys.modules["user_model"] = mod
    spec.loader.exec_module(mod)
    objs = captured or ([mod.result] if hasattr(mod, "result") else [])
    return objs

def _to_shapes(objs) -> List[cq.Shape]:
    shapes: List[cq.Shape] = []
    for o in objs:
        try:
            if isinstance(o, cq.Assembly):
                # single compound that contains all assembly solids
                shapes.append(o.toCompound())                                   # ok to bbox/preview as one shape
            elif isinstance(o, cq.Workplane):
                # get *all* results, not just .val()
                vals = []
                try:
                    vals = o.vals()                                            # all items on the stack
                except Exception:
                    vals = []
                if not vals:
                    # fallback to raw stack if needed
                    vals = [s for s in getattr(o, "objects", []) if isinstance(s, cq.Shape)]
                for v in vals:
                    if isinstance(v, cq.Shape):
                        shapes.append(v)
            elif isinstance(o, cq.Shape):
                shapes.append(o)
        except Exception:
            pass
    return shapes


def _bbox(shapes: List[cq.Shape]):
    bb0 = shapes[0].BoundingBox()
    xmin, xmax = bb0.xmin, bb0.xmax
    ymin, ymax = bb0.ymin, bb0.ymax
    zmin, zmax = bb0.zmin, bb0.zmax
    for s in shapes[1:]:
        bb = s.BoundingBox()
        xmin, xmax = min(xmin, bb.xmin), max(xmax, bb.xmax)
        ymin, ymax = min(ymin, bb.ymin), max(ymax, bb.ymax)
        zmin, zmax = min(zmin, bb.zmin), max(zmax, bb.zmax)
    return xmin, xmax, ymin, ymax, zmin, zmax

def _safe_dir(vx, vy, vz, eps=1e-3):
    # Avoid VTK 'view-up parallel to view normal' by a tiny tilt on axis-aligned views.
    if abs(vx) == 1 and vy == vz == 0:
        vz = eps
    elif abs(vy) == 1 and vx == vz == 0:
        vx = eps
    elif abs(vz) == 1 and vx == vy == 0:
        vx = eps
    n = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
    return vx / n, vy / n, vz / n

# ---- public API --------------------------------------------------------------

def render_six_views(
    infile: str,
    outdir: str,
    size: int = 800,
    margin: float = 1.2,
    tilt_eps: float = 1e-3,
    log_file: str | None = None,
) -> Dict[str, str]:
    """
    Render six axis views to PNG. Returns dict view->path.
    On any failure, writes a placeholder PNG *and* appends details to a log file.
    """
    out: Dict[str, str] = {}
    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(infile).stem
    log_path = Path(log_file) if log_file else (out_dir / f"{base}_render.log")

    try:
        if log_path.exists():
            log_path.unlink()
    except Exception:
        pass

    views = {
        "top":    ((0, 0,  1),   0),
        "bottom": ((0, 0, -1), 180),
        "front":  ((0, 1,  0),   0),
        "back":   ((0,-1,  0), 180),
        "left":   ((-1,0,  0),   0),
        "right":  ((1, 0,  0),   0),
    }

    # Load & normalize
    try:
        _log(log_path, "load", f"Loading module '{infile}'")
        objs = _load_module_and_collect(infile)
        _log(log_path, "load", f"Collected {len(objs)} object(s)")
    except Exception as e:
        _log(log_path, "load", "Module load failed", e)
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, f"Load error: {type(e).__name__}: {e}")
            out[name] = str(p)
        return out

    shapes = _to_shapes(objs)
    if not shapes:
        _log(log_path, "normalize", "No shapes to render (expected Shape/Workplane/Assembly)")
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, "No shapes to render")
            out[name] = str(p)
        return out

    # Bounds & center
    try:
        xmin, xmax, ymin, ymax, zmin, zmax = _bbox(shapes)
        cx, cy, cz = (xmax + xmin) / 2.0, (ymax + ymin) / 2.0, (zmax + zmin) / 2.0
        centered = [s.moved(cq.Location((-cx, -cy, -cz))) for s in shapes]
        dx, dy, dz = (xmax - xmin), (ymax - ymin), (zmax - zmin)
        R = max(1e-6, 0.5 * math.sqrt(dx * dx + dy * dy + dz * dz))
        fov_deg = 30.0  # VTK default vertical view angle
        theta = math.radians(fov_deg) / 2.0
        dist = (R / math.tan(theta)) * margin
        _log(log_path, "fit", f"bbox=({dx:.3f},{dy:.3f},{dz:.3f}) R={R:.3f} dist={dist:.3f}")
    except Exception as e:
        _log(log_path, "fit", "Bounding box / camera fit failed", e)
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, f"BBox error: {type(e).__name__}: {e}")
            out[name] = str(p)
        return out

    # Render all views (log per-view failures)
    for name, (d, roll) in views.items():
        p = out_dir / f"{base}_{name}.png"
        try:
            vx, vy, vz = _safe_dir(*d, eps=tilt_eps)
            position = (dist * vx, dist * vy, dist * vz)
            _log(log_path, "render", f"View={name} pos={position} roll={roll}")
            show(
                *centered,
                width=size,
                height=size,
                screenshot=str(p),
                position=position,
                roll=roll,
                interact=False,
            )
        except Exception as e:
            _log(log_path, "render", f"View={name} failed", e)
            _placeholder_png(p, size, f"Render error: {type(e).__name__}: {e}")
        out[name] = str(p)

    _log(log_path, "done", f"Wrote {len(out)} image(s) to {out_dir}")
    return out

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Render six views of a CadQuery .py")
    ap.add_argument("--infile", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--size", type=int, default=800)
    ap.add_argument("--margin", type=float, default=1.2)
    ap.add_argument("--tilt_eps", type=float, default=1e-3)
    ap.add_argument("--log_file", default=None, help="Path to append render/debug logs (default: <outdir>/<base>_render.log)")
    args = ap.parse_args()
    res = render_six_views(args.infile, args.outdir, args.size, args.margin, args.tilt_eps, args.log_file)
    for k, v in res.items():
        print(f"{k}: {v}")
