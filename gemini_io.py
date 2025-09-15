# gemini_io.py
from __future__ import annotations
import time, asyncio, platform, mimetypes
from pathlib import Path
from typing import List, Optional, Tuple
from google import genai
from google.genai import types

tools = [
    types.Tool(url_context=types.UrlContext()),
    types.Tool(google_search=types.GoogleSearch()),
]

ACTIVE_STATE = "ACTIVE"

def _is_active_state(state_obj) -> bool:
    if state_obj is None:
        return False
    if isinstance(state_obj, str):
        return state_obj.upper() == ACTIVE_STATE
    name = getattr(state_obj, "name", None)
    if isinstance(name, str):
        return name.upper() == ACTIVE_STATE
    return str(state_obj).upper().endswith(ACTIVE_STATE)

def upload_video_and_wait_active(
    client: genai.Client,
    video_path: str,
    timeout_s: int = 900,
    poll_s: float = 5.0
):
    print(f"[files] Uploading video: {video_path}")
    f = client.files.upload(file=video_path)
    print(f"[files] Uploaded name={getattr(f,'name',None)} uri={getattr(f,'uri',None)} "
          f"state={getattr(f,'state',None)} mime={getattr(f,'mime_type',None)}")
    start = time.time()
    while True:
        info = client.files.get(name=f.name)
        print(f"[files] Poll: state={getattr(info,'state',None)} elapsed={int(time.time()-start)}s")
        if _is_active_state(getattr(info, "state", None)):
            print("[files] File is ACTIVE, proceeding.")
            return info
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for file to become ACTIVE "
                f"(last state={getattr(info, 'state', None)})"
            )
        time.sleep(poll_s)

def _guess_image_mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    # fallbacks for common cases
    if mt in ("image/png", "image/jpeg", "image/jpg", "image/webp"):  # supported image inputs
        return "image/jpeg" if mt == "image/jpg" else mt
    # default to png if unknown
    return "image/png"

def prepare_source_media(
    client: genai.Client,
    video_path: Optional[str] = None,
    image_path: Optional[str] = None,
):
    """
    Return a media part that can go directly into `contents` as the first item.
    - video: returns a Files API File (ACTIVE) you can reuse across requests.  :contentReference[oaicite:1]{index=1}
    - image: returns an inline Part created from bytes with the proper MIME.     :contentReference[oaicite:2]{index=2}
    """
    if video_path:
        media = upload_video_and_wait_active(client, video_path)
        kind = "video"
    elif image_path:
        mime = _guess_image_mime(image_path)
        print(f"[media] Loading image bytes: {image_path} (mime={mime})")
        data = Path(image_path).read_bytes()
        media = types.Part.from_bytes(data=data, mime_type=mime)     # inline image bytes
        kind = "image"
    else:
        raise ValueError("Either video_path or image_path must be provided.")
    return media, kind

def build_contents(source_media, prompt_text: str):
    # Recommended order for multimodal: media first, then text. :contentReference[oaicite:3]{index=3}
    print(f"[build] Building contents with media first + text (prompt chars={len(prompt_text)})")
    return [source_media, prompt_text]

# ------------------ async generation (no exception handling) ------------------

async def _one_call(client, model, contents, gen_config, attempt: int, logs_dir: Path) -> str:
    cfg = types.GenerateContentConfig(
        tools=tools,
        response_mime_type="text/plain",
    )
    print(f"[gen][{attempt:02d}] sending generate_content(model={model})")
    resp = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=cfg,
    )
    cand = getattr(resp, "candidates", []) or []
    pf = getattr(resp, "prompt_feedback", None)
    print(f"[gen][{attempt:02d}] got response: candidates={len(cand)} "
          f"text_len={len(getattr(resp,'text','') or '')} prompt_feedback={pf}")
    return resp.text or ""

async def async_generate_variants(
    client: genai.Client,
    model: str,
    contents,
    num: int,
    gen_config: Optional[types.GenerateContentConfig],
    concurrency: int,
    logs_dir: Path,
) -> List[str]:
    print(f"[gen] google-genai version={getattr(genai,'__version__','?')} "
          f"python={platform.python_version()} concurrency={concurrency} n={num}")
    sem = asyncio.Semaphore(concurrency)
    async def bound_call(i: int):
        async with sem:
            local_contents = list(contents)
            await asyncio.sleep(0.01 * i)
            return await _one_call(client, model, local_contents, gen_config, i, logs_dir)
    tasks = [asyncio.create_task(bound_call(i)) for i in range(1, num + 1)]
    return await asyncio.gather(*tasks)
