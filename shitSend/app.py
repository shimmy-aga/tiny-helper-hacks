from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from pathlib import Path
import os
import mimetypes
import hashlib

# === CONFIG ===
FILE_PATH = Path(r"C:\Users\Santiago\Desktop\tinycloud\tinytexturepack.zip")  # <- set your real path
PUBLIC_NAME = "tinytexturepack.zip"                        # name shown to clients
SECRET_TOKEN = os.environ.get("DL_TOKEN", "")   # optional; set to require ?token=
CHUNK_SIZE = 1024 * 1024                        # 1 MiB

app = FastAPI(title="Texture Pack Downloader")

def require_token(req: Request):
    if not SECRET_TOKEN:
        return
    supplied = req.query_params.get("token", "")
    if supplied != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Missing/invalid token")

def file_size() -> int:
    if not FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FILE_PATH.stat().st_size

def parse_range(range_header: Optional[str], total: int):
    """
    Returns (start, end, status_code).
    If no valid Range, returns (0, total-1, 200).
    """
    if not range_header or not range_header.startswith("bytes="):
        return 0, total - 1, 200

    ranges = range_header.replace("bytes=", "").strip()
    if "," in ranges:
        return 0, total - 1, 200  # simple server: ignore multi-ranges

    start_str, _, end_str = ranges.partition("-")
    if start_str == "":  # suffix, like "-500"
        length = int(end_str)
        if length == 0:
            raise HTTPException(status_code=416, detail="Invalid range")
        start = max(total - length, 0)
        end = total - 1
    else:
        start = int(start_str)
        end = total - 1 if end_str == "" else int(end_str)
        if start > end or start >= total:
            raise HTTPException(status_code=416, detail="Invalid range")

    return start, min(end, total - 1), 206

def stream_file(path: Path, start: int, end: int):
    with path.open("rb") as f:
        f.seek(start)
        bytes_left = end - start + 1
        while bytes_left > 0:
            chunk = f.read(min(CHUNK_SIZE, bytes_left))
            if not chunk:
                break
            bytes_left -= len(chunk)
            yield chunk

@app.get("/", response_class=HTMLResponse)
async def index(req: Request):
    # Build base links (preserve token if required)
    qs_token = ""
    if SECRET_TOKEN:
        token = req.query_params.get("token", "")
        # If token provided in URL, keep it in the links; otherwise show placeholder
        qs_token = f"?token={token or 'YOUR_TOKEN_HERE'}"

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Download {PUBLIC_NAME}</title>
  <style>
    :root {{
      --bg1: #0f172a; /* slate-900 */
      --bg2: #111827cc;
      --card: #0b1220;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #60a5fa;
      --accent2: #34d399;
      --ring: #1f2937;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100svh;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji";
      color: var(--text);
      background: radial-gradient(1200px 800px at 20% -10%, #1f2937 0%, transparent 60%),
                  radial-gradient(1000px 700px at 120% 20%, #111827 0%, transparent 60%),
                  linear-gradient(180deg, var(--bg1), #020617 80%);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .wrap {{
      width: 100%;
      max-width: 720px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px;
      padding: 24px;
      backdrop-filter: blur(8px);
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(22px, 4vw, 32px);
      letter-spacing: 0.3px;
    }}
    .sub {{
      color: var(--muted);
      margin-bottom: 20px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 16px 0 24px;
    }}
    .pill {{
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 12px 14px;
      overflow: hidden;
    }}
    .pill .label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .pill .value {{
      font-weight: 600;
      word-break: break-all;
      user-select: all;
    }}
    .row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .btn {{
      appearance: none;
      border: 1px solid rgba(255,255,255,0.12);
      background: linear-gradient(180deg, #0ea5e9, #2563eb);
      color: white;
      font-weight: 700;
      padding: 12px 18px;
      border-radius: 12px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      transition: transform .06s ease, filter .2s ease, box-shadow .2s ease;
      box-shadow: 0 6px 18px rgba(37, 99, 235, 0.35);
    }}
    .btn:active {{ transform: translateY(1px); }}
    .ghost {{
      background: transparent;
      border: 1px solid rgba(255,255,255,0.18);
      color: var(--text);
      box-shadow: none;
    }}
    code {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.12);
      padding: 2px 6px;
      border-radius: 6px;
    }}
    .hint {{ color: var(--muted); font-size: 13px; margin-top: 10px; }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: 12px; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Download <code>{PUBLIC_NAME}</code></h1><br>
      <div class="sub">IK HEB EEN APP SPECIAAL HIERVOOR GEMAAKT. Ik hoop dat je de gelukkigste femboy ooit bent.</div>

      <div class="meta">
        <div class="pill">
          <span class="label">File size</span>
          <span class="value" id="size">—</span>
        </div>
        <div class="pill">
          <span class="label">SHA-256</span>
          <span class="value" id="hash">—</span>
        </div>
      </div>

      <div class="row">
        <a id="dl" class="btn" href="/download{qs_token}" download>⬇ Download</a>
        <button id="copy" class="btn ghost" type="button">🔗 Copy direct link</button>
      </div>

      <div class="hint">Ik vertrouw je niet, dus je authorizatie voor uploaden is bij deze verdwenen</div>
      <footer>Pro tip: Zuig mijn ballen</footer>
    </section>
  </main>

  <script>
    // Helper: format bytes nicely
    function fmtBytes(n) {{
      if (!n) return "—";
      const u = ["B","KB","MB","GB","TB"];
      let i = 0, val = Number(n);
      while (val >= 1024 && i < u.length-1) {{ val /= 1024; i++; }}
      return `${{val.toFixed(val < 10 && i > 0 ? 2 : 0)}} ${{u[i]}}`;
    }}

    // Build URLs, preserving token if present
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const qs = token ? `?token=${{encodeURIComponent(token)}}` : "{qs_token}";

    // Wire up buttons
    const dl = document.getElementById("dl");
    dl.href = "/download" + (qs || "");

    const copyBtn = document.getElementById("copy");
    copyBtn.addEventListener("click", async () => {{
      const url = window.location.origin + "/download" + (qs || "");
      await navigator.clipboard.writeText(url);
      copyBtn.textContent = "✅ Link copied";
      setTimeout(() => (copyBtn.textContent = "🔗 Copy direct link"), 1500);
    }});

    // Fetch checksum + size
    async function loadMeta() {{
      try {{
        const res = await fetch("/checksum" + (qs || ""));
        if (!res.ok) throw new Error("bad status");
        const data = await res.json();
        document.getElementById("size").textContent = fmtBytes(data.bytes);
        document.getElementById("hash").textContent = data.sha256;
      }} catch (e) {{
        document.getElementById("size").textContent = "Unavailable";
        document.getElementById("hash").textContent = "Unavailable";
      }}
    }}
    loadMeta();
  </script>
</body>
</html>
    """

@app.head("/download")
async def head(req: Request):
    require_token(req)
    total = file_size()
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(total),
        "Content-Type": mimetypes.guess_type(PUBLIC_NAME)[0] or "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{PUBLIC_NAME}"',
    }
    return Response(status_code=200, headers=headers)

@app.get("/download")
async def download(req: Request):
    require_token(req)
    total = file_size()
    start, end, status_code = parse_range(req.headers.get("range"), total)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mimetypes.guess_type(PUBLIC_NAME)[0] or "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{PUBLIC_NAME}"',
    }

    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
    else:
        headers["Content-Length"] = str(total)

    return StreamingResponse(
        stream_file(FILE_PATH, start, end),
        status_code=status_code,
        headers=headers,
    )

@app.get("/checksum")
async def checksum(req: Request):
    require_token(req)
    if not FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="File not found")
    h = hashlib.sha256()
    with FILE_PATH.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"file": PUBLIC_NAME, "sha256": h.hexdigest(), "bytes": file_size()}
