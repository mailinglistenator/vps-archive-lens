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

SITES_201_300 = [
    # Category 1: Think Tanks, Geopolitics & Policy Reviews (12)
    {"id": 201, "name": "Brookings Institution", "domain": "brookings.edu", "root": "https://www.brookings.edu/articles/", "type": "think_tank"},
    {"id": 202, "name": "CSIS", "domain": "csis.org", "root": "https://www.csis.org/analysis", "type": "think_tank"},
    {"id": 203, "name": "Carnegie Endowment", "domain": "carnegieendowment.org", "root": "https://carnegieendowment.org/publications/", "type": "think_tank"},
    {"id": 204, "name": "RAND Corporation", "domain": "rand.org", "root": "https://www.rand.org/pubs.html", "type": "think_tank"},
    {"id": 205, "name": "Chatham House", "domain": "chathamhouse.org", "root": "https://www.chathamhouse.org/research", "type": "think_tank"},
    {"id": 206, "name": "Project Syndicate", "domain": "project-syndicate.org", "root": "https://www.project-syndicate.org/", "type": "policy_opinion"},
    {"id": 207, "name": "Boston Review", "domain": "bostonreview.net", "root": "https://www.bostonreview.net/articles/", "type": "intellectual_review"},
    {"id": 208, "name": "London Review of Books", "domain": "lrb.co.uk", "root": "https://www.lrb.co.uk/", "type": "intellectual_review"},
    {"id": 209, "name": "New York Review of Books", "domain": "nybooks.com", "root": "https://www.nybooks.com/articles/", "type": "intellectual_review"},
    {"id": 210, "name": "The Conversation", "domain": "theconversation.com", "root": "https://theconversation.com/us", "type": "academic_journalism"},
    {"id": 211, "name": "Aeon Magazine", "domain": "aeon.co", "root": "https://aeon.co/essays", "type": "philosophy_essays"},
    {"id": 212, "name": "Lawfare", "domain": "lawfaremedia.org", "root": "https://www.lawfaremedia.org/", "type": "legal_national_security"},

    # Category 2: Premier Science, Biotech & Climate Journalism (12)
    {"id": 213, "name": "Nature News", "domain": "nature.com", "root": "https://www.nature.com/nature/articles?type=news", "type": "science_journal"},
    {"id": 214, "name": "Science.org News", "domain": "science.org", "root": "https://www.science.org/news", "type": "science_journal"},
    {"id": 215, "name": "The Lancet", "domain": "thelancet.com", "root": "https://www.thelancet.com/", "type": "medical_journal"},
    {"id": 216, "name": "STAT News", "domain": "statnews.com", "root": "https://www.statnews.com/", "type": "biotech_health"},
    {"id": 217, "name": "Fierce Biotech", "domain": "fiercebiotech.com", "root": "https://www.fiercebiotech.com/", "type": "biotech_industry"},
    {"id": 218, "name": "Inside Climate News", "domain": "insideclimatenews.org", "root": "https://insideclimatenews.org/", "type": "climate_journalism"},
    {"id": 219, "name": "Carbon Brief", "domain": "carbonbrief.org", "root": "https://www.carbonbrief.org/", "type": "climate_journalism"},
    {"id": 220, "name": "Grist", "domain": "grist.org", "root": "https://grist.org/", "type": "climate_journalism"},
    {"id": 221, "name": "Yale Environment 360", "domain": "e360.yale.edu", "root": "https://e360.yale.edu/", "type": "environmental_journal"},
    {"id": 222, "name": "Scientific American", "domain": "scientificamerican.com", "root": "https://www.scientificamerican.com/", "type": "science_magazine"},
    {"id": 223, "name": "Popular Science", "domain": "popsci.com", "root": "https://www.popsci.com/", "type": "science_magazine"},
    {"id": 224, "name": "Cell Press", "domain": "cell.com", "root": "https://www.cell.com/", "type": "scientific_journal"},

    # Category 3: Global Investigative & Non-Profit Watchdogs (10)
    {"id": 225, "name": "ICIJ", "domain": "icij.org", "root": "https://www.icij.org/investigations/", "type": "investigative_consortium"},
    {"id": 226, "name": "OCCRP", "domain": "occrp.org", "root": "https://www.occrp.org/en/investigations/", "type": "investigative_consortium"},
    {"id": 227, "name": "GIJN", "domain": "gijn.org", "root": "https://gijn.org/", "type": "investigative_network"},
    {"id": 228, "name": "Center for Public Integrity", "domain": "publicintegrity.org", "root": "https://publicintegrity.org/", "type": "investigative_watchdog"},
    {"id": 229, "name": "The Marshall Project", "domain": "themarshallproject.org", "root": "https://www.themarshallproject.org/", "type": "criminal_justice"},
    {"id": 230, "name": "Chalkbeat", "domain": "chalkbeat.org", "root": "https://www.chalkbeat.org/", "type": "education_journalism"},
    {"id": 231, "name": "Texas Tribune", "domain": "texastribune.org", "root": "https://www.texastribune.org/", "type": "nonprofit_state_news"},
    {"id": 232, "name": "CalMatters", "domain": "calmatters.org", "root": "https://calmatters.org/", "type": "nonprofit_state_news"},
    {"id": 233, "name": "OpenSecrets", "domain": "opensecrets.org", "root": "https://www.opensecrets.org/news/", "type": "campaign_finance_watchdog"},
    {"id": 234, "name": "Reveal News (CIR)", "domain": "revealnews.org", "root": "https://revealnews.org/article/", "type": "investigative_reporting"},

    # Category 4: Cybersecurity, Tech Law & Infrastructure (10)
    {"id": 235, "name": "Krebs on Security", "domain": "krebsonsecurity.com", "root": "https://krebsonsecurity.com/", "type": "cybersecurity_investigation"},
    {"id": 236, "name": "BleepingComputer", "domain": "bleepingcomputer.com", "root": "https://www.bleepingcomputer.com/", "type": "cybersecurity_news"},
    {"id": 237, "name": "Dark Reading", "domain": "darkreading.com", "root": "https://www.darkreading.com/", "type": "cybersecurity_news"},
    {"id": 238, "name": "SecurityWeek", "domain": "securityweek.com", "root": "https://www.securityweek.com/", "type": "cybersecurity_news"},
    {"id": 239, "name": "The Hacker News", "domain": "thehackernews.com", "root": "https://thehackernews.com/", "type": "cybersecurity_news"},
    {"id": 240, "name": "SCOTUSblog", "domain": "scotusblog.com", "root": "https://www.scotusblog.com/", "type": "legal_journalism"},
    {"id": 241, "name": "Just Security", "domain": "justsecurity.org", "root": "https://www.justsecurity.org/", "type": "national_security_law"},
    {"id": 242, "name": "FreightWaves", "domain": "freightwaves.com", "root": "https://www.freightwaves.com/news", "type": "supply_chain_logistics"},
    {"id": 243, "name": "Aviation Week", "domain": "aviationweek.com", "root": "https://aviationweek.com/", "type": "aerospace_defense"},
    {"id": 244, "name": "Simple Flying", "domain": "simpleflying.com", "root": "https://simpleflying.com/", "type": "aviation_news"},

    # Category 5: Nordic & Eastern European National Presses (10)
    {"id": 245, "name": "Dagens Nyheter", "domain": "dn.se", "root": "https://www.dn.se/", "type": "nordic_newspaper"},
    {"id": 246, "name": "Svenska Dagbladet", "domain": "svd.se", "root": "https://www.svd.se/", "type": "nordic_newspaper"},
    {"id": 247, "name": "Helsingin Sanomat", "domain": "hs.fi", "root": "https://www.hs.fi/", "type": "nordic_newspaper"},
    {"id": 248, "name": "Aftenposten", "domain": "aftenposten.no", "root": "https://www.aftenposten.no/", "type": "nordic_newspaper"},
    {"id": 249, "name": "Politiken", "domain": "politiken.dk", "root": "https://politiken.dk/", "type": "nordic_newspaper"},
    {"id": 250, "name": "Gazeta Wyborcza", "domain": "wyborcza.pl", "root": "https://wyborcza.pl/", "type": "eastern_european_newspaper"},
    {"id": 251, "name": "Denník N", "domain": "dennikn.sk", "root": "https://dennikn.sk/", "type": "eastern_european_newspaper"},
    {"id": 252, "name": "Telex", "domain": "telex.hu", "root": "https://telex.hu/english", "type": "eastern_european_newspaper"},
    {"id": 253, "name": "Novaya Gazeta Europe", "domain": "novayagazeta.eu", "root": "https://novayagazeta.eu/en", "type": "russian_independent_exile"},
    {"id": 254, "name": "Eurasianet", "domain": "eurasianet.org", "root": "https://eurasianet.org/", "type": "central_asia_caucasus"},

    # Category 6: South Asian & Southeast Asian Major Outlets (12)
    {"id": 255, "name": "The Wire (India)", "domain": "thewire.in", "root": "https://thewire.in/", "type": "indian_independent"},
    {"id": 256, "name": "Scroll.in", "domain": "scroll.in", "root": "https://scroll.in/", "type": "indian_digital_news"},
    {"id": 257, "name": "The Print", "domain": "theprint.in", "root": "https://theprint.in/", "type": "indian_digital_news"},
    {"id": 258, "name": "Livemint", "domain": "livemint.com", "root": "https://www.livemint.com/", "type": "indian_financial_daily"},
    {"id": 259, "name": "Business Standard", "domain": "business-standard.com", "root": "https://www.business-standard.com/", "type": "indian_financial_daily"},
    {"id": 260, "name": "Dawn", "domain": "dawn.com", "root": "https://www.dawn.com/", "type": "pakistani_newspaper"},
    {"id": 261, "name": "The Daily Star", "domain": "thedailystar.net", "root": "https://www.thedailystar.net/", "type": "bangladesh_newspaper"},
    {"id": 262, "name": "Jakarta Post", "domain": "thejakartapost.com", "root": "https://www.thejakartapost.com/", "type": "indonesian_newspaper"},
    {"id": 263, "name": "Bangkok Post", "domain": "bangkokpost.com", "root": "https://www.bangkokpost.com/", "type": "thai_newspaper"},
    {"id": 264, "name": "Rappler", "domain": "rappler.com", "root": "https://www.rappler.com/", "type": "philippine_investigative"},
    {"id": 265, "name": "VNExpress International", "domain": "e.vnexpress.net", "root": "https://e.vnexpress.net/", "type": "vietnamese_newspaper"},
    {"id": 266, "name": "Caixin Global", "domain": "caixinglobal.com", "root": "https://www.caixinglobal.com/", "type": "chinese_financial_journalism"},

    # Category 7: Latin American Heavyweights (10)
    {"id": 267, "name": "Reforma", "domain": "reforma.com", "root": "https://www.reforma.com/", "type": "mexican_newspaper"},
    {"id": 268, "name": "El Universal Mexico", "domain": "eluniversal.com.mx", "root": "https://www.eluniversal.com.mx/", "type": "mexican_newspaper"},
    {"id": 269, "name": "Animal Político", "domain": "animalpolitico.com", "root": "https://animalpolitico.com/", "type": "mexican_investigative"},
    {"id": 270, "name": "El Tiempo Colombia", "domain": "eltiempo.com", "root": "https://www.eltiempo.com/", "type": "colombian_newspaper"},
    {"id": 271, "name": "El Espectador", "domain": "elespectador.com", "root": "https://www.elespectador.com/", "type": "colombian_newspaper"},
    {"id": 272, "name": "La Nación Argentina", "domain": "lanacion.com.ar", "root": "https://www.lanacion.com.ar/", "type": "argentine_newspaper"},
    {"id": 273, "name": "El Mercurio Chile", "domain": "emol.com", "root": "https://www.emol.com/", "type": "chilean_newspaper"},
    {"id": 274, "name": "El Comercio Peru", "domain": "elcomercio.pe", "root": "https://elcomercio.pe/", "type": "peruvian_newspaper"},
    {"id": 275, "name": "O Globo", "domain": "oglobo.globo.com", "root": "https://oglobo.globo.com/", "type": "brazilian_newspaper"},
    {"id": 276, "name": "Página 12", "domain": "pagina12.com.ar", "root": "https://www.pagina12.com.ar/", "type": "argentine_newspaper"},

    # Category 8: African & Middle Eastern Leading Voices (8)
    {"id": 277, "name": "News24 South Africa", "domain": "news24.com", "root": "https://www.news24.com/", "type": "south_african_news"},
    {"id": 278, "name": "Mail & Guardian", "domain": "mg.co.za", "root": "https://mg.co.za/", "type": "south_african_investigative"},
    {"id": 279, "name": "Premium Times Nigeria", "domain": "premiumtimesng.com", "root": "https://www.premiumtimesng.com/", "type": "nigerian_investigative"},
    {"id": 280, "name": "Daily Nation Kenya", "domain": "nation.africa", "root": "https://nation.africa/kenya", "type": "east_african_daily"},
    {"id": 281, "name": "The Africa Report", "domain": "theafricareport.com", "root": "https://www.theafricareport.com/", "type": "pan_african_politics"},
    {"id": 282, "name": "Ahram Online", "domain": "english.ahram.org.eg", "root": "https://english.ahram.org.eg/", "type": "egyptian_newspaper"},
    {"id": 283, "name": "L'Orient Today", "domain": "today.lorientlejour.com", "root": "https://today.lorientlejour.com/", "type": "lebanese_independent"},
    {"id": 284, "name": "Asharq Al-Awsat", "domain": "english.aawsat.com", "root": "https://english.aawsat.com/", "type": "pan_arab_newspaper"},

    # Category 9: UK & US Thought, Culture & Independent Media (8)
    {"id": 285, "name": "The Spectator", "domain": "spectator.co.uk", "root": "https://www.spectator.co.uk/", "type": "conservative_weekly"},
    {"id": 286, "name": "New Statesman", "domain": "newstatesman.com", "root": "https://www.newstatesman.com/", "type": "progressive_weekly"},
    {"id": 287, "name": "Prospect Magazine", "domain": "prospectmagazine.co.uk", "root": "https://www.prospectmagazine.co.uk/", "type": "current_affairs"},
    {"id": 288, "name": "UnHerd", "domain": "unherd.com", "root": "https://unherd.com/", "type": "independent_opinion"},
    {"id": 289, "name": "Jacobin", "domain": "jacobin.com", "root": "https://jacobin.com/", "type": "socialist_political_review"},
    {"id": 290, "name": "Reason", "domain": "reason.com", "root": "https://reason.com/", "type": "libertarian_monthly"},
    {"id": 291, "name": "Pitchfork", "domain": "pitchfork.com", "root": "https://pitchfork.com/", "type": "music_culture"},
    {"id": 292, "name": "NME", "domain": "nme.com", "root": "https://www.nme.com/news", "type": "music_pop_culture"},

    # Category 10: Extended Korean & Japanese Regional & Specialized Press (8)
    {"id": 293, "name": "Sankei Shimbun", "domain": "sankei.com", "root": "https://www.sankei.com/", "type": "japanese_national_paper"},
    {"id": 294, "name": "Tokyo Shimbun", "domain": "tokyo-np.co.jp", "root": "https://www.tokyo-np.co.jp/", "type": "japanese_metro_daily"},
    {"id": 295, "name": "Nishinippon Shimbun", "domain": "nishinippon.co.jp", "root": "https://www.nishinippon.co.jp/", "type": "japanese_regional_daily"},
    {"id": 296, "name": "Kookmin Ilbo", "domain": "kmib.co.kr", "root": "https://www.kmib.co.kr/", "type": "korean_major_daily"},
    {"id": 297, "name": "Munhwa Ilbo", "domain": "munhwa.com", "root": "https://www.munhwa.com/", "type": "korean_evening_daily"},
    {"id": 298, "name": "Seoul Shinmun", "domain": "seoul.co.kr", "root": "https://www.seoul.co.kr/", "type": "korean_oldest_daily"},
    {"id": 299, "name": "Financial News Korea", "domain": "fnnews.com", "root": "https://www.fnnews.com/", "type": "korean_financial_daily"},
    {"id": 300, "name": "ZDNet Korea", "domain": "zdnet.co.kr", "root": "https://zdnet.co.kr/", "type": "korean_enterprise_tech"},
]

def find_article_link(soup, base_url, domain):
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if domain in parsed.netloc:
            path = parsed.path
            # typical article patterns
            if re.search(r"/\d{4}/\d{2}/|/article/|/articles/|/story/|/post/|/news/|/essay/|/essays/|/\d{6,}|-a-\d+", path, re.IGNORECASE):
                if not any(k in path for k in ["/tag/", "/category/", "/author/", "/topic/", "/browse", "/section/"]):
                    return full
    return None

async def check_direct_apis(client, domain):
    notes = []
    if "krebsonsecurity.com" in domain:
        notes.append("WordPress VIP RSS (/feed/) and REST API (/wp-json/wp/v2/posts) active")
    elif "theconversation.com" in domain:
        notes.append("The Conversation exposes open Creative Commons XML and RSS feeds")
    elif "scotusblog.com" in domain:
        notes.append("SCOTUSblog exposes clean RSS: /feed/")
    elif "bleepingcomputer.com" in domain:
        notes.append("BleepingComputer exposes RSS: /feed/")
    
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
        print(f"[{s_id}/300] Auditing {name} ({domain})...")

        # 1. Direct API check
        api_avail, api_note = await check_direct_apis(client, domain)
        if api_avail:
            res["direct_api_available"] = True
            res["direct_api_notes"] = api_note

        # 2. Fetch root / section page
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
            res["notes"].append("Could not auto-discover article link from root")

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
    print("STARTING LIVE AUDIT OF SITES 201 TO 300 (100 TARGET PLATFORMS)")
    print("=================================================================")

    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12.0) as client:
        tasks = [audit_single_site(site, client, sem) for site in SITES_201_300]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    out_file = "/home/redking/.gemini/antigravity/scratch/vps-archive-lens/server/scripts/audit_201_300_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("=================================================================")
    print(f"AUDIT COMPLETE. 100 sites analyzed. Output saved to {out_file}")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
