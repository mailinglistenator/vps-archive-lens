import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from server.app import (
    extract_heuristic_takeaways,
    render_reader_template,
    generate_ai_reader,
    STORAGE_DIR
)

class TestAIReader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.patcher = patch("server.app.STORAGE_DIR", Path(self.test_dir))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_extract_heuristic_takeaways_basic(self):
        text = """
The rapid advancements in artificial intelligence are reshaping scientific computing across biology and physics.
Researchers around the world have demonstrated that neural networks can predict protein structures with near-experimental accuracy, drastically reducing experimental timelines from years to minutes.

Historically, structural biologists spent decades solving crystalline configurations through X-ray crystallography and cryo-EM methods. The introduction of deep learning architectures has accelerated pharmaceutical pipelines and opened unprecedented avenues for targeted cancer therapeutics.

In conclusion, over 75% of surveyed biotechnology research labs report adopting automated predictive modeling into their everyday drug discovery workflows, marking a permanent paradigm shift in modern biochemistry.
"""
        bullets = extract_heuristic_takeaways(text, title="AI in Biology")
        self.assertGreaterEqual(len(bullets), 1)
        self.assertLessEqual(len(bullets), 3)
        for b in bullets:
            self.assertTrue(len(b) >= 30)
            self.assertTrue(b.endswith("."))

    def test_extract_heuristic_takeaways_noise_filtering(self):
        text = """
Click here to subscribe to our daily newsletter for more updates!
Follow us on Twitter and Facebook for breaking news alerts.

Artificial intelligence models achieved a record 94% accuracy score on the standardized benchmark examination this quarter.
The breakthrough highlights significant progress in multi-step mathematical reasoning and symbolic logic pipelines.

All rights reserved. Copyright 2026.
"""
        bullets = extract_heuristic_takeaways(text)
        self.assertTrue(any("94%" in b or "Artificial intelligence" in b for b in bullets))
        for b in bullets:
            self.assertNotIn("Click here", b)
            self.assertNotIn("Follow us", b)
            self.assertNotIn("Copyright", b)

    def test_extract_heuristic_takeaways_short_text(self):
        short = "Too short text."
        bullets = extract_heuristic_takeaways(short)
        self.assertEqual(bullets, [])

    def test_render_reader_template_with_takeaways(self):
        html = render_reader_template(
            snapshot_id="test_snap_1",
            title="Test Title",
            author="Jane Doe",
            date="2026-09-09",
            image="",
            orig_url="https://example.com/test",
            domain="example.com",
            reading_time=3,
            provider_name="Nous Solar Pro",
            summary_bullets=["Point 1.", "Point 2.", "Point 3."],
            body_html="<p>Article body content.</p>"
        )
        self.assertIn('<div class="takeaways-box">', html)
        self.assertIn("Point 1.", html)
        self.assertIn("Point 2.", html)
        self.assertIn("Point 3.", html)
        self.assertIn("Nous Solar Pro", html)

    def test_render_reader_template_without_takeaways(self):
        html = render_reader_template(
            snapshot_id="test_snap_2",
            title="Stub Title",
            author="",
            date="",
            image="",
            orig_url="https://example.com/stub",
            domain="example.com",
            reading_time=1,
            provider_name="",
            summary_bullets=[],
            body_html="<p>Short snippet.</p>"
        )
        self.assertNotIn('<div class="takeaways-box">', html)
        self.assertIn("<!-- no-takeaways -->", html)

    def test_generate_ai_reader_extractive_fallback(self):
        snap_id = "test_snapshot_extractive"
        raw_html = """<!DOCTYPE html>
<html>
<head><title>Historical Analysis of Space Missions</title><base href="https://example.com/article"></head>
<body>
  <article>
    <h1>Historical Analysis of Space Missions</h1>
    <p>The early Apollo lunar missions represented one of the most ambitious engineering undertakings in human civilization. Over 400,000 scientists, engineers, and technicians contributed to the development of the Saturn V launch vehicle.</p>
    <p>Subsequent missions during the shuttle era transitioned space exploration into routine orbital maintenance, deploying the Hubble Space Telescope and assembling the International Space Station across dozens of joint international flights.</p>
    <p>Looking ahead to the upcoming decade, public-private partnerships have reduced orbital payload launch costs by more than 70%, enabling permanent lunar base architecture planning.</p>
  </article>
</body>
</html>"""
        raw_file = Path(self.test_dir) / f"{snap_id}.html"
        raw_file.write_text(raw_html, encoding="utf-8")

        # Mock LLM failing / timing out to trigger extractive fallback
        with patch("server.app.get_hermes_ai_provider", return_value=None):
            reader_file = generate_ai_reader(snap_id)
            self.assertTrue(reader_file.is_file())
            content = reader_file.read_text(encoding="utf-8")
            self.assertIn("takeaways-box", content)
            self.assertIn("Key Takeaways (Extractive)", content)
            self.assertIn("Apollo lunar missions", content)

    def test_generate_ai_reader_cache_invalidation_for_missing_takeaways(self):
        snap_id = "test_snapshot_stale_cache"
        raw_html = """<!DOCTYPE html>
<html>
<head><title>Quantum Computing Breakthrough</title><base href="https://example.com/article"></head>
<body>
  <article>
    <h1>Quantum Computing Breakthrough</h1>
    <p>Physicists have constructed a fault-tolerant topological quantum circuit operating at room temperature with high logical fidelity. The experimental architecture suppresses environmental decoherence by several orders of magnitude.</p>
    <p>This breakthrough eliminates the historic cryogenic cooling requirement that previously restricted quantum systems to specialized research facilities, allowing commercial data center deployment.</p>
    <p>Industry analysts forecast that room-temperature quantum computing will accelerate chemical catalysis simulations and cryptographic research by 2028.</p>
  </article>
</body>
</html>"""
        raw_file = Path(self.test_dir) / f"{snap_id}.html"
        raw_file.write_text(raw_html, encoding="utf-8")

        # Simulate an old, stale reader HTML file that was cached WITHOUT takeaways
        stale_reader_html = """<!DOCTYPE html>
<html>
<head><title>Quantum Computing Breakthrough — Reader View</title></head>
<body>
  <main class="article-container">
    <h1>Quantum Computing Breakthrough</h1>
    <article class="article-body">
      <p>Physicists have constructed a fault-tolerant topological quantum circuit operating at room temperature...</p>
    </article>
  </main>
</body>
</html>"""
        reader_file = Path(self.test_dir) / f"{snap_id}_reader.html"
        reader_file.write_text(stale_reader_html, encoding="utf-8")

        # Call generate_ai_reader without force_refresh.
        # It should detect missing takeaways-box and invalidate the stale cache automatically!
        with patch("server.app.get_hermes_ai_provider", return_value=None):
            updated_reader = generate_ai_reader(snap_id, force_refresh=False)
            updated_content = updated_reader.read_text(encoding="utf-8")
            self.assertIn("takeaways-box", updated_content)
            self.assertIn("Key Takeaways (Extractive)", updated_content)

if __name__ == "__main__":
    unittest.main()
