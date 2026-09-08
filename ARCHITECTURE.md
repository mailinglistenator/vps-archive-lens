# 🏛️ VPS Archive Lens — System Architecture & Technical Specifications

This document provides an in-depth technical explanation of the internal architecture, subsystems, data flow, and threat model of **VPS Archive Lens**.

---

## 📑 Contents

1. [Architectural Principles](#1-architectural-principles)
2. [Component Overview](#2-component-overview)
3. [End-to-End Request Lifecycle](#3-end-to-end-request-lifecycle)
4. [Subsystem Deep Dives](#4-subsystem-deep-dives)
   - [Subsystem A: Headless Chromium Archiver](#subsystem-a-headless-chromium-archiver)
   - [Subsystem B: DOM Sanitizer & Paywall Neutralizer](#subsystem-b-dom-sanitizer--paywall-neutralizer)
   - [Subsystem C: Reverse Image Proxy & Caching Layer](#subsystem-c-reverse-image-proxy--caching-layer)
   - [Subsystem D: AI Reader View & Extraction Pipeline](#subsystem-d-ai-reader-view--extraction-pipeline)
   - [Subsystem E: Background Retention Pruner](#subsystem-e-background-retention-pruner)
   - [Subsystem F: Companion Browser Extension](#subsystem-f-companion-browser-extension)
5. [Security Architecture & Threat Model](#5-security-architecture--threat-model)

---

## 1. Architectural Principles

Unlike public archiving services (`archive.today`, `Wayback Machine`) which aim for immutable, permanent digital records of the entire web, VPS Archive Lens is built specifically around **personal reading utility**:

- **Ephemeral by Design**: Content is kept for immediate reading and reference (default: 90 days), avoiding runaway disk consumption and legal/maintenance liabilities.
- **Client-Side Neutralization**: Pages are frozen at DOM-level and stripped of executable scripts (`<script>`) so that paywalls, tracking pixels, and dynamic paywall scripts cannot re-arm during playback.
- **Network Decoupling (ISP Bypass)**: When local ISPs censor or DPI-throttle foreign news CDNs, the VPS acts as an unblocked proxy gateway.
- **Fail-Safe Processing**: The AI Reader View combines deterministic extraction (`trafilatura`) with an optional LLM layer. If third-party AI APIs are down or unconfigured, the reader view gracefully renders instantaneously with zero downtime.

---

## 2. Component Overview

```
vps-archive-lens/
├── Dockerfile                  # Container definition based on Playwright Python
├── docker-compose.yml          # Production container orchestration
├── .env.example                # Configuration template
├── server/
│   ├── app.py                  # Core FastAPI application daemon
│   └── requirements.txt        # Python dependencies (FastAPI, Playwright, Trafilatura, etc.)
├── extension/                  # Manifest V3 browser extension
│   ├── manifest.json           # Extension metadata and permissions
│   ├── background.js           # Background service worker & context menu handler
│   ├── popup.html / popup.js   # Browser action toolbar popup
│   ├── options.html / options.js # Configuration options & connectivity test
│   └── icons/                  # Extension icons (16, 48, 128px)
└── snapshots/                  # Runtime storage directory (auto-created)
    ├── image_cache/            # 30-day binary image cache
    ├── {id}.html               # Raw unpaywalled HTML snapshots
    └── {id}_reader.html        # Pre-rendered AI Reader View pages
```

---

## 3. End-to-End Request Lifecycle

```
[User Browser]
      │
      ├──> [Route A: Remote VPS Scraper]
      │      1. Right-Click Link -> "Archive & Unpaywall with VPS"
      │      2. Opens: GET /archive?url={target_url}&token={token}
      │      3. VPS launches Playwright Chromium (stealth UA, ad blocking, scroll)
      │
      └──> [Route B: Direct DOM Push (Cloudflare & Paywall Silver Bullet)]
             1. User clicks "🚀 Push Tab DOM" in extension popup
             2. Extension runs chrome.scripting.executeScript to capture verified DOM
             3. Sends POST /archive/push with {url, html, title}
      │
      ▼
[FastAPI Server (server/app.py)]
      │
      ├─ 4. Verifies API_TOKEN against incoming headers / query params
      │
      ├─ 5. DOM Sanitization & Snapshot Creation (Common Pipeline)
      │      ├─ Decomposes all <script> elements (prevents re-arming)
      │      ├─ Injects Self-Healing Image Observer Script
      │      ├─ Injects Glassmorphism Top Navigation Bar
      │      └─ Persists /snapshots/{snapshot_id}.html
      │
      ├─ 6. Client redirects to /view/{snapshot_id}
      │
      └─ 7. (Optional) User clicks "📖 AI Reader View"
             │
             ├─ Trafilatura parses article metadata & markdown
             ├─ Deduplicates redundant caption paragraphs into <figure>
             ├─ Queries LLM for 3-bullet executive summary
             ├─ Rewrites image sources to /api/proxy/image?url=...
             └─ Persists & returns /snapshots/{snapshot_id}_reader.html
```

---

## 4. Subsystem Deep Dives

### Subsystem A: Headless Chromium Archiver
The archiver utilizes Microsoft Playwright running headless Chromium in an ephemeral, incognito browser context:
- **Cookie & Storage Isolation**: Every capture runs in a fresh `BrowserContext`. No cookies or session identifiers are shared across scrapes, ensuring metered article counts (e.g. "You have 2 free articles remaining") are perpetually reset to 0.
- **Referer Spoofing**: Injects `Referer: https://www.google.com/` on the initial request. Major news outlets allow free access to organic search engine visitors to maximize SEO rankings.
- **Ad & Tracker Interception**: Injects a network route interceptor that matches against common analytics domains (`googletagmanager.com`, `scorecardresearch.com`, `chartbeat.net`, `taboola.com`, etc.) and immediately calls `route.abort()`. This reduces bandwidth by 70% and prevents scripts from triggering anti-adblock modals.
- **Dynamic Hydration**: Simulates mouse scrolling in incremental viewport increments to ensure lazy-loaded images (e.g. `data-src` attributes) are properly loaded into the DOM before extraction.

---

### Subsystem B: DOM Sanitizer & Paywall Neutralizer
Once Playwright has completed page rendering:
1. **Script Stripping**: All `<script>` tags, inline scripts, and dynamic imports are completely decomposed via BeautifulSoup. This permanently freezes the page state, preventing paywall modals from appearing after page load.
2. **Style & Scroll Unlocking**: Injects critical CSS overrides directly into the `<head>`:
   ```css
   html, body {
       overflow: auto !important;
       position: static !important;
       height: auto !important;
   }
   ```
3. **Modal Overlay Removal**: Known paywall containers (Piano, Tinypass, Evolok, and common overlay class selectors like `.paywall-overlay`, `[id*="regwall"]`) are stripped from the DOM.
4. **Header Navigation Pill & `<base href>` Hijacking Defense**:
   - Injects a responsive, non-intrusive floating glassmorphism banner containing the original source link, archive timestamp, and a direct toggle to the AI Reader View.
   - **RFC 3986 Relative Link Immunization**: Raw snapshots inject `<base href="{resolved_url}">` into `<head>` so original remote stylesheets and fonts load correctly. Under the HTML specification, browsers resolve all relative paths (including root-relative `/reader/...`) against the `<base href>` target. The archiver neutralizes this by dynamically binding all pill navigation links to the VPS server origin (`request.base_url`) and attaching an inline `onclick="window.location.href = window.location.origin + '/reader/{id}'; return false;"` handler.

---

### Subsystem C: Reverse Image Proxy & Caching Layer
Many regional ISPs utilize Deep Packet Inspection (DPI) to block access to international news media or CDN infrastructure (e.g., `i.dailymail.com`). When a user accesses an archived page directly, their local connection receives a TCP reset (`ECONNRESET`) during the TLS handshake.

**How the Proxy Resolves This:**
1. **Endpoint**: `GET /api/proxy/image?url={encoded_origin_url}`.
2. **Server-Side Fetch**: The VPS (which is unblocked) fetches the image using standard HTTP headers (`User-Agent`, `Referer: https://www.google.com/`).
3. **On-Disk Caching**: Images are hashed and stored in `STORAGE_DIR/image_cache/{sha256}.bin`. Subsequent requests for the same image return immediately from local disk.
4. **Browser Cache Headers**: Responses include `Cache-Control: public, max-age=2592000` (30 days), enabling browser disk caching.
5. **Self-Healing Fallback in Raw Snapshots**:
   Raw snapshots include an active client-side listener that intercepts any `<img>` load error and seamlessly rewires the `src` attribute through the VPS proxy without requiring user interaction:
   ```javascript
   window.addEventListener('error', function(e) {
     if (e.target && e.target.tagName === 'IMG' && !e.target.dataset.vpsProxied && e.target.src && e.target.src.startsWith('http')) {
       e.target.dataset.vpsProxied = '1';
       e.target.src = window.location.origin + '/api/proxy/image?url=' + encodeURIComponent(e.target.src);
     }
   }, true);
   ```

---

### Subsystem D: AI Reader View & Extraction Pipeline
The AI Reader View (`/reader/{snapshot_id}`) provides a distraction-free, Apple Books-grade reading experience:

```
[Raw Snapshot HTML]
       │
       ▼
[Trafilatura Extractor] ──> Title, Author, Date, Lead Image, Clean Markdown
       │
       ├─ Caption Deduplication & Figure Reconstruction
       │    ├─ Rewrites <img> URLs to VPS Reverse Proxy
       │    ├─ Converts images into <figure class="article-figure">
       │    ├─ Adds <figcaption class="article-caption">
       │    └─ Purges identical/redundant trailing <p> caption tags
       │
       ▼
[AI Provider Hierarchy]
       ├─ 1. Nous Research (~/.hermes/auth.json -> upstage/solar-pro4:free)
       │    ├─ Autonomous OAuth refresh via portal.nousresearch.com
       │    ├─ Automatic HTTP 401 retry & token rotation handler
       │    └─ Standalone CLI device-code authenticator (scripts/auth_nous.py)
       ├─ 2. OpenCode Go / Zen (glm-5)
       ├─ 3. NeuralWatt (glm-5.2)
       ├─ 4. OpenRouter Free (nemotron-3.5-lightning:free)
       ├─ 5. Generic OpenAI-Compatible (Ollama, vLLM, DeepSeek, LocalAI)
       └─ 6. Clean Reconstructed Text (no duplicate lead paragraphs)
       │
       ├─ Smart Forum Directory vs. Article Detection
       │    ├─ High prose count (>= 120 words) always renders Reader View
       │    ├─ Low prose (< 120 words) directory pages offer Faithful Snapshot button
       │    └─ Automatic invalidation for stale false-forum caches
       │
       ▼
[Apple Books-Grade HTML Template]
       ├─ 4 Themes (Dark, OLED, Sepia, Light)
       ├─ Serif & Sans Typography Engine
       ├─ Top Reading Progress Bar (0-100%)
       └─ Print-to-PDF Optimized Layout
```

---

### Subsystem E: Background Retention Pruner
To prevent disk exhaustion on modest VPS instances:
- On every archive invocation, the server launches an asynchronous maintenance worker:
  `asyncio.create_task(prune_old_snapshots())`.
- Scans `STORAGE_DIR` and `STORAGE_DIR/image_cache/`.
- Deletes files whose modification timestamp exceeds `RETENTION_DAYS` (default: 90 days).
- Operates non-blockingly with zero impact on user request latency.

---

### Subsystem F: Companion Browser Extension
The browser extension follows Chrome Manifest V3 specifications:
- **Event-Driven Background Worker**: Uses `chrome.runtime.onInstalled` to register context menus and automatically open options on initial installation.
- **Storage Synchronization**: Settings (`vpsUrl` and `apiToken`) are persisted in `chrome.storage.sync`, syncing securely across all user devices.
- **Unified Capture Flow**: Supports both right-click context menu triggering and toolbar popup activation (current tab or arbitrary URL input).
- **DOM Scripting**: Uses `chrome.scripting.executeScript` to extract `document.documentElement.outerHTML` from the active tab.

---

### Subsystem G: Direct DOM Ingestion Pipeline (Cloudflare & Turnstile Silver Bullet)
Datacenter IP ranges (Hetzner, AWS, DigitalOcean, Linode) face increasing friction on the modern web due to automated bot-scoring heuristics (such as Cloudflare Turnstile, Akamai Bot Manager, and Cloudflare "Under Attack" Mode).

While Playwright can emulate stealth browser environments, Cloudflare's interactive Turnstile checks (`[ ] Verify you are human`) enforce WebAssembly proof-of-work, canvas hardware checks, and CDP debugger connection probes that fail or trigger interactive checkboxes on datacenter ASNs.

To definitively solve this:
1. **Client-Side Verification**: The user loads the target URL on their personal desktop or mobile browser. Because the user is on a residential ISP, they either pass Turnstile invisibly or complete it once with a human click.
2. **DOM Extraction**: The browser extension injects a lightweight content probe:
   ```javascript
   chrome.scripting.executeScript({
       target: { tabId: tab.id },
       func: () => ({ html: document.documentElement.outerHTML, url: window.location.href, title: document.title })
   });
   ```
3. **Authenticated Push Ingestion**: The rendered DOM is sent via `POST /archive/push` directly to the VPS.
4. **Seamless Server Sanitization**: The VPS processes the incoming DOM through the exact same sanitization pipeline (script neutralization, image proxy routing, navigation injection, and AI Reader extraction).

This dual-architecture guarantees **100% archive capability across all sites**, combining the zero-effort convenience of server-side scraping with the impenetrable bypass capability of client-side DOM pushing.

---

---

## 5. Security Architecture & Threat Model

| Threat | Risk Level | Mitigation in VPS Archive Lens |
| :--- | :--- | :--- |
| **Server-Side Request Forgery (SSRF)** | Critical | Strict URL scheme validation (`http`/`https`), DNS pre-resolution blocking private, loopback, link-local, cloud metadata (`169.254.169.254`), and IPv6 mapped addresses. 30x redirects are intercepted and re-validated via `SafeRedirectHandler`. |
| **DoS / Memory Exhaustion via Large Files** | High | Upfront `Content-Length` inspection and chunked streaming enforcement with a hard 20MB ceiling (`MAX_IMAGE_SIZE_BYTES`). |
| **RAM / CPU Starvation via Concurrent Chromium** | High | Concurrent Playwright browser sessions are strictly throttled via `asyncio.Semaphore(MAX_CONCURRENT_ARCHIVES)` (default: 2). |
| **Malicious Scripts in Snapshots** | High | All `<script>` and `<noscript>` elements and dynamic loaders are stripped from the DOM before storage or replay. |
| **Unauthorized Proxy Usage (Open Relay)** | High | The `/archive`, `/archive/push`, and `/api/archive` endpoints require strict `API_TOKEN` verification via headers, query params, or session cookies. |
| **Token Leakage in History / Referrers** | Medium | Seamless cookie auto-upgrade: passing a valid `?token=` sets an `HttpOnly`, `SameSite=Lax` `lens_token` cookie, allowing query strings to be cleanly omitted on subsequent visits. |
| **Referrer & Privacy Leakage** | Low | Snapshots and Reader Views inject `<meta name="referrer" content="no-referrer">`, preventing source URLs from leaking to third parties. |
| **Disk Exhaustion (DoS)** | Medium | Bounded retention pruning automatically deletes snapshots and cached images older than 90 days. |
