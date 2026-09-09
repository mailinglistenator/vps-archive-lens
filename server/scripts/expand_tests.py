import re
import sys

NEW_DOMAINS = '''        # Batch 4: Sites 101–200 Additions
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
'''

NEW_TEST_METHODS = '''
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
'''

def main():
    filepath = "server/tests/test_adapters.py"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update TOP_100_DOMAINS to TOP_200_DOMAINS and insert NEW_DOMAINS
    target_needle = '        "smartbrief.com",\n    ]'
    if target_needle not in content:
        print("ERROR: target_needle not found in test_adapters.py")
        sys.exit(1)

    content = content.replace("TOP_100_DOMAINS = [", "TOP_200_DOMAINS = [")
    content = content.replace("test_all_top_100_registered", "test_all_top_200_registered")
    content = content.replace("for domain in self.TOP_100_DOMAINS:", "for domain in self.TOP_200_DOMAINS:")

    content = content.replace(
        target_needle,
        '        "smartbrief.com",\n' + NEW_DOMAINS + "    ]"
    )

    # 2. Add new test methods at end of class TestBatchExtractors (before if __name__ == "__main__":)
    main_needle = 'if __name__ == "__main__":'
    if main_needle not in content:
        print("ERROR: main_needle not found")
        sys.exit(1)

    content = content.replace(main_needle, NEW_TEST_METHODS + "\n\n" + main_needle)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully expanded test_adapters.py to TOP_200_DOMAINS with new test fixtures!")

if __name__ == "__main__":
    main()
