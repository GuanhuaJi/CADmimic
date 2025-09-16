# render_six_views.py  — headless + orthographic + safe clipping + color support
from __future__ import annotations
import base64
import importlib.util
import math
import os
# Force headless before importing VTK/CadQuery
os.environ.setdefault("VTK_DEFAULT_OPENGL_WINDOW", "vtkOSOpenGLRenderWindow")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cadquery as cq

# VTK modules (offscreen-friendly imports)
from vtkmodules.vtkCommonDataModel import VTK_TRIANGLE, VTK_LINE, VTK_VERTEX
from vtkmodules.vtkFiltersExtraction import vtkExtractCellsByType
from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper as vtkMapper,
    vtkRenderer,
    vtkRenderWindow,
    vtkWindowToImageFilter,
)

# ───────────────────────── helpers ─────────────────────────

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
    """Import the user .py and capture show_object(obj, options)."""
    spec = importlib.util.spec_from_file_location("user_model", infile)
    mod = importlib.util.module_from_spec(spec)
    captured: List[Tuple[object, dict]] = []
    def _capture(obj, name=None, options=None):
        captured.append((obj, options or {}))
    mod.show_object = _capture
    sys.modules["user_model"] = mod
    spec.loader.exec_module(mod)
    if captured:
        return captured
    if hasattr(mod, "result"):
        return [(mod.result, {})]
    return []

def _normalize_color(c) -> Tuple[Optional[Tuple[float, float, float]], Optional[float]]:
    """Accept cq.Color, '#RRGGBB'/name, or (r,g,b[,a]) → (rgb, alpha), all 0..1."""
    if c is None:
        return None, None
    if isinstance(c, cq.Color):
        r, g, b, a = c.toTuple()
        return (float(r), float(g), float(b)), float(a)
    if isinstance(c, str):
        r, g, b, a = cq.Color(c).toTuple()
        return (float(r), float(g), float(b)), float(a)
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        rgb = (float(c[0]), float(c[1]), float(c[2]))
        a = float(c[3]) if len(c) >= 4 else None
        return rgb, a
    return None, None

def _to_colored_shapes(objs_with_opts: List[Tuple[object, dict]]):
    """
    Return list[(shape, rgb, alpha)].
    - respects show_object(options={"color","alpha"})
    - respects cq.Assembly per-part color with inheritance
    - Workplane: collects solids() or Shape objects on stack
    """
    out = []
    for (o, opts) in objs_with_opts:
        base_rgb, base_a = _normalize_color(opts.get("color"))
        if "alpha" in opts:
            try:
                base_a = float(opts["alpha"])
            except Exception:
                pass

        if isinstance(o, cq.Assembly):
            # Iteration yields (Shape, name, Location, Color|None)
            for s, name, loc, acol in o:
                s2 = s.moved(loc)
                rgb2, a2 = _normalize_color(acol)
                out.append((s2, rgb2 or base_rgb, a2 if a2 is not None else base_a))
        elif isinstance(o, cq.Workplane):
            try:
                solids = o.solids().vals()
            except Exception:
                solids = []
            if not solids:
                solids = [s for s in getattr(o, "objects", []) if isinstance(s, cq.Shape)]
            for s in solids:
                out.append((s, base_rgb, base_a))
        elif isinstance(o, cq.Shape):
            out.append((o, base_rgb, base_a))
    return out

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

def _planar_and_depth(dx: float, dy: float, dz: float, d: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """Map camera direction to (planar width_x, planar width_y, depth)."""
    vx, vy, vz = d
    if vz != 0:      # ±Z → XY plane
        return dx, dy, dz
    elif vy != 0:    # ±Y → XZ plane
        return dx, dz, dy
    else:            # ±X → YZ plane
        return dy, dz, dx

def _vtk_actors_from_colored(colored_shapes: List[Tuple[cq.Shape, Optional[Tuple[float,float,float]], Optional[float]]]):
    """Build VTK actors for faces and edges; apply per-object color/alpha."""
    face_actors, edge_actors = [], []
    for s, rgb, alpha in colored_shapes:
        # Tessellate CadQuery shape to VTK polydata
        poly = s.toVtkPolyData(1e-3, 0.1)  # (linear tol, angular tol)

        # Separate triangles vs edges/points
        ext_tri = vtkExtractCellsByType()
        ext_tri.SetInputDataObject(poly)
        ext_tri.AddCellType(VTK_TRIANGLE)
        ext_tri.Update()
        data_faces = ext_tri.GetOutput()

        ext_edge = vtkExtractCellsByType()
        ext_edge.SetInputDataObject(poly)
        ext_edge.AddCellType(VTK_LINE)
        ext_edge.AddCellType(VTK_VERTEX)
        ext_edge.Update()
        data_edges = ext_edge.GetOutput()
        try:
            data_edges.GetPointData().RemoveArray("Normals")
        except Exception:
            pass

        m_faces = vtkMapper(); a_faces = vtkActor(); a_faces.SetMapper(m_faces)
        m_faces.SetInputDataObject(data_faces)
        fr, fg, fb = (rgb or (0.83, 0.83, 0.85))
        a_faces.GetProperty().SetColor(fr, fg, fb)
        a_faces.GetProperty().SetOpacity(alpha if alpha is not None else 1.0)

        m_edges = vtkMapper(); a_edges = vtkActor(); a_edges.SetMapper(m_edges)
        m_edges.SetInputDataObject(data_edges)
        if rgb:
            dr, dg, db = (max(0.0, fr*0.25), max(0.0, fg*0.25), max(0.0, fb*0.25))
            a_edges.GetProperty().SetColor(dr, dg, db)
        else:
            a_edges.GetProperty().SetColor(0.1, 0.1, 0.1)
        a_edges.GetProperty().SetLineWidth(1)

        face_actors.append(a_faces)
        edge_actors.append(a_edges)
    return face_actors, edge_actors

# ───────────────────────── public API ─────────────────────────

def render_six_views(
    infile: str,
    outdir: str,
    size: int = 800,
    margin: float = 1.12,
    tilt_eps: float = 1e-3,  # kept for CLI compatibility; not used here
    log_file: str | None = None,
) -> Dict[str, str]:
    """
    Render six orthographic PNG views (top/bottom/front/back/left/right),
    fully headless, with color support and safe clipping.
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
        # name: ((dir x,y,z), roll_deg, view_up)
        "top":    ((0, 0,  1),   0, (0, 1, 0)),
        "bottom": ((0, 0, -1), 180, (0, 1, 0)),
        "front":  ((0, 1,  0),   0, (0, 0, 1)),
        "back":   ((0,-1,  0), 180, (0, 0, 1)),
        "left":   ((-1,0,  0),   0, (0, 0, 1)),
        "right":  ((1, 0,  0),   0, (0, 0, 1)),
    }

    # Load & collect colored shapes
    try:
        _log(log_path, "load", f"Loading module '{infile}'")
        objs = _load_module_and_collect(infile)
        colored = _to_colored_shapes(objs)
        _log(log_path, "load", f"Collected {len(colored)} shape(s)")
    except Exception as e:
        _log(log_path, "load", "Module load failed", e)
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, f"Load error: {type(e).__name__}: {e}")
            out[name] = str(p)
        return out

    if not colored:
        _log(log_path, "normalize", "No shapes to render (expected Shape/Workplane/Assembly)")
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, "No shapes to render")
            out[name] = str(p)
        return out

    # Bounds & center
    try:
        xmin, xmax, ymin, ymax, zmin, zmax = _bbox([s for (s, _, _) in colored])
        cx, cy, cz = (xmax + xmin) / 2.0, (ymax + ymin) / 2.0, (zmax + zmin) / 2.0
        dx, dy, dz = (xmax - xmin), (ymax - ymin), (zmax - zmin)
        colored_centered = [(s.moved(cq.Location((-cx, -cy, -cz))), rgb, a) for (s, rgb, a) in colored]
        _log(log_path, "fit", f"bbox=({dx:.3f},{dy:.3f},{dz:.3f})  centered@origin")
    except Exception as e:
        _log(log_path, "fit", "Bounding box / center failed", e)
        for name in views:
            p = out_dir / f"{base}_{name}.png"
            _placeholder_png(p, size, f"BBox error: {type(e).__name__}: {e}")
            out[name] = str(p)
        return out

    # Render each view
    for name, (d, roll, up) in views.items():
        p = out_dir / f"{base}_{name}.png"
        try:
            vx, vy, vz = d
            wx, wy, depth = _planar_and_depth(dx, dy, dz, d)
            half_w = 0.5 * max(wx, wy) * margin
            safe_depth = max(depth, max(dx, dy, dz)) * 1.25

            face_actors, edge_actors = _vtk_actors_from_colored(colored_centered)

            ren = vtkRenderer()
            win = vtkRenderWindow()
            win.SetSize(size, size)
            win.SetOffScreenRendering(1)
            win.AddRenderer(ren)
            ren.SetBackground(1.0, 1.0, 1.0)

            for a in face_actors + edge_actors:
                ren.AddActor(a)

            # Initial render to ensure bounds are valid
            win.Render()

            cam = ren.GetActiveCamera()
            cam.ParallelProjectionOn()                 # orthographic projection
            cam.SetParallelScale(max(half_w, 1e-6))    # half viewport height in world units
            cam.SetFocalPoint(0.0, 0.0, 0.0)
            cam.SetViewUp(*up)
            cam.SetPosition(safe_depth * vx, safe_depth * vy, safe_depth * vz)
            if abs(roll) > 1e-9:
                cam.Roll(float(roll))

            ren.ResetCameraClippingRange()            # prevents near/far clipping

            win.Render()
            w2i = vtkWindowToImageFilter()
            w2i.SetInput(win)
            w2i.Update()
            writer = vtkPNGWriter()
            writer.SetFileName(str(p))
            writer.SetInputConnection(w2i.GetOutputPort())
            writer.Write()

        except Exception as e:
            _log(log_path, "render", f"View={name} failed", e)
            _placeholder_png(p, size, f"Render error: {type(e).__name__}: {e}")
        out[name] = str(p)

    _log(log_path, "done", f"Wrote {len(out)} image(s) to {out_dir}")
    return out

# ───────────────────────── CLI ─────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Render six views of a CadQuery .py (orthographic, headless, colored)")
    ap.add_argument("--infile", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--size", type=int, default=800)
    ap.add_argument("--margin", type=float, default=1.12)
    ap.add_argument("--tilt_eps", type=float, default=1e-3)  # kept for backward compat
    ap.add_argument("--log_file", default=None)
    args = ap.parse_args()
    res = render_six_views(args.infile, args.outdir, args.size, args.margin, args.tilt_eps, args.log_file)
    for k, v in res.items():
        print(f"{k}: {v}")



'''
python /Users/jiguanhua/vlmgineer/CADmimic/render_six_views.py \
    --infile /Users/jiguanhua/vlmgineer/CADmimic/output/2025-09-11_23-48-00/10/codes/variant_01.py \
         --outdir /Users/jiguanhua/vlmgineer/gemini_evolution/output/2025-09-11_23-48-00/10/renders --size 800 --margin 1.2 --tilt_eps 0.001 --log_file /Users/jiguanhua/vlmgineer/gemini_evolution/output/2025-09-11_23-48-00/10/renders/variant_01_render.log

python /Users/jiguanhua/vlmgineer/CADmimic/render_six_views.py \
    --infile /Users/jiguanhua/vlmgineer/CADmimic/output/2025-09-11_23-26-55/0/codes/variant_01.py \
         --outdir /Users/jiguanhua/vlmgineer/gemini_evolution/output/2025-09-11_23-48-00/10/renders --size 800 --margin 1.2 --tilt_eps 0.001

python /Users/jiguanhua/vlmgineer/CADmimic/render_six_views.py \
    --infile /Users/jiguanhua/vlmgineer/CADmimic/output/2025-09-11_21-55-26/10/codes/variant_08.py \
         --outdir /Users/jiguanhua/vlmgineer/gemini_evolution/output/2025-09-11_23-48-00/10/renders --size 800 --margin 1.2 --tilt_eps 0.001

         
'''
