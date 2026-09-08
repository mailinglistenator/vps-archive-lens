#!/home/hermes/personal-archiver/venv/bin/python3
"""
archive-lens: Command-line tool and Hermes Agent skill backend for VPS Archive Lens.
Archives web pages, bypasses paywalls, generates AI Reader Views, and outputs formatted summaries.
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from bs4 import BeautifulSoup

ENV_FILE = Path("/home/hermes/personal-archiver/.env")

def load_env() -> dict:
    env = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'").strip('"')
    return env

def main():
    parser = argparse.ArgumentParser(description="Archive a web page and get an AI Reader View.")
    parser.add_argument("url", help="URL of the article or page to archive")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    env = load_env()
    api_token = env.get("API_TOKEN", "")
    base_url = env.get("BASE_URL", "http://localhost:8888").rstrip("/")
    local_api = "http://127.0.0.1:8888"

    target_url = args.url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # 1. Trigger Archive
    post_url = f"{local_api}/api/archive?url={urllib.parse.quote(target_url, safe='')}&token={api_token}"
    req = urllib.request.Request(post_url, data=b"", method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = f"HTTP {e.code}: {e.reason}"
        try:
            body = json.loads(e.read().decode("utf-8"))
            if "detail" in body:
                err_msg = body["detail"]
        except Exception:
            pass
        if args.json:
            print(json.dumps({"error": err_msg}))
        else:
            print(f"❌ **Archiving Failed:** {err_msg}")
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"❌ **Connection Error:** Could not connect to local archiver: {e}")
        sys.exit(1)

    snapshot_id = data.get("id", "")
    view_url = data.get("view_url") or f"{base_url}/view/{snapshot_id}"
    reader_url = data.get("reader_url") or f"{base_url}/reader/{snapshot_id}"

    # 2. Fetch and parse the AI Reader View
    local_reader_url = f"{local_api}/reader/{snapshot_id}"
    title = ""
    reading_time = ""
    author = ""
    domain = ""
    bullets = []

    try:
        req_r = urllib.request.Request(local_reader_url, headers={"User-Agent": "archive-lens-cli/1.0"})
        with urllib.request.urlopen(req_r, timeout=30) as r_resp:
            soup = BeautifulSoup(r_resp.read().decode("utf-8"), "html.parser")

            t_el = soup.select_one("h1.article-title") or soup.find("h1") or soup.find("title")
            if t_el:
                title = t_el.get_text(strip=True).replace("— Reader View", "").strip()

            rt_el = soup.select_one(".reading-time")
            if rt_el:
                reading_time = rt_el.get_text(strip=True)

            dom_el = soup.select_one(".source-domain")
            if dom_el:
                domain = dom_el.get_text(strip=True)
            else:
                try:
                    domain = urllib.parse.urlparse(target_url).netloc
                except Exception:
                    pass

            bullets = [li.get_text(strip=True) for li in soup.select(".takeaways-list li") if li.get_text(strip=True)]
    except Exception as e:
        pass

    if not title:
        title = target_url

    # 3. Output
    if args.json:
        out = {
            "id": snapshot_id,
            "title": title,
            "url": target_url,
            "domain": domain,
            "reading_time": reading_time,
            "bullets": bullets,
            "reader_url": reader_url,
            "view_url": view_url
        }
        print(json.dumps(out, indent=2))
        return

    # Telegram-friendly Markdown
    lines = [f"📰 **{title}**"]
    
    meta_sub = []
    if reading_time:
        meta_sub.append(reading_time)
    if domain:
        meta_sub.append(domain)
    if meta_sub:
        lines.append(" • ".join(meta_sub))
    
    lines.append("")

    if bullets:
        lines.append("💡 **Key Takeaways:**")
        for b in bullets:
            lines.append(f"• {b}")
        lines.append("")

    lines.append(f"📖 **AI Reader View:** {reader_url}")
    lines.append(f"📸 **Raw Snapshot:** {view_url}")

    print("\n".join(lines))

if __name__ == "__main__":
    main()
