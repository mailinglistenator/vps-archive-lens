import os
import time
import json
import hashlib
import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("archiver")

PORT = int(os.getenv("PORT", "8888"))
API_TOKEN = os.getenv("API_TOKEN", "")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/home/hermes/personal-archiver/snapshots"))
BASE_URL = os.getenv("BASE_URL", "http://204.168.160.204:8888").rstrip("/")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Personal Web Archiver", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Known paywall/tracker domains to block at the network level
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
    auth_header = req.headers.get("Authorization")
    provided_token = None
    if auth_header and auth_header.startswith("Bearer "):
        provided_token = auth_header.split(" ", 1)[1].strip()
    elif token:
        provided_token = token.strip()
    
    if API_TOKEN and provided_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API token")
    return True

# Cache recent captures in memory for 10 minutes to avoid duplicate work
recent_cache = {}

# User-Agent profiles: Googlebot gets First-Click-Free/SEO unpaywall access and bypasses CDN datacenter blocks
UA_PROFILES = [
    {
        "name": "Googlebot (SEO / Paywall Bypass)",
        "ua": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "headers": {"Accept-Language": "en-US,en;q=0.9"}
    },
    {
        "name": "Desktop Chrome Stealth",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "DNT": "1"
        }
    }
]

def is_blocked_response(status_code: int, html: str) -> bool:
    if status_code in (401, 403, 429, 451, 503):
        return True
    lowered = html.lower()
    block_signatures = [
        "access denied",
        "errors.edgesuite.net",
        "checking your browser before accessing",
        "please enable cookies",
        "cloudflare ray id",
        "you don't have permission to access",
        "attention required! | cloudflare"
    ]
    return any(sig in lowered for sig in block_signatures)

async def capture_page(target_url: str) -> dict:
    url_hash = hashlib.sha256(target_url.encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d_%H%M%S")
    snapshot_id = f"{date_str}_{url_hash}"
    filepath = STORAGE_DIR / f"{snapshot_id}.html"

    logger.info(f"Starting capture for: {target_url} -> ID: {snapshot_id}")

    raw_html = ""
    resolved_url = target_url

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

        for profile in UA_PROFILES:
            logger.info(f"Attempting fetch with profile: {profile['name']}")
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=profile["ua"],
                extra_http_headers=profile.get("headers", {})
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
                resp = await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                status_code = resp.status if resp else 200

                # Scroll down to trigger lazy loading of images
                await page.evaluate("""async () => {
                    window.scrollBy(0, window.innerHeight * 1.5);
                    await new Promise(r => setTimeout(r, 600));
                    window.scrollTo(0, 0);
                }""")
                await asyncio.sleep(1.0)

                html_candidate = await page.content()
                resolved_url = page.url or target_url

                if not is_blocked_response(status_code, html_candidate):
                    logger.info(f"Success with {profile['name']} for {resolved_url}")
                    raw_html = html_candidate
                    await context.close()
                    break
                else:
                    logger.warning(f"Profile {profile['name']} was blocked or returned status {status_code}. Retrying with next profile...")
            except Exception as e:
                logger.warning(f"Fetch failed with {profile['name']}: {e}")
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

        await browser.close()

    if not raw_html:
        raise HTTPException(status_code=502, detail="Failed to fetch page: All bypass profiles were blocked by the destination server.")

    # Process and sanitize HTML with BeautifulSoup
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1. Strip all <script> and <noscript> tags to permanently neutralize client-side paywalls and tracking
    for s in soup.find_all(["script", "noscript"]):
        s.decompose()

    # 2. Inject <base> tag using the RESOLVED destination URL (not the redirect shortener)
    head = soup.head
    if not head:
        head = soup.new_tag("head")
        soup.insert(0, head)

    base_tag = soup.new_tag("base", href=resolved_url)
    head.insert(0, base_tag)

    # 3. Force scrollability on HTML and BODY tags
    html_tag = soup.find("html")
    if html_tag:
        classes = html_tag.get("class", [])
        if "allow-scroll" not in classes:
            classes.append("allow-scroll")
        html_tag["class"] = classes

    body_tag = soup.find("body")
    if body_tag:
        classes = body_tag.get("class", [])
        if "allow-scroll" not in classes:
            classes.append("allow-scroll")
        body_tag["class"] = classes

    # Inject forced scroll CSS into <head>
    scroll_style = soup.new_tag("style", id="vps-force-scroll")
    scroll_style.string = """
    html, body {
      overflow: auto !important;
      overflow-y: auto !important;
      overflow-x: hidden !important;
      position: static !important;
      height: auto !important;
      max-height: none !important;
      touch-action: auto !important;
    }
    .scrollable-content {
      overflow: visible !important;
    }
    [class*="overlay_"], [class*="fullHeight_"], [data-project*="cmp"], [class*="modal-backdrop"] {
      display: none !important;
    }
    """
    head.append(scroll_style)

    # Strip inline scroll locks and modal backdrops
    for tag in soup.find_all(True):
        style = tag.get("style", "")
        if "overflow" in style or "position: fixed" in style or "pointer-events" in style:
            new_style = re.sub(r"overflow(-[xy])?\s*:\s*hidden\s*(!important)?\s*;?", "", style, flags=re.IGNORECASE)
            new_style = re.sub(r"pointer-events\s*:\s*none\s*(!important)?\s*;?", "", new_style, flags=re.IGNORECASE)
            tag["style"] = new_style

    # 4. Remove common paywalls, cookie walls, and GDPR CMP annoyances
    annoyance_selectors = [
        # Paywalls
        '[id*="paywall"]', '[class*="paywall"]',
        '[class*="tp-modal"]', '[class*="tp-backdrop"]',
        '[class*="subscriber-gate"]', '[id*="gateway-content"]',
        '[class*="piano-overlay"]', '#reg-wall',

        # GDPR / CMP / Cookie walls (OneTrust, Didomi, SourcePoint, Quantcast, DailyMail mol-fe-cmp, etc.)
        '[data-project*="cmp"]', '[id*="cmp-"]', '[class*="cmp-"]',
        '#onetrust-consent-sdk', '#onetrust-banner-sdk', '.onetrust-pc-dark-filter',
        '[id*="sp_message_container"]', '[class*="sp_message_container"]',
        '[id*="didomi-host"]', '.didomi-popup-container', '#didomi-notice',
        '.qc-cmp2-container', '#qc-cmp2-container',
        '[id*="usercentrics-root"]',
        '.fc-dialog-container', '.fc-consent-root',
        '[class*="cookie-wall"]', '[id*="cookie-wall"]',
        '[class*="cookie-banner"]', '[id*="cookie-banner"]',
        '[class*="cookie-consent"]', '[id*="cookie-consent"]',
        '[class*="consent-overlay"]', '[class*="consent-modal"]',
        '[id*="privacy-wall"]', '[class*="privacy-wall"]',
        'iframe[src*="setABframe"]', 'iframe[name="__tcfapiLocator"]'
    ]
    for sel in annoyance_selectors:
        for elem in soup.select(sel):
            elem.decompose()

    # Dynamic scan for any fixed/fullscreen overlays that block reading
    for elem in soup.find_all(["div", "section", "aside", "dialog"]):
        style = elem.get("style", "").lower()
        if "position: fixed" in style or "position: absolute" in style:
            text = elem.get_text(separator=" ", strip=True).lower()
            annoyance_phrases = [
                "choose how to use",
                "purchase a daily mail essential",
                "reject and purchase",
                "view with personalised ads",
                "accept all cookies",
                "agree and continue",
                "disable your ad blocker to view",
                "we value your privacy",
                "before you continue to",
                "our privacy settings can also be accessed"
            ]
            if any(phrase in text for phrase in annoyance_phrases):
                elem.decompose()

    # 5. Inject a clean, non-intrusive metadata banner at the top of <body>
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
        ">✕ Close Banner</button>
    </div>
    """
    banner_soup = BeautifulSoup(banner_html, "html.parser")
    if soup.body:
        soup.body.insert(0, banner_soup)
    else:
        soup.append(banner_soup)

    # Save to disk
    final_html = str(soup)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_html)

    logger.info(f"Snapshot successfully saved: {filepath} ({len(final_html)} bytes)")

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
        "storage_dir": str(STORAGE_DIR),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/archive", response_class=HTMLResponse)
async def archive_web_view(request: Request, url: str = Query(...), token: str = Query(None)):
    """Browser entrypoint: Shows instant responsive loading page while unpaywalling."""
    verify_token(request, token)
    
    # Check if we already have this URL cached recently (within 5 mins)
    if url in recent_cache:
        return RedirectResponse(recent_cache[url]["view_url"])

    token_param = f"&token={token}" if token else ""
    url_json = json.dumps(url)
    
    # Render instant loading page with auto-fetch
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
    """API endpoint to trigger an archive job."""
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
          <span class="badge">90-Day Retention Active</span>
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
          Snapshots are automatically deleted 90 days after creation.
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
