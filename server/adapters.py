"""
VPS Archive Lens - Modular Site Adapters (adapters.py)

Standardized content extraction and browser automation hints across Top 30
news aggregators, portals, and digital publications.

Provides:
- SITE_ADAPTERS: Mapping of normalized domain patterns to extractor functions.
- BROWSER_HINTS: Registry of wait_for_selector and dismiss_selectors for Playwright.
- extract_article(url, html=None, fetch_network=True): High-level entrypoint returning
  a standardized article dictionary.
- get_browser_hints(url): Helper to resolve Playwright hydration and notice rules.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag
import httpx

logger = logging.getLogger("archive_lens.adapters")

# Normalized extraction dictionary schema:
# {
#     "title": str,
#     "body_html": str,       # Clean, semantic HTML (<p>...</p>, <h2>...</h2>, <blockquote>...</blockquote>)
#     "authors": list[str],
#     "published_date": str,  # ISO-8601 or normalized string
#     "hero_image_url": str,
#     "canonical_url": str,
#     "site_name": str,
# }


# ==============================================================================
# 1. Normalization & Utility Helpers
# ==============================================================================

def normalize_domain(url: str) -> str:
    """Extract and normalize domain hostname from a URL."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # Strip port if present
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        return netloc
    except Exception:
        return ""


def clean_text(text: Optional[str]) -> str:
    """Clean and unescape whitespace from a string."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    return re.sub(r"\s+", " ", unescaped).strip()


def text_to_semantic_html(text: str) -> str:
    """Convert raw text or markdown-style text into semantic HTML paragraphs."""
    if not text:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    cleaned = []
    for p in paras:
        escaped = html.escape(p)
        cleaned.append(f"<p>{escaped}</p>")
    return "\n".join(cleaned)


def sanitize_element_to_html(container: Tag) -> str:
    """
    Extract semantic HTML elements from a BeautifulSoup container Tag,
    preserving <p>, <h2>, <h3>, <h4>, <blockquote>, <ul>, <ol>, <li>,
    and converting lazy-loaded <img> tags into standard high-resolution images.
    Gracefully handles containers with <br> separators instead of <p> tags.
    """
    if not container:
        return ""

    # Remove script, style, noscript, svg, form, iframe, ads, and widgets
    for unwanted in container.find_all(
        ["script", "style", "noscript", "svg", "form", "iframe", "button", "input", "nav"]
    ):
        unwanted.decompose()

    # Also remove common ad and social widget classes
    for ad_node in container.find_all(
        class_=re.compile(
            r"ad-|advertisement|social-share|banner|related-articles|outbrain|taboola|newsletter",
            re.IGNORECASE,
        )
    ):
        ad_node.decompose()

    # Replace <br> tags with double newlines in text nodes
    for br in container.find_all("br"):
        br.replace_with("\n\n")

    p_tags = container.find_all("p")
    p_text_len = sum(len(p.get_text(strip=True)) for p in p_tags)

    output_blocks: List[str] = []
    seen_texts = set()

    # If container has few or empty <p> tags, extract direct text lines into paragraphs
    if p_text_len < 60:
        # Extract images first
        for img in container.find_all("img"):
            src = resolve_image_url(img)
            alt = html.escape(img.get("alt", "").strip())
            if src and not any(src in b for b in output_blocks):
                output_blocks.append(f'<figure><img src="{html.escape(src)}" alt="{alt}" loading="lazy"></figure>')
            img.decompose()

        raw_txt = container.get_text()
        for chunk in raw_txt.split("\n\n"):
            clean_chunk = chunk.strip()
            if len(clean_chunk) >= 5:
                output_blocks.append(f"<p>{html.escape(clean_chunk)}</p>")

        return "\n".join(output_blocks)

    for el in container.find_all(["p", "h2", "h3", "h4", "blockquote", "ul", "ol", "figure", "img"]):
        tag_name = el.name.lower()

        if tag_name == "img":
            src = resolve_image_url(el)
            alt = html.escape(el.get("alt", "").strip())
            if src and not any(src in block for block in output_blocks):
                output_blocks.append(f'<figure><img src="{html.escape(src)}" alt="{alt}" loading="lazy"></figure>')
            continue

        if tag_name == "figure":
            img = el.find("img")
            if img:
                src = resolve_image_url(img)
                caption = el.find(["figcaption", "span"])
                caption_txt = html.escape(caption.get_text(strip=True)) if caption else ""
                alt = html.escape(img.get("alt", "").strip() or caption_txt)
                if src:
                    cap_tag = f"<figcaption>{caption_txt}</figcaption>" if caption_txt else ""
                    output_blocks.append(f'<figure><img src="{html.escape(src)}" alt="{alt}" loading="lazy">{cap_tag}</figure>')
            continue

        raw_txt = el.get_text(strip=True)
        if not raw_txt or len(raw_txt) < 3:
            continue

        # Deduplicate identical consecutive blocks
        txt_hash = raw_txt[:80]
        if txt_hash in seen_texts:
            continue
        seen_texts.add(txt_hash)

        if tag_name in ["h2", "h3", "h4"]:
            output_blocks.append(f"<{tag_name}>{html.escape(raw_txt)}</{tag_name}>")
        elif tag_name == "blockquote":
            output_blocks.append(f"<blockquote><p>{html.escape(raw_txt)}</p></blockquote>")
        elif tag_name in ["ul", "ol"]:
            lis = [f"<li>{html.escape(li.get_text(strip=True))}</li>" for li in el.find_all("li") if li.get_text(strip=True)]
            if lis:
                output_blocks.append(f"<{tag_name}>\n  " + "\n  ".join(lis) + f"\n</{tag_name}>")
        else:
            # Paragraph
            output_blocks.append(f"<p>{html.escape(raw_txt)}</p>")

    if not output_blocks:
        return text_to_semantic_html(container.get_text(strip=True))

    return "\n".join(output_blocks)


def resolve_image_url(img_elem: Tag) -> str:
    """Resolve uncompressed, highest resolution image URL handling data-src/lazy loading."""
    if not img_elem:
        return ""

    candidates = [
        img_elem.get("data-src"),
        img_elem.get("data-original"),
        img_elem.get("data-org-src"),
        img_elem.get("data-srcset"),
        img_elem.get("srcset"),
        img_elem.get("content"),
        img_elem.get("src"),
    ]

    for cand in candidates:
        if not cand or not isinstance(cand, str):
            continue
        cand = cand.strip()
        if not cand or cand.startswith("data:image"):
            continue

        # If cand is srcset (comma-separated URL and width/multiplier)
        if "," in cand and " " in cand:
            parts = cand.split(",")
            last_part = parts[-1].strip().split(" ")[0].strip()
            if last_part.startswith("http") or last_part.startswith("//"):
                cand = last_part

        if cand.startswith("//"):
            cand = "https:" + cand

        # Clean resizing parameters where possible
        # Daum/Kakao: ?fname=http...
        if "daumcdn.net" in cand or "kakaocdn.net" in cand:
            parsed = urlparse(cand)
            qs = parse_qs(parsed.query)
            if "fname" in qs and qs["fname"]:
                return qs["fname"][0]

        # Naver: imgnews.pstatic.net?type=w800 -> strip ?type to get original
        if "imgnews.pstatic.net" in cand and "?type=" in cand:
            cand = cand.split("?type=")[0]

        return cand

    return ""


def extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract and parse all JSON-LD objects in an HTML document."""
    results: List[Dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            # Use strict=False to allow unescaped newlines/control characters
            data = json.loads(script.string.strip(), strict=False)
            if isinstance(data, list):
                results.extend([item for item in data if isinstance(item, dict)])
            elif isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    results.extend([item for item in data["@graph"] if isinstance(item, dict)])
                else:
                    results.append(data)
        except Exception:
            continue
    return results


def find_json_ld_article(json_ld_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the primary NewsArticle / Article / ReportageNewsArticle in JSON-LD objects."""
    target_types = {
        "NewsArticle",
        "Article",
        "ReportageNewsArticle",
        "BlogPosting",
        "TechArticle",
        "AnalysisNewsArticle",
        "OpinionNewsArticle",
        "ReviewNewsArticle",
    }
    for item in json_ld_list:
        raw_type = item.get("@type")
        types: set[str] = set()
        if isinstance(raw_type, list):
            types = set(raw_type)
        elif isinstance(raw_type, str):
            types = {raw_type}

        if types & target_types:
            return item
    return None


def parse_authors_from_json_ld(author_field: Any) -> List[str]:
    """Parse authors list from JSON-LD author property."""
    authors: List[str] = []
    if not author_field:
        return authors

    if isinstance(author_field, str):
        cleaned = clean_text(author_field)
        if cleaned:
            authors.append(cleaned)
    elif isinstance(author_field, dict):
        name = author_field.get("name")
        if name:
            authors.append(clean_text(name))
    elif isinstance(author_field, list):
        for entry in author_field:
            if isinstance(entry, dict) and entry.get("name"):
                authors.append(clean_text(entry["name"]))
            elif isinstance(entry, str) and entry.strip():
                authors.append(clean_text(entry))
    return [a for a in authors if a]


def parse_image_from_json_ld(img_field: Any) -> str:
    """Extract hero image URL from JSON-LD image property."""
    if not img_field:
        return ""
    if isinstance(img_field, str):
        return img_field.strip()
    if isinstance(img_field, dict):
        return img_field.get("url", "").strip()
    if isinstance(img_field, list) and img_field:
        first = img_field[0]
        if isinstance(first, str):
            return first.strip()
        if isinstance(first, dict):
            return first.get("url", "").strip()
    return ""


def parse_arc_fusion_metadata(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """
    Extract Arc XP / Fusion CMS globalContent object (used by Washington Post, Chosun Ilbo, etc.).
    Uses raw_decode to robustly parse nested JSON.
    """
    script = soup.find("script", id="fusion-metadata")
    if not script or not script.string:
        return None
    script_text = script.string
    idx = script_text.find("Fusion.globalContent")
    if idx == -1:
        return None
    eq_idx = script_text.find("=", idx)
    if eq_idx == -1:
        return None
    try:
        rest = script_text[eq_idx + 1:].strip()
        data, _ = json.JSONDecoder(strict=False).raw_decode(rest)
        return data
    except Exception:
        return None


# ==============================================================================
# 2. Site Extractors: Group A. Major Aggregators & Portals
# ==============================================================================

def extract_msn(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    MSN News extractor.
    Uses assets.msn.com/content/view/v2/Detail/{locale}/{id} endpoint when available,
    falling back to Web Component / article DOM parsing.
    """
    match = re.search(r"/ar-([a-zA-Z0-9]+)", url)
    if match and fetch_network:
        article_id = match.group(1)
        loc_match = re.search(r"msn\.com/([a-z]{2}-[a-z]{2})/", url.lower())
        locale = loc_match.group(1) if loc_match else "en-us"
        api_url = f"https://assets.msn.com/content/view/v2/Detail/{locale}/{article_id}"
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            with httpx.Client(headers=headers, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    title = clean_text(data.get("title", ""))
                    body = data.get("body", "") or data.get("subline", "")
                    if body and not body.startswith("<p>"):
                        body_html = text_to_semantic_html(body)
                    else:
                        body_soup = BeautifulSoup(body, "html.parser")
                        body_html = sanitize_element_to_html(body_soup)

                    authors = []
                    for prov in data.get("provider", []) if isinstance(data.get("provider"), list) else [data.get("provider")]:
                        if isinstance(prov, dict) and prov.get("name"):
                            authors.append(clean_text(prov["name"]))
                    for auth in data.get("authors", []):
                        if isinstance(auth, dict) and auth.get("name"):
                            authors.append(clean_text(auth["name"]))

                    img_url = ""
                    if data.get("image") and isinstance(data["image"], dict):
                        img_url = data["image"].get("url", "")

                    return {
                        "title": title,
                        "body_html": body_html,
                        "authors": authors,
                        "published_date": data.get("publishedDateTime", ""),
                        "hero_image_url": img_url,
                        "canonical_url": data.get("canonicalUrl", url),
                        "site_name": "MSN News",
                    }
        except Exception as e:
            logger.debug(f"MSN direct API failed, falling back to DOM: {e}")

    title = clean_text(soup.find("h1").get_text(strip=True) if soup.find("h1") else "")
    article = soup.find("article") or soup.find("div", attrs={"data-testid": "article-body"}) or soup.find(id="article-body")
    body_html = sanitize_element_to_html(article) if article else ""
    return {
        "title": title,
        "body_html": body_html,
        "authors": [],
        "published_date": "",
        "hero_image_url": "",
        "canonical_url": url,
        "site_name": "MSN News",
    }


def extract_yahoo(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Yahoo News & Finance extractor."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = ""
    authors = []
    published_date = ""
    hero_image = ""

    if json_ld:
        title = clean_text(json_ld.get("headline", ""))
        authors = parse_authors_from_json_ld(json_ld.get("author") or json_ld.get("creator"))
        published_date = json_ld.get("datePublished", "")
        hero_image = parse_image_from_json_ld(json_ld.get("image"))

    if not title and soup.find("h1"):
        title = clean_text(soup.find("h1").get_text(strip=True))

    body_elem = (
        soup.find("div", class_=re.compile(r"col-body"))
        or soup.find("div", class_="caas-body")
        or soup.find("article", class_=re.compile(r"caas-container"))
        or soup.find("article")
    )
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": published_date,
        "hero_image_url": hero_image,
        "canonical_url": url,
        "site_name": "Yahoo News",
    }


def extract_google_news(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Google News syndication & feed extractor."""
    canonical = soup.find("link", rel="canonical")
    canon_url = canonical["href"].strip() if canonical and canonical.get("href") else url

    title_elem = soup.find("h1") or soup.find("title")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")
    if " - " in title:
        title = title.rsplit(" - ", 1)[0].strip()

    body_elem = soup.find("article") or soup.find("c-wiz") or soup.find("main")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": [],
        "published_date": "",
        "hero_image_url": "",
        "canonical_url": canon_url,
        "site_name": "Google News",
    }


def extract_smartnews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """SmartNews extractor."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    date = json_ld.get("datePublished", "") if json_ld else ""
    image = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []

    if not title and soup.find("h1"):
        title = clean_text(soup.find("h1").get_text(strip=True))

    body_elem = soup.find("article") or soup.find(class_=re.compile(r"article-body|content-body"))
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": date,
        "hero_image_url": image,
        "canonical_url": url,
        "site_name": "SmartNews",
    }


def extract_substack(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    Substack extractor.
    Queries Substack's public REST endpoint (/api/v1/posts/{slug}) for full pristine body_html,
    with graceful fallback to SSR HTML and JSON-LD.
    """
    parsed = urlparse(url)
    slug_match = re.search(r"/p/([a-zA-Z0-9_\-]+)", parsed.path)

    if slug_match and fetch_network:
        slug = slug_match.group(1)
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/v1/posts/{slug}"
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            with httpx.Client(headers=headers, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    b_html = data.get("body_html", "")
                    b_soup = BeautifulSoup(b_html, "html.parser")
                    clean_body = sanitize_element_to_html(b_soup)
                    authors = [
                        clean_text(b["name"])
                        for b in data.get("publishedBylines", [])
                        if isinstance(b, dict) and b.get("name")
                    ]
                    return {
                        "title": clean_text(data.get("title", "")),
                        "body_html": clean_body,
                        "authors": authors,
                        "published_date": data.get("post_date", ""),
                        "hero_image_url": data.get("cover_image", ""),
                        "canonical_url": data.get("canonical_url", url),
                        "site_name": "Substack",
                    }
        except Exception as e:
            logger.debug(f"Substack API query failed, falling back: {e}")

    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = clean_text(soup.find("h1").get_text(strip=True))

    body_elem = soup.find("div", class_=re.compile(r"available-content|body\s+markup|post-content")) or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Substack",
    }


def extract_medium(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Medium extractor."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = clean_text(soup.find("h1").get_text(strip=True))

    body_elem = soup.find("article") or soup.find("section")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Medium",
    }


def extract_reddit(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    Reddit post extractor.
    Appends .json to post URL for full structured post data with markdown/HTML,
    falling back to shreddit-post or legacy DOM elements.
    """
    parsed = urlparse(url)
    if "/comments/" in parsed.path and fetch_network:
        clean_path = parsed.path.rstrip("/") + ".json"
        json_url = f"https://www.reddit.com{clean_path}"
        try:
            headers = {"User-Agent": "VPSArchiveLens/1.0 (Personal Reader Assistant)"}
            with httpx.Client(headers=headers, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(json_url)
                if resp.status_code == 200:
                    data = resp.json()
                    post = data[0]["data"]["children"][0]["data"]
                    title = clean_text(post.get("title", ""))
                    selftext = post.get("selftext", "")
                    selftext_html = post.get("selftext_html", "")
                    if selftext_html:
                        body_soup = BeautifulSoup(html.unescape(selftext_html), "html.parser")
                        body_html = sanitize_element_to_html(body_soup)
                    else:
                        body_html = text_to_semantic_html(selftext)

                    author = post.get("author", "")
                    authors = [author] if author and author != "[deleted]" else []
                    thumbnail = post.get("thumbnail", "")
                    hero_img = thumbnail if thumbnail.startswith("http") else ""

                    return {
                        "title": title,
                        "body_html": body_html,
                        "authors": authors,
                        "published_date": str(post.get("created_utc", "")),
                        "hero_image_url": hero_img,
                        "canonical_url": f"https://www.reddit.com{post.get('permalink', parsed.path)}",
                        "site_name": f"r/{post.get('subreddit', 'reddit')}",
                    }
        except Exception as e:
            logger.debug(f"Reddit JSON endpoint failed, falling back: {e}")

    shreddit = soup.find("shreddit-post")
    title = shreddit.get("post-title", "") if shreddit else ""
    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("div", slot="text-body") or soup.find(class_=re.compile(r"usertext-body"))
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    author = shreddit.get("author", "") if shreddit else ""
    authors = [author] if author else []

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": "",
        "hero_image_url": "",
        "canonical_url": url,
        "site_name": "Reddit",
    }


def extract_rss_syndication(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Feedly & RSS / Atom feed syndication extractor."""
    is_xml = soup.find(["rss", "feed", "channel"]) is not None
    if is_xml:
        item = soup.find(["item", "entry"])
        if item:
            title_node = item.find("title")
            title = clean_text(title_node.get_text(strip=True) if title_node else "")

            content_node = item.find("content:encoded") or item.find("content") or item.find("description")
            content_text = content_node.get_text(strip=True) if content_node else ""
            if "<p" in content_text or "<div" in content_text:
                c_soup = BeautifulSoup(content_text, "html.parser")
                body_html = sanitize_element_to_html(c_soup)
            else:
                body_html = text_to_semantic_html(content_text)

            pub_node = item.find(["pubDate", "published", "updated"])
            pub_date = clean_text(pub_node.get_text(strip=True) if pub_node else "")

            author_node = item.find(["dc:creator", "author"])
            author = clean_text(author_node.get_text(strip=True) if author_node else "")
            authors = [author] if author else []

            enclosure = item.find("enclosure")
            hero_img = enclosure.get("url", "") if enclosure and "image" in enclosure.get("type", "") else ""

            link_node = item.find("link")
            link = link_node.get("href") or link_node.get_text(strip=True) if link_node else url

            return {
                "title": title,
                "body_html": body_html,
                "authors": authors,
                "published_date": pub_date,
                "hero_image_url": hero_img,
                "canonical_url": link,
                "site_name": "RSS Feed",
            }

    title = clean_text(soup.find("h1").get_text(strip=True) if soup.find("h1") else "")
    body_elem = soup.find("article") or soup.find(class_=re.compile(r"entry-content|article-content"))
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": [],
        "published_date": "",
        "hero_image_url": "",
        "canonical_url": url,
        "site_name": "Feedly / Syndication",
    }


# ==============================================================================
# 3. Site Extractors: Group B. Korean & East Asian News Outlets
# ==============================================================================

def extract_naver_news(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Naver News extractor (n.news.naver.com / news.naver.com)."""
    title_elem = soup.find(id="title_area") or soup.find("h2", class_="media_end_head_headline")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find(id="dic_area") or soup.find(id="articeBody") or soup.find(id="newsct_article")
    og_img = soup.find("meta", property="og:image")
    hero_image = resolve_image_url(og_img) if og_img else ""
    if not hero_image and body_elem:
        img_tag = body_elem.find("img")
        hero_image = resolve_image_url(img_tag) if img_tag else ""

    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    date_elem = soup.find("span", class_=re.compile(r"media_end_head_info_datestamp_time"))
    published_date = ""
    if date_elem:
        published_date = date_elem.get("data-date-time") or clean_text(date_elem.get_text(strip=True))

    author_elem = soup.find("em", class_="media_end_head_journalist_name") or soup.find("span", class_="byline_s")
    authors = [clean_text(author_elem.get_text(strip=True))] if author_elem else []

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": published_date,
        "hero_image_url": hero_image,
        "canonical_url": url,
        "site_name": "Naver News",
    }


def extract_daum_news(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Daum / Kakao News extractor (v.daum.net)."""
    title_elem = soup.find("h3", class_="tit_view") or soup.find("h1")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find("div", class_="article_view") or soup.find("section", attrs={"dmcf-sid": True})
    og_img = soup.find("meta", property="og:image")
    hero_image = resolve_image_url(og_img) if og_img else ""

    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    date_elem = soup.find("span", class_="num_date")
    published_date = clean_text(date_elem.get_text(strip=True) if date_elem else "")

    author_elem = soup.find("span", class_="txt_info")
    authors = [a.strip() for a in author_elem.get_text(strip=True).split(",") if a.strip()] if author_elem else []

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": published_date,
        "hero_image_url": hero_image,
        "canonical_url": url,
        "site_name": "Daum News",
    }


def extract_nate_news(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Nate News extractor (news.nate.com)."""
    title_elem = soup.find("h3", class_=re.compile(r"articleSubecjt|viewHeadline")) or soup.find("h1")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find(id="realContents") or soup.find(id="articleContetns")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    date_elem = soup.find("span", class_="firstDate") or soup.find("em", class_="date")
    published_date = clean_text(date_elem.get_text(strip=True) if date_elem else "")

    author_elem = soup.find("span", class_="reporterNameCopyright") or soup.find("span", class_="medium")
    authors = [clean_text(author_elem.get_text(strip=True))] if author_elem else []

    og_img = soup.find("meta", property="og:image")
    hero_image = og_img.get("content", "").strip() if og_img else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": published_date,
        "hero_image_url": hero_image,
        "canonical_url": url,
        "site_name": "Nate News",
    }


def extract_yna(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Yonhap News Agency extractor (yna.co.kr)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = ""
    authors = []
    published_date = ""
    hero_image = ""

    if json_ld:
        title = clean_text(json_ld.get("headline", ""))
        authors = parse_authors_from_json_ld(json_ld.get("author"))
        published_date = json_ld.get("datePublished", "")
        hero_image = parse_image_from_json_ld(json_ld.get("image"))

    if not title:
        title_elem = soup.find("h1", class_=re.compile(r"tit")) or soup.find("h1")
        title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find("article", class_="story-news") or soup.find("div", class_="story-news")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    if not authors:
        writer_elem = soup.find("p", class_="writer") or soup.find("span", class_="tit-name")
        if writer_elem:
            authors = [clean_text(writer_elem.get_text(strip=True))]

    if not published_date:
        pub_meta = soup.find("meta", property="article:published_time")
        if pub_meta and pub_meta.get("content"):
            published_date = pub_meta["content"].strip()

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": published_date,
        "hero_image_url": hero_image,
        "canonical_url": url,
        "site_name": "Yonhap News Agency",
    }


def extract_chosun(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Chosun Ilbo extractor (chosun.com) using Arc XP Fusion globalContent or DOM."""
    fusion = parse_arc_fusion_metadata(soup)
    if fusion:
        headline = fusion.get("headlines", {}).get("basic", "")
        date = fusion.get("display_date") or fusion.get("first_publish_date", "")
        authors = [clean_text(b["name"]) for b in fusion.get("credits", {}).get("by", []) if b.get("name")]
        hero_img = fusion.get("promo_items", {}).get("basic", {}).get("url", "")

        paras = []
        for el in fusion.get("content_elements", []):
            if el.get("type") == "text":
                content = el.get("content", "").strip()
                if content:
                    paras.append(f"<p>{html.escape(content)}</p>")
            elif el.get("type") == "image":
                img_url = el.get("url", "")
                caption = el.get("caption", "")
                if img_url:
                    cap_tag = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
                    paras.append(f'<figure><img src="{html.escape(img_url)}" loading="lazy">{cap_tag}</figure>')

        body_html = "\n".join(paras)
        return {
            "title": clean_text(headline),
            "body_html": body_html,
            "authors": authors,
            "published_date": date,
            "hero_image_url": hero_img,
            "canonical_url": fusion.get("canonical_url", url),
            "site_name": "Chosun Ilbo",
        }

    title = clean_text(soup.find("h1").get_text(strip=True) if soup.find("h1") else "")
    body_elem = soup.find("section", class_="article-body") or soup.find("div", itemprop="articleBody")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": [],
        "published_date": "",
        "hero_image_url": "",
        "canonical_url": url,
        "site_name": "Chosun Ilbo",
    }


def extract_joongang(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """JoongAng Ilbo extractor (joongang.co.kr)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find(id="article_body") or soup.find("div", class_="article_body")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "JoongAng Ilbo",
    }


def extract_donga(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Dong-A Ilbo extractor (donga.com)."""
    title_elem = soup.find("h1", class_=re.compile(r"title")) or soup.find("h1")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find("section", class_=re.compile(r"news_view")) or soup.find(id="article_txt") or soup.find("div", class_="article_txt")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    date_elem = soup.find("div", class_="title_foot") or soup.find("span", class_="date")
    pub_date = clean_text(date_elem.get_text(strip=True) if date_elem else "")

    author_elem = soup.find("span", class_="reporter") or soup.find("span", class_="report")
    authors = [clean_text(author_elem.get_text(strip=True))] if author_elem else []

    og_img = soup.find("meta", property="og:image")
    hero_img = og_img.get("content", "").strip() if og_img else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Dong-A Ilbo",
    }


def extract_hankookilbo(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Hankook Ilbo extractor (hankookilbo.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("div", class_="editor-body") or soup.find("div", class_="col-main")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Hankook Ilbo",
    }


def extract_topstarnews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """TopStarNews extractor (topstarnews.net)."""
    title_elem = soup.find("h3", class_="heading") or soup.find("div", class_="article-head-title") or soup.find("h1")
    title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find(id="article-view-content-div") or soup.find("div", class_="article-vew-body")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    date_elem = soup.find("ul", class_="info-text")
    pub_date = ""
    authors = []
    if date_elem:
        lis = date_elem.find_all("li")
        if len(lis) >= 2:
            authors = [clean_text(lis[0].get_text(strip=True))]
            pub_date = clean_text(lis[1].get_text(strip=True))

    og_img = soup.find("meta", property="og:image")
    hero_img = og_img.get("content", "").strip() if og_img else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "TopStarNews",
    }


def extract_tenasia(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """TenAsia extractor (tenasia.co.kr / tenasia.hankyung.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title:
        title_elem = soup.find("h1", class_=re.compile(r"article-tit|tit")) or (soup.find_all("h1")[-1] if soup.find_all("h1") else None)
        title = clean_text(title_elem.get_text(strip=True) if title_elem else "")

    body_elem = soup.find("article", class_="article-view") or soup.find("div", class_="article-contents") or soup.find(id="articletxt")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "TenAsia",
    }


# ==============================================================================
# 4. Site Extractors: Group C. International & Business Publications
# ==============================================================================

def extract_reuters(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Reuters extractor (reuters.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    if json_ld and json_ld.get("articleBody") and len(json_ld["articleBody"]) > 80:
        body_html = text_to_semantic_html(json_ld["articleBody"])
    else:
        body_elem = (
            soup.find("div", attrs={"data-testid": "ArticleBody"})
            or soup.find("div", class_=re.compile(r"article-body__content"))
            or soup.find("article")
        )
        body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Reuters",
    }


def extract_apnews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Associated Press extractor (apnews.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("div", class_="RichTextStoryBody") or soup.find("div", class_="Page-content") or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Associated Press",
    }


def extract_bbc(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """BBC News extractor (bbc.com / bbc.co.uk)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("article") or soup.find("main", role="main")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "BBC News",
    }


def extract_theguardian(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Guardian extractor (theguardian.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    if json_ld and json_ld.get("articleBody") and len(json_ld["articleBody"]) > 80:
        body_html = text_to_semantic_html(json_ld["articleBody"])
    else:
        body_elem = (
            soup.find("div", attrs={"data-gu-name": "body"})
            or soup.find(id="maincontent")
            or soup.find("div", class_="article-body-commercial-selector")
        )
        body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "The Guardian",
    }


def extract_bloomberg(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Bloomberg extractor (bloomberg.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("div", attrs={"data-component": "article-body"}) or soup.find("div", class_="body-content") or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Bloomberg",
    }


def extract_wsj(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Wall Street Journal extractor (wsj.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("section", attrs={"subscriptions-section": "content"}) or soup.find("div", class_="article-content") or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Wall Street Journal",
    }


def extract_ft(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Financial Times extractor (ft.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = (
        soup.find("div", class_="article__content-body")
        or soup.find("div", attrs={"data-trackable": "article-body"})
        or soup.find(id="site-content")
        or soup.find("article")
    )
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "Financial Times",
    }


def extract_nytimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """New York Times extractor (nytimes.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("section", attrs={"name": "articleBody"}) or soup.find("div", class_=re.compile(r"StoryBodyCompanionColumn")) or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "The New York Times",
    }


def extract_washingtonpost(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Washington Post extractor (washingtonpost.com) using Arc Fusion globalContent or DOM."""
    fusion = parse_arc_fusion_metadata(soup)
    if fusion:
        headline = fusion.get("headlines", {}).get("basic", "")
        date = fusion.get("display_date") or fusion.get("first_publish_date", "")
        authors = [clean_text(b["name"]) for b in fusion.get("credits", {}).get("by", []) if b.get("name")]
        hero_img = fusion.get("promo_items", {}).get("basic", {}).get("url", "")

        paras = []
        for el in fusion.get("content_elements", []):
            if el.get("type") == "text":
                content = el.get("content", "").strip()
                if content:
                    paras.append(f"<p>{html.escape(content)}</p>")
            elif el.get("type") == "image":
                img_url = el.get("url", "")
                caption = el.get("caption", "")
                if img_url:
                    cap_tag = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
                    paras.append(f'<figure><img src="{html.escape(img_url)}" loading="lazy">{cap_tag}</figure>')

        body_html = "\n".join(paras)
        return {
            "title": clean_text(headline),
            "body_html": body_html,
            "authors": authors,
            "published_date": date,
            "hero_image_url": hero_img,
            "canonical_url": fusion.get("canonical_url", url),
            "site_name": "The Washington Post",
        }

    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_elem = soup.find("div", class_="article-body") or soup.find("div", attrs={"data-qa": "article-body"}) or soup.find("article")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "The Washington Post",
    }


def extract_cnn(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CNN extractor (cnn.com / edition.cnn.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    if json_ld and json_ld.get("articleBody") and len(json_ld["articleBody"]) > 80:
        body_html = text_to_semantic_html(json_ld["articleBody"])
    else:
        body_elem = (
            soup.find("div", class_=re.compile(r"article__content"))
            or soup.find("div", class_="story__body")
            or soup.find("article")
        )
        body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "CNN",
    }


def extract_cnbc(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CNBC extractor (cnbc.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    if json_ld and json_ld.get("articleBody") and len(json_ld["articleBody"]) > 80:
        body_html = text_to_semantic_html(json_ld["articleBody"])
    else:
        body_elem = soup.find("div", class_=re.compile(r"ArticleBody-articleBody")) or soup.find("div", attrs={"data-module": "ArticleBody"}) or soup.find("article")
        body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "CNBC",
    }


def extract_theverge(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Verge & Vox Media extractor (theverge.com / vox.com)."""
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = json_ld.get("headline", "") if json_ld else ""
    pub_date = json_ld.get("datePublished", "") if json_ld else ""
    authors = parse_authors_from_json_ld(json_ld.get("author")) if json_ld else []
    hero_img = parse_image_from_json_ld(json_ld.get("image")) if json_ld else ""

    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    if json_ld and json_ld.get("articleBody") and len(json_ld["articleBody"]) > 80:
        body_html = text_to_semantic_html(json_ld["articleBody"])
    else:
        body_elem = (
            soup.find("div", class_=re.compile(r"duet--article--article-body-component|c-entry-content"))
            or soup.find("div", class_=re.compile(r"articleBody"))
            or soup.find("article")
        )
        body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": clean_text(title),
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": "The Verge",
    }


# ==============================================================================
# 5. Generic Fallback Extractor
# ==============================================================================

def extract_generic_fallback(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    Universal fallback extractor using JSON-LD metadata, semantic HTML heuristics,
    and OpenGraph tags.
    """
    json_ld = find_json_ld_article(extract_json_ld(soup))
    title = ""
    authors: List[str] = []
    pub_date = ""
    hero_img = ""

    if json_ld:
        title = clean_text(json_ld.get("headline", ""))
        authors = parse_authors_from_json_ld(json_ld.get("author"))
        pub_date = json_ld.get("datePublished", "")
        hero_img = parse_image_from_json_ld(json_ld.get("image"))

        if json_ld.get("articleBody") and len(json_ld["articleBody"]) > 150:
            return {
                "title": title,
                "body_html": text_to_semantic_html(json_ld["articleBody"]),
                "authors": authors,
                "published_date": pub_date,
                "hero_image_url": hero_img,
                "canonical_url": url,
                "site_name": urlparse(url).netloc,
            }

    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = clean_text(og_title["content"])
        elif soup.find("h1"):
            title = clean_text(soup.find("h1").get_text(strip=True))
        elif soup.find("title"):
            title = clean_text(soup.find("title").get_text(strip=True))

    if not hero_img:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            hero_img = og_img["content"].strip()

    if not pub_date:
        for p_meta in ["article:published_time", "date", "pubdate"]:
            m = soup.find("meta", attrs={"property": p_meta}) or soup.find("meta", attrs={"name": p_meta})
            if m and m.get("content"):
                pub_date = m["content"].strip()
                break

    article_elem = (
        soup.find("article")
        or soup.find("div", attrs={"itemprop": "articleBody"})
        or soup.find("main")
        or soup.find("div", id=re.compile(r"content|article|story", re.IGNORECASE))
    )
    body_html = sanitize_element_to_html(article_elem) if article_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": urlparse(url).netloc,
    }


# ==============================================================================
# 6. Central Registries (SITE_ADAPTERS & BROWSER_HINTS)
# ==============================================================================

SITE_ADAPTERS: Dict[str, Callable[[str, BeautifulSoup, str, bool], Dict[str, Any]]] = {
    # A. Major Aggregators & Portals
    "msn.com": extract_msn,
    "assets.msn.com": extract_msn,
    "news.yahoo.com": extract_yahoo,
    "finance.yahoo.com": extract_yahoo,
    "yahoo.com": extract_yahoo,
    "news.google.com": extract_google_news,
    "smartnews.com": extract_smartnews,
    "substack.com": extract_substack,
    "medium.com": extract_medium,
    "reddit.com": extract_reddit,
    "sh.reddit.com": extract_reddit,
    "old.reddit.com": extract_reddit,
    "feedly.com": extract_rss_syndication,

    # B. Korean & East Asian News Outlets
    "n.news.naver.com": extract_naver_news,
    "news.naver.com": extract_naver_news,
    "v.daum.net": extract_daum_news,
    "news.daum.net": extract_daum_news,
    "news.nate.com": extract_nate_news,
    "yna.co.kr": extract_yna,
    "chosun.com": extract_chosun,
    "joongang.co.kr": extract_joongang,
    "donga.com": extract_donga,
    "hankookilbo.com": extract_hankookilbo,
    "topstarnews.net": extract_topstarnews,
    "tenasia.co.kr": extract_tenasia,
    "tenasia.hankyung.com": extract_tenasia,

    # C. International & Business Publications
    "reuters.com": extract_reuters,
    "apnews.com": extract_apnews,
    "bbc.com": extract_bbc,
    "bbc.co.uk": extract_bbc,
    "theguardian.com": extract_theguardian,
    "bloomberg.com": extract_bloomberg,
    "wsj.com": extract_wsj,
    "ft.com": extract_ft,
    "nytimes.com": extract_nytimes,
    "washingtonpost.com": extract_washingtonpost,
    "cnn.com": extract_cnn,
    "edition.cnn.com": extract_cnn,
    "cnbc.com": extract_cnbc,
    "theverge.com": extract_theverge,
    "vox.com": extract_theverge,
}


BROWSER_HINTS: Dict[str, Dict[str, Any]] = {
    # A. Major Aggregators & Portals
    "msn.com": {
        "wait_for_selector": "article, [data-testid='article-body'], #article-body",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button.reject-all",
            ".cookie-banner button",
        ],
    },
    "news.yahoo.com": {
        "wait_for_selector": "div.col-body, div.caas-body, article",
        "dismiss_selectors": [
            "button[name='agree']",
            "#consent-page button",
            ".consent-form button",
        ],
    },
    "finance.yahoo.com": {
        "wait_for_selector": "div.col-body, div.caas-body, article",
        "dismiss_selectors": [
            "button[name='agree']",
            "#consent-page button",
            ".consent-form button",
        ],
    },
    "news.google.com": {
        "wait_for_selector": "c-wiz, article, [role='main']",
        "dismiss_selectors": [
            "button[aria-label*='Agree']",
            "button[aria-label*='Accept']",
        ],
    },
    "smartnews.com": {
        "wait_for_selector": "article, .article-body, .content-body",
        "dismiss_selectors": [
            ".modal-close",
            "button[class*='dismiss']",
        ],
    },
    "substack.com": {
        "wait_for_selector": "div.available-content, div.body.markup, article",
        "dismiss_selectors": [
            "div[role='dialog'] button.close",
            ".subscribe-widget .close",
            "button[class*='guest']",
        ],
    },
    "medium.com": {
        "wait_for_selector": "article, section p",
        "dismiss_selectors": [
            "div[role='dialog'] button[aria-label='close']",
            "div#branch-banner button",
        ],
    },
    "reddit.com": {
        "wait_for_selector": "shreddit-post, div[slot='text-body'], .usertext-body",
        "dismiss_selectors": [
            "button[aria-label='Close']",
            "reddit-cookie-banner button",
        ],
    },
    "feedly.com": {
        "wait_for_selector": "article, .entry-content",
        "dismiss_selectors": [
            ".button-close",
        ],
    },

    # B. Korean & East Asian News Outlets
    "n.news.naver.com": {
        "wait_for_selector": "#dic_area, #newsct_article, #articeBody",
        "dismiss_selectors": [
            "._btn_close",
            ".u_cbox_btn_close",
        ],
    },
    "v.daum.net": {
        "wait_for_selector": "div.article_view, section[dmcf-sid]",
        "dismiss_selectors": [
            ".btn_close",
        ],
    },
    "news.nate.com": {
        "wait_for_selector": "#realContents, #articleContetns",
        "dismiss_selectors": [
            ".layer_close",
        ],
    },
    "yna.co.kr": {
        "wait_for_selector": "article.story-news, div.story-news",
        "dismiss_selectors": [
            ".btn-close",
        ],
    },
    "chosun.com": {
        "wait_for_selector": "section.article-body, #fusion-metadata",
        "dismiss_selectors": [
            "button.close",
            ".app-down-banner button",
        ],
    },
    "joongang.co.kr": {
        "wait_for_selector": "div#article_body, div.article_body",
        "dismiss_selectors": [
            "button.btn_close",
        ],
    },
    "donga.com": {
        "wait_for_selector": "section.news_view, div#article_txt, div.article_txt",
        "dismiss_selectors": [
            ".btn_close",
        ],
    },
    "hankookilbo.com": {
        "wait_for_selector": "p.editor-p, div.col-main, div.editor-body",
        "dismiss_selectors": [
            ".modal-close",
        ],
    },
    "topstarnews.net": {
        "wait_for_selector": "div#article-view-content-div",
        "dismiss_selectors": [
            ".close",
        ],
    },
    "tenasia.co.kr": {
        "wait_for_selector": "article.article-view, div.article-contents, #articletxt",
        "dismiss_selectors": [
            ".btn_close",
        ],
    },
    "tenasia.hankyung.com": {
        "wait_for_selector": "article.article-view, div.article-contents, #articletxt",
        "dismiss_selectors": [
            ".btn_close",
        ],
    },

    # C. International & Business Publications
    "reuters.com": {
        "wait_for_selector": "div[data-testid='ArticleBody'], article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "apnews.com": {
        "wait_for_selector": "div.RichTextStoryBody",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "bbc.com": {
        "wait_for_selector": "article",
        "dismiss_selectors": [
            "button[data-testid='banner-button-accept']",
            "#bbcprivacy-accept-button",
        ],
    },
    "bbc.co.uk": {
        "wait_for_selector": "article",
        "dismiss_selectors": [
            "button[data-testid='banner-button-accept']",
            "#bbcprivacy-accept-button",
        ],
    },
    "theguardian.com": {
        "wait_for_selector": "div[data-gu-name='body']",
        "dismiss_selectors": [
            "button[data-link-name='accept-all']",
            "button[id*='sp_message']",
        ],
    },
    "bloomberg.com": {
        "wait_for_selector": "div[data-component='article-body'], div.body-content, article",
        "dismiss_selectors": [
            "button[id*='accept']",
            ".paywall-overlay button",
        ],
    },
    "wsj.com": {
        "wait_for_selector": "section[subscriptions-section='content'], article",
        "dismiss_selectors": [
            "button[id*='accept']",
            "button.solid.style__btn",
        ],
    },
    "ft.com": {
        "wait_for_selector": "div.article__content-body, div[data-trackable='article-body'], article",
        "dismiss_selectors": [
            "button[data-trackable='consent-accept']",
            ".o-cookie-message button",
        ],
    },
    "nytimes.com": {
        "wait_for_selector": "section[name='articleBody'], div.StoryBodyCompanionColumn, article",
        "dismiss_selectors": [
            "button[data-testid='GDPR-accept']",
            "button.css-v6pt5v",
            "#compliance-overlay button",
        ],
    },
    "washingtonpost.com": {
        "wait_for_selector": "div.article-body, article, div[data-qa='article-body']",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "cnn.com": {
        "wait_for_selector": "div.article__content, article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "edition.cnn.com": {
        "wait_for_selector": "div.article__content, article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "cnbc.com": {
        "wait_for_selector": "div.ArticleBody-articleBody, article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
        ],
    },
    "theverge.com": {
        "wait_for_selector": "div.duet--article--article-body-component, div.c-entry-content, article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button[id*='privacy']",
        ],
    },
    "vox.com": {
        "wait_for_selector": "div.c-entry-content, article",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button[id*='privacy']",
        ],
    },
}


# ==============================================================================
# 7. Unified Extractor & Browser Hint Entrypoints
# ==============================================================================

def get_adapter_for_url(url: str) -> Optional[Callable[[str, BeautifulSoup, str, bool], Dict[str, Any]]]:
    """Find the best matching site adapter for a URL."""
    domain = normalize_domain(url)
    if not domain:
        return None

    if domain in SITE_ADAPTERS:
        return SITE_ADAPTERS[domain]

    for reg_domain, adapter in SITE_ADAPTERS.items():
        if domain.endswith("." + reg_domain):
            return adapter

    return None


def get_browser_hints(url: str) -> Dict[str, Any]:
    """
    Lookup Playwright automation hints (wait_for_selector and dismiss_selectors) for a URL.
    Returns default hints dictionary if domain is unknown.
    """
    domain = normalize_domain(url)
    if domain in BROWSER_HINTS:
        return BROWSER_HINTS[domain]

    for reg_domain, hints in BROWSER_HINTS.items():
        if domain.endswith("." + reg_domain):
            return hints

    return {
        "wait_for_selector": "article, main, [role='main']",
        "dismiss_selectors": [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
            ".cookie-banner button",
            "button[aria-label*='Accept']",
        ],
    }


def extract_article(
    url: str,
    html: Optional[str] = None,
    fetch_network: bool = True,
) -> Dict[str, Any]:
    """
    High-level article extraction entrypoint for VPS Archive Lens.

    Parameters:
    - url: Target article URL.
    - html: Raw HTML string (if already fetched via Playwright or user push).
    - fetch_network: If True, allows querying direct syndication/REST endpoints
      (e.g., Substack API, Reddit .json, MSN API).

    Returns:
    Normalized dictionary:
    {
        "title": str,
        "body_html": str,
        "authors": list[str],
        "published_date": str,
        "hero_image_url": str,
        "canonical_url": str,
        "site_name": str,
    }
    """
    raw_html = html or ""
    soup = BeautifulSoup(raw_html, "html.parser") if raw_html else BeautifulSoup("", "html.parser")

    adapter = get_adapter_for_url(url)
    if adapter:
        try:
            result = adapter(url, soup, raw_html, fetch_network)
            if result and result.get("body_html") and len(result["body_html"].strip()) > 80:
                return result
            fallback = extract_generic_fallback(url, soup, raw_html, fetch_network)
            if not result.get("body_html"):
                result["body_html"] = fallback["body_html"]
            if not result.get("title"):
                result["title"] = fallback["title"]
            if not result.get("hero_image_url"):
                result["hero_image_url"] = fallback["hero_image_url"]
            if not result.get("published_date"):
                result["published_date"] = fallback["published_date"]
            if not result.get("authors"):
                result["authors"] = fallback["authors"]
            return result
        except Exception as e:
            logger.warning(f"Adapter error for {url}: {e}. Falling back to generic extractor.")

    return extract_generic_fallback(url, soup, raw_html, fetch_network)
