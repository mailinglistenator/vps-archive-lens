import re
import sys

NEW_EXTRACTORS = '''
# ==============================================================================
# 5D. Sites 101–200: High-Priority Archiving & Deep Research Platforms
# ==============================================================================

# Category A: Premium Paywalled, Longform Journalism & Thought Leadership (Sites 101–115)

def extract_newyorker(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The New Yorker extractor with full JSON-LD articleBody priority."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The New Yorker",
        body_selectors=["div[data-testid='BodyWrapper']", "div.article__body", "article"],
        title_selectors=["h1[data-testid='ContentHeaderHed']", "h1"],
        check_json_ld_body=True,
        min_json_ld_body_len=100,
    )


def extract_theinformation(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Information tech journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Information",
        body_selectors=["div.article-content", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_pucknews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Puck News insider journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Puck News",
        body_selectors=["div.post-content", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_hbr(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Harvard Business Review extractor with full JSON-LD articleBody priority."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Harvard Business Review",
        body_selectors=["div.article-body", "div.article__body", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
        min_json_ld_body_len=100,
    )


def extract_technologyreview(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """MIT Technology Review extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="MIT Technology Review",
        body_selectors=["div[data-component='article-body']", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_foreignaffairs(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Foreign Affairs geopolitical journal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Foreign Affairs",
        body_selectors=["div.article-body-content", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_foreignpolicy(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Foreign Policy magazine extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Foreign Policy",
        body_selectors=["div.article-content", "div.post-content", "article"],
        title_selectors=["h1"],
    )


def extract_theintercept(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Intercept investigative journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Intercept",
        body_selectors=["div.entry-content", "div.post-content", "article"],
        title_selectors=["h1"],
    )


def extract_slate(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Slate online magazine extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Slate",
        body_selectors=["div.story-card__body", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_salon(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Salon news and culture extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Salon",
        body_selectors=["div.article-content", "div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_thedailybeast(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Daily Beast news commentary extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Daily Beast",
        body_selectors=["div.BodyContent", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_motherjones(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Mother Jones investigative reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Mother Jones",
        body_selectors=["div.entry-content", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_vanityfair(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Vanity Fair magazine extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Vanity Fair",
        body_selectors=["div[data-testid='BodyWrapper']", "article"],
        title_selectors=["h1"],
    )


# Category B: Tech, Hardware, AI, Dev & Science Communities (Sites 116–130)

def extract_theregister(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Register enterprise tech extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Register",
        body_selectors=["div#body", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_tomshardware(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Tom's Hardware enthusiast tech extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Tom's Hardware",
        body_selectors=["div#article-body", "div.content-body", "article"],
        title_selectors=["h1"],
    )


def extract_techradar(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """TechRadar consumer tech extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="TechRadar",
        body_selectors=["div#article-body", "article"],
        title_selectors=["h1"],
    )


def extract_thenextweb(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Next Web (TNW) European tech news extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Next Web",
        body_selectors=["div.c-articleContent", "article"],
        title_selectors=["h1"],
    )


def extract_hackernoon(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """HackerNoon technologist publication extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="HackerNoon",
        body_selectors=["div.story-container", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_slashdot(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Slashdot news and discussion extractor with syndicated RSS fast path."""
    return extract_with_rss_fallback(
        url=url,
        soup=soup,
        site_name="Slashdot",
        feed_url="https://slashdot.org/slashdot.rss",
        body_selectors=["div.body", "article", "div#storytext", "div.story"],
        title_selectors=["h1", "h2.story", "header h2"],
        fetch_network=fetch_network,
    )


def extract_lobsters(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Lobste.rs developer community extractor with native REST API fast path."""
    story_match = re.search(r"/s/([a-zA-Z0-9]+)", url)
    if fetch_network and story_match:
        story_id = story_match.group(1)
        api_url = f"https://lobste.rs/s/{story_id}.json"
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "")
                    author = data.get("submitter_user", "")
                    pub_date = data.get("created_at", "")
                    desc = data.get("description_plain") or data.get("description") or ""
                    story_url = data.get("url", "")
                    
                    body_parts = []
                    if story_url and not story_url.startswith("https://lobste.rs"):
                        body_parts.append(f'<p><strong>Source Link:</strong> <a href="{story_url}">{story_url}</a></p>')
                    if desc:
                        body_parts.append(f'<blockquote>{desc}</blockquote>')
                    
                    comments = data.get("comments") or []
                    if comments:
                        body_parts.append(f'<h3>Discussion Comments ({len(comments)})</h3>')
                        for c in comments[:25]:
                            c_user = c.get("commenting_user", "Anonymous")
                            c_text = c.get("comment_plain") or c.get("comment") or ""
                            if c_text:
                                body_parts.append(f'<div class="comment" style="margin-bottom:12px;padding:8px;border-left:3px solid #ccc;"><strong>@{c_user}:</strong><p>{c_text}</p></div>')
                    
                    return {
                        "title": title,
                        "body_html": "\n".join(body_parts) if body_parts else f"<p>{title}</p>",
                        "authors": [author] if author else [],
                        "published_date": pub_date,
                        "hero_image_url": "",
                        "canonical_url": url,
                        "site_name": "Lobste.rs",
                    }
        except Exception as e:
            logger.warning(f"Lobste.rs REST API fetch failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Lobste.rs",
        body_selectors=["div.comment_text", "div.story_content", "ol.comments", "div.comments", "article"],
        title_selectors=["h1", "span.link a"],
    )


def extract_9to5mac(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """9to5Mac / 9to5Google Apple and tech reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="9to5Mac",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_macrumors(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """MacRumors news and rumors extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="MacRumors",
        body_selectors=["div.content-body", "div.article", "article"],
        title_selectors=["h1"],
    )


def extract_androidcentral(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Android Central mobile technology extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Android Central",
        body_selectors=["div#article-body", "article"],
        title_selectors=["h1"],
    )


def extract_androidpolice(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Android Police ecosystem reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Android Police",
        body_selectors=["div.content-block-regular", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_xdadevelopers(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """XDA Developers software and modding community extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="XDA Developers",
        body_selectors=["div.content-block-regular", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_siliconangle(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """SiliconANGLE enterprise cloud and AI extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="SiliconANGLE",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_quantamagazine(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Quanta Magazine mathematics and physics journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Quanta Magazine",
        body_selectors=["div.post__content", "div.article__body", "article"],
        title_selectors=["h1"],
    )


def extract_newscientist(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """New Scientist international science weekly extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="New Scientist",
        body_selectors=["div.ArticleBody", "div.article-body", "article"],
        title_selectors=["h1"],
    )


# Category C: Geopolitics, Defense, Conflict & Strategic Studies (Sites 131–145)

def extract_kyivindependent(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Kyiv Independent Ukrainian English-language reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Kyiv Independent",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_themoscowtimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Moscow Times independent Russian press extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Moscow Times",
        body_selectors=["div.article__body", "article"],
        title_selectors=["h1"],
    )


def extract_meduza(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Meduza independent Russian/English news portal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Meduza",
        body_selectors=["div.GeneralMaterial-article", "article"],
        title_selectors=["h1"],
    )


def extract_bellingcat(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Bellingcat open-source intelligence and investigative journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Bellingcat",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_warontherocks(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """War on the Rocks foreign policy and defense commentary extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="War on the Rocks",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_defenseone(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Defense One national security and defense analysis extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Defense One",
        body_selectors=["div.story-text", "article"],
        title_selectors=["h1"],
    )


def extract_breakingdefense(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Breaking Defense military and aerospace analysis extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Breaking Defense",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_thediplomat(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Diplomat Asia-Pacific geopolitics extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Diplomat",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_haaretz(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Haaretz English Middle East reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Haaretz",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_jpost(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Jerusalem Post extractor with full JSON-LD articleBody priority."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Jerusalem Post",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
        min_json_ld_body_len=100,
    )


def extract_timesofisrael(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Times of Israel news portal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Times of Israel",
        body_selectors=["div.article-text", "article"],
        title_selectors=["h1"],
    )


def extract_almonitor(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Al-Monitor Middle East regional reporting extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Al-Monitor",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_middleeasteye(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Middle East Eye independent regional analysis extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Middle East Eye",
        body_selectors=["div.field--name-body", "article"],
        title_selectors=["h1"],
    )


def extract_taiwannews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Taiwan News English portal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Taiwan News",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_nknews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """NK News North Korea specialist analysis extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="NK News",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


# Category D: Finance, Markets, Venture & Crypto (Sites 146–160)

def extract_zerohedge(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ZeroHedge financial analysis and macroeconomic blog extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ZeroHedge",
        body_selectors=["div.node-content", "article"],
        title_selectors=["h1"],
    )


def extract_seekingalpha(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Seeking Alpha crowdsourced equity research extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Seeking Alpha",
        body_selectors=["div[data-test-id='article-content']", "article"],
        title_selectors=["h1"],
    )


def extract_fool(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Motley Fool retail investing advice extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Motley Fool",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_investopedia(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Investopedia financial education and definitions extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Investopedia",
        body_selectors=["div#article-body", "article"],
        title_selectors=["h1"],
    )


def extract_benzinga(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Benzinga real-time financial market news extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Benzinga",
        body_selectors=["div.article-content-body", "article"],
        title_selectors=["h1"],
    )


def extract_decrypt(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Decrypt Web3 and decentralized media extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Decrypt",
        body_selectors=["div.post-content", "article"],
        title_selectors=["h1"],
    )


def extract_blockworks(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Blockworks financial journalism for crypto investors extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Blockworks",
        body_selectors=["div.post-content", "article"],
        title_selectors=["h1"],
    )


def extract_theblock(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Block digital assets and institutional crypto research extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Block",
        body_selectors=["div.articleContent", "article"],
        title_selectors=["h1"],
    )


def extract_morningstar(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Morningstar independent investment research extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Morningstar",
        body_selectors=["div.article__body", "article"],
        title_selectors=["h1"],
    )


def extract_cityam(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """City A.M. London financial and business newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="City A.M.",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_pitchbook(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """PitchBook venture capital and private equity news extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="PitchBook",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_crunchbase_news(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Crunchbase News startup funding and venture trends extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Crunchbase News",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_americanbanker(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """American Banker retail banking and fintech extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="American Banker",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_pionline(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Pensions & Investments institutional money management extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Pensions & Investments",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_institutionalinvestor(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Institutional Investor global financial journal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Institutional Investor",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


# Category E: European, Middle Eastern & Global Major Presses (Sites 161–175)

def extract_elpais(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """El País Spanish daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="El País",
        body_selectors=["div.article_body", "article"],
        title_selectors=["h1"],
    )


def extract_elmundo(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """El Mundo extractor with full JSON-LD articleBody priority."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="El Mundo",
        body_selectors=["div.ue-c-article__body", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
        min_json_ld_body_len=100,
    )


def extract_corriere(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Corriere della Sera Italian daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Corriere della Sera",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_repubblica(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """La Repubblica Italian national daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="La Repubblica",
        body_selectors=["div.story__text", "article"],
        title_selectors=["h1"],
    )


def extract_zeit(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Die Zeit German national weekly newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Die Zeit",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_faz(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """FAZ (Frankfurter Allgemeine Zeitung) German daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Frankfurter Allgemeine Zeitung",
        body_selectors=["div.atc-Text", "article"],
        title_selectors=["h1"],
    )


def extract_nzz(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """NZZ (Neue Zürcher Zeitung) Swiss daily newspaper of record extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Neue Zürcher Zeitung",
        body_selectors=["div.article__body", "article"],
        title_selectors=["h1"],
    )


def extract_irishtimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Irish Times daily broadsheet newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Irish Times",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_scotsman(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Scotsman Scottish compact daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Scotsman",
        body_selectors=["div.markup", "article"],
        title_selectors=["h1"],
    )


def extract_arabnews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Arab News Saudi English-language daily extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Arab News",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_khaleejtimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Khaleej Times UAE English-language daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Khaleej Times",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_trtworld(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """TRT World international broadcast and news wire extractor with full JSON-LD articleBody priority."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="TRT World",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
        min_json_ld_body_len=100,
    )


def extract_folha(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Folha de S.Paulo Brazilian daily newspaper of record extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Folha de S.Paulo",
        body_selectors=["div.c-news__body", "article"],
        title_selectors=["h1"],
    )


def extract_clarin(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Clarín Argentine daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Clarín",
        body_selectors=["div.body-nota", "article"],
        title_selectors=["h1"],
    )


def extract_dailymaverick(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Daily Maverick South African online news publication extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Daily Maverick",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


# Category F: US & Commonwealth Metropolitan & Regional Papers (Sites 176–188)

def extract_chicagotribune(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Chicago Tribune metropolitan daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Chicago Tribune",
        body_selectors=["div.story-content", "article"],
        title_selectors=["h1"],
    )


def extract_bostonglobe(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Boston Globe regional daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Boston Globe",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_sfchronicle(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """San Francisco Chronicle Bay Area daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="San Francisco Chronicle",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_seattletimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Seattle Times Pacific Northwest daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Seattle Times",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_dallasnews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Dallas Morning News Texas metropolitan daily extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Dallas Morning News",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_miamiherald(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Miami Herald South Florida daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Miami Herald",
        body_selectors=["div.story-body", "article"],
        title_selectors=["h1"],
    )


def extract_ajc(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Atlanta Journal-Constitution Southeast daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Atlanta Journal-Constitution",
        body_selectors=["div.story-content", "article"],
        title_selectors=["h1"],
    )


def extract_houstonchronicle(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Houston Chronicle Texas daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Houston Chronicle",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_inquirer(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Philadelphia Inquirer daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Philadelphia Inquirer",
        body_selectors=["div.inq-article-body", "article"],
        title_selectors=["h1"],
    )


def extract_denverpost(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Denver Post Rocky Mountain daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Denver Post",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_thestar(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Toronto Star Canadian metropolitan daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Toronto Star",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_nationalpost(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """National Post Canadian national broadsheet extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="National Post",
        body_selectors=["div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_nzherald(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The New Zealand Herald national daily newspaper extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The New Zealand Herald",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


# Category G: Korean & Japanese Specialized & Independent Media (Sites 189–200)

def extract_pressian(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Pressian Korean progressive online news extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Pressian",
        body_selectors=["div#articleBody", "div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_mediatoday(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """MediaToday Korean media criticism and analysis extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="MediaToday",
        body_selectors=["div#article-view-content-div", "article"],
        title_selectors=["h1"],
    )


def extract_sisajournal(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Sisa Journal Korean weekly investigative journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Sisa Journal",
        body_selectors=["div.article-view-content-div", "div#article-view-content-div", "article"],
        title_selectors=["h1"],
    )


def extract_bloter(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Bloter Korean digital technology and internet media extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Bloter",
        body_selectors=["div.article-body", "div#article-view-content-div", "article"],
        title_selectors=["h1"],
    )


def extract_dongascience(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """DongA Science Korean popular science portal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="DongA Science",
        body_selectors=["div.article-content", "div.view_text", "article"],
        title_selectors=["h1"],
    )


def extract_newspim(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """NewsPim Korean economic and political news wire extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="NewsPim",
        body_selectors=["div#news-contents", "div.news_contents", "article"],
        title_selectors=["h1"],
    )


def extract_newstapa(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Newstapa (Korea Center for Investigative Journalism) extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Newstapa",
        body_selectors=["div.article-body", "div.content-body", "article"],
        title_selectors=["h1"],
    )


def extract_toyokeizai(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Toyo Keizai Japanese business and economic journalism extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Toyo Keizai",
        body_selectors=["div.article-body", "div.body-text", "article"],
        title_selectors=["h1"],
    )


def extract_diamond(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Diamond Online Japanese business and management media extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Diamond Online",
        body_selectors=["div.article-body", "div#article-body", "article"],
        title_selectors=["h1"],
    )


def extract_president(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """President Online Japanese business leadership and career magazine extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="President Online",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_itmedia(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ITmedia Japanese comprehensive IT and technology portal extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ITmedia",
        body_selectors=["div#cmsBody", "div.cms-body", "article"],
        title_selectors=["h1"],
    )


def extract_ascii(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ASCII.jp Japanese computing and digital hobbyist media extractor."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ASCII.jp",
        body_selectors=["div.article-body", "div#article-body", "article"],
        title_selectors=["h1"],
    )
'''

NEW_ADAPTERS_ENTRIES = '''
    # Batch 4: Sites 101–200 Additions
    # Category A: Premium Paywalled & Thought Leadership
    "newyorker.com": extract_newyorker,
    "theinformation.com": extract_theinformation,
    "puck.news": extract_pucknews,
    "hbr.org": extract_hbr,
    "technologyreview.com": extract_technologyreview,
    "foreignaffairs.com": extract_foreignaffairs,
    "foreignpolicy.com": extract_foreignpolicy,
    "theintercept.com": extract_theintercept,
    "slate.com": extract_slate,
    "salon.com": extract_salon,
    "thedailybeast.com": extract_thedailybeast,
    "motherjones.com": extract_motherjones,
    "vanityfair.com": extract_vanityfair,

    # Category B: Tech, Hardware, AI, Dev & Science Communities
    "theregister.com": extract_theregister,
    "tomshardware.com": extract_tomshardware,
    "techradar.com": extract_techradar,
    "thenextweb.com": extract_thenextweb,
    "hackernoon.com": extract_hackernoon,
    "slashdot.org": extract_slashdot,
    "lobste.rs": extract_lobsters,
    "9to5mac.com": extract_9to5mac,
    "9to5google.com": extract_9to5mac,
    "electrek.co": extract_9to5mac,
    "macrumors.com": extract_macrumors,
    "androidcentral.com": extract_androidcentral,
    "androidpolice.com": extract_androidpolice,
    "xda-developers.com": extract_xdadevelopers,
    "siliconangle.com": extract_siliconangle,
    "quantamagazine.org": extract_quantamagazine,
    "newscientist.com": extract_newscientist,

    # Category C: Geopolitics, Defense, Conflict & Strategic Studies
    "kyivindependent.com": extract_kyivindependent,
    "themoscowtimes.com": extract_themoscowtimes,
    "meduza.io": extract_meduza,
    "bellingcat.com": extract_bellingcat,
    "warontherocks.com": extract_warontherocks,
    "defenseone.com": extract_defenseone,
    "breakingdefense.com": extract_breakingdefense,
    "thediplomat.com": extract_thediplomat,
    "haaretz.com": extract_haaretz,
    "jpost.com": extract_jpost,
    "timesofisrael.com": extract_timesofisrael,
    "al-monitor.com": extract_almonitor,
    "middleeasteye.net": extract_middleeasteye,
    "taiwannews.com.tw": extract_taiwannews,
    "nknews.org": extract_nknews,

    # Category D: Finance, Markets, Venture & Crypto
    "zerohedge.com": extract_zerohedge,
    "seekingalpha.com": extract_seekingalpha,
    "fool.com": extract_fool,
    "investopedia.com": extract_investopedia,
    "benzinga.com": extract_benzinga,
    "decrypt.co": extract_decrypt,
    "blockworks.co": extract_blockworks,
    "theblock.co": extract_theblock,
    "morningstar.com": extract_morningstar,
    "cityam.com": extract_cityam,
    "pitchbook.com": extract_pitchbook,
    "news.crunchbase.com": extract_crunchbase_news,
    "crunchbase.com": extract_crunchbase_news,
    "americanbanker.com": extract_americanbanker,
    "pionline.com": extract_pionline,
    "institutionalinvestor.com": extract_institutionalinvestor,

    # Category E: European, Middle Eastern & Global Major Presses
    "elpais.com": extract_elpais,
    "elmundo.es": extract_elmundo,
    "corriere.it": extract_corriere,
    "repubblica.it": extract_repubblica,
    "zeit.de": extract_zeit,
    "faz.net": extract_faz,
    "nzz.ch": extract_nzz,
    "irishtimes.com": extract_irishtimes,
    "scotsman.com": extract_scotsman,
    "arabnews.com": extract_arabnews,
    "khaleejtimes.com": extract_khaleejtimes,
    "trtworld.com": extract_trtworld,
    "folha.uol.com.br": extract_folha,
    "clarin.com": extract_clarin,
    "dailymaverick.co.za": extract_dailymaverick,

    # Category F: US & Commonwealth Metropolitan & Regional Papers
    "chicagotribune.com": extract_chicagotribune,
    "bostonglobe.com": extract_bostonglobe,
    "sfchronicle.com": extract_sfchronicle,
    "seattletimes.com": extract_seattletimes,
    "dallasnews.com": extract_dallasnews,
    "miamiherald.com": extract_miamiherald,
    "ajc.com": extract_ajc,
    "houstonchronicle.com": extract_houstonchronicle,
    "inquirer.com": extract_inquirer,
    "denverpost.com": extract_denverpost,
    "thestar.com": extract_thestar,
    "nationalpost.com": extract_nationalpost,
    "nzherald.co.nz": extract_nzherald,

    # Category G: Korean & Japanese Specialized & Independent Media
    "pressian.com": extract_pressian,
    "mediatoday.co.kr": extract_mediatoday,
    "sisajournal.com": extract_sisajournal,
    "bloter.net": extract_bloter,
    "dongascience.com": extract_dongascience,
    "newspim.com": extract_newspim,
    "newstapa.org": extract_newstapa,
    "toyokeizai.net": extract_toyokeizai,
    "diamond.jp": extract_diamond,
    "president.jp": extract_president,
    "itmedia.co.jp": extract_itmedia,
    "ascii.jp": extract_ascii,
'''

NEW_HINTS_ENTRIES = '''
    # Batch 4: Sites 101–200 Additions
    # Category A: Premium Paywalled & Thought Leadership
    "newyorker.com": {
        "wait_for_selector": "div[data-testid='BodyWrapper'], article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler", "button[data-testid='modal-close']"],
    },
    "theinformation.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "puck.news": {
        "wait_for_selector": "div.post-content, article",
        "dismiss_selectors": ["button[aria-label='Close']"],
    },
    "hbr.org": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },
    "technologyreview.com": {
        "wait_for_selector": "div[data-component='article-body'], article",
        "dismiss_selectors": [".cookie-banner button"],
    },
    "foreignaffairs.com": {
        "wait_for_selector": "div.article-body-content, article",
        "dismiss_selectors": ["button.agree-button", ".eu-cookie-compliance-secondary-button"],
    },
    "foreignpolicy.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "theintercept.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["button.close-modal"],
    },
    "slate.com": {
        "wait_for_selector": "div.story-card__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "salon.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "thedailybeast.com": {
        "wait_for_selector": "div.BodyContent, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "motherjones.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "vanityfair.com": {
        "wait_for_selector": "div[data-testid='BodyWrapper'], article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category B: Tech, Hardware, AI, Dev & Science Communities
    "theregister.com": {
        "wait_for_selector": "div#body, article",
        "dismiss_selectors": ["button[aria-label='Accept all']"],
    },
    "tomshardware.com": {
        "wait_for_selector": "div#article-body, article",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },
    "techradar.com": {
        "wait_for_selector": "div#article-body, article",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },
    "thenextweb.com": {
        "wait_for_selector": "div.c-articleContent, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "hackernoon.com": {
        "wait_for_selector": "div.story-container, article",
        "dismiss_selectors": ["button.close"],
    },
    "slashdot.org": {
        "wait_for_selector": "div.body, article",
        "dismiss_selectors": [],
    },
    "lobste.rs": {
        "wait_for_selector": "div.comment_text, div.story_content, article",
        "dismiss_selectors": [],
    },
    "9to5mac.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "9to5google.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "electrek.co": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "macrumors.com": {
        "wait_for_selector": "div.content-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "androidcentral.com": {
        "wait_for_selector": "div#article-body, article",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },
    "androidpolice.com": {
        "wait_for_selector": "div.content-block-regular, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "xda-developers.com": {
        "wait_for_selector": "div.content-block-regular, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "siliconangle.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "quantamagazine.org": {
        "wait_for_selector": "div.post__content, article",
        "dismiss_selectors": [],
    },
    "newscientist.com": {
        "wait_for_selector": "div.ArticleBody, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category C: Geopolitics, Defense, Conflict & Strategic Studies
    "kyivindependent.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["button[aria-label='Close']"],
    },
    "themoscowtimes.com": {
        "wait_for_selector": "div.article__body, article",
        "dismiss_selectors": ["button.cookie-policy__btn"],
    },
    "meduza.io": {
        "wait_for_selector": "div.GeneralMaterial-article, article",
        "dismiss_selectors": ["button.GeneralMaterial-close"],
    },
    "bellingcat.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "warontherocks.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["button.agree-button"],
    },
    "defenseone.com": {
        "wait_for_selector": "div.story-text, article",
        "dismiss_selectors": ["button.close"],
    },
    "breakingdefense.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "thediplomat.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["button.close-modal"],
    },
    "haaretz.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "jpost.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "timesofisrael.com": {
        "wait_for_selector": "div.article-text, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "al-monitor.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "middleeasteye.net": {
        "wait_for_selector": "div.field--name-body, article",
        "dismiss_selectors": ["button.agree-button"],
    },
    "taiwannews.com.tw": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": [],
    },
    "nknews.org": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category D: Finance, Markets, Venture & Crypto
    "zerohedge.com": {
        "wait_for_selector": "div.node-content, article",
        "dismiss_selectors": ["button.agree-button"],
    },
    "seekingalpha.com": {
        "wait_for_selector": "div[data-test-id='article-content'], article",
        "dismiss_selectors": ["button[data-test-id='modal-close-button']"],
    },
    "fool.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "investopedia.com": {
        "wait_for_selector": "div#article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "benzinga.com": {
        "wait_for_selector": "div.article-content-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "decrypt.co": {
        "wait_for_selector": "div.post-content, article",
        "dismiss_selectors": ["button[aria-label='Accept']"],
    },
    "blockworks.co": {
        "wait_for_selector": "div.post-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "theblock.co": {
        "wait_for_selector": "div.articleContent, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "morningstar.com": {
        "wait_for_selector": "div.article__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "cityam.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "pitchbook.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "news.crunchbase.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "crunchbase.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "americanbanker.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "pionline.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "institutionalinvestor.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category E: European, Middle Eastern & Global Major Presses
    "elpais.com": {
        "wait_for_selector": "div.article_body, article",
        "dismiss_selectors": ["#didomi-notice-agree-button"],
    },
    "elmundo.es": {
        "wait_for_selector": "div.ue-c-article__body, article",
        "dismiss_selectors": ["#didomi-notice-agree-button", "#onetrust-accept-btn-handler"],
    },
    "corriere.it": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["button#privacy-agree"],
    },
    "repubblica.it": {
        "wait_for_selector": "div.story__text, article",
        "dismiss_selectors": ["button#privacy-agree"],
    },
    "zeit.de": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["button.sp_choice_type_11"],
    },
    "faz.net": {
        "wait_for_selector": "div.atc-Text, article",
        "dismiss_selectors": ["button.sp_choice_type_11"],
    },
    "nzz.ch": {
        "wait_for_selector": "div.article__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "irishtimes.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "scotsman.com": {
        "wait_for_selector": "div.markup, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "arabnews.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "khaleejtimes.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "trtworld.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "folha.uol.com.br": {
        "wait_for_selector": "div.c-news__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "clarin.com": {
        "wait_for_selector": "div.body-nota, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "dailymaverick.co.za": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category F: US & Commonwealth Metropolitan & Regional Papers
    "chicagotribune.com": {
        "wait_for_selector": "div.story-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "bostonglobe.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["button.meter-modal__close", "#onetrust-accept-btn-handler"],
    },
    "sfchronicle.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["button.fancybox-close-small", "#onetrust-accept-btn-handler"],
    },
    "seattletimes.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "dallasnews.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "miamiherald.com": {
        "wait_for_selector": "div.story-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "ajc.com": {
        "wait_for_selector": "div.story-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "houstonchronicle.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "inquirer.com": {
        "wait_for_selector": "div.inq-article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "denverpost.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "thestar.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "nationalpost.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "nzherald.co.nz": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Category G: Korean & Japanese Specialized & Independent Media
    "pressian.com": {
        "wait_for_selector": "div#articleBody, article",
        "dismiss_selectors": [],
    },
    "mediatoday.co.kr": {
        "wait_for_selector": "div#article-view-content-div, article",
        "dismiss_selectors": [],
    },
    "sisajournal.com": {
        "wait_for_selector": "div.article-view-content-div, article",
        "dismiss_selectors": [],
    },
    "bloter.net": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
    "dongascience.com": {
        "wait_for_selector": "div.article-content, article",
        "dismiss_selectors": [],
    },
    "newspim.com": {
        "wait_for_selector": "div#news-contents, article",
        "dismiss_selectors": [],
    },
    "newstapa.org": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
    "toyokeizai.net": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
    "diamond.jp": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
    "president.jp": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
    "itmedia.co.jp": {
        "wait_for_selector": "div#cmsBody, article",
        "dismiss_selectors": [],
    },
    "ascii.jp": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": [],
    },
'''

def main():
    filepath = "server/adapters.py"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Insert NEW_EXTRACTORS right before "# 6. Central Registries"
    target_split = "# 6. Central Registries (SITE_ADAPTERS & BROWSER_HINTS)"
    if target_split not in content:
        print("ERROR: Target split not found in adapters.py")
        sys.exit(1)
    
    parts = content.split(target_split, 1)
    content = parts[0] + NEW_EXTRACTORS + "\n\n" + target_split + parts[1]

    # 2. Insert NEW_ADAPTERS_ENTRIES at the end of SITE_ADAPTERS (before closing bracket "}\n\n\nBROWSER_HINTS")
    target_site_adapters_end = '    "smartbrief.com": extract_smartbrief,\n}'
    if target_site_adapters_end not in content:
        print("ERROR: target_site_adapters_end not found")
        sys.exit(1)

    content = content.replace(
        target_site_adapters_end,
        '    "smartbrief.com": extract_smartbrief,\n' + NEW_ADAPTERS_ENTRIES + "}"
    )

    # 3. Insert NEW_HINTS_ENTRIES at the end of BROWSER_HINTS
    target_browser_hints_end = '    "smartbrief.com": {\n        "wait_for_selector": "div.brief-content, article",\n        "dismiss_selectors": ["#onetrust-accept-btn-handler"],\n    },\n}'
    if target_browser_hints_end not in content:
        print("ERROR: target_browser_hints_end not found")
        sys.exit(1)

    content = content.replace(
        target_browser_hints_end,
        '    "smartbrief.com": {\n        "wait_for_selector": "div.brief-content, article",\n        "dismiss_selectors": ["#onetrust-accept-btn-handler"],\n    },\n' + NEW_HINTS_ENTRIES + "}"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated server/adapters.py with Sites 101–200!")

if __name__ == "__main__":
    main()
