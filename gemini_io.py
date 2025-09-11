# gemini_io.py
from __future__ import annotations
import time, asyncio, platform
from pathlib import Path
from typing import List, Optional
from google import genai
from google.genai import types

tools = [
    types.Tool(url_context=types.UrlContext()),   # allow reading specific URLs
    types.Tool(google_search=types.GoogleSearch())  # optional: combine with Search
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

def build_contents(uploaded_file, prompt_text: str):
    print(f"[build] Building contents with video first + text (prompt chars={len(prompt_text)})")
    return [uploaded_file, prompt_text]

# ------------------ async generation (no exception handling) ------------------

async def _one_call(client, model, contents, gen_config, attempt: int, logs_dir: Path) -> str:
    gen_config = types.GenerateContentConfig(
        tools=tools,
        response_mime_type="text/plain",
    )
    print(f"[gen][{attempt:02d}] sending generate_content(model={model}) "
          f"temp={getattr(gen_config,'temperature',None)} top_p={getattr(gen_config,'top_p',None)} "
          f"max_tokens={getattr(gen_config,'max_output_tokens',None)}")
    resp = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=gen_config,
    )

    # Debug summary
    cand = getattr(resp, "candidates", []) or []
    pf = getattr(resp, "prompt_feedback", None)
    print(f"[gen][{attempt:02d}] got response: candidates={len(cand)} "
          f"text_len={len(getattr(resp,'text','') or '')} prompt_feedback={pf}")

    # Per-candidate finish reasons (if present)
    try:
        frs = [getattr(c, "finish_reason", None) for c in cand]
        print(f"[gen][{attempt:02d}] finish_reasons={frs}")
    except Exception:
        pass

    # Return raw .text (can be empty if model omitted it)
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
            # build fresh list to avoid any accidental mutation by the SDK
            local_contents = list(contents)
            await asyncio.sleep(0.01 * i)  # tiny stagger
            return await _one_call(client, model, local_contents, gen_config, i, logs_dir)

    tasks = [asyncio.create_task(bound_call(i)) for i in range(1, num + 1)]
    return await asyncio.gather(*tasks)
