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


def extract_with_selectors(
    url: str,
    soup: BeautifulSoup,
    site_name: str,
    body_selectors: List[str],
    title_selectors: Optional[List[str]] = None,
    author_selectors: Optional[List[str]] = None,
    date_selectors: Optional[List[str]] = None,
    check_json_ld_body: bool = False,
    min_json_ld_body_len: int = 100,
) -> Dict[str, Any]:
    """
    Standardized helper combining JSON-LD resolution with custom scoped DOM selectors
    for article title, body, author, and published date.
    """
    json_ld = find_json_ld_article(extract_json_ld(soup))

    # Title resolution: Prioritize scoped specific selectors, then JSON-LD, then generic h1 / og:title
    title = ""
    if title_selectors:
        for sel in title_selectors:
            if sel != "h1":
                elem = soup.select_one(sel)
                if elem and elem.get_text(strip=True):
                    title = clean_text(elem.get_text(strip=True))
                    break
    if not title and json_ld:
        title = clean_text(json_ld.get("headline", ""))
    if not title and title_selectors and "h1" in title_selectors:
        h1_elem = soup.find("h1")
        if h1_elem and h1_elem.get_text(strip=True):
            title = clean_text(h1_elem.get_text(strip=True))
    if not title:
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = clean_text(og_title["content"])
    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = clean_text(h1.get_text(strip=True))

    # Authors resolution
    authors: List[str] = []
    if json_ld:
        authors = parse_authors_from_json_ld(json_ld.get("author"))
    if not authors and author_selectors:
        for sel in author_selectors:
            elems = soup.select(sel)
            for el in elems:
                t = clean_text(el.get_text(strip=True))
                if t and t not in authors:
                    authors.append(t)
            if authors:
                break
    if not authors:
        meta_author = soup.find("meta", attrs={"name": re.compile(r"author|byl", re.I)})
        if meta_author and meta_author.get("content"):
            authors = [clean_text(meta_author["content"])]

    # Published date resolution
    pub_date = ""
    if json_ld:
        pub_date = json_ld.get("datePublished", "") or json_ld.get("dateModified", "")
    if not pub_date and date_selectors:
        for sel in date_selectors:
            elem = soup.select_one(sel)
            if elem:
                pub_date = elem.get("datetime") or elem.get("data-date-time") or clean_text(elem.get_text(strip=True))
                if pub_date:
                    break
    if not pub_date:
        meta_date = soup.find("meta", property=re.compile(r"published_time|release_date", re.I)) or soup.find("meta", attrs={"name": re.compile(r"date|pubdate", re.I)})
        if meta_date and meta_date.get("content"):
            pub_date = clean_text(meta_date["content"])

    # Hero image resolution
    hero_img = ""
    if json_ld:
        hero_img = parse_image_from_json_ld(json_ld.get("image"))
    if not hero_img:
        og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        if og_img and og_img.get("content"):
            hero_img = og_img["content"].strip()

    # Fast-path JSON-LD articleBody check
    body_html = ""
    if check_json_ld_body and json_ld and json_ld.get("articleBody"):
        body_text = json_ld["articleBody"].strip()
        if len(body_text) >= min_json_ld_body_len:
            body_html = text_to_semantic_html(body_text)

    # DOM body extraction
    if not body_html and body_selectors:
        for sel in body_selectors:
            elem = soup.select_one(sel)
            if elem:
                extracted = sanitize_element_to_html(elem)
                if len(extracted.strip()) > 30:
                    body_html = extracted
                    break

    # Fallback to article or main
    if not body_html:
        fallback_elem = soup.find("article") or soup.find("main")
        if fallback_elem:
            body_html = sanitize_element_to_html(fallback_elem)

    return {
        "title": title,
        "body_html": body_html,
        "authors": authors,
        "published_date": pub_date,
        "hero_image_url": hero_img,
        "canonical_url": url,
        "site_name": site_name,
    }


def extract_with_rss_fallback(
    url: str,
    soup: BeautifulSoup,
    site_name: str,
    feed_url: str,
    body_selectors: List[str],
    title_selectors: Optional[List[str]] = None,
    fetch_network: bool = True,
) -> Dict[str, Any]:
    """
    Attempts matching article URL within publisher's public RSS/syndication feed
    for full text, falling back to standard selector-based extraction.
    """
    if fetch_network and feed_url:
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=6.0, follow_redirects=True) as client:
                resp = client.get(feed_url)
                if resp.status_code == 200:
                    try:
                        feed_soup = BeautifulSoup(resp.content, "xml")
                    except Exception:
                        feed_soup = BeautifulSoup(resp.content, "html.parser")

                    for item in feed_soup.find_all(["item", "entry"]):
                        link_node = item.find("link")
                        link = ""
                        if link_node:
                            link = (
                                link_node.get("href")
                                or link_node.get_text(strip=True)
                                or (link_node.next_sibling and str(link_node.next_sibling))
                                or ""
                            ).strip()
                        if not link:
                            m = re.search(r"<link[^>]*>([^<]+)</link>|<link[^>]+href=[\"']([^\"']+)[\"']", str(item))
                            if m:
                                link = (m.group(1) or m.group(2) or "").strip()

                        if link and (link in url or url in link):
                            content_node = item.find("content:encoded") or item.find("content") or item.find("description")
                            if content_node:
                                c_text = content_node.get_text(strip=True)
                                if len(c_text) > 120:
                                    title_node = item.find("title")
                                    title = clean_text(title_node.get_text(strip=True) if title_node else "")
                                    c_soup = BeautifulSoup(c_text, "html.parser")
                                    pub_node = item.find(["pubdate", "pubDate", "published"])
                                    return {
                                        "title": title,
                                        "body_html": sanitize_element_to_html(c_soup),
                                        "authors": [],
                                        "published_date": clean_text(pub_node.get_text(strip=True)) if pub_node else "",
                                        "hero_image_url": "",
                                        "canonical_url": link,
                                        "site_name": site_name,
                                    }
        except Exception as e:
            logger.debug(f"Feed query for {site_name} failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name=site_name,
        body_selectors=body_selectors,
        title_selectors=title_selectors,
    )


# ==============================================================================
# 2. Site Extractors: Group A. Major Aggregators & Portals
# ==============================================================================

def extract_msn(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    MSN News extractor.
    Uses assets.msn.com/content/view/v2/Detail/{locale}/{id} endpoint when available,
    falling back to Web Component / article DOM parsing.
    """
    match = re.search(r"/(?:ar|ss|vi)-([a-zA-Z0-9]+)", url) or re.search(r"/([a-zA-Z0-9]{8,})", url)
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

                    # Map image resources
                    img_map = {}
                    for res in data.get("imageResources", []):
                        if isinstance(res, dict) and res.get("cmsId") and res.get("url"):
                            img_map[res["cmsId"]] = res["url"]

                    body = data.get("body", "") or data.get("subline", "")
                    if body:
                        # Replace MSN cmsId placeholders with real image URLs
                        for cms_id, u in img_map.items():
                            body = re.sub(r'<img[^>]*data-document-id="' + re.escape(cms_id) + r'"[^>]*>', f'<img src="{u}" />', body)
                            body = body.replace(f'data-document-id="{cms_id}"', f'src="{u}"')
                        body_soup = BeautifulSoup(body, "html.parser")
                        body_html = sanitize_element_to_html(body_soup)
                    elif data.get("slides"):
                        slides_parts = []
                        for s in data["slides"]:
                            stitle = s.get("title", "")
                            sbody = s.get("body", "")
                            simg = s.get("image", {})
                            simg_url = simg.get("url", "") if isinstance(simg, dict) else ""
                            scaption = simg.get("caption", "") if isinstance(simg, dict) else ""
                            part = ['<div class="slide-item">']
                            if simg_url:
                                part.append(f'<img src="{simg_url}" />')
                            if stitle:
                                part.append(f'<h3>{html.escape(stitle)}</h3>')
                            if sbody:
                                part.append(sbody)
                            elif scaption:
                                part.append(scaption)
                            part.append('</div>')
                            slides_parts.append("\n".join(part))
                        slides_soup = BeautifulSoup("\n".join(slides_parts), "html.parser")
                        body_html = sanitize_element_to_html(slides_soup)
                    elif data.get("abstract"):
                        body_html = f"<p>{html.escape(data['abstract'])}</p>"
                    else:
                        body_html = ""

                    authors = []
                    for prov in data.get("provider", []) if isinstance(data.get("provider"), list) else [data.get("provider")]:
                        if isinstance(prov, dict) and prov.get("name"):
                            authors.append(clean_text(prov["name"]))
                    for auth in data.get("authors", []):
                        if isinstance(auth, dict) and auth.get("name"):
                            authors.append(clean_text(auth["name"]))

                    img_url = ""
                    if data.get("imageResources") and isinstance(data["imageResources"], list) and len(data["imageResources"]) > 0:
                        img_url = data["imageResources"][0].get("url", "")
                    elif data.get("image") and isinstance(data["image"], dict):
                        img_url = data["image"].get("url", "")

                    return {
                        "title": title,
                        "body_html": body_html,
                        "authors": authors,
                        "published_date": data.get("publishedDateTime", ""),
                        "hero_image_url": img_url,
                        "canonical_url": data.get("sourceHref") or data.get("canonicalUrl", url),
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
# ==============================================================================
# 4. Extended Platform Extractors (Sites 31 to 100)
# ==============================================================================

# ------------------------------------------------------------------------------
# Batch 1: Aggregators, Developer Feeds & Modern Discourse (Sites 31–38)
# ------------------------------------------------------------------------------

def extract_hackernews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Hacker News extractor (news.ycombinator.com) with Firebase REST API fast path."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    item_id = qs.get("id", [""])[0]

    if item_id and fetch_network:
        api_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        title = clean_text(data.get("title", ""))
                        by = data.get("by", "")
                        score = data.get("score", 0)
                        descendants = data.get("descendants", 0)
                        text = data.get("text", "")
                        story_url = data.get("url", "")
                        pub_time = ""
                        if data.get("time"):
                            from datetime import datetime, timezone
                            pub_time = datetime.fromtimestamp(data["time"], timezone.utc).isoformat()

                        body_parts = []
                        if story_url:
                            body_parts.append(f'<p><strong>Original Link:</strong> <a href="{html.escape(story_url)}" target="_blank">{html.escape(story_url)}</a></p>')
                            body_parts.append(f'<p><em>Score: {score} points | Comments: {descendants}</em></p>')
                        if text:
                            t_soup = BeautifulSoup(text, "html.parser")
                            body_parts.append(sanitize_element_to_html(t_soup))

                        return {
                            "title": title or "Hacker News Discussion",
                            "body_html": "\n".join(body_parts) if body_parts else "<p>Hacker News Discussion</p>",
                            "authors": [by] if by else [],
                            "published_date": pub_time,
                            "hero_image_url": "",
                            "canonical_url": url,
                            "site_name": "Hacker News",
                        }
        except Exception as e:
            logger.debug(f"Hacker News API fetch failed: {e}")

    title_elem = soup.select_one(".titleline > a") or soup.select_one(".title a") or soup.find("h1")
    title = clean_text(title_elem.get_text(strip=True)) if title_elem else "Hacker News"
    subtext = soup.select_one(".subtext")
    author = ""
    date = ""
    if subtext:
        author_elem = subtext.select_one(".hnuser")
        if author_elem:
            author = clean_text(author_elem.get_text(strip=True))
        age_elem = subtext.select_one(".age")
        if age_elem:
            date = age_elem.get("title", "") or clean_text(age_elem.get_text(strip=True))

    body_elem = soup.select_one(".toptext") or soup.select_one(".comment-tree") or soup.select_one("table.fatitem")
    body_html = sanitize_element_to_html(body_elem) if body_elem else ""

    return {
        "title": title,
        "body_html": body_html,
        "authors": [author] if author else [],
        "published_date": date,
        "hero_image_url": "",
        "canonical_url": url,
        "site_name": "Hacker News",
    }


def extract_flipboard(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Flipboard extractor (flipboard.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Flipboard",
        body_selectors=["div[data-testid='article-body']", ".article-content", "article", ".post-content"],
        title_selectors=["h1.title", "h1[data-testid='title']", "h1"],
    )


def extract_pocket(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Pocket extractor (getpocket.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Pocket",
        body_selectors=["article", ".reader-container", ".item-body", ".article-content"],
        title_selectors=["h1.title", "h1"],
    )


def extract_applenews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Apple News Web extractor (apple.news)."""
    canonical = url
    can_tag = soup.find("link", rel="canonical")
    if can_tag and can_tag.get("href"):
        canonical = can_tag["href"]
    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        canonical = og_url["content"]

    return extract_with_selectors(
        url=canonical,
        soup=soup,
        site_name="Apple News",
        body_selectors=["div.article-content", "article", "main"],
        title_selectors=["h1.title", "h1"],
    )


def extract_devto(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Dev.to extractor with public REST API fast-path."""
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) >= 2 and fetch_network:
        username = path_parts[0]
        slug = path_parts[1]
        api_url = f"https://dev.to/api/articles/{username}/{slug}"
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("body_html"):
                        b_soup = BeautifulSoup(data["body_html"], "html.parser")
                        return {
                            "title": clean_text(data.get("title", "")),
                            "body_html": sanitize_element_to_html(b_soup),
                            "authors": [clean_text(data.get("user", {}).get("name", ""))] if data.get("user") else [],
                            "published_date": data.get("published_at", ""),
                            "hero_image_url": data.get("cover_image", "") or data.get("social_image", ""),
                            "canonical_url": data.get("canonical_url", url),
                            "site_name": "DEV Community",
                        }
        except Exception as e:
            logger.debug(f"Dev.to API fetch failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="DEV Community",
        body_selectors=["div#article-body", "div.crayons-article__main", "article"],
        title_selectors=["h1", ".crayons-article__title"],
    )


def extract_bluesky(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Bluesky extractor (bsky.app) with AT Protocol public API."""
    parsed = urlparse(url)
    match = re.search(r"/profile/([^/]+)/post/([^/]+)", parsed.path)
    if match and fetch_network:
        actor = match.group(1)
        rkey = match.group(2)
        api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://{actor}/app.bsky.feed.post/{rkey}&depth=1"
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    thread = data.get("thread", {})
                    post = thread.get("post", {})
                    record = post.get("record", {})
                    author_info = post.get("author", {})
                    author_name = author_info.get("displayName") or author_info.get("handle", "")
                    text = record.get("text", "")
                    created_at = record.get("createdAt", "")
                    avatar = author_info.get("avatar", "")

                    return {
                        "title": f"Bluesky post by {author_name}" if author_name else "Bluesky Post",
                        "body_html": text_to_semantic_html(text),
                        "authors": [clean_text(author_name)] if author_name else [],
                        "published_date": created_at,
                        "hero_image_url": avatar,
                        "canonical_url": url,
                        "site_name": "Bluesky",
                    }
        except Exception as e:
            logger.debug(f"Bluesky API fetch failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Bluesky",
        body_selectors=["div[data-testid*='postText']", "div[data-testid='postThreadItem']", "article"],
        title_selectors=["h1", "title"],
    )


def extract_ghost(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Ghost CMS Blog extractor (ghost.org / *.ghost.io)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Ghost",
        body_selectors=["div.gh-content", "div.post-content", "article.post", "article"],
        title_selectors=["h1.article-title", "h1.post-title", "h1"],
    )


def extract_wordpress(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Generic WordPress / WP Core REST extractor."""
    wp_link = soup.find("link", rel="alternate", type="application/json", href=re.compile(r"/wp-json/wp/v2/posts/\d+"))
    if wp_link and wp_link.get("href") and fetch_network:
        api_url = wp_link["href"]
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        title = clean_text(data.get("title", {}).get("rendered", ""))
                        b_soup = BeautifulSoup(data.get("content", {}).get("rendered", ""), "html.parser")
                        return {
                            "title": title,
                            "body_html": sanitize_element_to_html(b_soup),
                            "authors": [],
                            "published_date": data.get("date_gmt", "") or data.get("date", ""),
                            "hero_image_url": "",
                            "canonical_url": data.get("link", url),
                            "site_name": "WordPress",
                        }
        except Exception as e:
            logger.debug(f"WP REST API fetch failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="WordPress",
        body_selectors=["div.entry-content", "div.wp-block-post-content", "div.post-content", "article"],
        title_selectors=["h1.entry-title", "h1"],
    )


# ------------------------------------------------------------------------------
# Batch 2: Extended East Asian Outlets (Sites 39–48 & 93–98)
# ------------------------------------------------------------------------------

def extract_mk(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Maeil Business Newspaper / MK extractor (mk.co.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="매일경제 (MK)",
        body_selectors=["div.news_cnt_detail_wrap", "div#article_body", "div.art_txt", "article"],
        title_selectors=["h2.top_title", "h2.news_ttl", "h1.top_title", "h1"],
        date_selectors=["li.lasttime", "span.time", "div.time_area"],
        author_selectors=["span.author", "li.author"],
    )


def extract_hankyung(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Korea Economic Daily / Hankyung extractor (hankyung.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="한국경제 (Hankyung)",
        body_selectors=["#articletxt", "div.article-body", "article"],
        title_selectors=["h1.article-tit", "h1.headline", "h1"],
        date_selectors=["span.date-time", "span.date"],
        author_selectors=["span.author", "div.byline"],
    )


def extract_hani(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Hankyoreh extractor (hani.co.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="한겨레 (Hankyoreh)",
        body_selectors=["div.article-text", "div.text", "article"],
        title_selectors=["h1.title", "span.title", "h1"],
        date_selectors=["span.date-time", "ul.date-time"],
        author_selectors=["span.name", "li.name"],
    )


def extract_khan(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Kyunghyang Shinmun extractor (khan.co.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="경향신문 (Kyunghyang)",
        body_selectors=["div.art_body", "p.content_text", "div#articleBody", "article"],
        title_selectors=["h1.headline", "article h1", "h1"],
        date_selectors=["span.date", "em.date"],
        author_selectors=["span.name", "em.name"],
    )


def extract_segye(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Segye Ilbo extractor (segye.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="세계일보 (Segye)",
        body_selectors=["#article_txt", "div.view_con", "article"],
        title_selectors=["h1.title", "h1#article_title", "h1"],
        date_selectors=["span.date", "p.date"],
        author_selectors=["span.name", "p.byline"],
    )


def extract_news1(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """News1 Korea extractor (news1.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="뉴스1 (News1)",
        body_selectors=["div#articles_detail", "div.detail", "article"],
        title_selectors=["h1.title", "h1"],
        date_selectors=["span.date", "div.info"],
        author_selectors=["span.reporter", "span.name"],
    )


def extract_newsis(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Newsis extractor (newsis.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="뉴시스 (Newsis)",
        body_selectors=["article#articleBody", "div.viewer", "article"],
        title_selectors=["h1.title", "h1"],
        date_selectors=["p.date", "span.date"],
        author_selectors=["p.writer", "span.writer"],
    )


def extract_yahoojp(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """
    Yahoo! Japan extractor (news.yahoo.co.jp).
    Specifically avoids top-level 'Yahoo!ニュース' portal logo h1 by targeting article h1.
    """
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Yahoo! JAPAN ニュース",
        body_selectors=["div.article_body", "#uamods-article", "div[class*='articleBody']", "article"],
        title_selectors=["article h1", "h1[class*='Title']", "h1.sc-1bx5pky-0"],
        date_selectors=["time"],
        author_selectors=["p[class*='source']", "span[class*='source']"],
    )


def extract_nikkei(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Nikkei / Nikkei Asia extractor (asia.nikkei.com / nikkei.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Nikkei Asia",
        body_selectors=["div.c-article_body", "article", "div[class*='articleBody']"],
        title_selectors=["h1[class*='title']", "h1"],
        date_selectors=["time", "span[class*='time']"],
        author_selectors=["span[class*='author']"],
    )


def extract_asahi(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Asahi Shimbun extractor (asahi.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="朝日新聞 (Asahi Shimbun)",
        body_selectors=["div.ArticleBody", "div.nfyDetail", "article"],
        title_selectors=["h1", "div[class*='Title'] h1"],
        date_selectors=["time", "span.UpdateDate"],
    )


def extract_yomiuri(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Yomiuri Shimbun extractor (yomiuri.co.jp)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="読売新聞 (Yomiuri Shimbun)",
        body_selectors=["div.body-text", "article"],
        title_selectors=["h1.title", "h1"],
        date_selectors=["time"],
    )


def extract_mainichi(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Mainichi Shimbun extractor (mainichi.jp)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="毎日新聞 (Mainichi Shimbun)",
        body_selectors=["div.main-text", "article"],
        title_selectors=["h1.title", "h1"],
        date_selectors=["time"],
    )


def extract_kyodonews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Kyodo News extractor (english.kyodonews.net / kyodonews.net)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Kyodo News",
        body_selectors=["div.article-body", "div.p-article-body", "article"],
        title_selectors=["h1", "h1.title"],
        date_selectors=["time", "p.date"],
    )


def extract_moneytoday(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """MoneyToday extractor (mt.co.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="머니투데이 (MoneyToday)",
        body_selectors=["div#textBody", "div.article_body", "article"],
        title_selectors=["h1.subject", "h1"],
        date_selectors=["li.date", "span.date"],
        author_selectors=["li.author", "span.author"],
    )


def extract_edaily(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Edaily extractor (edaily.co.kr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="이데일리 (Edaily)",
        body_selectors=["div.news_body", "article"],
        title_selectors=["h1.headline", "h1"],
        date_selectors=["div.dates", "span.date"],
        author_selectors=["div.byline", "span.author"],
    )


def extract_ohmynews(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """OhmyNews extractor (ohmynews.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="오마이뉴스 (OhmyNews)",
        body_selectors=["div.content_box", "div.at_content", "article"],
        title_selectors=["h3.atc", "h1"],
        date_selectors=["div.info_data", "span.date"],
        author_selectors=["div.info_data a"],
    )


# ------------------------------------------------------------------------------
# Batch 3: Global Tech, Science & In-Depth Journalism (Sites 49–60)
# ------------------------------------------------------------------------------

def extract_arstechnica(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Ars Technica extractor (arstechnica.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Ars Technica",
        body_selectors=["div.article-content", "section.article-guts", "article"],
        title_selectors=["h1"],
    )


def extract_wired(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Wired extractor (wired.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Wired",
        body_selectors=["div[data-testid='BodyWrapper']", "div.body__inner-container", "article"],
        title_selectors=["h1"],
    )


def extract_techcrunch(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """TechCrunch extractor with WordPress VIP REST API fast path."""
    parsed = urlparse(url)
    slug_match = re.search(r"/([^/]+)/?$", parsed.path.strip("/"))
    slug = slug_match.group(1) if slug_match else ""

    if slug and fetch_network:
        api_url = f"https://techcrunch.com/wp-json/wp/v2/posts?slug={slug}"
        try:
            with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    posts = resp.json()
                    if isinstance(posts, list) and posts:
                        p = posts[0]
                        title = clean_text(p.get("title", {}).get("rendered", ""))
                        rendered_body = p.get("content", {}).get("rendered", "")
                        b_soup = BeautifulSoup(rendered_body, "html.parser")
                        body_html = sanitize_element_to_html(b_soup)
                        pub_date = p.get("date_gmt", "") or p.get("date", "")

                        authors = []
                        hero_image = ""
                        yoast = p.get("yoast_head_json", {})
                        if isinstance(yoast, dict):
                            if yoast.get("author"):
                                authors.append(clean_text(yoast["author"]))
                            og_img = yoast.get("og_image", [])
                            if og_img and isinstance(og_img, list) and og_img[0].get("url"):
                                hero_image = og_img[0]["url"]

                        return {
                            "title": title,
                            "body_html": body_html,
                            "authors": authors,
                            "published_date": pub_date,
                            "hero_image_url": hero_image,
                            "canonical_url": p.get("link", url),
                            "site_name": "TechCrunch",
                        }
        except Exception as e:
            logger.debug(f"TechCrunch WP API fetch failed: {e}")

    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="TechCrunch",
        body_selectors=["div.entry-content", "div.wp-block-post-content", "article"],
        title_selectors=["h1.article__title", "h1"],
    )


def extract_theatlantic(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Atlantic extractor (theatlantic.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Atlantic",
        body_selectors=["section[data-component='ArticleBody']", "article", "div.c-article__body"],
        title_selectors=["h1"],
    )


def extract_politico(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Politico extractor (politico.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Politico",
        body_selectors=["div.story-text", "div.story-content", "article"],
        title_selectors=["h1"],
    )


def extract_forbes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Forbes extractor (forbes.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Forbes",
        body_selectors=["div.article-body-container", "div.body-container", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
    )


def extract_economist(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Economist extractor (economist.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Economist",
        body_selectors=["div[data-component='article-body']", "article", "div.article__body"],
        title_selectors=["h1"],
    )


def extract_propublica(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ProPublica extractor (propublica.org)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ProPublica",
        body_selectors=["div.article-body", "div.body-content", "article"],
        title_selectors=["h1"],
    )


def extract_latimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Los Angeles Times extractor (latimes.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Los Angeles Times",
        body_selectors=["article", "div.page-content", "div.story-body"],
        title_selectors=["h1[class*='headline']", "h1"],
    )


def extract_aljazeera(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Al Jazeera English extractor (aljazeera.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Al Jazeera",
        body_selectors=["div.wysiwyg--all-content", "div.wysiwyg", "article"],
        title_selectors=["h1"],
    )


def extract_dw(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Deutsche Welle extractor (dw.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Deutsche Welle",
        body_selectors=["div.rich-text", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_npr(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """NPR extractor (npr.org)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="NPR",
        body_selectors=["div#storytext", "div.storytext", "article"],
        title_selectors=["h1"],
    )


# ------------------------------------------------------------------------------
# Batch 4: Global Breaking News & International Presses (Sites 61–72)
# ------------------------------------------------------------------------------

def extract_usatoday(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """USA Today extractor (usatoday.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="USA Today",
        body_selectors=["div.gnt_ar_b", "div.story-asset", "div[class*='article-body']", "article"],
        title_selectors=["h1.headline", "h1"],
    )


def extract_timesofindia(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Times of India extractor with JSON-LD articleBody zero-scrape fast path."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Times of India",
        body_selectors=["div._s30J", "div.main-content", "div.artText", "article"],
        title_selectors=["h1.HNMDR", "h1"],
        check_json_ld_body=True,
    )


def extract_thehindu(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Hindu extractor (thehindu.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Hindu",
        body_selectors=["div#schemaDiv", "div.articlebodycontent", "div[class*='article-body']", "article"],
        title_selectors=["h1.title", "h1"],
    )


def extract_smh(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Sydney Morning Herald / The Age extractor (smh.com.au / theage.com.au)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Sydney Morning Herald",
        body_selectors=["div[data-testid='article-body']", "article"],
        title_selectors=["h1[data-testid='headline']", "h1"],
    )


def extract_abc_au(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ABC News Australia extractor (abc.net.au)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ABC News (Australia)",
        body_selectors=["div#body", "div[data-component='ArticleBody']", "div[class*='ArticleBody']", "article"],
        title_selectors=["h1[data-component='Heading']", "h1"],
    )


def extract_cbc(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CBC News extractor (cbc.ca)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="CBC News",
        body_selectors=["div.story", "div.storyWrapper", "div[class*='story']", "article"],
        title_selectors=["h1.detail-headline", "h1"],
    )


def extract_globeandmail(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Globe and Mail extractor (theglobeandmail.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Globe and Mail",
        body_selectors=["div.c-article-body", "div[data-testid='article-body']", "article"],
        title_selectors=["h1.c-article-header__headline", "h1"],
    )


def extract_scmp(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """South China Morning Post extractor with JSON-LD articleBody zero-scrape fast path."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="South China Morning Post",
        body_selectors=["div.article-body-wrapper", "div[class*='articleBody']", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
    )


def extract_straitstimes(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Straits Times extractor (straitstimes.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="The Straits Times",
        body_selectors=["div.text-wrapper", "div.story-content", "div[class*='article-body']", "article"],
        title_selectors=["h1.headline", "h1"],
    )


def extract_france24(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """France 24 extractor (france24.com) with public wire RSS fast path."""
    return extract_with_rss_fallback(
        url=url,
        soup=soup,
        site_name="France 24",
        feed_url="https://www.france24.com/en/rss",
        body_selectors=["div.t-content__body", "div[class*='t-content__body']", "article"],
        title_selectors=["h1"],
        fetch_network=fetch_network,
    )


def extract_lemonde(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Le Monde extractor (lemonde.fr)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Le Monde",
        body_selectors=["section.article__content", "div.article__content", "article"],
        title_selectors=["h1.article__title", "h1"],
    )


def extract_spiegel(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Der Spiegel International extractor (spiegel.de)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Der Spiegel",
        body_selectors=["div[data-sara-click-el='body_content']", "div.word-break", "article"],
        title_selectors=["h1[title]", "h1"],
    )


# ------------------------------------------------------------------------------
# Batch 5: Tech, Science, Crypto & Digital Culture (Sites 73–82)
# ------------------------------------------------------------------------------

def extract_engadget(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Engadget extractor (engadget.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Engadget",
        body_selectors=["div.caas-body", "article"],
        title_selectors=["h1"],
    )


def extract_gizmodo(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Gizmodo extractor (gizmodo.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Gizmodo",
        body_selectors=["div.entry-content", "article"],
        title_selectors=["h1"],
    )


def extract_mashable(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Mashable extractor with JSON-LD articleBody zero-scrape fast path."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Mashable",
        body_selectors=["section.article-content", "article"],
        title_selectors=["h1"],
        check_json_ld_body=True,
    )


def extract_cnet(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CNET extractor (cnet.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="CNET",
        body_selectors=["div.c-articleCore_body", "article"],
        title_selectors=["h1[class*='c-head']", "h1"],
    )


def extract_venturebeat(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """VentureBeat extractor (venturebeat.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="VentureBeat",
        body_selectors=["div[class*='article-body']", "div.article-content", "article"],
        title_selectors=["h1"],
    )


def extract_coindesk(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CoinDesk extractor (coindesk.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="CoinDesk",
        body_selectors=["div.content-wrapper", "div[data-module-name='article-body']", "article"],
        title_selectors=["h1.typography__StyledTypography", "h1"],
    )


def extract_cointelegraph(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """CoinTelegraph extractor (cointelegraph.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="CoinTelegraph",
        body_selectors=["div.post-content", "article"],
        title_selectors=["h1.post__title", "h1"],
    )


def extract_sciencedaily(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """ScienceDaily extractor (sciencedaily.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="ScienceDaily",
        body_selectors=["div#story_text", "div#story_content", "article"],
        title_selectors=["h1#headline", "h1"],
    )


def extract_physorg(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Phys.org extractor (phys.org)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Phys.org",
        body_selectors=["div.article-main", "article"],
        title_selectors=["h1"],
    )


def extract_polygon(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Polygon extractor (polygon.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Polygon",
        body_selectors=["div.c-entry-content", "article"],
        title_selectors=["h1.c-page-title", "h1"],
    )


# ------------------------------------------------------------------------------
# Batch 6: Business, Finance, Markets & Policy (Sites 83–92 & 99–100)
# ------------------------------------------------------------------------------

def extract_businessinsider(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Business Insider / Insider extractor (businessinsider.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Business Insider",
        body_selectors=["div.content-lock-content", "div.post-content", "article"],
        title_selectors=["h1"],
    )


def extract_marketwatch(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """MarketWatch extractor with Dow Jones public RSS fast path."""
    return extract_with_rss_fallback(
        url=url,
        soup=soup,
        site_name="MarketWatch",
        feed_url="https://feeds.content.dowjones.io/public/rss/mw_topstories",
        body_selectors=["div.article__body", "article"],
        title_selectors=["h1"],
        fetch_network=fetch_network,
    )


def extract_barrons(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Barron's extractor (barrons.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Barron's",
        body_selectors=["div.article__body", "article"],
        title_selectors=["h1"],
    )


def extract_fortune(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Fortune extractor (fortune.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Fortune",
        body_selectors=["div[class*='articleBody']", "div.articleContent", "article"],
        title_selectors=["h1"],
    )


def extract_fastcompany(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Fast Company extractor (fastcompany.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Fast Company",
        body_selectors=["div[data-component='article-body']", "article"],
        title_selectors=["h1"],
    )


def extract_inc(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Inc. Magazine extractor (inc.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Inc. Magazine",
        body_selectors=["div.article-body", "article"],
        title_selectors=["h1"],
    )


def extract_spglobal(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """S&P Global extractor (spglobal.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="S&P Global",
        body_selectors=["div.article-content", "div[class*='article-body']", "article"],
        title_selectors=["h1"],
    )


def extract_thehill(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """The Hill extractor with public RSS feed fast path."""
    return extract_with_rss_fallback(
        url=url,
        soup=soup,
        site_name="The Hill",
        feed_url="https://thehill.com/feed/",
        body_selectors=["div.article__text", "article"],
        title_selectors=["h1"],
        fetch_network=fetch_network,
    )


def extract_axios(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Axios extractor with public RSS feed fast path."""
    return extract_with_rss_fallback(
        url=url,
        soup=soup,
        site_name="Axios",
        feed_url="https://www.axios.com/feeds/feed.rss",
        body_selectors=["div[data-cy='story-body']", "div[class*='story-body']", "article"],
        title_selectors=["h1"],
        fetch_network=fetch_network,
    )


def extract_semafor(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """Semafor extractor (semafor.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="Semafor",
        body_selectors=["div[data-testid='story-content']", "article"],
        title_selectors=["h1"],
    )


def extract_alltop(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """AllTop extractor (alltop.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="AllTop",
        body_selectors=["div.entry-content", "main", "article"],
        title_selectors=["h1"],
    )


def extract_smartbrief(url: str, soup: BeautifulSoup, raw_html: str, fetch_network: bool = True) -> Dict[str, Any]:
    """SmartBrief extractor (smartbrief.com)."""
    return extract_with_selectors(
        url=url,
        soup=soup,
        site_name="SmartBrief",
        body_selectors=["div.brief-content", "article"],
        title_selectors=["h1"],
    )


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

# Batch 1: Aggregators, Developer Feeds & Modern Discourse
    "news.ycombinator.com": extract_hackernews,
    "flipboard.com": extract_flipboard,
    "getpocket.com": extract_pocket,
    "apple.news": extract_applenews,
    "dev.to": extract_devto,
    "bsky.app": extract_bluesky,
    "ghost.org": extract_ghost,
    "wordpress.org": extract_wordpress,

    # Batch 2: Extended East Asian Outlets
    "mk.co.kr": extract_mk,
    "hankyung.com": extract_hankyung,
    "hani.co.kr": extract_hani,
    "khan.co.kr": extract_khan,
    "segye.com": extract_segye,
    "news1.kr": extract_news1,
    "newsis.com": extract_newsis,
    "news.yahoo.co.jp": extract_yahoojp,
    "asia.nikkei.com": extract_nikkei,
    "nikkei.com": extract_nikkei,
    "asahi.com": extract_asahi,
    "yomiuri.co.jp": extract_yomiuri,
    "mainichi.jp": extract_mainichi,
    "english.kyodonews.net": extract_kyodonews,
    "kyodonews.net": extract_kyodonews,
    "mt.co.kr": extract_moneytoday,
    "edaily.co.kr": extract_edaily,
    "ohmynews.com": extract_ohmynews,

    # Batch 3: Global Tech, Science & In-Depth Journalism
    "arstechnica.com": extract_arstechnica,
    "wired.com": extract_wired,
    "techcrunch.com": extract_techcrunch,
    "theatlantic.com": extract_theatlantic,
    "politico.com": extract_politico,
    "forbes.com": extract_forbes,
    "economist.com": extract_economist,
    "propublica.org": extract_propublica,
    "latimes.com": extract_latimes,
    "aljazeera.com": extract_aljazeera,
    "dw.com": extract_dw,
    "npr.org": extract_npr,

    # Batch 4: Global Breaking News & International Presses
    "usatoday.com": extract_usatoday,
    "timesofindia.indiatimes.com": extract_timesofindia,
    "indiatimes.com": extract_timesofindia,
    "thehindu.com": extract_thehindu,
    "smh.com.au": extract_smh,
    "theage.com.au": extract_smh,
    "abc.net.au": extract_abc_au,
    "cbc.ca": extract_cbc,
    "theglobeandmail.com": extract_globeandmail,
    "scmp.com": extract_scmp,
    "straitstimes.com": extract_straitstimes,
    "france24.com": extract_france24,
    "lemonde.fr": extract_lemonde,
    "spiegel.de": extract_spiegel,

    # Batch 5: Tech, Science, Crypto & Digital Culture
    "engadget.com": extract_engadget,
    "gizmodo.com": extract_gizmodo,
    "mashable.com": extract_mashable,
    "cnet.com": extract_cnet,
    "venturebeat.com": extract_venturebeat,
    "coindesk.com": extract_coindesk,
    "cointelegraph.com": extract_cointelegraph,
    "sciencedaily.com": extract_sciencedaily,
    "phys.org": extract_physorg,
    "polygon.com": extract_polygon,

    # Batch 6: Business, Finance, Markets & Policy
    "businessinsider.com": extract_businessinsider,
    "insider.com": extract_businessinsider,
    "marketwatch.com": extract_marketwatch,
    "barrons.com": extract_barrons,
    "fortune.com": extract_fortune,
    "fastcompany.com": extract_fastcompany,
    "inc.com": extract_inc,
    "spglobal.com": extract_spglobal,
    "thehill.com": extract_thehill,
    "axios.com": extract_axios,
    "semafor.com": extract_semafor,
    "alltop.com": extract_alltop,
    "smartbrief.com": extract_smartbrief,
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

# Batch 1: Aggregators, Developer Feeds & Modern Discourse
    "news.ycombinator.com": {
        "wait_for_selector": "table.itemlist, table.fatitem, .titleline",
        "dismiss_selectors": [],
    },
    "flipboard.com": {
        "wait_for_selector": "article, div[data-testid='article-body']",
        "dismiss_selectors": [".modal-close", "button[aria-label='Close']"],
    },
    "getpocket.com": {
        "wait_for_selector": "article, .reader-container",
        "dismiss_selectors": ["button[aria-label='Close']"],
    },
    "apple.news": {
        "wait_for_selector": "article, div.article-content",
        "dismiss_selectors": [],
    },
    "dev.to": {
        "wait_for_selector": "div#article-body, div.crayons-article__main, article",
        "dismiss_selectors": ["button[aria-label='Close']"],
    },
    "bsky.app": {
        "wait_for_selector": "div[data-testid*='postText']",
        "dismiss_selectors": [],
    },
    "ghost.org": {
        "wait_for_selector": "div.gh-content, div.post-content, article",
        "dismiss_selectors": [],
    },
    "wordpress.org": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": [],
    },

    # Batch 2: Extended East Asian Outlets
    "mk.co.kr": {
        "wait_for_selector": "div.news_cnt_detail_wrap, div#article_body",
        "dismiss_selectors": [".btn_close", ".layer_close"],
    },
    "hankyung.com": {
        "wait_for_selector": "#articletxt, div.article-body",
        "dismiss_selectors": [".btn_close"],
    },
    "hani.co.kr": {
        "wait_for_selector": "div.article-text, div.text",
        "dismiss_selectors": [".close"],
    },
    "khan.co.kr": {
        "wait_for_selector": "div.art_body, p.content_text",
        "dismiss_selectors": [".btn_close"],
    },
    "segye.com": {
        "wait_for_selector": "#article_txt, div.view_con",
        "dismiss_selectors": [".btn_close"],
    },
    "news1.kr": {
        "wait_for_selector": "div#articles_detail, div.detail",
        "dismiss_selectors": [".btn_close"],
    },
    "newsis.com": {
        "wait_for_selector": "article#articleBody, div.viewer",
        "dismiss_selectors": [".btn_close"],
    },
    "news.yahoo.co.jp": {
        "wait_for_selector": "div.article_body, #uamods-article",
        "dismiss_selectors": [".close", "button[aria-label='閉じる']"],
    },
    "asia.nikkei.com": {
        "wait_for_selector": "div.c-article_body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler", ".close-btn"],
    },
    "nikkei.com": {
        "wait_for_selector": "div.c-article_body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler", ".close-btn"],
    },
    "asahi.com": {
        "wait_for_selector": "div.ArticleBody, div.nfyDetail",
        "dismiss_selectors": [".close", "#onetrust-accept-btn-handler"],
    },
    "yomiuri.co.jp": {
        "wait_for_selector": "div.body-text, article",
        "dismiss_selectors": [".close", "#onetrust-accept-btn-handler"],
    },
    "mainichi.jp": {
        "wait_for_selector": "div.main-text, article",
        "dismiss_selectors": [".close", "#onetrust-accept-btn-handler"],
    },
    "english.kyodonews.net": {
        "wait_for_selector": "div.article-body, div.p-article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "kyodonews.net": {
        "wait_for_selector": "div.article-body, div.p-article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "mt.co.kr": {
        "wait_for_selector": "div#textBody, div.article_body",
        "dismiss_selectors": [".btn_close"],
    },
    "edaily.co.kr": {
        "wait_for_selector": "div.news_body, article",
        "dismiss_selectors": [".btn_close"],
    },
    "ohmynews.com": {
        "wait_for_selector": "div.content_box, div.at_content",
        "dismiss_selectors": [],
    },

    # Batch 3: Global Tech, Science & In-Depth Journalism
    "arstechnica.com": {
        "wait_for_selector": "div.article-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "wired.com": {
        "wait_for_selector": "div[data-testid='BodyWrapper']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "techcrunch.com": {
        "wait_for_selector": "div.entry-content, div.wp-block-post-content, article",
        "dismiss_selectors": ["button[name='agree']", "#consent-page button"],
    },
    "theatlantic.com": {
        "wait_for_selector": "section[data-component='ArticleBody'], article",
        "dismiss_selectors": ["button[data-qa='close-button']", "button.c-modal__close"],
    },
    "politico.com": {
        "wait_for_selector": "div.story-text, div.story-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "forbes.com": {
        "wait_for_selector": "div.article-body-container, div.body-container",
        "dismiss_selectors": [".fbs-ad--ad-blocker-modal button", "#onetrust-accept-btn-handler"],
    },
    "economist.com": {
        "wait_for_selector": "div[data-component='article-body'], article",
        "dismiss_selectors": ["#sp_message_container button", "button[aria-label='Close']"],
    },
    "propublica.org": {
        "wait_for_selector": "div.article-body, div.body-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "latimes.com": {
        "wait_for_selector": "article, div.page-content, div.story-body",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "aljazeera.com": {
        "wait_for_selector": "div.wysiwyg--all-content, div.wysiwyg",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "dw.com": {
        "wait_for_selector": "div.rich-text, div.article-content",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },
    "npr.org": {
        "wait_for_selector": "div#storytext, div.storytext",
        "dismiss_selectors": ["button#onetrust-accept-btn-handler"],
    },

    # Batch 4: Global Breaking News & International Presses
    "usatoday.com": {
        "wait_for_selector": "div.gnt_ar_b, div.story-asset",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "timesofindia.indiatimes.com": {
        "wait_for_selector": "div._s30J, div.main-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "indiatimes.com": {
        "wait_for_selector": "div._s30J, div.main-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "thehindu.com": {
        "wait_for_selector": "div#schemaDiv, div.articlebodycontent",
        "dismiss_selectors": [".close", ".tp-close"],
    },
    "smh.com.au": {
        "wait_for_selector": "div[data-testid='article-body'], article",
        "dismiss_selectors": ["button[data-testid='close-button']"],
    },
    "theage.com.au": {
        "wait_for_selector": "div[data-testid='article-body'], article",
        "dismiss_selectors": ["button[data-testid='close-button']"],
    },
    "abc.net.au": {
        "wait_for_selector": "div#body, div[data-component='ArticleBody']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "cbc.ca": {
        "wait_for_selector": "div.story, div.storyWrapper",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "theglobeandmail.com": {
        "wait_for_selector": "div.c-article-body, div[data-testid='article-body']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "scmp.com": {
        "wait_for_selector": "div.article-body-wrapper, div[class*='articleBody']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "straitstimes.com": {
        "wait_for_selector": "div.text-wrapper, div.story-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "france24.com": {
        "wait_for_selector": "div.t-content__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "lemonde.fr": {
        "wait_for_selector": "section.article__content, div.article__content",
        "dismiss_selectors": ["#js-cookie-banner button", ".gdpr-lmd-button"],
    },
    "spiegel.de": {
        "wait_for_selector": "div[data-sara-click-el='body_content'], div.word-break",
        "dismiss_selectors": ["button[title*='Einverstanden']", "#sp_message_container button"],
    },

    # Batch 5: Tech, Science, Crypto & Digital Culture
    "engadget.com": {
        "wait_for_selector": "div.caas-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler", "button[name='agree']"],
    },
    "gizmodo.com": {
        "wait_for_selector": "div.entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "mashable.com": {
        "wait_for_selector": "section.article-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "cnet.com": {
        "wait_for_selector": "div.c-articleCore_body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "venturebeat.com": {
        "wait_for_selector": "div[class*='article-body'], div.article-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "coindesk.com": {
        "wait_for_selector": "div.content-wrapper, div[data-module-name='article-body']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "cointelegraph.com": {
        "wait_for_selector": "div.post-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "sciencedaily.com": {
        "wait_for_selector": "div#story_text, div#story_content",
        "dismiss_selectors": [],
    },
    "phys.org": {
        "wait_for_selector": "div.article-main, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "polygon.com": {
        "wait_for_selector": "div.c-entry-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },

    # Batch 6: Business, Finance, Markets & Policy
    "businessinsider.com": {
        "wait_for_selector": "div.content-lock-content, div.post-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "insider.com": {
        "wait_for_selector": "div.content-lock-content, div.post-content",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "marketwatch.com": {
        "wait_for_selector": "div.article__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "barrons.com": {
        "wait_for_selector": "div.article__body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "fortune.com": {
        "wait_for_selector": "div[class*='articleBody'], div.articleContent",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "fastcompany.com": {
        "wait_for_selector": "div[data-component='article-body'], article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "inc.com": {
        "wait_for_selector": "div.article-body, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "spglobal.com": {
        "wait_for_selector": "div.article-content, div[class*='article-body']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "thehill.com": {
        "wait_for_selector": "div.article__text, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "axios.com": {
        "wait_for_selector": "div[data-cy='story-body'], div[class*='story-body']",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "semafor.com": {
        "wait_for_selector": "div[data-testid='story-content'], article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
    },
    "alltop.com": {
        "wait_for_selector": "div.entry-content, main",
        "dismiss_selectors": [],
    },
    "smartbrief.com": {
        "wait_for_selector": "div.brief-content, article",
        "dismiss_selectors": ["#onetrust-accept-btn-handler"],
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
