import asyncio
import json
import re
import sys
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}

# The 30 target sites to audit
SITES_TO_AUDIT = [
    # Group 1: Aggregators, Developer Feeds & Modern Discourse
    {"id": 31, "name": "Hacker News", "domain": "news.ycombinator.com", "root": "https://news.ycombinator.com/", "type": "aggregator"},
    {"id": 32, "name": "Flipboard", "domain": "flipboard.com", "root": "https://flipboard.com/", "type": "aggregator"},
    {"id": 33, "name": "Pocket", "domain": "getpocket.com", "root": "https://getpocket.com/explore", "type": "aggregator"},
    {"id": 34, "name": "Apple News Web", "domain": "apple.news", "root": "https://apple.news/", "type": "aggregator"},
    {"id": 35, "name": "Dev.to", "domain": "dev.to", "root": "https://dev.to/", "type": "developer"},
    {"id": 36, "name": "Bluesky", "domain": "bsky.app", "root": "https://bsky.app/", "type": "social_discourse"},
    {"id": 37, "name": "Ghost CMS", "domain": "ghost.org", "root": "https://ghost.org/blog/", "type": "cms_network"},
    {"id": 38, "name": "WordPress Core REST", "domain": "wordpress.org", "root": "https://wordpress.org/news/", "type": "cms_network"},

    # Group 2: Extended East Asian Outlets (Korea & Japan)
    {"id": 39, "name": "Maeil Business (MK)", "domain": "mk.co.kr", "root": "https://www.mk.co.kr/", "type": "korean_news"},
    {"id": 40, "name": "Korea Economic Daily", "domain": "hankyung.com", "root": "https://www.hankyung.com/", "type": "korean_news"},
    {"id": 41, "name": "Hankyoreh", "domain": "hani.co.kr", "root": "https://www.hani.co.kr/", "type": "korean_news"},
    {"id": 42, "name": "Kyunghyang Shinmun", "domain": "khan.co.kr", "root": "https://www.khan.co.kr/", "type": "korean_news"},
    {"id": 43, "name": "Segye Ilbo", "domain": "segye.com", "root": "https://www.segye.com/", "type": "korean_news"},
    {"id": 44, "name": "News1", "domain": "news1.kr", "root": "https://www.news1.kr/", "type": "korean_news"},
    {"id": 45, "name": "Newsis", "domain": "newsis.com", "root": "https://www.newsis.com/", "type": "korean_news"},
    {"id": 46, "name": "Yahoo! Japan", "domain": "news.yahoo.co.jp", "root": "https://news.yahoo.co.jp/", "type": "japanese_news"},
    {"id": 47, "name": "Nikkei / Nikkei Asia", "domain": "asia.nikkei.com", "root": "https://asia.nikkei.com/", "type": "japanese_news"},
    {"id": 48, "name": "Asahi Shimbun", "domain": "asahi.com", "root": "https://www.asahi.com/", "type": "japanese_news"},

    # Group 3: Global Tech, Science & In-Depth Journalism
    {"id": 49, "name": "Ars Technica", "domain": "arstechnica.com", "root": "https://arstechnica.com/", "type": "tech_media"},
    {"id": 50, "name": "Wired", "domain": "wired.com", "root": "https://www.wired.com/", "type": "tech_media"},
    {"id": 51, "name": "TechCrunch", "domain": "techcrunch.com", "root": "https://techcrunch.com/", "type": "tech_media"},
    {"id": 52, "name": "The Atlantic", "domain": "theatlantic.com", "root": "https://www.theatlantic.com/", "type": "journalism"},
    {"id": 53, "name": "Politico", "domain": "politico.com", "root": "https://www.politico.com/", "type": "journalism"},
    {"id": 54, "name": "Forbes", "domain": "forbes.com", "root": "https://www.forbes.com/", "type": "business_media"},
    {"id": 55, "name": "The Economist", "domain": "economist.com", "root": "https://www.economist.com/", "type": "business_media"},
    {"id": 56, "name": "ProPublica", "domain": "propublica.org", "root": "https://www.propublica.org/", "type": "investigative"},
    {"id": 57, "name": "Los Angeles Times", "domain": "latimes.com", "root": "https://www.latimes.com/", "type": "journalism"},
    {"id": 58, "name": "Al Jazeera English", "domain": "aljazeera.com", "root": "https://www.aljazeera.com/", "type": "global_broadcaster"},
    {"id": 59, "name": "Deutsche Welle (DW)", "domain": "dw.com", "root": "https://www.dw.com/en/top-stories/s-9097", "type": "global_broadcaster"},
    {"id": 60, "name": "NPR", "domain": "npr.org", "root": "https://www.npr.org/", "type": "public_media"},
]

def find_article_link(soup, base_url, domain):
    """Heuristic link finder to discover an active article URL from a homepage or section."""
    patterns = {
        "news.ycombinator.com": r"item\?id=\d+",
        "mk.co.kr": r"/news/[a-z]+/\d+",
        "hankyung.com": r"/article/\d+",
        "hani.co.kr": r"/arti/[a-z]+/[a-z]+/\d+\.html",
        "khan.co.kr": r"/article/\d+",
        "segye.com": r"/newsView/\d+",
        "news1.kr": r"/articles/\?id=\d+|/articles/\d+",
        "newsis.com": r"/view/\?id=[A-Z0-9]+",
        "news.yahoo.co.jp": r"/articles/[a-f0-9]+",
        "asia.nikkei.com": r"/(?:Economy|Business|Politics|Spotlight)/[a-zA-Z0-9_\-]+",
        "asahi.com": r"/articles/[A-Z0-9]+\.html",
        "arstechnica.com": r"/\d{4}/\d{2}/[a-z0-9\-]+/",
        "wired.com": r"/story/[a-z0-9\-]+",
        "techcrunch.com": r"/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+",
        "theatlantic.com": r"/(?:magazine|ideas|politics|technology|culture)/archive/\d{4}/\d{2}/",
        "politico.com": r"/news/\d{4}/\d{2}/\d{2}/",
        "forbes.com": r"/sites/[a-zA-Z0-9_\-]+/\d{4}/\d{2}/\d{2}/",
        "economist.com": r"/(?:leaders|briefing|united-states|the-americas|asia|china|middle-east-and-africa|international|business|finance-and-economics|science-and-technology|culture)/\d{4}/\d{2}/\d{2}/",
        "propublica.org": r"/article/[a-z0-9\-]+",
        "latimes.com": r"/story/\d{4}-\d{2}-\d{2}/[a-z0-9\-]+",
        "aljazeera.com": r"/news/\d{4}/\d{1,2}/\d{1,2}/",
        "dw.com": r"/en/[a-z0-9\-]+/a-\d+",
        "npr.org": r"/\d{4}/\d{2}/\d{2}/\d+/",
        "ghost.org": r"/blog/[a-z0-9\-]+/",
        "dev.to": r"/[a-zA-Z0-9_\-]+/[a-z0-9\-]+",
    }
    
    pat = patterns.get(domain)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        if pat and re.search(pat, full, re.IGNORECASE):
            return full

    # Generic fallback: look for links with date structures or slug patterns
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        if domain in urlparse(full).netloc:
            if re.search(r"/\d{4}/\d{2}/|/article/|/news/|/story/", full):
                return full
    return None

def audit_site(site_meta, client):
    """Audit an individual website."""
    s_id = site_meta["id"]
    name = site_meta["name"]
    domain = site_meta["domain"]
    root = site_meta["root"]

    res = {
        "id": s_id,
        "name": name,
        "domain": domain,
        "type": site_meta["type"],
        "accessible": False,
        "status_code": None,
        "direct_api_available": False,
        "direct_api_notes": None,
        "article_url_sampled": None,
        "json_ld": {
            "found": False,
            "types": [],
            "has_headline": False,
            "has_date": False,
            "has_author": False,
            "has_article_body": False,
        },
        "dom_selectors": {
            "title_selector": None,
            "body_selector": None,
            "author_selector": None,
            "date_selector": None,
        },
        "image_handling": {
            "lazy_attrs": [],
            "cdn_host": None,
            "unresizing_rule": None,
        },
        "notice_dialogs": {
            "consent_banner": None,
            "paywall_modal": None,
        },
        "rendering_model": "SSR", # Default SSR, updated if SPA detected
        "wait_for_selector": None,
        "notes": [],
    }

    print(f"[{s_id}/60] Auditing {name} ({domain})...")

    # 1. Check direct APIs if applicable
    if domain == "news.ycombinator.com":
        try:
            api_resp = client.get("https://hacker-news.firebaseio.com/v0/topstories.json?limitToFirst=1&orderBy=\"$key\"")
            if api_resp.status_code == 200:
                res["direct_api_available"] = True
                res["direct_api_notes"] = "Firebase REST API at https://hacker-news.firebaseio.com/v0/item/{id}.json"
        except Exception:
            pass

    if domain == "dev.to":
        try:
            api_resp = client.get("https://dev.to/api/articles?per_page=1")
            if api_resp.status_code == 200:
                res["direct_api_available"] = True
                res["direct_api_notes"] = "Public REST API at https://dev.to/api/articles/{id} with full body_html"
        except Exception:
            pass

    if domain == "techcrunch.com":
        try:
            api_resp = client.get("https://techcrunch.com/wp-json/wp/v2/posts?per_page=1")
            if api_resp.status_code == 200:
                res["direct_api_available"] = True
                res["direct_api_notes"] = "WordPress VIP REST API at /wp-json/wp/v2/posts?slug={slug} returns content.rendered"
        except Exception:
            pass

    if domain == "ghost.org":
        try:
            api_resp = client.get("https://ghost.org/blog/rss/")
            if api_resp.status_code == 200:
                res["direct_api_available"] = True
                res["direct_api_notes"] = "RSS and Ghost Content API (/ghost/api/v4/content/posts/)"
        except Exception:
            pass

    # 2. Fetch root page to find live article
    try:
        r = client.get(root)
        res["status_code"] = r.status_code
        if r.status_code in [200, 301, 302, 304]:
            res["accessible"] = True
        else:
            res["notes"].append(f"Root returned HTTP status {r.status_code}")
            return res
    except Exception as e:
        res["notes"].append(f"Root fetch error: {e}")
        return res

    soup = BeautifulSoup(r.text, "html.parser")
    art_url = find_article_link(soup, root, domain)

    if not art_url and domain == "news.ycombinator.com":
        art_url = "https://news.ycombinator.com/item?id=41490000"

    if not art_url:
        # Fallback to known structure or root if specific
        res["notes"].append("Could not auto-discover article link from root page")
        art_url = root

    res["article_url_sampled"] = art_url

    # 3. Fetch article page
    try:
        art_resp = client.get(art_url)
        art_html = art_resp.text
        asoup = BeautifulSoup(art_html, "html.parser")
    except Exception as e:
        res["notes"].append(f"Article fetch error ({art_url}): {e}")
        return res

    # 4. Analyze JSON-LD
    for script in asoup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string.strip(), strict=False)
            items = data if isinstance(data, list) else [data]
            for it in items:
                if isinstance(it, dict):
                    t = it.get("@type")
                    if t:
                        if isinstance(t, list):
                            res["json_ld"]["types"].extend(t)
                        else:
                            res["json_ld"]["types"].append(t)
                        res["json_ld"]["found"] = True
                    if it.get("headline"):
                        res["json_ld"]["has_headline"] = True
                    if it.get("datePublished") or it.get("dateCreated"):
                        res["json_ld"]["has_date"] = True
                    if it.get("author"):
                        res["json_ld"]["has_author"] = True
                    if it.get("articleBody") and len(str(it["articleBody"])) > 100:
                        res["json_ld"]["has_article_body"] = True
        except Exception:
            pass

    # 5. Analyze DOM Selectors
    # Title
    for t_sel in ["h1[class*='headline']", "h1[class*='title']", "article h1", "h1", "h2.news_ttl", "h2.top_title"]:
        matched = asoup.select(t_sel)
        if matched and len(matched[0].get_text(strip=True)) > 5:
            # Check if it's not the site logo
            txt = matched[0].get_text(strip=True)
            if not any(logo in txt.lower() for logo in ["yahoo!ニュース", "home", "the economist", "hankyung", "asahi shimbun"]):
                res["dom_selectors"]["title_selector"] = t_sel
                break

    # Body
    for b_sel in [
        "div[data-testid='ArticleBody']",
        "div[data-testid='BodyWrapper']",
        "div[data-component='article-body']",
        "section[data-component='ArticleBody']",
        "div.news_cnt_detail_wrap",
        "div.art_txt",
        "#articletxt",
        "div.article-body",
        "div.article_body",
        "div.article-text",
        "div.art_body",
        "div#articles_detail",
        "article#articleBody",
        "#uamods-article",
        "div.c-article_body",
        "div.ArticleBody",
        "div.article-content",
        "div.entry-content",
        "div.story-text",
        "div.article-body-container",
        "div.wysiwyg--all-content",
        "div.rich-text",
        "div#storytext",
        "article",
        "main",
    ]:
        matched = asoup.select(b_sel)
        if matched:
            txt_len = len(matched[0].get_text(strip=True))
            if txt_len > 250:
                res["dom_selectors"]["body_selector"] = b_sel
                res["wait_for_selector"] = b_sel
                break

    # Author
    for a_sel in ["[class*='author']", "[class*='byline']", "[itemprop='author']", "[rel='author']", ".reporter"]:
        matched = asoup.select(a_sel)
        if matched and matched[0].get_text(strip=True):
            res["dom_selectors"]["author_selector"] = a_sel
            break

    # Date
    for d_sel in ["time[datetime]", "[class*='date']", "[class*='time']", "span.num_date", "span.firstDate"]:
        matched = asoup.select(d_sel)
        if matched and matched[0].get_text(strip=True):
            res["dom_selectors"]["date_selector"] = d_sel
            break

    # 6. Analyze Image attributes & CDN
    img_nodes = asoup.find_all("img")
    for img in img_nodes[:10]:
        for attr in ["data-src", "data-original", "data-org-src", "data-srcset", "srcset"]:
            if img.get(attr) and attr not in res["image_handling"]["lazy_attrs"]:
                res["image_handling"]["lazy_attrs"].append(attr)
        src = img.get("src", "")
        if src.startswith("http"):
            c_host = urlparse(src).netloc
            if not res["image_handling"]["cdn_host"] and ("img" in c_host or "cdn" in c_host or "media" in c_host):
                res["image_handling"]["cdn_host"] = c_host

    # Specific unresizing patterns
    if "news.yahoo.co.jp" in domain:
        res["image_handling"]["unresizing_rule"] = "Strip resizing dimensions from yimg.jp"
    elif "hankyung.com" in domain or "tenasia" in domain:
        res["image_handling"]["unresizing_rule"] = "Direct image CDN at img.hankyung.com"

    # 7. Analyze Consent / Overlay Dialogs
    for c_id in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button", "#sp_message_container", ".cookie-banner", "button[name='agree']", ".btn_close"]:
        if c_id.startswith("#"):
            if asoup.find(id=c_id[1:]):
                res["notice_dialogs"]["consent_banner"] = c_id
        elif c_id.startswith("."):
            if asoup.find(class_=c_id[1:]):
                res["notice_dialogs"]["consent_banner"] = c_id

    # 8. Rendering Model Detection
    if any(spa_sig in art_html.lower() for spa_sig in ["__next_data__", "window.__initial_state__", "<shreddit-", "gatsby-hydrate"]):
        res["rendering_model"] = "SSR + Client Hydration (Next.js / SPA)"
        if not res["wait_for_selector"]:
            res["wait_for_selector"] = "article, main"
    else:
        res["rendering_model"] = "SSR (Server-Rendered HTML)"

    return res

def main():
    client = httpx.Client(headers=HEADERS, timeout=12.0, follow_redirects=True)
    all_results = []

    print("=================================================================")
    print("STARTING AUDIT OF SITES 31 TO 60 FOR VPS ARCHIVE LENS")
    print("=================================================================")

    for site in SITES_TO_AUDIT:
        try:
            r = audit_site(site, client)
            all_results.append(r)
        except Exception as e:
            print(f"Error auditing {site['name']}: {e}")
            all_results.append({
                "id": site["id"],
                "name": site["name"],
                "domain": site["domain"],
                "error": str(e),
                "accessible": False
            })

    # Save structured audit JSON
    out_file = "/home/redking/.gemini/antigravity/scratch/vps-archive-lens/server/scripts/audit_31_60_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("=================================================================")
    print(f"AUDIT COMPLETE. Results saved to {out_file}")
    print(f"Total sites audited: {len(all_results)}")
    print("=================================================================")

if __name__ == "__main__":
    main()
