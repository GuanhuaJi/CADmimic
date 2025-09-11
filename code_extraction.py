# code_extraction.py
import re
from pathlib import Path
from typing import List

FENCE_RE = re.compile(
    r"```(?:python|py)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
PY_HINTS = (
    "import cadquery", "from cadquery", "show_object(", "cq.Workplane(", "result"
)

# code_extraction.py (add this near the top or bottom)
import ast, re

def sanitize_extrude_centered(code: str) -> str:
    """
    Drop `centered=` ONLY when used in `.extrude(...)`.
    CadQuery's Workplane.extrude doesn't accept `centered`,
    whereas primitives like `box`/`rect` do. 
    """
    class _Strip(ast.NodeTransformer):
        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "extrude":
                node.keywords = [kw for kw in node.keywords if kw.arg != "centered"]
            return node

    try:
        tree = ast.parse(code)
        tree = _Strip().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)  # Py3.9+
    except Exception:
        # regex fallback to be safe if parse fails
        s = code
        s = re.sub(r'(\.extrude\s*\([^)]*?),\s*centered\s*=\s*(True|False)\s*,', r'\1,', s, flags=re.DOTALL)
        s = re.sub(r'(\.extrude\s*\([^)]*?)\s*,\s*centered\s*=\s*(True|False)\s*(?=\))', r'\1', s, flags=re.DOTALL)
        s = re.sub(r'(\.extrude\s*\()\s*centered\s*=\s*(True|False)\s*(\))', r'\1\3', s, flags=re.DOTALL)
        return s


def _pick_best_block(blocks: List[str]) -> str:
    if not blocks:
        return ""
    # prefer blocks that mention CadQuery / result / show_object
    scored = []
    for b in blocks:
        score = sum(h in b for h in PY_HINTS)
        scored.append((score, len(b), b))
    scored.sort(reverse=True)
    return scored[0][2]

def extract_python_code(text: str) -> str:
    if not text:
        return ""
    blocks = [m.group(1) for m in FENCE_RE.finditer(text)]
    if blocks:
        return _pick_best_block(blocks).strip()
    # No fences; assume entire text is code
    return text.strip()

def write_code_files(codes: List[str], out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for i, code in enumerate(codes, start=1):
        p = out_dir / f"variant_{i:02d}.py"
        p.write_text(code, encoding="utf-8")
        paths.append(p)
    return paths
