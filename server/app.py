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
import trafilatura
import markdown
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("archiver")

PORT = int(os.getenv("PORT", "8888"))
API_TOKEN = os.getenv("API_TOKEN", "")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./snapshots"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8888").rstrip("/")

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

    # 5. Remove empty advertisement placeholders and broken billboard boxes (safe check)
    ad_selectors = [
        'div[class*="billboard-container"]', '.billboard-container',
        'div[class*="adHolder"]', 'div[class*="ad-holder"]', 'div[class*="ad_holder"]',
        'div[id*="billBoard"]', 'div[id*="billboard"]',
        '#sky-left-container', '#sky-right-container', '#sky-left', '#sky-right',
        '.mol-ads-label-container',
        'div[class*="advert"]', 'div[id*="advert"]',
        'ins.adsbygoogle', 'div[class*="ad-container"]', 'div[id*="ad-container"]',
        'div[class*="ad-slot"]', 'div[id*="ad-slot"]', 'div[class*="ad-wrapper"]',
        'div[id*="ad-wrapper"]', '.commercial-unit', '.ad-unit',
        '[class*="outbrain"]', '[class*="taboola"]'
    ]
    for sel in ad_selectors:
        for elem in soup.select(sel):
            if elem.name in ["html", "body", "head"]:
                continue
            elem.decompose()

    # Clean out molads_ ad classes from html and body so they don't break styles
    for root_tag in [soup.find("html"), soup.find("body")]:
        if root_tag:
            clean_classes = [c for c in root_tag.get("class", []) if not c.startswith("molads_")]
            if "allow-scroll" not in clean_classes:
                clean_classes.append("allow-scroll")
            root_tag["class"] = clean_classes

    # 6. Inject a sleek, modern floating glassmorphism pill banner at the top of <body>
    date_display = now.strftime('%Y-%m-%d %H:%M UTC')
    pill_html = f"""
    <div id="vps-lens-pill" style="
        position: fixed;
        top: 14px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 2147483647;
        background: rgba(15, 23, 42, 0.92);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        color: #f8fafc;
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 9999px;
        box-shadow: 0 10px 25px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.2);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 13px;
        padding: 7px 18px;
        display: flex;
        align-items: center;
        gap: 12px;
        user-select: none;
    ">
        <div style="display: flex; align-items: center; gap: 6px; font-weight: 600; color: #38bdf8;">
            <span>🔍</span>
            <span>Archive Lens</span>
        </div>
        <span style="color: #475569;">•</span>
        <span style="color: #cbd5e1; font-size: 12px;">{date_display}</span>
        <span style="color: #475569;">•</span>
        <a href="{resolved_url}" target="_blank" rel="noopener noreferrer" style="color: #38bdf8; text-decoration: none; font-size: 12px; font-weight: 500;">Original Source ↗</a>
        <span style="color: #475569;">•</span>
        <a href="/reader/{snapshot_id}" style="
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: #0284c7;
            color: #ffffff;
            padding: 3px 10px;
            border-radius: 9999px;
            text-decoration: none;
            font-size: 11.5px;
            font-weight: 600;
        ">📖 AI Reader View</a>
        <button onclick="document.getElementById('vps-lens-pill').style.display='none'" style="
            background: rgba(255,255,255,0.1);
            border: none;
            color: #94a3b8;
            border-radius: 9999px;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 11px;
            margin-left: 4px;
        " title="Dismiss">✕</button>
    </div>
    """
    pill_soup = BeautifulSoup(pill_html, "html.parser")
    if soup.body:
        soup.body.insert(0, pill_soup)
    else:
        soup.append(pill_soup)

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

def get_hermes_ai_provider():
    """
    Resolves available free/configured AI provider from Hermes configuration or environment.
    Priority:
    1. Nous Research Free Model (upstage/solar-pro4:free via portal token in ~/.hermes/auth.json)
    2. OpenCode Go / Zen (if key set in env or auth.json)
    3. NeuralWatt GLM-5.2 (from ~/.hermes/config.yaml or env)
    4. OpenRouter Free (if OPENROUTER_API_KEY set)
    """
    # 1. Nous Free
    auth_file = Path.home() / ".hermes/auth.json"
    if auth_file.is_file():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                nous = d.get("providers", {}).get("nous", {})
                token = nous.get("access_token") or nous.get("agent_key")
                if token:
                    return {
                        "provider": "nous",
                        "model": "upstage/solar-pro4:free",
                        "base_url": "https://inference-api.nousresearch.com/v1",
                        "auth_header": f"Bearer {token}",
                        "extra_headers": {"User-Agent": "HermesAgent/1.0"},
                        "display_name": "Nous Solar Pro (Free)"
                    }
        except Exception as e:
            logger.warning(f"Could not load Nous auth: {e}")

    # 2. OpenCode Go / Zen
    opencode_key = os.getenv("OPENCODE_GO_API_KEY") or os.getenv("OPENCODE_ZEN_API_KEY")
    if opencode_key:
        return {
            "provider": "opencode",
            "model": "glm-5",
            "base_url": os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"),
            "auth_header": f"Bearer {opencode_key}",
            "extra_headers": {
                "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                "X-Title": "Hermes Agent",
                "User-Agent": "HermesAgent/1.0"
            },
            "display_name": "OpenCode Go (GLM-5)"
        }

    # 3. NeuralWatt
    nw_key = os.getenv("NEURALWATT_API_KEY")
    nw_base = os.getenv("NEURALWATT_BASE_URL", "https://api.neuralwatt.com/v1")
    nw_model = os.getenv("NEURALWATT_MODEL", "glm-5.2")
    config_yaml = Path.home() / ".hermes/config.yaml"
    if not nw_key and config_yaml.is_file():
        try:
            with open(config_yaml, "r", encoding="utf-8") as f:
                content = f.read()
                m_key = re.search(r'neuralwatt:\s*(?:[^\n]+\n)*?\s*api_key:\s*([^\s\n]+)', content)
                if m_key:
                    nw_key = m_key.group(1).strip()
                m_base = re.search(r'neuralwatt:\s*(?:[^\n]+\n)*?\s*base_url:\s*([^\s\n]+)', content)
                if m_base:
                    nw_base = m_base.group(1).strip()
                m_model = re.search(r'neuralwatt:\s*(?:[^\n]+\n)*?\s*default_model:\s*([^\s\n]+)', content)
                if m_model:
                    nw_model = m_model.group(1).strip()
        except Exception as e:
            logger.warning(f"Failed to parse config.yaml: {e}")

    if nw_key:
        return {
            "provider": "neuralwatt",
            "model": nw_model,
            "base_url": nw_base,
            "auth_header": f"Bearer {nw_key}",
            "extra_headers": {},
            "display_name": f"NeuralWatt ({nw_model})"
        }

    # 4. OpenRouter
    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        return {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3.5-lightning:free",
            "base_url": "https://openrouter.ai/api/v1",
            "auth_header": f"Bearer {or_key}",
            "extra_headers": {},
            "display_name": "OpenRouter Free"
        }

    return None

def render_reader_template(
    snapshot_id: str,
    title: str,
    author: str,
    date: str,
    image: str,
    orig_url: str,
    domain: str,
    reading_time: int,
    provider_name: str,
    summary_bullets: list,
    body_html: str
) -> str:
    bullets_li = "".join([f"<li>{b}</li>" for b in summary_bullets]) if summary_bullets else ""
    takeaways_section = f"""
    <div class="takeaways-box">
      <div class="takeaways-header">
        <span class="takeaways-badge">⚡ AI Key Takeaways</span>
        <span class="takeaways-provider">{provider_name}</span>
      </div>
      <ul class="takeaways-list">
        {bullets_li}
      </ul>
    </div>
    """ if summary_bullets else ""

    hero_section = f"""
    <figure class="hero-figure">
      <img src="{image}" alt="{title}" class="hero-image" onerror="this.parentElement.style.display='none'">
    </figure>
    """ if image else ""

    byline_parts = []
    if author:
        byline_parts.append(f'<span class="author-name">By {author}</span>')
    if date:
        byline_parts.append(f'<span class="pub-date">{date}</span>')
    byline_parts.append(f'<span class="reading-time">⏱️ {reading_time} min read</span>')
    if domain:
        byline_parts.append(f'<span class="source-domain">{domain}</span>')
    
    meta_row = ' <span class="meta-sep">•</span> '.join(byline_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title} — Reader View</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      --bg: #0f172a;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --card-bg: #1e293b;
      --card-border: #334155;
      --accent: #38bdf8;
      --accent-dim: rgba(56, 189, 248, 0.15);
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-size: 18px;
      --line-height: 1.8;
      --nav-bg: rgba(15, 23, 42, 0.88);
      --nav-border: #334155;
    }}
    body.theme-oled {{
      --bg: #000000;
      --text: #e2e8f0;
      --text-muted: #888888;
      --card-bg: #111111;
      --card-border: #222222;
      --accent: #38bdf8;
      --accent-dim: rgba(56, 189, 248, 0.12);
      --nav-bg: rgba(0, 0, 0, 0.9);
      --nav-border: #222222;
    }}
    body.theme-sepia {{
      --bg: #f4ecd8;
      --text: #433422;
      --text-muted: #7d6b53;
      --card-bg: #eae0c8;
      --card-border: #dcd0b5;
      --accent: #b45309;
      --accent-dim: rgba(180, 83, 9, 0.12);
      --nav-bg: rgba(244, 236, 216, 0.92);
      --nav-border: #dcd0b5;
    }}
    body.theme-light {{
      --bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --card-bg: #f8fafc;
      --card-border: #e2e8f0;
      --accent: #0284c7;
      --accent-dim: rgba(2, 132, 199, 0.1);
      --nav-bg: rgba(255, 255, 255, 0.92);
      --nav-border: #e2e8f0;
    }}
    body.font-serif {{
      --font-family: "Charter", "Merriweather", "Georgia", serif;
    }}
    body.font-sans {{
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-family);
      font-size: var(--font-size);
      line-height: var(--line-height);
      margin: 0;
      padding: 0;
      transition: background-color 0.2s ease, color 0.2s ease;
    }}
    #progress-bar {{
      position: fixed;
      top: 0;
      left: 0;
      height: 3px;
      width: 0%;
      background: var(--accent);
      z-index: 2147483647;
      transition: width 0.1s ease-out;
    }}
    .navbar {{
      position: sticky;
      top: 0;
      z-index: 1000;
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--nav-border);
      padding: 10px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    .nav-left, .nav-right {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .nav-btn {{
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--card-border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .nav-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .theme-palette {{
      display: flex;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 2px;
      gap: 2px;
    }}
    .theme-opt {{
      background: transparent;
      border: none;
      padding: 4px 8px;
      cursor: pointer;
      border-radius: 4px;
      font-size: 13px;
    }}
    .theme-opt:hover, .theme-opt.active {{
      background: var(--accent-dim);
    }}
    .article-container {{
      max-width: 740px;
      margin: 0 auto;
      padding: 48px 24px 100px 24px;
    }}
    h1.article-title {{
      font-size: 2.25rem;
      line-height: 1.25;
      font-weight: 700;
      margin: 0 0 18px 0;
      color: var(--text);
      letter-spacing: -0.01em;
    }}
    .meta-row {{
      font-size: 0.88rem;
      color: var(--text-muted);
      margin-bottom: 30px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
    }}
    .meta-sep {{
      opacity: 0.5;
    }}
    .takeaways-box {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-left: 4px solid var(--accent);
      border-radius: 10px;
      padding: 20px 24px;
      margin-bottom: 36px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }}
    .takeaways-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }}
    .takeaways-badge {{
      font-weight: 700;
      font-size: 0.92rem;
      color: var(--accent);
      display: flex;
      align-items: center;
      gap: 6px;
      letter-spacing: 0.02em;
    }}
    .takeaways-provider {{
      font-size: 0.76rem;
      color: var(--text-muted);
      background: var(--accent-dim);
      padding: 2px 8px;
      border-radius: 9999px;
    }}
    .takeaways-list {{
      margin: 0;
      padding-left: 20px;
    }}
    .takeaways-list li {{
      margin-bottom: 8px;
      font-size: 0.95rem;
      line-height: 1.6;
    }}
    .hero-figure {{
      margin: 0 0 36px 0;
      width: 100%;
    }}
    .hero-image {{
      width: 100%;
      height: auto;
      border-radius: 10px;
      display: block;
      box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }}
    .article-body {{
      font-size: 1em;
    }}
    .article-body p {{
      margin: 0 0 1.6em 0;
    }}
    .article-body h2, .article-body h3, .article-body h4 {{
      color: var(--text);
      margin: 2em 0 0.8em 0;
      line-height: 1.3;
    }}
    .article-body h2 {{ font-size: 1.5rem; }}
    .article-body h3 {{ font-size: 1.25rem; }}
    .article-body blockquote {{
      border-left: 3px solid var(--accent);
      margin: 1.8em 0;
      padding: 8px 20px;
      font-style: italic;
      color: var(--text-muted);
      background: var(--card-bg);
      border-radius: 0 8px 8px 0;
    }}
    .article-body img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      display: block;
      margin: 2em auto;
      box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }}
    .article-body a {{
      color: var(--accent);
      text-decoration: underline;
      text-underline-offset: 3px;
    }}
    .article-footer {{
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    @media (max-width: 640px) {{
      .navbar {{ padding: 8px 12px; }}
      h1.article-title {{ font-size: 1.7rem; }}
      .article-container {{ padding: 24px 16px 60px 16px; }}
    }}
    @media print {{
      .navbar, #progress-bar, .takeaways-box {{ display: none !important; }}
      body {{ background: white !important; color: black !important; font-size: 12pt !important; }}
    }}
  </style>
</head>
<body class="theme-dark font-sans">
  <div id="progress-bar"></div>

  <nav class="navbar">
    <div class="nav-left">
      <a href="/view/{snapshot_id}" class="nav-btn">← Full Snapshot</a>
      <a href="{orig_url}" target="_blank" rel="noopener noreferrer" class="nav-btn">Original ↗</a>
    </div>

    <div class="nav-right">
      <button class="nav-btn" onclick="toggleFont()" title="Switch Serif/Sans" id="fontToggleBtn">Aa Serif</button>
      <button class="nav-btn" onclick="adjustFontSize(-1)" title="Smaller text">A-</button>
      <button class="nav-btn" onclick="adjustFontSize(1)" title="Larger text">A+</button>
      
      <div class="theme-palette">
        <button class="theme-opt active" onclick="setTheme('theme-dark')" title="Dark">🌙</button>
        <button class="theme-opt" onclick="setTheme('theme-oled')" title="OLED Black">🖤</button>
        <button class="theme-opt" onclick="setTheme('theme-sepia')" title="Sepia">📜</button>
        <button class="theme-opt" onclick="setTheme('theme-light')" title="Light">☀️</button>
      </div>

      <button class="nav-btn" onclick="window.print()" title="Print / Save PDF">🖨️</button>
    </div>
  </nav>

  <main class="article-container">
    <header>
      <h1 class="article-title">{title}</h1>
      <div class="meta-row">
        {meta_row}
      </div>
    </header>

    {takeaways_section}

    {hero_section}

    <article class="article-body">
      {body_html}
    </article>

    <footer class="article-footer">
      <span>Archived & Reconstructed with <strong>VPS Archive Lens</strong></span>
      <a href="/view/{snapshot_id}" style="color: var(--accent); text-decoration: none;">View Original Snapshot →</a>
    </footer>
  </main>

  <script>
    window.addEventListener('scroll', () => {{
      const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = totalHeight > 0 ? (window.scrollY / totalHeight) * 100 : 0;
      document.getElementById('progress-bar').style.width = Math.min(100, Math.max(0, progress)) + '%';
    }});

    function setTheme(theme) {{
      document.body.classList.remove('theme-dark', 'theme-oled', 'theme-sepia', 'theme-light');
      document.body.classList.add(theme);
      localStorage.setItem('vps_reader_theme', theme);
      document.querySelectorAll('.theme-opt').forEach(btn => {{
        btn.classList.toggle('active', btn.getAttribute('onclick').includes(theme));
      }});
    }}

    function toggleFont() {{
      const isSerif = document.body.classList.toggle('font-serif');
      document.body.classList.toggle('font-sans', !isSerif);
      const btn = document.getElementById('fontToggleBtn');
      btn.textContent = isSerif ? 'Aa Sans' : 'Aa Serif';
      localStorage.setItem('vps_reader_font', isSerif ? 'serif' : 'sans');
    }}

    let currentFontSize = 18;
    function adjustFontSize(delta) {{
      currentFontSize = Math.min(26, Math.max(14, currentFontSize + (delta * 2)));
      document.documentElement.style.setProperty('--font-size', currentFontSize + 'px');
      localStorage.setItem('vps_reader_size', currentFontSize);
    }}

    (function initPreferences() {{
      const savedTheme = localStorage.getItem('vps_reader_theme');
      if (savedTheme) setTheme(savedTheme);

      const savedFont = localStorage.getItem('vps_reader_font');
      if (savedFont === 'serif') {{
        document.body.classList.add('font-serif');
        document.body.classList.remove('font-sans');
        document.getElementById('fontToggleBtn').textContent = 'Aa Sans';
      }}

      const savedSize = localStorage.getItem('vps_reader_size');
      if (savedSize) {{
        currentFontSize = parseInt(savedSize, 10);
        document.documentElement.style.setProperty('--font-size', currentFontSize + 'px');
      }}
    }})();
  </script>
</body>
</html>
"""

def generate_ai_reader(snapshot_id: str, force_refresh: bool = False) -> Path:
    safe_id = "".join(c for c in snapshot_id if c.isalnum() or c in ("_", "-"))
    raw_path = STORAGE_DIR / f"{safe_id}.html"
    reader_path = STORAGE_DIR / f"{safe_id}_reader.html"

    if not raw_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    if reader_path.is_file() and not force_refresh:
        return reader_path

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_html = f.read()

    soup = BeautifulSoup(raw_html, "html.parser")

    # 1. Metadata extraction
    meta = trafilatura.extract_metadata(raw_html)
    title = (meta.title if meta and meta.title else soup.find("title").text if soup.find("title") else "Archived Article").strip()
    author = (meta.author if meta and meta.author else "").strip()
    date = (meta.date if meta and meta.date else "").strip()
    image = (meta.image if meta and meta.image else "").strip()

    if not image:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image = og_img["content"]

    base_elem = soup.find("base")
    orig_url = base_elem.get("href", "#") if base_elem else "#"
    domain = ""
    try:
        domain = urlparse(orig_url).netloc
    except Exception:
        pass

    # 2. Article markdown extraction
    extracted_md = trafilatura.extract(raw_html, include_images=True, include_links=True, output_format="markdown") or ""

    if len(extracted_md.strip()) < 150:
        article_elem = soup.find("article") or soup.find(itemprop="articleBody") or soup.find("main") or soup.body
        if article_elem:
            ps = [p.get_text(strip=True) for p in article_elem.find_all("p") if len(p.get_text(strip=True)) > 40]
            extracted_md = "\n\n".join(ps)

    # Clean promotional and boilerplate lines
    cleaned_lines = []
    for line in extracted_md.split("\n"):
        low = line.lower().strip()
        if any(noise in low for noise in [
            "save us as a preferred source",
            "download our app",
            "follow us on",
            "sign up for our newsletter",
            "click here to subscribe",
            "advertisement"
        ]):
            continue
        if low.startswith("# ") and title.lower() in low:
            continue
        cleaned_lines.append(line)
    clean_md = "\n".join(cleaned_lines).strip()

    word_count = len(clean_md.split())
    reading_time = max(1, round(word_count / 220))

    # 3. AI Key Takeaways
    ai_provider = get_hermes_ai_provider()
    summary_bullets = []
    provider_name = "Heuristic Extractor"

    if ai_provider:
        provider_name = ai_provider["display_name"]
        prompt = f"""You are an expert news editor. Given this article, summarize the 3 most important key takeaways into concise, high-impact bullet points.
Return strictly valid JSON in this format:
{{"summary": ["Key takeaway 1", "Key takeaway 2", "Key takeaway 3"]}}

Article:
{clean_md[:4500]}
"""
        try:
            req_data = json.dumps({
                "model": ai_provider["model"],
                "messages": [
                    {"role": "system", "content": "You are an editorial assistant. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }).encode()

            headers = {
                "Authorization": ai_provider["auth_header"],
                "Content-Type": "application/json",
                **ai_provider.get("extra_headers", {})
            }
            req = urllib.request.Request(f"{ai_provider['base_url']}/chat/completions", data=req_data, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                content_str = data["choices"][0]["message"]["content"]
                content_str = re.sub(r"^```json\s*", "", content_str.strip())
                content_str = re.sub(r"\s*```$", "", content_str.strip())
                parsed = json.loads(content_str)
                summary_bullets = parsed.get("summary", [])
        except Exception as e:
            logger.warning(f"AI summary request failed ({provider_name}): {e}")

    # Fallback bullets if AI unavailable
    if not summary_bullets:
        summary_bullets = [
            line.strip() for line in clean_md.split("\n\n")
            if len(line.strip()) > 60 and not any(line.strip().startswith(c) for c in (">", "[", "!", "#", "*", "-"))
        ][:3]

    # Convert clean markdown to HTML body
    body_html = markdown.markdown(clean_md, extensions=["extra", "nl2br", "sane_lists"])

    reader_html = render_reader_template(
        snapshot_id=safe_id,
        title=title,
        author=author,
        date=date,
        image=image,
        orig_url=orig_url,
        domain=domain,
        reading_time=reading_time,
        provider_name=provider_name,
        summary_bullets=summary_bullets,
        body_html=body_html
    )

    with open(reader_path, "w", encoding="utf-8") as f:
        f.write(reader_html)

    logger.info(f"AI Reader view created: {reader_path}")
    return reader_path

@app.get("/reader/{snapshot_id}", response_class=HTMLResponse)
def reader_view(snapshot_id: str, refresh: str = Query(None)):
    """Serves a clean, AI-reconstructed reader view."""
    force_refresh = (refresh == "1" or refresh == "true")
    reader_file = generate_ai_reader(snapshot_id, force_refresh=force_refresh)
    return FileResponse(reader_file, media_type="text/html")

@app.get("/", response_class=HTMLResponse)
@app.get("/list", response_class=HTMLResponse)
def dashboard(token: str = Query(None)):
    files = sorted([f for f in STORAGE_DIR.glob("*.html") if not f.stem.endswith("_reader")], key=lambda f: f.stat().st_mtime, reverse=True)[:40]
    token_str = token or API_TOKEN
    token_param = f"?token={token_str}" if token_str else ""
    
    rows = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        size_kb = round(f.stat().st_size / 1024, 1)
        name = f.stem
        rows.append(f"""
        <tr style="border-bottom: 1px solid #334155;">
          <td style="padding: 10px 12px;"><a href="/reader/{name}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 500;">{name}</a></td>
          <td style="padding: 10px 12px; color: #94a3b8;">{mtime} UTC</td>
          <td style="padding: 10px 12px; color: #cbd5e1;">{size_kb} KB</td>
          <td style="padding: 10px 12px; display: flex; gap: 8px;">
            <a href="/reader/{name}" target="_blank" style="background: #0284c7; color: #ffffff; padding: 4px 10px; border-radius: 6px; text-decoration: none; font-size: 0.8rem; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">📖 Reader</a>
            <a href="/view/{name}" target="_blank" style="color: #94a3b8; text-decoration: underline; font-size: 0.85rem; display: inline-flex; align-items: center; padding: 4px;">Raw</a>
          </td>
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
