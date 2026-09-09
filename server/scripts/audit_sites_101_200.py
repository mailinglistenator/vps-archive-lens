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

SITES_101_200 = [
    # Category A: Premium Paywalled, Longform Journalism & Thought Leadership (15)
    {"id": 101, "name": "Substack", "domain": "substack.com", "root": "https://substack.com/browse", "type": "paywalled_newsletter"},
    {"id": 102, "name": "Medium", "domain": "medium.com", "root": "https://medium.com/", "type": "metered_platform"},
    {"id": 103, "name": "The New Yorker", "domain": "newyorker.com", "root": "https://www.newyorker.com/", "type": "paywalled_magazine"},
    {"id": 104, "name": "The Information", "domain": "theinformation.com", "root": "https://www.theinformation.com/", "type": "paywalled_tech"},
    {"id": 105, "name": "Puck News", "domain": "puck.news", "root": "https://puck.news/", "type": "paywalled_newsletter"},
    {"id": 106, "name": "Harvard Business Review", "domain": "hbr.org", "root": "https://hbr.org/", "type": "metered_business"},
    {"id": 107, "name": "MIT Technology Review", "domain": "technologyreview.com", "root": "https://www.technologyreview.com/", "type": "metered_tech"},
    {"id": 108, "name": "Foreign Affairs", "domain": "foreignaffairs.com", "root": "https://www.foreignaffairs.com/", "type": "paywalled_geopolitics"},
    {"id": 109, "name": "Foreign Policy", "domain": "foreignpolicy.com", "root": "https://foreignpolicy.com/", "type": "paywalled_geopolitics"},
    {"id": 110, "name": "The Intercept", "domain": "theintercept.com", "root": "https://theintercept.com/", "type": "investigative_journalism"},
    {"id": 111, "name": "Slate", "domain": "slate.com", "root": "https://slate.com/", "type": "opinion_magazine"},
    {"id": 112, "name": "Salon", "domain": "salon.com", "root": "https://www.salon.com/", "type": "opinion_magazine"},
    {"id": 113, "name": "The Daily Beast", "domain": "thedailybeast.com", "root": "https://www.thedailybeast.com/", "type": "investigative_tabloid"},
    {"id": 114, "name": "Mother Jones", "domain": "motherjones.com", "root": "https://www.motherjones.com/", "type": "investigative_journalism"},
    {"id": 115, "name": "Vanity Fair", "domain": "vanityfair.com", "root": "https://www.vanityfair.com/", "type": "culture_investigative"},

    # Category B: Tech, Hardware, AI, Dev & Science Communities (15)
    {"id": 116, "name": "The Register", "domain": "theregister.com", "root": "https://www.theregister.com/", "type": "tech_media"},
    {"id": 117, "name": "Tom's Hardware", "domain": "tomshardware.com", "root": "https://www.tomshardware.com/", "type": "hardware_reviews"},
    {"id": 118, "name": "TechRadar", "domain": "techradar.com", "root": "https://www.techradar.com/", "type": "consumer_tech"},
    {"id": 119, "name": "The Next Web", "domain": "thenextweb.com", "root": "https://thenextweb.com/", "type": "tech_media"},
    {"id": 120, "name": "HackerNoon", "domain": "hackernoon.com", "root": "https://hackernoon.com/", "type": "tech_blog"},
    {"id": 121, "name": "Slashdot", "domain": "slashdot.org", "root": "https://slashdot.org/", "type": "tech_aggregator"},
    {"id": 122, "name": "Lobste.rs", "domain": "lobste.rs", "root": "https://lobste.rs/", "type": "tech_aggregator"},
    {"id": 123, "name": "9to5Mac", "domain": "9to5mac.com", "root": "https://9to5mac.com/", "type": "tech_media"},
    {"id": 124, "name": "MacRumors", "domain": "macrumors.com", "root": "https://www.macrumors.com/", "type": "tech_media"},
    {"id": 125, "name": "Android Central", "domain": "androidcentral.com", "root": "https://www.androidcentral.com/", "type": "tech_media"},
    {"id": 126, "name": "Android Police", "domain": "androidpolice.com", "root": "https://www.androidpolice.com/", "type": "tech_media"},
    {"id": 127, "name": "XDA Developers", "domain": "xda-developers.com", "root": "https://www.xda-developers.com/", "type": "dev_hardware"},
    {"id": 128, "name": "SiliconANGLE", "domain": "siliconangle.com", "root": "https://siliconangle.com/", "type": "enterprise_tech"},
    {"id": 129, "name": "Quanta Magazine", "domain": "quantamagazine.org", "root": "https://www.quantamagazine.org/", "type": "science_magazine"},
    {"id": 130, "name": "New Scientist", "domain": "newscientist.com", "root": "https://www.newscientist.com/", "type": "science_magazine"},

    # Category C: Geopolitics, Defense, Conflict & Strategic Studies (15)
    {"id": 131, "name": "The Kyiv Independent", "domain": "kyivindependent.com", "root": "https://kyivindependent.com/", "type": "conflict_geopolitics"},
    {"id": 132, "name": "The Moscow Times", "domain": "themoscowtimes.com", "root": "https://www.themoscowtimes.com/", "type": "independent_russian"},
    {"id": 133, "name": "Meduza", "domain": "meduza.io", "root": "https://meduza.io/en", "type": "independent_russian"},
    {"id": 134, "name": "Bellingcat", "domain": "bellingcat.com", "root": "https://www.bellingcat.com/", "type": "osint_investigative"},
    {"id": 135, "name": "War on the Rocks", "domain": "warontherocks.com", "root": "https://warontherocks.com/", "type": "defense_geopolitics"},
    {"id": 136, "name": "Defense One", "domain": "defenseone.com", "root": "https://www.defenseone.com/", "type": "defense_geopolitics"},
    {"id": 137, "name": "Breaking Defense", "domain": "breakingdefense.com", "root": "https://breakingdefense.com/", "type": "defense_geopolitics"},
    {"id": 138, "name": "The Diplomat", "domain": "thediplomat.com", "root": "https://thediplomat.com/", "type": "asia_geopolitics"},
    {"id": 139, "name": "Haaretz (English)", "domain": "haaretz.com", "root": "https://www.haaretz.com/", "type": "middle_east_newspaper"},
    {"id": 140, "name": "The Jerusalem Post", "domain": "jpost.com", "root": "https://www.jpost.com/", "type": "middle_east_newspaper"},
    {"id": 141, "name": "The Times of Israel", "domain": "timesofisrael.com", "root": "https://www.timesofisrael.com/", "type": "middle_east_newspaper"},
    {"id": 142, "name": "Al-Monitor", "domain": "al-monitor.com", "root": "https://www.al-monitor.com/", "type": "middle_east_policy"},
    {"id": 143, "name": "Middle East Eye", "domain": "middleeasteye.net", "root": "https://www.middleeasteye.net/", "type": "middle_east_news"},
    {"id": 144, "name": "Taiwan News", "domain": "taiwannews.com.tw", "root": "https://www.taiwannews.com.tw/en", "type": "taiwan_news"},
    {"id": 145, "name": "NK News", "domain": "nknews.org", "root": "https://www.nknews.org/", "type": "korean_peninsula_specialist"},

    # Category D: Finance, Markets, Venture & Crypto (15)
    {"id": 146, "name": "ZeroHedge", "domain": "zerohedge.com", "root": "https://www.zerohedge.com/", "type": "alternative_finance"},
    {"id": 147, "name": "Seeking Alpha", "domain": "seekingalpha.com", "root": "https://seekingalpha.com/", "type": "financial_markets"},
    {"id": 148, "name": "The Motley Fool", "domain": "fool.com", "root": "https://www.fool.com/", "type": "financial_markets"},
    {"id": 149, "name": "Investopedia", "domain": "investopedia.com", "root": "https://www.investopedia.com/", "type": "financial_education"},
    {"id": 150, "name": "Benzinga", "domain": "benzinga.com", "root": "https://www.benzinga.com/", "type": "financial_markets"},
    {"id": 151, "name": "Decrypt", "domain": "decrypt.co", "root": "https://decrypt.co/", "type": "crypto_web3"},
    {"id": 152, "name": "Blockworks", "domain": "blockworks.co", "root": "https://blockworks.co/", "type": "crypto_web3"},
    {"id": 153, "name": "The Block", "domain": "theblock.co", "root": "https://www.theblock.co/", "type": "crypto_web3"},
    {"id": 154, "name": "Morningstar", "domain": "morningstar.com", "root": "https://www.morningstar.com/", "type": "financial_markets"},
    {"id": 155, "name": "City A.M.", "domain": "cityam.com", "root": "https://www.cityam.com/", "type": "financial_markets"},
    {"id": 156, "name": "PitchBook News", "domain": "pitchbook.com", "root": "https://pitchbook.com/news", "type": "venture_capital"},
    {"id": 157, "name": "Crunchbase News", "domain": "news.crunchbase.com", "root": "https://news.crunchbase.com/", "type": "venture_capital"},
    {"id": 158, "name": "American Banker", "domain": "americanbanker.com", "root": "https://www.americanbanker.com/", "type": "banking_finance"},
    {"id": 159, "name": "Pensions & Investments", "domain": "pionline.com", "root": "https://www.pionline.com/", "type": "institutional_finance"},
    {"id": 160, "name": "Institutional Investor", "domain": "institutionalinvestor.com", "root": "https://www.institutionalinvestor.com/", "type": "institutional_finance"},

    # Category E: European, Middle Eastern & Global Major Presses (15)
    {"id": 161, "name": "El País", "domain": "elpais.com", "root": "https://english.elpais.com/", "type": "european_newspaper"},
    {"id": 162, "name": "El Mundo", "domain": "elmundo.es", "root": "https://www.elmundo.es/", "type": "european_newspaper"},
    {"id": 163, "name": "Corriere della Sera", "domain": "corriere.it", "root": "https://www.corriere.it/", "type": "european_newspaper"},
    {"id": 164, "name": "La Repubblica", "domain": "repubblica.it", "root": "https://www.repubblica.it/", "type": "european_newspaper"},
    {"id": 165, "name": "Die Zeit", "domain": "zeit.de", "root": "https://www.zeit.de/index", "type": "european_newspaper"},
    {"id": 166, "name": "Frankfurter Allgemeine (FAZ)", "domain": "faz.net", "root": "https://www.faz.net/aktuell/", "type": "european_newspaper"},
    {"id": 167, "name": "Neue Zürcher Zeitung (NZZ)", "domain": "nzz.ch", "root": "https://www.nzz.ch/", "type": "european_newspaper"},
    {"id": 168, "name": "The Irish Times", "domain": "irishtimes.com", "root": "https://www.irishtimes.com/", "type": "european_newspaper"},
    {"id": 169, "name": "The Scotsman", "domain": "scotsman.com", "root": "https://www.scotsman.com/", "type": "uk_newspaper"},
    {"id": 170, "name": "Arab News", "domain": "arabnews.com", "root": "https://www.arabnews.com/", "type": "middle_east_newspaper"},
    {"id": 171, "name": "Khaleej Times", "domain": "khaleejtimes.com", "root": "https://www.khaleejtimes.com/", "type": "middle_east_newspaper"},
    {"id": 172, "name": "TRT World", "domain": "trtworld.com", "root": "https://www.trtworld.com/", "type": "international_broadcaster"},
    {"id": 173, "name": "Folha de S.Paulo", "domain": "folha.uol.com.br", "root": "https://www1.folha.uol.com.br/internacional/en/", "type": "latin_american_newspaper"},
    {"id": 174, "name": "Clarín", "domain": "clarin.com", "root": "https://www.clarin.com/", "type": "latin_american_newspaper"},
    {"id": 175, "name": "Daily Maverick", "domain": "dailymaverick.co.za", "root": "https://www.dailymaverick.co.za/", "type": "african_investigative"},

    # Category F: US & Commonwealth Metropolitan & Regional Papers (13)
    {"id": 176, "name": "Chicago Tribune", "domain": "chicagotribune.com", "root": "https://www.chicagotribune.com/", "type": "us_metro_newspaper"},
    {"id": 177, "name": "Boston Globe", "domain": "bostonglobe.com", "root": "https://www.bostonglobe.com/", "type": "us_metro_newspaper"},
    {"id": 178, "name": "San Francisco Chronicle", "domain": "sfchronicle.com", "root": "https://www.sfchronicle.com/", "type": "us_metro_newspaper"},
    {"id": 179, "name": "Seattle Times", "domain": "seattletimes.com", "root": "https://www.seattletimes.com/", "type": "us_metro_newspaper"},
    {"id": 180, "name": "Dallas Morning News", "domain": "dallasnews.com", "root": "https://www.dallasnews.com/", "type": "us_metro_newspaper"},
    {"id": 181, "name": "Miami Herald", "domain": "miamiherald.com", "root": "https://www.miamiherald.com/", "type": "us_metro_newspaper"},
    {"id": 182, "name": "Atlanta Journal-Constitution", "domain": "ajc.com", "root": "https://www.ajc.com/", "type": "us_metro_newspaper"},
    {"id": 183, "name": "Houston Chronicle", "domain": "houstonchronicle.com", "root": "https://www.houstonchronicle.com/", "type": "us_metro_newspaper"},
    {"id": 184, "name": "Philadelphia Inquirer", "domain": "inquirer.com", "root": "https://www.inquirer.com/", "type": "us_metro_newspaper"},
    {"id": 185, "name": "Denver Post", "domain": "denverpost.com", "root": "https://www.denverpost.com/", "type": "us_metro_newspaper"},
    {"id": 186, "name": "Toronto Star", "domain": "thestar.com", "root": "https://www.thestar.com/", "type": "canadian_metro_newspaper"},
    {"id": 187, "name": "National Post", "domain": "nationalpost.com", "root": "https://nationalpost.com/", "type": "canadian_newspaper"},
    {"id": 188, "name": "The New Zealand Herald", "domain": "nzherald.co.nz", "root": "https://www.nzherald.co.nz/", "type": "nz_newspaper"},

    # Category G: Korean & Japanese Specialized & Independent Media (12)
    {"id": 189, "name": "Pressian", "domain": "pressian.com", "root": "https://www.pressian.com/", "type": "korean_independent"},
    {"id": 190, "name": "MediaToday", "domain": "mediatoday.co.kr", "root": "https://www.mediatoday.co.kr/", "type": "korean_media_watchdog"},
    {"id": 191, "name": "Sisa Journal", "domain": "sisajournal.com", "root": "https://www.sisajournal.com/", "type": "korean_weekly_magazine"},
    {"id": 192, "name": "Bloter", "domain": "bloter.net", "root": "https://www.bloter.net/", "type": "korean_tech_journalism"},
    {"id": 193, "name": "DongA Science", "domain": "dongascience.com", "root": "https://www.dongascience.com/", "type": "korean_science_journalism"},
    {"id": 194, "name": "NewsPim", "domain": "newspim.com", "root": "https://www.newspim.com/", "type": "korean_financial_wire"},
    {"id": 195, "name": "Newstapa", "domain": "newstapa.org", "root": "https://newstapa.org/", "type": "korean_investigative"},
    {"id": 196, "name": "Toyo Keizai", "domain": "toyokeizai.net", "root": "https://toyokeizai.net/", "type": "japanese_business_magazine"},
    {"id": 197, "name": "Diamond Online", "domain": "diamond.jp", "root": "https://diamond.jp/", "type": "japanese_business_magazine"},
    {"id": 198, "name": "President Online", "domain": "president.jp", "root": "https://president.jp/", "type": "japanese_business_magazine"},
    {"id": 199, "name": "ITmedia", "domain": "itmedia.co.jp", "root": "https://www.itmedia.co.jp/", "type": "japanese_tech_portal"},
    {"id": 200, "name": "ASCII.jp", "domain": "ascii.jp", "root": "https://ascii.jp/", "type": "japanese_tech_media"},
]

def find_article_link(soup, base_url, domain):
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if domain in parsed.netloc:
            path = parsed.path
            # typical article patterns
            if re.search(r"/\d{4}/\d{2}/|/article/|/story/|/p/|/news/|/post/|/opinion/|/\d{6,}|-a-\d+", path, re.IGNORECASE):
                # avoid tags, authors, categories
                if not any(k in path for k in ["/tag/", "/category/", "/author/", "/section/", "/topic/", "/browse"]):
                    return full
    return None

async def check_direct_apis(client, domain):
    notes = []
    if "substack.com" in domain:
        notes.append("Substack exposes public REST API: /api/v1/posts?limit=10 and RSS /feed")
    elif "medium.com" in domain:
        notes.append("Medium exposes user/tag RSS feeds: medium.com/feed/@{user}")
    elif "lobste.rs" in domain:
        try:
            r = await client.get("https://lobste.rs/hottest.json", timeout=5.0)
            if r.status_code == 200:
                return True, "Lobste.rs exposes official JSON endpoints: /hottest.json, /s/{id}.json"
        except Exception:
            pass
    elif "hackernoon.com" in domain:
        notes.append("HackerNoon exposes GraphQL & RSS: /feed")
    elif "slashdot.org" in domain:
        notes.append("Slashdot exposes clean RSS: slashdot.org/slashdot.rss and mobile view")
    
    if notes:
        return True, "; ".join(notes)
    return False, None

async def audit_single_site(site_meta, client, sem):
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

    async with sem:
        print(f"[{s_id}/200] Auditing {name} ({domain})...")

        # 1. Direct API / Endpoints check
        api_avail, api_note = await check_direct_apis(client, domain)
        if api_avail:
            res["direct_api_available"] = True
            res["direct_api_notes"] = api_note

        # 2. Fetch root page
        try:
            r = await client.get(root, timeout=10.0)
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
            art_url = root
            res["notes"].append("Could not auto-discover dedicated article URL from root")

        res["article_url_sampled"] = art_url

        # 3. Fetch article page
        try:
            art_resp = await client.get(art_url, timeout=10.0)
            art_html = art_resp.text
            asoup = BeautifulSoup(art_html, "html.parser")
        except Exception as e:
            res["notes"].append(f"Article fetch error ({art_url}): {e}")
            return res

        # 4. JSON-LD analysis
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

        # 5. DOM Selectors
        # Title
        for t_sel in ["h1[class*='headline']", "h1[class*='title']", "article h1", "h1.entry-title", "h1", "h2.news_ttl", "h2.title"]:
            m = asoup.select(t_sel)
            if m and len(m[0].get_text(strip=True)) > 5:
                res["dom_selectors"]["title_selector"] = t_sel
                break

        # Body
        for b_sel in [
            "div[data-testid='ArticleBody']",
            "div[data-component='article-body']",
            "div.article-body",
            "div.entry-content",
            "div.story-body",
            "div.article-content",
            "div.post-content",
            "div.c-entry-content",
            "div.article__body",
            "div#article-body",
            "div#storytext",
            "div#article_body",
            "div#textBody",
            "div.content_box",
            "div.article_view",
            "div.article-main",
            "article",
            "main",
        ]:
            m = asoup.select(b_sel)
            if m:
                txt_len = len(m[0].get_text(strip=True))
                if txt_len > 250:
                    res["dom_selectors"]["body_selector"] = b_sel
                    res["wait_for_selector"] = b_sel
                    break

        # Author
        for a_sel in ["[class*='author']", "[class*='byline']", "[itemprop='author']", "[rel='author']", ".reporter"]:
            m = asoup.select(a_sel)
            if m and m[0].get_text(strip=True):
                res["dom_selectors"]["author_selector"] = a_sel
                break

        # Date
        for d_sel in ["time[datetime]", "[class*='date']", "[class*='time']", "span.num_date"]:
            m = asoup.select(d_sel)
            if m and m[0].get_text(strip=True):
                res["dom_selectors"]["date_selector"] = d_sel
                break

        # 6. Images
        for img in asoup.find_all("img")[:10]:
            for attr in ["data-src", "data-original", "data-srcset", "srcset"]:
                if img.get(attr) and attr not in res["image_handling"]["lazy_attrs"]:
                    res["image_handling"]["lazy_attrs"].append(attr)
            src = img.get("src", "")
            if src.startswith("http"):
                c_host = urlparse(src).netloc
                if not res["image_handling"]["cdn_host"] and ("img" in c_host or "cdn" in c_host or "media" in c_host):
                    res["image_handling"]["cdn_host"] = c_host

        # 7. Overlays / Banners
        for c_id in ["#onetrust-accept-btn-handler", "#didomi-notice-agree-button", "#sp_message_container", ".cookie-banner", "button[name='agree']"]:
            if c_id.startswith("#"):
                if asoup.find(id=c_id[1:]):
                    res["notice_dialogs"]["consent_banner"] = c_id
            elif c_id.startswith("."):
                if asoup.find(class_=c_id[1:]):
                    res["notice_dialogs"]["consent_banner"] = c_id

        # 8. Rendering model
        if any(spa_sig in art_html.lower() for spa_sig in ["__next_data__", "window.__initial_state__", "gatsby-hydrate", "id=\"__nuxt\""]):
            res["rendering_model"] = "SSR + Client Hydration (Next.js/Nuxt/SPA)"
            if not res["wait_for_selector"]:
                res["wait_for_selector"] = "article, main"
        else:
            res["rendering_model"] = "SSR (Server-Rendered HTML)"

        return res

async def main():
    print("=================================================================")
    print("STARTING LIVE AUDIT OF SITES 101 TO 200 (100 TARGET PLATFORMS)")
    print("=================================================================")

    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12.0) as client:
        tasks = [audit_single_site(site, client, sem) for site in SITES_101_200]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    out_file = "/home/redking/.gemini/antigravity/scratch/vps-archive-lens/server/scripts/audit_101_200_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("=================================================================")
    print(f"AUDIT COMPLETE. 100 sites analyzed. Output saved to {out_file}")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
