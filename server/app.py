import os
import time
import json
import hashlib
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("archiver")

PORT = int(os.getenv("PORT", "8888"))
API_TOKEN = os.getenv("API_TOKEN", "")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./snapshots"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8888").rstrip("/")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))

STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Periodic background cleaner for snapshots older than RETENTION_DAYS
async def retention_cleanup_loop():
    while True:
        try:
            cutoff = time.time() - (RETENTION_DAYS * 86400)
            removed = 0
            for f in STORAGE_DIR.glob("*.html"):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        removed += 1
                    except Exception as e:
                        logger.error(f"Error deleting expired file {f}: {e}")
            if removed > 0:
                logger.info(f"Auto-retention cleaned {removed} expired snapshot(s) (> {RETENTION_DAYS} days old).")
        except Exception as e:
            logger.error(f"Retention loop encountered an error: {e}")
        # Run cleanup every 24 hours
        await asyncio.sleep(86400)

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleaner_task = asyncio.create_task(retention_cleanup_loop())
    yield
    cleaner_task.cancel()

app = FastAPI(title="VPS Archive Lens", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BLOCKED_DOMAINS = [
    "tinypass.com",
    "piano.io",
    "cxense.com",
    "evolok.net",
    "zephr.com",
    "adlightning.com",
    "doubleclick.net",
    "googlesyndication.com",
    "google-analytics.com",
    "analytics.google.com",
    "connect.facebook.net",
    "scorecardresearch.com",
    "criteo.com",
    "outbrain.com",
    "taboola.com"
]

def verify_token(req: Request, token: str = Query(None)):
    if not API_TOKEN:
        return True
    auth_header = req.headers.get("Authorization")
    provided = None
    if auth_header and auth_header.startswith("Bearer "):
        provided = auth_header.split(" ", 1)[1].strip()
    elif token:
        provided = token.strip()
    
    if provided != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API token")
    return True

recent_cache = {}

async def capture_page(target_url: str) -> dict:
    url_hash = hashlib.sha256(target_url.encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d_%H%M%S")
    snapshot_id = f"{date_str}_{url_hash}"
    filepath = STORAGE_DIR / f"{snapshot_id}.html"

    logger.info(f"Capturing: {target_url} -> {snapshot_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "DNT": "1"
            }
        )

        page = await context.new_page()

        async def route_interceptor(route):
            req_url = route.request.url.lower()
            if any(blocked in req_url for blocked in BLOCKED_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", route_interceptor)

        try:
            try:
                await page.goto(target_url, wait_until="networkidle", timeout=18000)
            except Exception:
                pass

            # Scroll to trigger lazy loading
            await page.evaluate("""async () => {
                window.scrollBy(0, window.innerHeight * 1.5);
                await new Promise(r => setTimeout(r, 500));
                window.scrollTo(0, 0);
            }""")
            await asyncio.sleep(1.0)

            raw_html = await page.content()
        finally:
            await browser.close()

    soup = BeautifulSoup(raw_html, "html.parser")

    # Strip scripts and noscripts
    for s in soup.find_all(["script", "noscript"]):
        s.decompose()

    # Base tag for relative links
    head = soup.head
    if not head:
        head = soup.new_tag("head")
        soup.insert(0, head)
    base_tag = soup.new_tag("base", href=target_url)
    head.insert(0, base_tag)

    # Remove scroll lock CSS
    for tag in soup.find_all(True):
        style = tag.get("style", "")
        if "overflow" in style or "position: fixed" in style:
            new_style = re.sub(r"overflow(-[xy])?\s*:\s*hidden\s*(!important)?\s*;?", "", style, flags=re.IGNORECASE)
            new_style = re.sub(r"pointer-events\s*:\s*none\s*(!important)?\s*;?", "", new_style, flags=re.IGNORECASE)
            tag["style"] = new_style

    # Remove common paywall overlays
    paywall_selectors = [
        '[id*="paywall"]', '[class*="paywall"]',
        '[class*="tp-modal"]', '[class*="tp-backdrop"]',
        '[class*="subscriber-gate"]', '[id*="gateway-content"]',
        '[class*="piano-overlay"]', '#reg-wall', '.fc-dialog-container'
    ]
    for sel in paywall_selectors:
        for elem in soup.select(sel):
            if len(elem.get_text(strip=True)) < 1000:
                elem.decompose()

    date_display = now.strftime('%Y-%m-%d %H:%M:%S UTC')
    banner_html = f"""
    <div id="vps-lens-banner" style="
        position: sticky;
        top: 0;
        left: 0;
        right: 0;
        z-index: 9999999;
        background: #0f172a;
        color: #f8fafc;
        border-bottom: 2px solid #38bdf8;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 13px;
        padding: 8px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    ">
        <div style="display: flex; align-items: center; gap: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            <span style="font-weight: 700; color: #38bdf8;">⚡ VPS Archive Lens</span>
            <span style="color: #94a3b8;">|</span>
            <span style="color: #cbd5e1;">Archived: {date_display}</span>
            <span style="color: #94a3b8;">|</span>
            <a href="{target_url}" target="_blank" rel="noopener noreferrer" style="color: #38bdf8; text-decoration: underline; overflow: hidden; text-overflow: ellipsis;">Original Source</a>
        </div>
        <button onclick="document.getElementById('vps-lens-banner').style.display='none'" style="
            background: #334155;
            color: #f8fafc;
            border: none;
            border-radius: 4px;
            padding: 3px 8px;
            cursor: pointer;
            font-size: 12px;
            margin-left: 12px;
        ">✕ Close</button>
    </div>
    """
    banner_soup = BeautifulSoup(banner_html, "html.parser")
    if soup.body:
        soup.body.insert(0, banner_soup)
    else:
        soup.append(banner_soup)

    final_html = str(soup)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_html)

    meta = {
        "id": snapshot_id,
        "url": target_url,
        "filename": f"{snapshot_id}.html",
        "created_at": now.isoformat(),
        "view_url": f"{BASE_URL}/view/{snapshot_id}"
    }
    recent_cache[target_url] = meta
    return meta

@app.get("/health")
def health():
    snapshots = list(STORAGE_DIR.glob("*.html"))
    return {
        "status": "online",
        "snapshots_count": len(snapshots),
        "retention_days": RETENTION_DAYS,
        "storage_dir": str(STORAGE_DIR),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/archive", response_class=HTMLResponse)
async def archive_web_view(request: Request, url: str = Query(...), token: str = Query(None)):
    verify_token(request, token)
    if url in recent_cache:
        return RedirectResponse(recent_cache[url]["view_url"])

    token_param = f"&token={token}" if token else ""
    url_json = json.dumps(url)

    return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Unpaywalling & Archiving...</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        body {{
          background: #0f172a;
          color: #f8fafc;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100vh;
          margin: 0;
        }}
        .card {{
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 12px;
          padding: 36px 32px;
          max-width: 480px;
          text-align: center;
          box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        .spinner {{
          width: 48px;
          height: 48px;
          border: 4px solid #334155;
          border-top-color: #38bdf8;
          border-radius: 50%;
          animation: spin 0.9s linear infinite;
          margin: 0 auto 24px auto;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        h2 {{ margin: 0 0 12px 0; font-size: 1.3rem; color: #38bdf8; }}
        p {{ margin: 0 0 20px 0; color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }}
        .url-box {{
          background: #0b1120;
          padding: 10px 14px;
          border-radius: 6px;
          color: #cbd5e1;
          font-family: monospace;
          font-size: 0.85rem;
          word-break: break-all;
          margin-bottom: 16px;
          border: 1px solid #1e293b;
        }}
        #error-msg {{
          color: #ef4444;
          display: none;
          font-size: 0.9rem;
          margin-top: 15px;
        }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="spinner" id="spinner"></div>
        <h2>Bypassing & Archiving</h2>
        <p>Fetching article, bypassing paywall scripts & generating clean snapshot...</p>
        <div class="url-box">{url}</div>
        <div id="error-msg"></div>
      </div>
      <script>
        async function run() {{
          try {{
            const res = await fetch("/api/archive?url=" + encodeURIComponent({url_json}) + "{token_param}", {{
              method: "POST"
            }});
            const data = await res.json();
            if (res.ok && data.view_url) {{
              window.location.replace(data.view_url);
            }} else {{
              throw new Error(data.detail || "Failed to process article");
            }}
          }} catch (err) {{
            document.getElementById("spinner").style.display = "none";
            const errDiv = document.getElementById("error-msg");
            errDiv.style.display = "block";
            errDiv.textContent = "Error: " + err.message;
          }}
        }}
        run();
      </script>
    </body>
    </html>
    """

@app.post("/api/archive")
async def api_archive(request: Request, url: str = Query(None), token: str = Query(None)):
    verify_token(request, token)
    target_url = url
    if not target_url:
        try:
            body = await request.json()
            target_url = body.get("url")
        except Exception:
            pass

    if not target_url:
        raise HTTPException(status_code=400, detail="Missing target URL parameter")

    if target_url in recent_cache:
        return recent_cache[target_url]

    try:
        meta = await capture_page(target_url)
        return meta
    except Exception as e:
        logger.error(f"Failed to capture {target_url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Archiving failed: {str(e)}")

@app.get("/view/{snapshot_id}", response_class=HTMLResponse)
def view_snapshot(snapshot_id: str):
    safe_id = "".join(c for c in snapshot_id if c.isalnum() or c in ("_", "-"))
    file_path = STORAGE_DIR / f"{safe_id}.html"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found or expired (>90 days).")
    return FileResponse(file_path, media_type="text/html")

@app.get("/", response_class=HTMLResponse)
@app.get("/list", response_class=HTMLResponse)
def dashboard(token: str = Query(None)):
    files = sorted(STORAGE_DIR.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)[:30]
    token_str = token or API_TOKEN
    token_param = f"?token={token_str}" if token_str else ""
    
    rows = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        size_kb = round(f.stat().st_size / 1024, 1)
        name = f.stem
        rows.append(f"""
        <tr style="border-bottom: 1px solid #334155;">
          <td style="padding: 10px 12px;"><a href="/view/{name}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 500;">{name}</a></td>
          <td style="padding: 10px 12px; color: #94a3b8;">{mtime} UTC</td>
          <td style="padding: 10px 12px; color: #cbd5e1;">{size_kb} KB</td>
          <td style="padding: 10px 12px;"><a href="/view/{name}" target="_blank" style="color: #38bdf8; text-decoration: underline;">Open</a></td>
        </tr>
        """)
    
    table_content = "".join(rows) if rows else '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #94a3b8;">No snapshots yet.</td></tr>'

    return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>VPS Archive Lens - Dashboard</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        body {{ background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 30px 20px; display: flex; justify-content: center; }}
        .container {{ width: 100%; max-width: 860px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid #334155; padding-bottom: 16px; }}
        h1 {{ margin: 0; font-size: 1.5rem; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
        .badge {{ background: #0369a1; color: #e0f2fe; padding: 4px 10px; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }}
        .archive-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
        .form-row {{ display: flex; gap: 10px; }}
        input[type="text"] {{ flex: 1; padding: 10px 14px; background: #0b1120; border: 1px solid #334155; border-radius: 6px; color: #f8fafc; font-size: 0.95rem; outline: none; }}
        input:focus {{ border-color: #38bdf8; }}
        button {{ padding: 10px 20px; background: #38bdf8; color: #042f2e; border: none; border-radius: 6px; font-size: 0.95rem; font-weight: 600; cursor: pointer; }}
        button:hover {{ background: #0284c7; color: white; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; border: 1px solid #334155; font-size: 0.9rem; }}
        th {{ background: #0b1120; color: #94a3b8; text-align: left; padding: 12px; font-weight: 600; border-bottom: 1px solid #334155; }}
        .meta-info {{ font-size: 0.82rem; color: #94a3b8; margin-top: 14px; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>⚡ VPS Archive Lens Dashboard</h1>
          <span class="badge">{RETENTION_DAYS}-Day Retention Active</span>
        </div>

        <div class="archive-card">
          <div class="form-row">
            <input type="text" id="urlInput" placeholder="https://example.com/paywalled-article...">
            <button onclick="archiveUrl()">Archive & View</button>
          </div>
        </div>

        <h3 style="color: #cbd5e1; margin-bottom: 12px;">Recent Snapshots</h3>
        <table>
          <thead>
            <tr>
              <th>Snapshot ID</th>
              <th>Timestamp</th>
              <th>Size</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {table_content}
          </tbody>
        </table>

        <div class="meta-info">
          Snapshots are automatically deleted {RETENTION_DAYS} days after creation.
        </div>
      </div>

      <script>
        function archiveUrl() {{
          const url = document.getElementById('urlInput').value.trim();
          if (!url) return;
          window.location.href = '/archive?url=' + encodeURIComponent(url) + '{token_param}';
        }}
        document.getElementById('urlInput').addEventListener('keydown', (e) => {{
          if (e.key === 'Enter') archiveUrl();
        }});
      </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
