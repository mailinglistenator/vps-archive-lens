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

SITES_61_100 = [
    # Group 1: Global Breaking News, Major Broadcasters & International Presses (12)
    {"id": 61, "name": "USA Today", "domain": "usatoday.com", "root": "https://www.usatoday.com/", "type": "us_news"},
    {"id": 62, "name": "The Times of India", "domain": "timesofindia.indiatimes.com", "root": "https://timesofindia.indiatimes.com/", "type": "global_news"},
    {"id": 63, "name": "The Hindu", "domain": "thehindu.com", "root": "https://www.thehindu.com/news/", "type": "global_news"},
    {"id": 64, "name": "The Sydney Morning Herald", "domain": "smh.com.au", "root": "https://www.smh.com.au/", "type": "australian_news"},
    {"id": 65, "name": "ABC News Australia", "domain": "abc.net.au", "root": "https://www.abc.net.au/news", "type": "australian_news"},
    {"id": 66, "name": "CBC News", "domain": "cbc.ca", "root": "https://www.cbc.ca/news", "type": "canadian_news"},
    {"id": 67, "name": "The Globe and Mail", "domain": "theglobeandmail.com", "root": "https://www.theglobeandmail.com/", "type": "canadian_news"},
    {"id": 68, "name": "South China Morning Post", "domain": "scmp.com", "root": "https://www.scmp.com/", "type": "asian_news"},
    {"id": 69, "name": "The Straits Times", "domain": "straitstimes.com", "root": "https://www.straitstimes.com/", "type": "asian_news"},
    {"id": 70, "name": "France 24", "domain": "france24.com", "root": "https://www.france24.com/en/", "type": "global_broadcaster"},
    {"id": 71, "name": "Le Monde (English)", "domain": "lemonde.fr", "root": "https://www.lemonde.fr/en/", "type": "european_news"},
    {"id": 72, "name": "Der Spiegel (Int)", "domain": "spiegel.de", "root": "https://www.spiegel.de/international/", "type": "european_news"},

    # Group 2: Tech, Science, Crypto, Gaming & Digital Culture (10)
    {"id": 73, "name": "Engadget", "domain": "engadget.com", "root": "https://www.engadget.com/", "type": "tech_media"},
    {"id": 74, "name": "Gizmodo", "domain": "gizmodo.com", "root": "https://gizmodo.com/", "type": "tech_media"},
    {"id": 75, "name": "Mashable", "domain": "mashable.com", "root": "https://mashable.com/", "type": "tech_media"},
    {"id": 76, "name": "CNET", "domain": "cnet.com", "root": "https://www.cnet.com/", "type": "tech_media"},
    {"id": 77, "name": "VentureBeat", "domain": "venturebeat.com", "root": "https://venturebeat.com/", "type": "tech_media"},
    {"id": 78, "name": "CoinDesk", "domain": "coindesk.com", "root": "https://www.coindesk.com/", "type": "crypto_finance"},
    {"id": 79, "name": "CoinTelegraph", "domain": "cointelegraph.com", "root": "https://cointelegraph.com/", "type": "crypto_finance"},
    {"id": 80, "name": "ScienceDaily", "domain": "sciencedaily.com", "root": "https://www.sciencedaily.com/", "type": "science_news"},
    {"id": 81, "name": "Phys.org", "domain": "phys.org", "root": "https://phys.org/", "type": "science_news"},
    {"id": 82, "name": "Polygon", "domain": "polygon.com", "root": "https://www.polygon.com/", "type": "gaming_culture"},

    # Group 3: Business, Finance, Markets & Policy (10)
    {"id": 83, "name": "Business Insider", "domain": "businessinsider.com", "root": "https://www.businessinsider.com/", "type": "business_media"},
    {"id": 84, "name": "MarketWatch", "domain": "marketwatch.com", "root": "https://www.marketwatch.com/", "type": "financial_markets"},
    {"id": 85, "name": "Barron's", "domain": "barrons.com", "root": "https://www.barrons.com/", "type": "financial_markets"},
    {"id": 86, "name": "Fortune", "domain": "fortune.com", "root": "https://fortune.com/", "type": "business_media"},
    {"id": 87, "name": "Fast Company", "domain": "fastcompany.com", "root": "https://www.fastcompany.com/", "type": "business_media"},
    {"id": 88, "name": "Inc. Magazine", "domain": "inc.com", "root": "https://www.inc.com/", "type": "business_media"},
    {"id": 89, "name": "S&P Global", "domain": "spglobal.com", "root": "https://www.spglobal.com/en/research-insights", "type": "financial_markets"},
    {"id": 90, "name": "The Hill", "domain": "thehill.com", "root": "https://thehill.com/", "type": "policy_news"},
    {"id": 91, "name": "Axios", "domain": "axios.com", "root": "https://www.axios.com/", "type": "news_newsletter"},
    {"id": 92, "name": "Semafor", "domain": "semafor.com", "root": "https://www.semafor.com/", "type": "news_newsletter"},

    # Group 4: Extended Regional Outlets & Digital Curators (8)
    {"id": 93, "name": "Yomiuri Shimbun", "domain": "yomiuri.co.jp", "root": "https://www.yomiuri.co.jp/", "type": "japanese_news"},
    {"id": 94, "name": "Mainichi Shimbun", "domain": "mainichi.jp", "root": "https://mainichi.jp/", "type": "japanese_news"},
    {"id": 95, "name": "Kyodo News", "domain": "english.kyodonews.net", "root": "https://english.kyodonews.net/", "type": "japanese_news"},
    {"id": 96, "name": "MoneyToday", "domain": "mt.co.kr", "root": "https://news.mt.co.kr/", "type": "korean_news"},
    {"id": 97, "name": "Edaily", "domain": "edaily.co.kr", "root": "https://www.edaily.co.kr/", "type": "korean_news"},
    {"id": 98, "name": "OhmyNews", "domain": "ohmynews.com", "root": "https://www.ohmynews.com/", "type": "korean_news"},
    {"id": 99, "name": "AllTop", "domain": "alltop.com", "root": "https://alltop.com/", "type": "aggregator"},
    {"id": 100, "name": "SmartBrief", "domain": "smartbrief.com", "root": "https://www.smartbrief.com/", "type": "aggregator"},
]

def find_article_link(soup, base_url, domain):
    """Discover a live article URL from a homepage or section."""
    patterns = {
        "usatoday.com": r"/story/[a-z0-9\-]+/\d{4}/\d{2}/\d{2}/",
        "timesofindia.indiatimes.com": r"/articleshow/\d+\.cms",
        "thehindu.com": r"/news/[a-z0-9\-]+/[a-z0-9\-]+/article\d+\.ece",
        "smh.com.au": r"/[a-z0-9\-]+/[a-z0-9\-]+-\d{8}-p[a-z0-9]+\.html",
        "abc.net.au": r"/news/\d{4}-\d{2}-\d{2}/[a-z0-9\-]+/\d+",
        "cbc.ca": r"/news/[a-z0-9\-]+/[a-z0-9\-]+-\d+\.\d+",
        "theglobeandmail.com": r"/article-[a-z0-9\-]+/",
        "scmp.com": r"/news/[a-z0-9\-]+/[a-z0-9\-]+/article/\d+/",
        "straitstimes.com": r"/[a-z0-9\-]+/[a-z0-9\-]+",
        "france24.com": r"/en/[a-z0-9\-]+/\d{8}-[a-z0-9\-]+",
        "lemonde.fr": r"/en/[a-z0-9\-]+/article/\d{4}/\d{2}/\d{2}/",
        "spiegel.de": r"/international/[a-z0-9\-]+/[a-z0-9\-]+-a-[a-f0-9\-]+\.html",
        "engadget.com": r"/[a-z0-9\-]+-[a-z0-9\-]+\.html",
        "gizmodo.com": r"/[a-z0-9\-]+-\d+",
        "mashable.com": r"/article/[a-z0-9\-]+",
        "cnet.com": r"/(?:tech|culture|home|science)/[a-z0-9\-]+/",
        "venturebeat.com": r"/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+/",
        "coindesk.com": r"/(?:markets|policy|business|tech)/\d{4}/\d{2}/\d{2}/",
        "cointelegraph.com": r"/news/[a-z0-9\-]+",
        "sciencedaily.com": r"/releases/\d{4}/\d{2}/\d+\.htm",
        "phys.org": r"/news/\d{4}-\d{2}-[a-z0-9\-]+\.html",
        "polygon.com": r"/\d{4}/\d{1,2}/\d{1,2}/\d+/[a-z0-9\-]+",
        "businessinsider.com": r"/[a-z0-9\-]+-\d{4}-\d{1,2}",
        "marketwatch.com": r"/story/[a-z0-9\-]+-\d+",
        "barrons.com": r"/articles/[a-z0-9\-]+",
        "fortune.com": r"/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+/",
        "fastcompany.com": r"/\d+/[a-z0-9\-]+",
        "inc.com": r"/[a-zA-Z0-9_\-]+/[a-z0-9\-]+\.html",
        "spglobal.com": r"/en/research-insights/articles/[a-z0-9\-]+",
        "thehill.com": r"/[a-z0-9\-]+/\d+-[a-z0-9\-]+/",
        "axios.com": r"/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+",
        "semafor.com": r"/article/\d{2}/\d{2}/\d{4}/[a-z0-9\-]+",
        "yomiuri.co.jp": r"/[a-z]+/\d{8}-[a-z0-9]+/",
        "mainichi.jp": r"/articles/\d{8}/[a-z0-9/]+",
        "english.kyodonews.net": r"/news/\d{4}/\d{2}/[a-f0-9]+\.html",
        "mt.co.kr": r"/view/mtview\.php\?no=\d+",
        "edaily.co.kr": r"/news/read\?newsId=\d+",
        "ohmynews.com": r"/NWS_Web/View/at_pg\.aspx\?CNTN_CD=\d+",
        "alltop.com": r"/viral/[a-z0-9\-]+",
        "smartbrief.com": r"/original/\d{4}/\d{2}/[a-z0-9\-]+",
    }

    pat = patterns.get(domain)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        if pat and re.search(pat, full, re.IGNORECASE):
            return full

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        if domain in urlparse(full).netloc:
            if re.search(r"/\d{4}/\d{2}/|/article|/story/|/news/|/releases/", full):
                return full
    return None

def audit_site(site_meta, client):
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
        },
        "rendering_model": "SSR",
        "wait_for_selector": None,
        "notes": [],
    }

    print(f"[{s_id}/100] Auditing {name} ({domain})...")

    # 1. Check direct APIs if applicable (VentureBeat WP REST, Axios GraphQL, etc.)
    if domain == "venturebeat.com":
        try:
            r_api = client.get("https://venturebeat.com/wp-json/wp/v2/posts?per_page=1")
            if r_api.status_code == 200:
                res["direct_api_available"] = True
                res["direct_api_notes"] = "WordPress VIP REST API (/wp-json/wp/v2/posts) active"
        except Exception:
            pass

    # 2. Fetch root page
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

    if not art_url:
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
    for t_sel in ["h1[class*='headline']", "h1[class*='title']", "article h1", "h1", "h2[class*='title']", "h2.news_ttl"]:
        matched = asoup.select(t_sel)
        if matched and len(matched[0].get_text(strip=True)) > 5:
            txt = matched[0].get_text(strip=True)
            if not any(logo in txt.lower() for logo in ["home", "cnet", "engadget", "usa today", "france 24"]):
                res["dom_selectors"]["title_selector"] = t_sel
                break

    # Body
    for b_sel in [
        "div[data-testid='ArticleBody']",
        "div[data-testid='article-body']",
        "div[data-component='article-body']",
        "section[data-component='ArticleBody']",
        "div.article-content",
        "div.entry-content",
        "div.story-text",
        "div.story-body",
        "div.article__body",
        "div.ArticleBody",
        "div.c-entry-content",
        "div.c-article_body",
        "div#article-body",
        "div#storytext",
        "div#content-body",
        "div.news_cnt_detail_wrap",
        "div#article_txt",
        "div#textBody",
        "div.wysiwyg",
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
    for d_sel in ["time[datetime]", "[class*='date']", "[class*='time']", "span.num_date"]:
        matched = asoup.select(d_sel)
        if matched and matched[0].get_text(strip=True):
            res["dom_selectors"]["date_selector"] = d_sel
            break

    # 6. Analyze Images & CDN
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

    # 7. Analyze Consent / Overlay Dialogs
    for c_id in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button", "#sp_message_container", ".cookie-banner", "button[name='agree']"]:
        if c_id.startswith("#"):
            if asoup.find(id=c_id[1:]):
                res["notice_dialogs"]["consent_banner"] = c_id
        elif c_id.startswith("."):
            if asoup.find(class_=c_id[1:]):
                res["notice_dialogs"]["consent_banner"] = c_id

    # 8. Rendering Model
    if any(spa_sig in art_html.lower() for spa_sig in ["__next_data__", "window.__initial_state__", "gatsby-hydrate"]):
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
    print("STARTING AUDIT OF SITES 61 TO 100 FOR VPS ARCHIVE LENS")
    print("=================================================================")

    for site in SITES_61_100:
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

    out_file = "/home/redking/.gemini/antigravity/scratch/vps-archive-lens/server/scripts/audit_61_100_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("=================================================================")
    print(f"AUDIT COMPLETE. Results saved to {out_file}")
    print(f"Total sites audited: {len(all_results)}")
    print("=================================================================")

if __name__ == "__main__":
    main()
