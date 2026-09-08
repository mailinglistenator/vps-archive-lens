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
      │ 1. Right-Click Link -> "Archive & Unpaywall with VPS"
      ▼
[Extension Service Worker (background.js)]
      │
      │ 2. Reads vpsUrl & apiToken from chrome.storage.sync
      │ 3. Opens new tab: GET /archive?url={target_url}&token={token}
      ▼
[FastAPI Server (server/app.py)]
      │
      ├─ 4. Verifies API_TOKEN against incoming headers / query params
      │
      ├─ 5. Spawns Playwright Chromium Incognito Context
      │      ├─ Spoofs Referer ("https://www.google.com/")
      │      ├─ Aborts tracking requests (DoubleClick, Criteo, GA, etc.)
      │      ├─ Scrolls page down to trigger lazy-loaded media
      │      └─ Injects CSS overrides to unlock document scrollbars
      │
      ├─ 6. DOM Sanitization & Snapshot Creation
      │      ├─ Decomposes all <script> elements
      │      ├─ Injects Self-Healing Image Observer Script
      │      ├─ Injects Glassmorphism Header Pill
      │      └─ Persists /snapshots/{snapshot_id}.html
      │
      ├─ 7. Client redirects to /view/{snapshot_id}
      │
      └─ 8. (Optional) User clicks "📖 AI Reader View"
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
4. **Header Navigation Pill**: Injects a responsive, non-intrusive floating glassmorphism banner containing the original source link, archive timestamp, and a direct toggle to the AI Reader View.

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
     if (e.target && e.target.tagName === 'IMG' && !e.target.dataset.vpsProxied && e.target.src.startsWith('http')) {
       e.target.dataset.vpsProxied = '1';
       e.target.src = '/api/proxy/image?url=' + encodeURIComponent(e.target.src);
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
       ├─ 1. Local Hermes (~/.hermes/auth.json -> Nous Solar Pro Free)
       ├─ 2. OpenCode Go / Zen (glm-5)
       ├─ 3. NeuralWatt (glm-5.2)
       ├─ 4. OpenRouter Free (nemotron-3.5-lightning:free)
       ├─ 5. Generic OpenAI-Compatible (Ollama, vLLM, DeepSeek, LocalAI)
       └─ 6. Heuristic Fallback (First 3 core paragraphs)
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

---

## 5. Security Architecture & Threat Model

| Threat | Risk Level | Mitigation in VPS Archive Lens |
| :--- | :--- | :--- |
| **Malicious Scripts in Snapshots** | High | All `<script>` elements and dynamic loaders are stripped from the DOM before storage or replay. |
| **Unauthorized Proxy Usage (Open Relay)** | High | The `/archive` and `/list` endpoints require strict `API_TOKEN` verification via headers or query parameters. |
| **Server-Side Request Forgery (SSRF)** | Medium | The image proxy only accepts `http://` and `https://` schemas and blocks loopback/internal RFC1918 IPs by default. |
| **Referrer & Privacy Leakage** | Low | Snapshots and Reader Views inject `<meta name="referrer" content="no-referrer">`, preventing source URLs from leaking to third parties. |
| **Disk Exhaustion (DoS)** | Medium | Bounded retention pruning automatically deletes snapshots and cached images older than 90 days. |
