"""
Unit and integration tests for VPS Archive Lens Modular Site Adapters (adapters.py).
Tests all 30 target platforms, domain resolution, browser automation hints,
and direct structured feed parsing.
"""

import unittest
from bs4 import BeautifulSoup

from server.adapters import (
    SITE_ADAPTERS,
    BROWSER_HINTS,
    normalize_domain,
    get_adapter_for_url,
    get_browser_hints,
    extract_article,
    extract_msn,
    extract_yahoo,
    extract_google_news,
    extract_smartnews,
    extract_substack,
    extract_medium,
    extract_reddit,
    extract_rss_syndication,
    extract_naver_news,
    extract_daum_news,
    extract_nate_news,
    extract_yna,
    extract_chosun,
    extract_joongang,
    extract_donga,
    extract_hankookilbo,
    extract_topstarnews,
    extract_tenasia,
    extract_reuters,
    extract_apnews,
    extract_bbc,
    extract_theguardian,
    extract_bloomberg,
    extract_wsj,
    extract_ft,
    extract_nytimes,
    extract_washingtonpost,
    extract_cnn,
    extract_cnbc,
    extract_theverge,
    extract_generic_fallback,
)


class TestAdaptersRegistry(unittest.TestCase):
    """Verify registry mappings and browser hints for all Top 30 platforms."""

    TOP_200_DOMAINS = [
        # Batch 1 (1–30 Original)
        "msn.com",
        "news.yahoo.com",
        "finance.yahoo.com",
        "news.google.com",
        "smartnews.com",
        "substack.com",
        "medium.com",
        "reddit.com",
        "feedly.com",
        "n.news.naver.com",
        "v.daum.net",
        "news.nate.com",
        "yna.co.kr",
        "chosun.com",
        "joongang.co.kr",
        "donga.com",
        "hankookilbo.com",
        "topstarnews.net",
        "tenasia.co.kr",
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "theguardian.com",
        "bloomberg.com",
        "wsj.com",
        "ft.com",
        "nytimes.com",
        "washingtonpost.com",
        "cnn.com",
        "cnbc.com",
        "theverge.com",
        # Batch 1 Additions (31–38)
        "news.ycombinator.com",
        "flipboard.com",
        "getpocket.com",
        "apple.news",
        "dev.to",
        "bsky.app",
        "ghost.org",
        "wordpress.org",
        # Batch 2 Additions (39–48)
        "mk.co.kr",
        "hankyung.com",
        "hani.co.kr",
        "khan.co.kr",
        "segye.com",
        "news1.kr",
        "newsis.com",
        "news.yahoo.co.jp",
        "asia.nikkei.com",
        "asahi.com",
        # Batch 3 Additions (49–60)
        "arstechnica.com",
        "wired.com",
        "techcrunch.com",
        "theatlantic.com",
        "politico.com",
        "forbes.com",
        "economist.com",
        "propublica.org",
        "latimes.com",
        "aljazeera.com",
        "dw.com",
        "npr.org",
        # Batch 4 Additions (61–72)
        "usatoday.com",
        "timesofindia.indiatimes.com",
        "thehindu.com",
        "smh.com.au",
        "abc.net.au",
        "cbc.ca",
        "theglobeandmail.com",
        "scmp.com",
        "straitstimes.com",
        "france24.com",
        "lemonde.fr",
        "spiegel.de",
        # Batch 5 Additions (73–82)
        "engadget.com",
        "gizmodo.com",
        "mashable.com",
        "cnet.com",
        "venturebeat.com",
        "coindesk.com",
        "cointelegraph.com",
        "sciencedaily.com",
        "phys.org",
        "polygon.com",
        # Batch 6 Additions (83–92)
        "businessinsider.com",
        "marketwatch.com",
        "barrons.com",
        "fortune.com",
        "fastcompany.com",
        "inc.com",
        "spglobal.com",
        "thehill.com",
        "axios.com",
        "semafor.com",
        # Batch 7 Additions (93–100)
        "yomiuri.co.jp",
        "mainichi.jp",
        "english.kyodonews.net",
        "mt.co.kr",
        "edaily.co.kr",
        "ohmynews.com",
        "alltop.com",
        "smartbrief.com",
        # Batch 4: Sites 101–200 Additions
        # Category A: Premium Paywalled & Thought Leadership
        "newyorker.com",
        "theinformation.com",
        "puck.news",
        "hbr.org",
        "technologyreview.com",
        "foreignaffairs.com",
        "foreignpolicy.com",
        "theintercept.com",
        "slate.com",
        "salon.com",
        "thedailybeast.com",
        "motherjones.com",
        "vanityfair.com",
        # Category B: Tech, Hardware, AI, Dev & Science Communities
        "theregister.com",
        "tomshardware.com",
        "techradar.com",
        "thenextweb.com",
        "hackernoon.com",
        "slashdot.org",
        "lobste.rs",
        "9to5mac.com",
        "9to5google.com",
        "electrek.co",
        "macrumors.com",
        "androidcentral.com",
        "androidpolice.com",
        "xda-developers.com",
        "siliconangle.com",
        "quantamagazine.org",
        "newscientist.com",
        # Category C: Geopolitics, Defense, Conflict & Strategic Studies
        "kyivindependent.com",
        "themoscowtimes.com",
        "meduza.io",
        "bellingcat.com",
        "warontherocks.com",
        "defenseone.com",
        "breakingdefense.com",
        "thediplomat.com",
        "haaretz.com",
        "jpost.com",
        "timesofisrael.com",
        "al-monitor.com",
        "middleeasteye.net",
        "taiwannews.com.tw",
        "nknews.org",
        # Category D: Finance, Markets, Venture & Crypto
        "zerohedge.com",
        "seekingalpha.com",
        "fool.com",
        "investopedia.com",
        "benzinga.com",
        "decrypt.co",
        "blockworks.co",
        "theblock.co",
        "morningstar.com",
        "cityam.com",
        "pitchbook.com",
        "news.crunchbase.com",
        "crunchbase.com",
        "americanbanker.com",
        "pionline.com",
        "institutionalinvestor.com",
        # Category E: European, Middle Eastern & Global Major Presses
        "elpais.com",
        "elmundo.es",
        "corriere.it",
        "repubblica.it",
        "zeit.de",
        "faz.net",
        "nzz.ch",
        "irishtimes.com",
        "scotsman.com",
        "arabnews.com",
        "khaleejtimes.com",
        "trtworld.com",
        "folha.uol.com.br",
        "clarin.com",
        "dailymaverick.co.za",
        # Category F: US & Commonwealth Metropolitan & Regional Papers
        "chicagotribune.com",
        "bostonglobe.com",
        "sfchronicle.com",
        "seattletimes.com",
        "dallasnews.com",
        "miamiherald.com",
        "ajc.com",
        "houstonchronicle.com",
        "inquirer.com",
        "denverpost.com",
        "thestar.com",
        "nationalpost.com",
        "nzherald.co.nz",
        # Category G: Korean & Japanese Specialized & Independent Media
        "pressian.com",
        "mediatoday.co.kr",
        "sisajournal.com",
        "bloter.net",
        "dongascience.com",
        "newspim.com",
        "newstapa.org",
        "toyokeizai.net",
        "diamond.jp",
        "president.jp",
        "itmedia.co.jp",
        "ascii.jp",
    ]

    def test_all_top_200_registered(self):
        for domain in self.TOP_200_DOMAINS:
            with self.subTest(domain=domain):
                adapter = get_adapter_for_url(f"https://{domain}/article/sample")
                self.assertIsNotNone(adapter, f"Missing adapter for {domain}")

    def test_browser_hints_registered(self):
        for domain in self.TOP_200_DOMAINS:
            with self.subTest(domain=domain):
                hints = get_browser_hints(f"https://{domain}/article/sample")
                self.assertIn("wait_for_selector", hints)
                self.assertIn("dismiss_selectors", hints)
                self.assertTrue(len(hints["wait_for_selector"]) > 0)
                self.assertIsInstance(hints["dismiss_selectors"], list)

    def test_subdomain_resolution(self):
        # Substack custom subdomain
        adapter = get_adapter_for_url("https://astralcodexten.substack.com/p/test-post")
        self.assertEqual(adapter, extract_substack)

        # Medium custom subdomain
        adapter = get_adapter_for_url("https://towardsdatascience.medium.com/test-article")
        self.assertEqual(adapter, extract_medium)

        # Reddit old/sh subdomains
        adapter = get_adapter_for_url("https://old.reddit.com/r/technology/comments/123/test")
        self.assertEqual(adapter, extract_reddit)

        # BBC co.uk
        adapter = get_adapter_for_url("https://www.bbc.co.uk/news/articles/12345")
        self.assertEqual(adapter, extract_bbc)

        # CNN edition
        adapter = get_adapter_for_url("https://edition.cnn.com/2026/09/09/world/index.html")
        self.assertEqual(adapter, extract_cnn)


class TestGroupAAdapters(unittest.TestCase):
    """Group A: Major Aggregators & Portals."""

    def test_extract_msn_dom(self):
        html = """
        <html>
          <body>
            <h1>Microsoft Unveils New Cloud AI Features</h1>
            <article>
              <p>Microsoft today announced enhanced cloud capabilities for enterprise workloads.</p>
              <p>The rollouts will begin immediately across major datacenters globally.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_msn("https://www.msn.com/en-us/news/tech/sample/ar-BB123", soup, html, fetch_network=False)
        self.assertIn("Microsoft Unveils", res["title"])
        self.assertIn("<p>Microsoft today announced", res["body_html"])
        self.assertIn("<p>The rollouts will begin", res["body_html"])

    def test_extract_yahoo_json_ld_and_dom(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "NewsArticle",
              "headline": "Markets Rally on Tech Earnings",
              "datePublished": "2026-09-09T14:00:00Z",
              "author": {"@type": "Person", "name": "Jane Doe"},
              "image": "https://s.yimg.com/sample.jpg"
            }
            </script>
          </head>
          <body>
            <div class="col-body">
              <p>Stocks gained sharply as major tech companies posted strong quarterly numbers.</p>
              <p>Investors welcomed the optimistic forward guidance.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_yahoo("https://finance.yahoo.com/news/markets-rally.html", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Markets Rally on Tech Earnings")
        self.assertEqual(res["published_date"], "2026-09-09T14:00:00Z")
        self.assertEqual(res["authors"], ["Jane Doe"])
        self.assertIn("<p>Stocks gained sharply", res["body_html"])

    def test_extract_google_news(self):
        html = """
        <html>
          <head>
            <link rel="canonical" href="https://example.com/original-source">
            <title>Global Summit Concludes - Google News</title>
          </head>
          <body>
            <h1>Global Summit Concludes</h1>
            <article>
              <p>World leaders agreed on updated carbon transition frameworks at the summit.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_google_news("https://news.google.com/articles/sample", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Global Summit Concludes")
        self.assertEqual(res["canonical_url"], "https://example.com/original-source")
        self.assertIn("<p>World leaders agreed", res["body_html"])

    def test_extract_smartnews(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Breakthrough in Battery Tech Announced",
              "datePublished": "2026-09-09",
              "author": [{"name": "Dr. Smith"}]
            }
            </script>
          </head>
          <body>
            <div class="article-body">
              <p>Researchers have demonstrated a solid-state cell with double the energy density.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_smartnews("https://www.smartnews.com/en/article/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Breakthrough in Battery Tech Announced")
        self.assertEqual(res["authors"], ["Dr. Smith"])
        self.assertIn("<p>Researchers have demonstrated", res["body_html"])

    def test_extract_substack_dom(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "BlogPosting",
              "headline": "The Future of Autonomous Agents",
              "datePublished": "2026-09-08T10:00:00Z",
              "author": {"name": "AI Researcher"}
            }
            </script>
          </head>
          <body>
            <div class="available-content">
              <p>Autonomous agents are progressing from isolated tool executors to full collaborators.</p>
              <p>This post discusses key architectural challenges and solutions.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_substack("https://example.substack.com/p/autonomous-agents", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "The Future of Autonomous Agents")
        self.assertEqual(res["authors"], ["AI Researcher"])
        self.assertIn("<p>Autonomous agents are progressing", res["body_html"])

    def test_extract_medium_dom(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Building Robust Microservices in Go",
              "datePublished": "2026-09-07",
              "author": "Gopher Expert"
            }
            </script>
          </head>
          <body>
            <article>
              <p>Writing reliable distributed services requires thoughtful error boundaries.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_medium("https://medium.com/@user/go-microservices", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Building Robust Microservices in Go")
        self.assertEqual(res["authors"], ["Gopher Expert"])
        self.assertIn("<p>Writing reliable distributed", res["body_html"])

    def test_extract_reddit_dom(self):
        html = """
        <html>
          <body>
            <shreddit-post post-title="Open source release of our new deep learning framework" author="researcher99">
              <div slot="text-body">
                <p>We are excited to open source our lightweight framework for mobile edge inference.</p>
                <p>Check out our GitHub benchmarks and pre-trained weights.</p>
              </div>
            </shreddit-post>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_reddit("https://reddit.com/r/MachineLearning/comments/xyz123/post", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Open source release of our new deep learning framework")
        self.assertEqual(res["authors"], ["researcher99"])
        self.assertIn("<p>We are excited to open source", res["body_html"])

    def test_extract_rss_syndication(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <item>
              <title>New Space Telescope Deployed</title>
              <link>https://space.example.com/telescope</link>
              <dc:creator>Astronomer Team</dc:creator>
              <pubDate>Wed, 09 Sep 2026 12:00:00 GMT</pubDate>
              <content:encoded><![CDATA[<p>The space telescope has reached its destination orbit and opened its primary mirrors.</p>]]></content:encoded>
            </item>
          </channel>
        </rss>
        """
        soup = BeautifulSoup(xml, "xml")
        res = extract_rss_syndication("https://space.example.com/rss", soup, xml, fetch_network=False)
        self.assertEqual(res["title"], "New Space Telescope Deployed")
        self.assertEqual(res["authors"], ["Astronomer Team"])
        self.assertEqual(res["canonical_url"], "https://space.example.com/telescope")
        self.assertIn("<p>The space telescope has reached", res["body_html"])


class TestGroupBAdapters(unittest.TestCase):
    """Group B: Korean & East Asian News Outlets."""

    def test_extract_naver_news(self):
        html = """
        <html>
          <body>
            <h2 id="title_area">정부, 신규 R&D 예산 대폭 확대 발표</h2>
            <span class="media_end_head_info_datestamp_time" data-date-time="2026-09-09 14:30:00">2026.09.09. 오후 2:30</span>
            <em class="media_end_head_journalist_name">홍길동 기자</em>
            <div id="dic_area">
              <span class="end_photo_org"><img data-src="https://imgnews.pstatic.net/sample.jpg?type=w800" alt="정부청사"></span>
              정부는 내년도 인공지능 및 첨단 바이오 분야 R&D 예산을 역대 최대 규모로 편성한다고 밝혔다.<br>
              이번 투자로 국가 핵심 기술 경쟁력이 한층 강화될 전망이다.
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_naver_news("https://n.news.naver.com/article/001/0012345", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "정부, 신규 R&D 예산 대폭 확대 발표")
        self.assertEqual(res["published_date"], "2026-09-09 14:30:00")
        self.assertEqual(res["authors"], ["홍길동 기자"])
        self.assertEqual(res["hero_image_url"], "https://imgnews.pstatic.net/sample.jpg")
        self.assertIn("<p>정부는 내년도", res["body_html"])

    def test_extract_daum_news(self):
        html = """
        <html>
          <head>
            <meta property="og:image" content="https://img1.daumcdn.net/thumb/S1200x630/?fname=https://t1.daumcdn.net/news/original.jpg">
          </head>
          <body>
            <h3 class="tit_view">국회 본회의, 민생 법안 다수 처리</h3>
            <span class="num_date">2026. 9. 9. 15:45</span>
            <span class="txt_info">이영희, 김철수</span>
            <div class="article_view">
              <p>여야는 본회의를 열고 주요 민생 법안을 여야 합의로 가결했다.</p>
              <p>법안 시행에 따라 서민 지원 혜택이 확대된다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_daum_news("https://v.daum.net/v/2026090912345", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "국회 본회의, 민생 법안 다수 처리")
        self.assertEqual(res["published_date"], "2026. 9. 9. 15:45")
        self.assertEqual(res["authors"], ["이영희", "김철수"])
        self.assertEqual(res["hero_image_url"], "https://t1.daumcdn.net/news/original.jpg")
        self.assertIn("<p>여야는 본회의를 열고", res["body_html"])

    def test_extract_nate_news(self):
        html = """
        <html>
          <body>
            <h3 class="viewHeadline">가을 태풍 경로 북상 중… 주말 전국 비</h3>
            <span class="firstDate">기사전송 2026-09-09 17:00</span>
            <span class="reporterNameCopyright">박기자</span>
            <div id="realContents">
              <p>기상청은 제14호 태풍이 주말 한반도 인근으로 진입할 것이라고 예보했다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_nate_news("https://news.nate.com/view/20260909n12345", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "가을 태풍 경로 북상 중… 주말 전국 비")
        self.assertEqual(res["published_date"], "기사전송 2026-09-09 17:00")
        self.assertEqual(res["authors"], ["박기자"])
        self.assertIn("<p>기상청은 제14호", res["body_html"])

    def test_extract_yna(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "한국은행, 기준금리 동결 결정",
              "datePublished": "2026-09-09T10:30:00+09:00",
              "author": {"@type": "Person", "name": "연합 송고"}
            }
            </script>
          </head>
          <body>
            <article class="story-news">
              <p>한국은행 금융통화위원회는 물가와 가계부채를 고려해 현 금리 수준을 유지하기로 했다.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_yna("https://www.yna.co.kr/view/AKR202609090001", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "한국은행, 기준금리 동결 결정")
        self.assertEqual(res["published_date"], "2026-09-09T10:30:00+09:00")
        self.assertEqual(res["authors"], ["연합 송고"])
        self.assertIn("<p>한국은행 금융통화위원회는", res["body_html"])

    def test_extract_chosun_arc_fusion(self):
        html = """
        <html>
          <head>
            <script id="fusion-metadata">
            window.Fusion=window.Fusion||{};
            Fusion.globalContent={
              "headlines": {"basic": "조선일보 창간 기념 특별 기획"},
              "display_date": "2026-09-09T06:00:00Z",
              "credits": {"by": [{"name": "조선 취재팀"}]},
              "promo_items": {"basic": {"url": "https://images.chosun.com/hero.jpg"}},
              "content_elements": [
                {"type": "text", "content": "100년 역사를 돌아보고 새로운 미래 기술을 조망합니다."},
                {"type": "text", "content": "글로벌 석학들의 심층 인터뷰를 연재합니다."}
              ]
            };
            </script>
          </head>
          <body>
            <h1>Fallback</h1>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_chosun("https://www.chosun.com/national/2026/09/09/ABC/", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "조선일보 창간 기념 특별 기획")
        self.assertEqual(res["published_date"], "2026-09-09T06:00:00Z")
        self.assertEqual(res["authors"], ["조선 취재팀"])
        self.assertEqual(res["hero_image_url"], "https://images.chosun.com/hero.jpg")
        self.assertIn("<p>100년 역사를 돌아보고", res["body_html"])

    def test_extract_joongang(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "중앙일보 단독 인터뷰",
              "datePublished": "2026-09-09T11:00:00+09:00",
              "author": [{"@type": "Person", "name": "김기자"}]
            }
            </script>
          </head>
          <body>
            <div id="article_body">
              <p>혁신 창업 생태계를 이끄는 스타트업 대표와의 단독 대담 내용입니다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_joongang("https://www.joongang.co.kr/article/12345", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "중앙일보 단독 인터뷰")
        self.assertEqual(res["authors"], ["김기자"])
        self.assertIn("<p>혁신 창업 생태계를", res["body_html"])

    def test_extract_donga(self):
        html = """
        <html>
          <body>
            <h1 class="article_title">동아일보 사설: 미래 교육 혁신</h1>
            <div class="title_foot"><span class="date">2026-09-09 03:00</span></div>
            <span class="reporter">논설위원실</span>
            <section class="news_view">
              <p>인공지능 시대를 맞아 디지털 문해력 교육 체계의 전면 개편이 시급하다.</p>
            </section>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_donga("https://www.donga.com/news/article/all/20260909/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "동아일보 사설: 미래 교육 혁신")
        self.assertEqual(res["published_date"], "2026-09-09 03:00")
        self.assertEqual(res["authors"], ["논설위원실"])
        self.assertIn("<p>인공지능 시대를 맞아", res["body_html"])

    def test_extract_hankookilbo(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "한국일보 기획 보도",
              "datePublished": "2026-09-09T18:00:00+09:00",
              "author": [{"@type": "Person", "name": "이서희"}]
            }
            </script>
          </head>
          <body>
            <div class="col-main">
              <p class="editor-p">현대 사회의 세대 갈등 해법을 모색하는 특별 좌담회가 개최되었다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_hankookilbo("https://www.hankookilbo.com/news/article/A123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "한국일보 기획 보도")
        self.assertEqual(res["authors"], ["이서희"])
        self.assertIn("<p>현대 사회의 세대", res["body_html"])

    def test_extract_topstarnews(self):
        html = """
        <html>
          <body>
            <h3 class="heading">인기 드라마 시즌2 제작 확정 발표</h3>
            <ul class="info-text">
              <li>연예부 기자</li>
              <li>2026.09.09 16:20</li>
            </ul>
            <div id="article-view-content-div">
              <p>팬들의 큰 성원에 힘입어 주연 배우들이 모두 합류한 시즌2 촬영이 시작된다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_topstarnews("https://www.topstarnews.net/news/articleView.html?idxno=123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "인기 드라마 시즌2 제작 확정 발표")
        self.assertEqual(res["authors"], ["연예부 기자"])
        self.assertEqual(res["published_date"], "2026.09.09 16:20")
        self.assertIn("<p>팬들의 큰 성원에", res["body_html"])

    def test_extract_tenasia(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "텐아시아 뮤직 어워즈 개최 안내",
              "datePublished": "2026-09-09",
              "author": [{"name": "K-pop 담당"}]
            }
            </script>
          </head>
          <body>
            <article class="article-view">
              <p>올해를 빛낸 K-pop 아티스트들이 총출동하는 연례 음악 축제가 열린다.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_tenasia("https://www.tenasia.co.kr/article/202609090001", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "텐아시아 뮤직 어워즈 개최 안내")
        self.assertEqual(res["authors"], ["K-pop 담당"])
        self.assertIn("<p>올해를 빛낸", res["body_html"])


class TestGroupCAdapters(unittest.TestCase):
    """Group C: International & Business Publications."""

    def test_extract_reuters(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Central Banks Coordinate on Liquidity Safeguards",
              "datePublished": "2026-09-09T08:00:00Z",
              "author": [{"name": "Reuters Staff"}]
            }
            </script>
          </head>
          <body>
            <div data-testid="ArticleBody">
              <p>Major central banks announced reciprocal currency swap arrangements today.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_reuters("https://www.reuters.com/business/finance/central-banks-swap", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Central Banks Coordinate on Liquidity Safeguards")
        self.assertEqual(res["authors"], ["Reuters Staff"])
        self.assertIn("<p>Major central banks", res["body_html"])

    def test_extract_apnews(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "International Climate Pact Finalized",
              "datePublished": "2026-09-09T12:00:00Z",
              "author": [{"name": "AP Science Writer"}]
            }
            </script>
          </head>
          <body>
            <div class="RichTextStoryBody">
              <p>Delegates approved binding emissions targets after marathon overnight sessions.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_apnews("https://apnews.com/article/climate-pact-123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "International Climate Pact Finalized")
        self.assertIn("<p>Delegates approved binding", res["body_html"])

    def test_extract_bbc(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "ReportageNewsArticle",
              "headline": "Historic Discovery at Archaeological Dig",
              "datePublished": "2026-09-09T09:00:00Z",
              "author": [{"name": "BBC Science Reporter"}]
            }
            </script>
          </head>
          <body>
            <article>
              <p>Archaeologists have uncovered an intact Roman villa with pristine mosaics.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_bbc("https://www.bbc.com/news/articles/roman-villa", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Historic Discovery at Archaeological Dig")
        self.assertIn("<p>Archaeologists have uncovered", res["body_html"])

    def test_extract_theguardian(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Renewable Power Surpasses Fossil Fuels in Europe",
              "datePublished": "2026-09-09T07:30:00Z",
              "author": [{"name": "Energy Correspondent"}]
            }
            </script>
          </head>
          <body>
            <div data-gu-name="body">
              <p>Wind and solar generation reached record output during the past quarter.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_theguardian("https://www.theguardian.com/environment/2026/sep/09/renewable-power", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Renewable Power Surpasses Fossil Fuels in Europe")
        self.assertIn("<p>Wind and solar generation", res["body_html"])

    def test_extract_bloomberg(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Semiconductor Demand Surges on Data Center Buildouts",
              "datePublished": "2026-09-09",
              "author": [{"name": "Tech Reporter"}]
            }
            </script>
          </head>
          <body>
            <div data-component="article-body">
              <p>Order backlogs for high-bandwidth memory chips continue to expand.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_bloomberg("https://www.bloomberg.com/news/articles/2026-09-09/semiconductor-demand", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Semiconductor Demand Surges on Data Center Buildouts")
        self.assertIn("<p>Order backlogs for", res["body_html"])

    def test_extract_wsj(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Treasury Yields Move Lower as Inflation Cools",
              "datePublished": "2026-09-09",
              "author": [{"name": "Markets Desk"}]
            }
            </script>
          </head>
          <body>
            <section subscriptions-section="content">
              <p>Bond prices rallied across the curve following positive wholesale price index figures.</p>
            </section>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_wsj("https://www.wsj.com/economy/treasury-yields", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Treasury Yields Move Lower as Inflation Cools")
        self.assertIn("<p>Bond prices rallied", res["body_html"])

    def test_extract_ft(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Global Trade Flows Rebound Following Supply Chain Easing",
              "datePublished": "2026-09-09",
              "author": [{"name": "Trade Editor"}]
            }
            </script>
          </head>
          <body>
            <div class="article__content-body">
              <p>Container shipping rates have stabilized as port congestion cleared across Pacific routes.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_ft("https://www.ft.com/content/sample-id", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Global Trade Flows Rebound Following Supply Chain Easing")
        self.assertIn("<p>Container shipping rates", res["body_html"])

    def test_extract_nytimes(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "City Unveils Modernized Transit Fleet",
              "datePublished": "2026-09-09T13:00:00Z",
              "author": [{"name": "Urban Affairs Reporter"}]
            }
            </script>
          </head>
          <body>
            <section name="articleBody">
              <p>The transit authority introduced 200 all-electric subway and bus vehicles into service.</p>
            </section>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_nytimes("https://www.nytimes.com/2026/09/09/nyregion/transit-fleet.html", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "City Unveils Modernized Transit Fleet")
        self.assertIn("<p>The transit authority introduced", res["body_html"])

    def test_extract_washingtonpost_arc_fusion(self):
        html = """
        <html>
          <head>
            <script id="fusion-metadata">
            window.Fusion=window.Fusion||{};
            Fusion.globalContent={
              "headlines": {"basic": "Senate Confirms Key Diplomatic Nominees"},
              "display_date": "2026-09-09T16:00:00Z",
              "credits": {"by": [{"name": "Congressional Bureau"}]},
              "content_elements": [
                {"type": "text", "content": "Lawmakers approved ambassadorial posts in a bipartisan vote."},
                {"type": "text", "content": "The nominees will assume their posts ahead of the fall summit."}
              ]
            };
            </script>
          </head>
          <body>
            <h1>Fallback</h1>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_washingtonpost("https://www.washingtonpost.com/politics/2026/09/09/senate-vote", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Senate Confirms Key Diplomatic Nominees")
        self.assertEqual(res["authors"], ["Congressional Bureau"])
        self.assertIn("<p>Lawmakers approved ambassadorial", res["body_html"])

    def test_extract_cnn_json_ld_articlebody(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Aviation Investigators Conclude Field Analysis",
              "datePublished": "2026-09-09T15:00:00Z",
              "author": [{"name": "Aviation Team"}],
              "articleBody": "Federal investigators completed on-site documentation of the cargo flight incident today.\n\nFlight data recorders have been transferred to headquarters for decoding."
            }
            </script>
          </head>
          <body>
            <div class="article__content">
              <p>Federal investigators completed on-site documentation.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_cnn("https://www.cnn.com/2026/09/09/aviation-report", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Aviation Investigators Conclude Field Analysis")
        self.assertIn("<p>Federal investigators completed", res["body_html"])
        self.assertIn("<p>Flight data recorders have been", res["body_html"])

    def test_extract_cnbc(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Venture Capital Inflows Accelerate in AI Sector",
              "datePublished": "2026-09-09",
              "author": [{"name": "Silicon Valley Bureau"}]
            }
            </script>
          </head>
          <body>
            <div class="ArticleBody-articleBody">
              <p>Funding rounds for foundational AI startups reached a new quarterly record.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_cnbc("https://www.cnbc.com/2026/09/09/vc-funding-ai.html", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Venture Capital Inflows Accelerate in AI Sector")
        self.assertIn("<p>Funding rounds for", res["body_html"])

    def test_extract_theverge(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Next-Gen Smartphone Camera Sensors Analyzed",
              "datePublished": "2026-09-09",
              "author": [{"name": "Hardware Editor"}]
            }
            </script>
          </head>
          <body>
            <div class="duet--article--article-body-component">
              <p>New 1-inch mobile sensors are closing the gap with dedicated compact cameras.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_theverge("https://www.theverge.com/2026/09/09/camera-sensors", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Next-Gen Smartphone Camera Sensors Analyzed")
        self.assertIn("<p>New 1-inch mobile sensors", res["body_html"])


class TestHighLevelExtractArticle(unittest.TestCase):
    """Test unified extract_article function and fallback behaviors."""

    def test_extract_article_routes_correctly(self):
        html = """
        <html>
          <head><title>General Article Page</title></head>
          <body>
            <h1>General News Headline</h1>
            <article>
              <p>This is a generic paragraph from an unlisted news blog or publication site.</p>
              <p>The extractor successfully falls back to high-grade semantic HTML normalization.</p>
            </article>
          </body>
        </html>
        """
        res = extract_article("https://unknown-blog.org/news/post1", html, fetch_network=False)
        self.assertEqual(res["title"], "General News Headline")
        self.assertIn("<p>This is a generic paragraph", res["body_html"])
        self.assertIn("<p>The extractor successfully", res["body_html"])

    def test_extract_article_empty_html_resilience(self):
        res = extract_article("https://example.com/broken", "", fetch_network=False)
        self.assertIsInstance(res, dict)
        self.assertIn("title", res)
        self.assertIn("body_html", res)
        self.assertIn("authors", res)


class TestNewPlatformExtractors(unittest.TestCase):
    """Unit tests for newly added platform extractors across Batches 1 to 7."""

    def test_extract_hackernews(self):
        from server.adapters import extract_hackernews
        html = """
        <html>
          <body>
            <table>
              <tr><td class="title"><span class="titleline"><a href="https://example.com/show-hn">Show HN: Offline Archiver</a></span></td></tr>
              <tr><td class="subtext"><span class="hnuser">antigravity</span> <span class="age"><a href="item?id=12345">2 hours ago</a></span></td></tr>
              <tr><td class="toptext">This is an Ask or Show HN description text for testing.</td></tr>
            </table>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_hackernews("https://news.ycombinator.com/item?id=12345", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Show HN: Offline Archiver")
        self.assertIn("<p>This is an Ask or Show HN", res["body_html"])
        self.assertEqual(res["authors"], ["antigravity"])

    def test_extract_devto(self):
        from server.adapters import extract_devto
        html = """
        <html>
          <body>
            <h1 class="crayons-article__title">Building Web Scrapers with Modern Best Practices</h1>
            <div id="article-body">
              <p>Python and BeautifulSoup make content extraction reliable and maintainable.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_devto("https://dev.to/author/modern-scraping", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Building Web Scrapers with Modern Best Practices")
        self.assertIn("<p>Python and BeautifulSoup", res["body_html"])

    def test_extract_mk(self):
        from server.adapters import extract_mk
        html = """
        <html>
          <body>
            <h2 class="top_title">매일경제 주요 헤드라인 기사</h2>
            <div class="news_cnt_detail_wrap">
              <p>국내 증시가 상승 마감하며 긍정적인 투자 심리를 반영했습니다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_mk("https://mk.co.kr/news/economy/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "매일경제 주요 헤드라인 기사")
        self.assertIn("<p>국내 증시가 상승", res["body_html"])

    def test_extract_yahoojp(self):
        from server.adapters import extract_yahoojp
        html = """
        <html>
          <body>
            <header><h1>Yahoo!ニュース</h1></header>
            <article>
              <h1>日本の経済動向と今後の展望について</h1>
              <div class="article_body">
                <p>日銀の金融政策決定会合が終了し、新たな方針が発表されました。</p>
              </div>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_yahoojp("https://news.yahoo.co.jp/articles/xyz", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "日本の経済動向と今後の展望について")
        self.assertNotIn("Yahoo!ニュース", res["title"])
        self.assertIn("<p>日銀の金融政策決定会合", res["body_html"])

    def test_extract_timesofindia_json_ld(self):
        from server.adapters import extract_timesofindia
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "India Launches Landmark Renewable Energy Initiative",
              "articleBody": "New Delhi announced an extensive expansion of solar and wind generation capacity today, signaling rapid acceleration toward green infrastructure targets over the next decade. Industry analysts praised the aggressive policy incentives outlined during the summit."
            }
            </script>
          </head>
          <body>
            <h1>Fallback H1</h1>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_timesofindia("https://timesofindia.indiatimes.com/india/energy/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "India Launches Landmark Renewable Energy Initiative")
        self.assertIn("<p>New Delhi announced", res["body_html"])

    def test_extract_mashable_json_ld(self):
        from server.adapters import extract_mashable
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "The Ultimate Guide to Modern Smart Home Gear",
              "articleBody": "Smart home standards are evolving with Matter protocol support expanding across major device manufacturers worldwide. Here are our top-rated smart switches and hubs for 2026."
            }
            </script>
          </head>
          <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_mashable("https://mashable.com/article/smart-home-guide", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "The Ultimate Guide to Modern Smart Home Gear")
        self.assertIn("<p>Smart home standards", res["body_html"])

    def test_extract_techcrunch_dom(self):
        from server.adapters import extract_techcrunch
        html = """
        <html>
          <body>
            <h1 class="article__title">Autonomous Logistics Startup Raises $50M Series B</h1>
            <div class="entry-content">
              <p>The round was led by premier venture funds with participation from strategic industrial partners.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_techcrunch("https://techcrunch.com/2026/09/09/autonomous-logistics-50m", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Autonomous Logistics Startup Raises $50M Series B")
        self.assertIn("<p>The round was led", res["body_html"])

    def test_extract_axios_dom(self):
        from server.adapters import extract_axios
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Why AI Infrastructure is Driving Regional Tech Hubs"
            }
            </script>
          </head>
          <body>
            <div data-cy="story-body">
              <p>Data center expansion across the Midwest is spurring local economic growth and specialized talent pipelines.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_axios("https://www.axios.com/2026/09/09/ai-infrastructure-hubs", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Why AI Infrastructure is Driving Regional Tech Hubs")
        self.assertIn("<p>Data center expansion", res["body_html"])

    def test_extract_scmp_json_ld(self):
        from server.adapters import extract_scmp
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "Hong Kong Enhances Cross-Border Trade Technology Infrastructure",
              "articleBody": "Hong Kong's financial authority announced modernized digital clearing corridors today to streamline cross-border enterprise settlements. The development is designed to reduce friction for international supply chains throughout the region."
            }
            </script>
          </head>
          <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_scmp("https://scmp.com/economy/global/article/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Hong Kong Enhances Cross-Border Trade Technology Infrastructure")
        self.assertIn("financial authority announced modernized digital clearing", res["body_html"])

    def test_extract_hani(self):
        from server.adapters import extract_hani
        html = """
        <html>
          <body>
            <h1 class="title">한겨레 단독: 기후위기 대응 특별 보고서 공개</h1>
            <div class="article-text">
              <p>탄소 배출 저감을 위한 신규 에너지 전환 정책이 국회 심의에 돌입했습니다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_hani("https://www.hani.co.kr/arti/economy/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "한겨레 단독: 기후위기 대응 특별 보고서 공개")
        self.assertIn("<p>탄소 배출 저감을", res["body_html"])

    def test_extract_nikkei(self):
        from server.adapters import extract_nikkei
        html = """
        <html>
          <body>
            <h1 class="c-article_title">Japan Advanced Semiconductor Materials Gain Global Demand</h1>
            <div class="c-article_body">
              <p>Specialized packaging silicon and wafer substrates are seeing surge bookings from international fabrication plants.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_nikkei("https://asia.nikkei.com/Business/Tech/semiconductors", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Japan Advanced Semiconductor Materials Gain Global Demand")
        self.assertIn("<p>Specialized packaging silicon", res["body_html"])

    def test_extract_usatoday(self):
        from server.adapters import extract_usatoday
        html = """
        <html>
          <body>
            <h1 class="headline">New High-Speed Rail Corridors Receive Federal Grant Approvals</h1>
            <div class="gnt_ar_b">
              <p>Transportation officials announced billions in matching infrastructure investments across key intercity transit routes.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_usatoday("https://usatoday.com/story/news/transit/123", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "New High-Speed Rail Corridors Receive Federal Grant Approvals")
        self.assertIn("<p>Transportation officials announced", res["body_html"])

    def test_extract_coindesk(self):
        from server.adapters import extract_coindesk
        html = """
        <html>
          <body>
            <h1 class="typography__StyledTypography">Decentralized Settlement Layer Upgrades Mainnet Protocol</h1>
            <div class="content-wrapper">
              <p>Zero-knowledge verification algorithms have been finalized following extensive cryptographic testnet auditing.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_coindesk("https://coindesk.com/tech/2026/09/09/zk-mainnet", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Decentralized Settlement Layer Upgrades Mainnet Protocol")
        self.assertIn("<p>Zero-knowledge verification", res["body_html"])

    def test_extract_sciencedaily(self):
        from server.adapters import extract_sciencedaily
        html = """
        <html>
          <body>
            <h1 id="headline">Marine Biologists Discover Novel Deep-Sea Enzyme Mechanism</h1>
            <div id="story_text">
              <p>Extreme barophilic organisms employ unique peptide folding patterns capable of bioremediation applications.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_sciencedaily("https://sciencedaily.com/releases/2026/09/123.htm", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Marine Biologists Discover Novel Deep-Sea Enzyme Mechanism")
        self.assertIn("<p>Extreme barophilic organisms", res["body_html"])



    def test_extract_newyorker_json_ld(self):
        from server.adapters import extract_newyorker
        long_essay = "<p>This is a complete longform essay analyzing narrative journalism in the 21st century.</p>" * 20
        html = f"""
        <html>
          <head>
            <script type="application/ld+json">
            {{
              "@context": "https://schema.org",
              "@type": "NewsArticle",
              "headline": "The Art of the Longform Essay in the Digital Era",
              "datePublished": "2026-09-09T10:00:00Z",
              "author": [{{"@type": "Person", "name": "David Remnick"}}],
              "articleBody": "{long_essay}"
            }}
            </script>
          </head>
          <body>
            <div data-testid="BodyWrapper">
              <p>Short preview text truncated by web paywall.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_newyorker("https://newyorker.com/magazine/2026/09/essay", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "The Art of the Longform Essay in the Digital Era")
        self.assertIn("analyzing narrative journalism", res["body_html"])
        self.assertEqual(res["authors"], ["David Remnick"])

    def test_extract_hbr_json_ld(self):
        from server.adapters import extract_hbr
        case_study = "Strategic agility allows established firms to navigate sudden macroeconomic turbulence. " * 25
        html = f"""
        <html>
          <head>
            <script type="application/ld+json">
            {{
              "@context": "https://schema.org",
              "@type": "NewsArticle",
              "headline": "Strategic Agility in Uncertain Macroeconomic Environments",
              "datePublished": "2026-09-09T08:00:00Z",
              "author": [{{"@type": "Person", "name": "Michael E. Porter"}}],
              "articleBody": "{case_study}"
            }}
            </script>
          </head>
          <body>
            <div class="article-body">
              <p>Preview snippet only.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_hbr("https://hbr.org/2026/09/strategic-agility", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Strategic Agility in Uncertain Macroeconomic Environments")
        self.assertIn("Strategic agility allows established firms", res["body_html"])

    def test_extract_lobsters_dom(self):
        from server.adapters import extract_lobsters
        html = """
        <html>
          <body>
            <span class="link"><a href="/s/abc123">Optimizing SQLite for Embedded Systems</a></span>
            <div class="story_content">
              <p>Here is an exploration of custom VFS implementations for low-power microcontroller environments.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_lobsters("https://lobste.rs/s/abc123/optimizing_sqlite", soup, html, fetch_network=False)
        self.assertIn("Optimizing SQLite", res["title"])
        self.assertIn("custom VFS implementations", res["body_html"])

    def test_extract_slashdot_dom(self):
        from server.adapters import extract_slashdot
        html = """
        <html>
          <body>
            <h2 class="story">Open Source Kernel Architecture Passes New Formal Verification Milestone</h2>
            <div class="body">
              <p>Developers working on the seL4 microkernel ecosystem have verified new multi-core memory capabilities.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_slashdot("https://slashdot.org/story/26/09/09/sel4-milestone", soup, html, fetch_network=False)
        self.assertIn("Open Source Kernel Architecture", res["title"])
        self.assertIn("seL4 microkernel", res["body_html"])

    def test_extract_kyivindependent(self):
        from server.adapters import extract_kyivindependent
        html = """
        <html>
          <body>
            <h1>Reconstruction Grants Allocated for Regional Grid Modernization</h1>
            <div class="article-content">
              <p>International partners signed technical agreements to reinforce high-voltage substations across the power network.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_kyivindependent("https://kyivindependent.com/grid-modernization-2026", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Reconstruction Grants Allocated for Regional Grid Modernization")
        self.assertIn("reinforce high-voltage substations", res["body_html"])

    def test_extract_zerohedge(self):
        from server.adapters import extract_zerohedge
        html = """
        <html>
          <body>
            <h1>Global Liquidity Indicators Signal Central Bank Balance Sheet Shift</h1>
            <div class="node-content">
              <p>Cross-border sovereign yields adjusted as overnight repo facility usage reached seasonal equilibrium.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_zerohedge("https://zerohedge.com/markets/global-liquidity-shift", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "Global Liquidity Indicators Signal Central Bank Balance Sheet Shift")
        self.assertIn("Cross-border sovereign yields", res["body_html"])

    def test_extract_elpais(self):
        from server.adapters import extract_elpais
        html = """
        <html>
          <body>
            <h1>La Cumbre Iberoamericana acuerda nuevos fondos para la transición ecológica</h1>
            <div class="article_body">
              <p>Los jefes de Estado y de Gobierno reunidos han ratificado un plan conjunto de inversión en energías renovables.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_elpais("https://elpais.com/internacional/2026-09-09/cumbre-fondos.html", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "La Cumbre Iberoamericana acuerda nuevos fondos para la transición ecológica")
        self.assertIn("ratificado un plan conjunto", res["body_html"])

    def test_extract_pressian(self):
        from server.adapters import extract_pressian
        html = """
        <html>
          <body>
            <h1>기후 위기 대응을 위한 재생에너지 분산형 전력망 구축 방안</h1>
            <div id="articleBody">
              <p>지역 단위의 분산 전원과 스마트 그리드 연계를 통해 탄소 배출 저감 효과를 극대화할 수 있다는 정책 연구 결과가 제시되었다.</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_pressian("https://pressian.com/pages/articles/20260909001", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "기후 위기 대응을 위한 재생에너지 분산형 전력망 구축 방안")
        self.assertIn("지역 단위의 분산 전원", res["body_html"])

    def test_extract_toyokeizai(self):
        from server.adapters import extract_toyokeizai
        html = """
        <html>
          <body>
            <h1>次世代半導体コンソーシアム、2ナノプロセス試作ラインの稼働を開始</h1>
            <div class="article-body">
              <p>国内ファウンドリ拠点で最先端露光装置の搬入が完了し、次世代コンピューティング向けチップの試験製造が始まった。</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        res = extract_toyokeizai("https://toyokeizai.net/articles/-/823456", soup, html, fetch_network=False)
        self.assertEqual(res["title"], "次世代半導体コンソーシアム、2ナノプロセス試作ラインの稼働を開始")
        self.assertIn("次世代コンピューティング向けチップ", res["body_html"])


if __name__ == "__main__":
    unittest.main()
