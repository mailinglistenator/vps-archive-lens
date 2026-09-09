# ⚡ VPS Archive Lens

> **Self-hosted, lightweight web archiver and paywall/region bypass service with an Apple Books-style AI Reader View, reverse image proxy, and a 1-click companion browser extension.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](server/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Manifest V3](https://img.shields.io/badge/Extension-Manifest%20V3-orange)](extension/)

> 💡 **Looking for deep technical specifications, data flow sequence diagrams, and threat models?** Check out [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 📖 Table of Contents

- [The Problem VPS Archive Lens Solves](#-the-problem-vps-archive-lens-solves)
- [Key Features](#-key-features)
- [High-Level Architecture & Request Flow](#-high-level-architecture--request-flow)
- [Deep Dive: How the Core Engines Work](#-deep-dive-how-the-core-engines-work)
  - [1. The Headless Chromium Archiving Engine](#1-the-headless-chromium-archiving-engine)
  - [2. The Reverse Image Proxy & ISP Bypass](#2-the-reverse-image-proxy--isp-bypass)
  - [3. The AI Reader View Pipeline](#3-the-ai-reader-view-pipeline)
  - [4. Automated Retention Pruning](#4-automated-retention-pruning)
- [Quickstart: Deployment](#-quickstart-deployment)
  - [Option A: Docker Compose (Recommended)](#option-a-docker-compose-recommended)
  - [Option B: Bare-Metal Ubuntu / Debian Systemd](#option-b-bare-metal-ubuntu--debian-systemd)
  - [Option C: Co-Locating with Hermes Agent](#option-c-co-locating-with-hermes-agent)
- [Browser Extension Installation](#-browser-extension-installation)
- [Configuration Reference (.env)](#-configuration-reference-env)
- [Multi-User Management & Sharing with Friends](#-multi-user-management--sharing-with-friends)
- [REST API Reference](#-rest-api-reference)
- [Production Hardening & HTTPS](#-production-hardening--https)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [License](#-license)

---

## 🎯 The Problem VPS Archive Lens Solves

Reading news, long-form essays, and technical journalism on the modern web has become increasingly frustrating:
- **Metered & Script-Enforced Paywalls**: Sites deploy aggressive client-side paywall walls (Piano, Tinypass, Evolok) and intrusive cookie walls that trap your browser.
- **Regional ISP Censorship & DPI Filtering**: Regional ISPs actively throttle or reset TLS connections (`curl: (35) Recv failure: Connection reset by peer`) when connecting to foreign news media and image CDNs (e.g., `i.dailymail.com`).
- **Cloudflare Captchas on Public Archivers**: Public archiving services (`archive.ph`, `archive.is`) are frequently blocked by Cloudflare turnstiles, rate limits, or slow queuing.
- **Disk Bloat of Traditional Archivers**: You usually only want to read an article once or reference it over the next couple of months—you don't need petabytes of permanent historical records.

**VPS Archive Lens** turns your cheap Linux VPS (Hetzner, DigitalOcean, Linode, Oracle Free Tier, etc.) into an unblockable personal archiving station:
1. **Fetches from your VPS IP**: Bypasses regional ISP blocks and resets metered paywalls using isolated incognito browser contexts.
2. **Strips Scripts & Modals**: Freezes the rendered DOM and strips `<script>` execution tags so paywalls cannot re-arm during reading.
3. **Proxies & Caches Images**: Bypasses local censorship of media CDNs by proxying image streams through your VPS with 30-day on-disk caching.
4. **AI Reader View with 3-Bullet Executive Summaries**: Transforms bloated news pages into an Apple Books-grade distraction-free reading experience with AI key takeaways powered by free LLMs.
5. **Zero-Maintenance Retention**: Automatically deletes snapshots older than 90 days in the background.

---

## ✨ Key Features

- 🖱️ **1-Click Browser Extension (Manifest V3)**:
  - **🚀 Push Tab DOM (Bypass Cloudflare)**: Captures the active tab's verified DOM and uploads it directly to your VPS (`POST /archive/push`). 100% bypasses Cloudflare Turnstile ("Verify you are human"), "Under Attack" mode, and subscriber paywalls you're logged into.
  - **🌐 Remote VPS Fetch**: Right-click any hyperlink or article -> *"Archive & Unpaywall with VPS"*.
  - Toolbar popup to push active tab, remote-fetch active tab, or paste custom URLs.
  - Quick launcher to browse all archived snapshots.
- 🚀 **Dual Capture Engine (Remote Stealth vs. Direct DOM Push)**:
  - **Remote Fetch**: Runs stealth Playwright Chromium on your VPS datacenter IP.
  - **Direct Push**: Ingests client-side DOM snapshots from residential browsers, solving the datacenter IP reputation challenge once and for all.
- 🎭 **Stealth Playwright Chromium Engine**:
  - Injects realistic desktop Chrome user agents, viewport sizes, and Google Referer headers.
  - Aborts analytics, telemetry, and tracking endpoints to accelerate page capture.
  - Auto-scrolls the page to trigger lazy-loaded images and dynamic content hydration.
- 🖼️ **Intelligent Reverse Image Proxy**:
  - Automatically routes image requests through the VPS (`/api/proxy/image?url=...`).
  - Caches binary image streams locally for 30 days (`Cache-Control: public, max-age=2592000`).
  - Injects dynamic self-healing listeners into raw snapshots to rescue any failing third-party images on the fly.
  - Gracefully hides broken images via `onerror`—no ugly broken image icons or stubs.
- 📖 **Apple Books-Grade AI Reader View (`/reader/{id}`)**:
  - **Deterministic Article Extraction**: Uses `trafilatura` to extract clean headlines, author bylines, publish dates, reading time, and clean markdown.
  - **Free AI Key Takeaways**: Auto-detects local Hermes setup or OpenAI-compatible endpoints to generate 3 punchy executive bullet points summarizing the core facts.
  - **Resilient Fallback**: Zero external dependencies needed—if the AI provider is offline or unconfigured, the reader view gracefully renders immediately.
  - **4 Color Themes**: Slate Dark (`#0f172a`), Pure OLED Black (`#000000`), Warm Sepia Parchment (`#f4ecd8`), and Crisp Paper Light (`#ffffff`).
  - **Customizable Typography**: Switch between Serif (`Charter`, `Merriweather`, `Georgia`) and Sans-serif (`Inter`, system UI), with dynamic font scaling (`A-` / `A+`) saved to `localStorage`.
  - **Reading Progress Bar**: Visual top-edge scroll percentage tracker (0–100%).
  - **Print & PDF Optimized**: Dedicated print stylesheet that strips headers and renders a clean, single-document printout.
- 📱 **Hermes Agent & Telegram Mobile Integration**:
  - Native Hermes Agent skill (`archive-lens`) and CLI tool.
  - Forward or paste any article link to your private Hermes Telegram bot on your phone.
  - Automatically captures, unpaywalls, and replies directly in Telegram with the headline, 3-bullet AI key takeaways, and direct links to the Reader View and Raw Snapshot.
- 🛡️ **Zero Data Leakage & Strict Authentication**:
  - API protected by private `API_TOKEN`.
  - Seamless `lens_token` session cookie auto-upgrade prevents token leakage in browser history or access logs.
  - Extension never exposes your private server secrets to destination sites.
  - Snapshot viewer injects `<meta name="referrer" content="no-referrer">` to protect your privacy.

---

## 🏗️ High-Level Architecture & Request Flow

```
+-----------------------------------------------------------------------------------------+
|                                    USER WORKSTATION                                     |
|                                                                                         |
|  [ Chrome / Brave / Edge / Firefox Extension ]                                          |
|           │                                                                             |
|           ├──> Route A (Remote Fetch): "Fetch & Archive via VPS"                        |
|           │    └──> GET /archive?url={target_url}&token={token}                         |
|           │                                                                             |
|           └──> Route B (Direct DOM Push): "Push Tab DOM to VPS"                         |
|                └──> Injects chrome.scripting to capture document.documentElement        |
|                └──> POST /archive/push (bypasses Cloudflare Turnstile & login walls)    |
+───────────────────────────┬─────────────────────────┬───────────────────────────────────+
                            │                         │
                            ▼                         ▼
+-----------------------------------------------------------------------------------------+
|                                  VPS ARCHIVER SERVER                                    |
|                                                                                         |
|  [ FastAPI Daemon (Port 8888) ]                                                         |
|    │                                                                                    |
|    ├──> Authentication Check (API_TOKEN verification)                                   |
|    │                                                                                    |
|    ├──> Ingestion Pipeline:                                                             |
|    │      ├─ [From Route A]: Stealth Playwright Chromium (Remote Scraper)               |
|    │      │    ├─ Realistic Chrome Stealth UA & Headers                                 |
|    │      │    ├─ Aborts Ad / Analytics / Telemetry Requests                            |
|    │      │    └─ Auto-Scrolls & Unlocks Scrollbars                                     |
|    │      │                                                                             |
|    │      └─ [From Route B]: Client DOM Ingestion (Zero CAPTCHA, Pre-Authenticated)     |
|    │                                                                                    |
|    ├──> DOM Sanitizer & Snapshot Generator                                              |
|    │      ├─ Strips <script> Tags (Prevents Paywalls from Re-Arming)                    |
|    │      ├─ Injects Self-Healing Image Observer Script                                 |
|    │      ├─ Injects Navigation Bar (Source Link + Reader Mode Trigger)                 |
|    │      └─ Persists HTML Snapshot to Disk: snapshots/{id}.html                        |
|    │                                                                                    |
|    ├──> 4. Reverse Image Proxy Engine (/api/proxy/image)                                |
|    │      ├─ Fetches Images from Origin CDNs (Bypasses Local ISP Censorship)            |
|    │      └─ Caches to /snapshots/image_cache/ (30-Day TTL)                             |
|    │                                                                                    |
|    ├──> 5. AI Reader View Pipeline (/reader/{id})                                       |
|    │      ├─ Trafilatura: Extracts Headline, Byline, Date, Hero Image, Clean Body       |
|    │      ├─ LLM Layer: Generates 3-Bullet Executive Summary                            |
|    │      │    (Nous Portal Free / OpenCode / NeuralWatt / OpenAI-Compatible)           |
|    │      ├─ Deduplicates Extracted Image Captions & Formats <figure> Tags              |
|    │      └─ Caches {snapshot_id}_reader.html (Sub-10ms subsequent hits)                |
|    │                                                                                    |
|    └──> 6. Background Retention Pruner                                                  |
|           └─ Purges snapshots and cached images older than RETENTION_DAYS (90 days)     |
+-----------------------------------------------------------------------------------------+
```

---

## 🔬 Deep Dive: How the Core Engines Work

### 1. The Headless Chromium Archiving Engine
When you request an archive, VPS Archive Lens spawns an isolated browser context inside Playwright Chromium:
1. **Referer Spoofing**: Injects `Referer: https://www.google.com/` and realistic navigation headers. Many paywalls allow users originating from Google Search to view articles for free.
2. **Ad & Tracker Interception**: Aborts network requests matching known telemetry and tracking domains (`googletagmanager`, `doubleclick`, `criteo`, `scorecardresearch`, `taboola`, etc.). This cuts load times by 60–80%.
3. **Scroll Hydration**: Automatically scrolls down the document to trigger `IntersectionObserver` elements and lazy-loaded image sources (`srcset`, `data-src`).
4. **DOM Freezing**: Extracts the fully rendered DOM, removes all executable `<script>` tags, and strips overlay blockers (Piano, Tinypass, Evolok, and generic modal backdrops) so that paywall scripts cannot execute during replay.

### 2. The Reverse Image Proxy & ISP Bypass
Many regional internet service providers (ISPs) actively censor news media domains or DPI-throttle image CDNs (e.g., `i.dailymail.com`). When a user visits a snapshot from their local network:
- The user's browser attempts to fetch the image from `i.dailymail.com`.
- The ISP middlebox injects a TCP RST packet or terminates the TLS handshake (`Connection reset by peer`), causing the browser to render a broken image icon.
- **The VPS Archive Lens Solution**:
  - The server includes an asynchronous streaming image proxy at `/api/proxy/image?url=...`.
  - In the **AI Reader View**, all images are automatically rewritten to point to this proxy.
  - In **Raw Snapshots**, a lightweight inline error listener catches any `<img>` load failures and dynamically reroutes them through the proxy using `window.location.origin` (preventing `<base href>` hijacking):
    ```javascript
    window.addEventListener('error', function(e) {
      if (e.target && e.target.tagName === 'IMG' && !e.target.dataset.vpsProxied && e.target.src && e.target.src.startsWith('http')) {
        e.target.dataset.vpsProxied = '1';
        e.target.src = window.location.origin + '/api/proxy/image?url=' + encodeURIComponent(e.target.src);
      }
    }, true);
    ```
  - Proxied images are stored in `STORAGE_DIR/image_cache/` and served with HTTP 304 / 30-day cache headers, saving bandwidth and delivering instant playback.
  - **`<base href>` Relative Link Defense**: Raw snapshots inject `<base href="...">` to preserve remote CSS/fonts. Under RFC 3986, browsers resolve relative links against `<base href>`. The archiver dynamically binds the floating navigation pill to the VPS origin with `onclick="window.location.href = window.location.origin + '/reader/{id}'; return false;"` so clicking the Reader View always stays on your VPS.

### 3. The AI Reader View Pipeline
The Reader View (`/reader/{snapshot_id}`) is engineered to never fail:
1. **Deterministic Parsing**: `trafilatura` extracts clean semantic Markdown directly from the unpaywalled HTML snapshot. It isolates the true article body while stripping ads, newsletter signups, and navigation cruft.
2. **Multi-Tier AI Provider Hierarchy**:
   - **Tier 1 (Nous Solar Pro Free)**: Auto-detects local Hermes credentials in `~/.hermes/auth.json` to access `upstage/solar-pro4:free`. Includes **autonomous OAuth token auto-refresh**, rotated token persistence, and automatic 401 retries. Easily link new accounts with `python3 server/scripts/auth_nous.py`.
   - **Tier 2 (OpenCode Go)**: If `OPENCODE_GO_API_KEY` is configured, queries OpenCode Zen (`glm-5`).
   - **Tier 3 (NeuralWatt)**: If `NEURALWATT_API_KEY` or `~/.hermes/config.yaml` is detected, queries NeuralWatt (`glm-5.2`).
   - **Tier 4 (OpenRouter Free)**: If `OPENROUTER_API_KEY` is set, queries `nvidia/nemotron-3.5-lightning:free`.
   - **Tier 5 (Generic OpenAI-Compatible)**: If `AI_BASE_URL` is set, connects to Ollama, vLLM, DeepSeek, LocalAI, or any standard endpoint.
   - **Tier 6 (Resilient Fallback)**: If no LLM is configured or an API call fails, the reader view displays the clean reconstructed article body without any broken or repetitive paragraphs.
3. **Smart Forum Index vs. Article Heuristic**:
   - Articles with common words like `"community"` or `"thread"` in their headline slug are accurately preserved and summarized.
   - True index/directory listings (e.g. `forumdisplay.php` with `< 120 words`) display an informative navigation card with a 1-click button to the Full Faithful Snapshot.
4. **Caption Deduplication & Figure Formatting**:
   - Trafilatura frequently extracts image captions twice (once in the Markdown image tag `![Caption](url)` and once in the following paragraph `<p>`).
   - The parser detects adjacent redundant text paragraphs and merges them cleanly into `<figure>` and `<figcaption>` elements with responsive shadow styling.

### 4. Automated Retention Pruning
Public archivers hoard data forever. VPS Archive Lens is designed for personal utility:
- On every archive request, an asynchronous background task checks `STORAGE_DIR`.
- Any HTML snapshot or cached image older than `RETENTION_DAYS` (default: **90 days**) is automatically deleted.
- Keeps your VPS disk consumption predictable and maintenance-free.

---

## 🚀 Quickstart: Deployment

### Option A: Docker Compose (Recommended)

Docker Compose provides an isolated environment pre-packaged with Playwright, Chromium, and all system libraries.

```bash
# 1. Clone the repository on your VPS
git clone https://github.com/mailinglistenator/vps-archive-lens.git
cd vps-archive-lens

# 2. Configure environment
cp .env.example .env
nano .env
```

Set your secret token and public address in `.env`:
```ini
PORT=8888
API_TOKEN=generate_a_secure_token_with_openssl
BASE_URL=http://YOUR_VPS_IP:8888
RETENTION_DAYS=90
```

Start the container in the background:
```bash
docker compose up -d
```

Verify your server is live:
```bash
curl http://localhost:8888/health
# {"status":"ok","snapshots_count":0,"version":"1.0.0"}
```

---

### Option B: Bare-Metal Ubuntu / Debian Systemd

If you prefer running directly on the host system without Docker:

```bash
# 1. Install system prerequisites
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# 2. Clone repository
git clone https://github.com/mailinglistenator/vps-archive-lens.git /opt/vps-archive-lens
cd /opt/vps-archive-lens

# 3. Create virtual environment & install requirements
python3 -m venv venv
./venv/bin/pip install -r server/requirements.txt

# 4. Install Playwright browser & system dependencies
./venv/bin/playwright install chromium
sudo ./venv/bin/playwright install-deps chromium

# 5. Setup configuration
cp .env.example .env
nano .env
```

#### Setup Systemd Service
Create `/etc/systemd/system/vps-archive-lens.service`:
```ini
[Unit]
Description=VPS Archive Lens Daemon
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/vps-archive-lens
EnvironmentFile=/opt/vps-archive-lens/.env
ExecStart=/opt/vps-archive-lens/venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8888
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vps-archive-lens
```

---

### Option C: Co-Locating with Hermes Agent

If you are already running [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) on your VPS:
1. Run VPS Archive Lens under the same user account (e.g., `/home/hermes/`).
2. VPS Archive Lens will **automatically detect** your existing Nous credentials in `~/.hermes/auth.json` or `~/.hermes/config.yaml`.
3. You immediately get **free, instant AI Key Takeaways** powered by Nous Solar Pro (`upstage/solar-pro4:free`) without entering any API keys!

---

## 🧩 Browser Extension Installation

The extension works on any Chromium-based browser (**Chrome, Brave, Edge, Arc**) and **Mozilla Firefox**.

### Chrome / Brave / Edge / Arc
1. Download or clone this repository to your local computer.
2. Open your browser extension management page:
   - **Chrome**: `chrome://extensions`
   - **Brave**: `brave://extensions`
   - **Edge**: `edge://extensions`
3. Toggle on **Developer mode** (top-right corner).
4. Click **Load unpacked** (top-left corner).
5. Select the `extension/` folder inside this repository.
6. The Settings page will automatically open. Enter:
   - **VPS Archiver Endpoint URL**: `http://YOUR_VPS_IP:8888` (or your domain/tunnel URL)
   - **Secret API Token**: The `API_TOKEN` you configured in `.env`
7. Click **Test Connection** to verify, then click **Save Settings**.

### Firefox
1. Navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**.
3. Select `extension/manifest.json`.
4. Click the extension icon and configure your VPS URL and API Token.

---

## ⚙️ Configuration Reference (.env)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8888` | Port the FastAPI application listens on. |
| `API_TOKEN` | *(empty)* | Secret key required to access `/archive` and `/list`. Highly recommended. |
| `BASE_URL` | `http://localhost:8888` | The public base URL used to construct links returned to the browser extension. |
| `STORAGE_DIR` | `./snapshots` | Path where HTML snapshots and the image cache are stored. |
| `RETENTION_DAYS` | `90` | Number of days before snapshots and image caches are pruned. |
| `OPENCODE_GO_API_KEY` | *(empty)* | Optional API key for OpenCode Go (`zen/go/v1`). |
| `NEURALWATT_API_KEY` | *(empty)* | Optional API key for NeuralWatt (`glm-5.2`). |
| `OPENROUTER_API_KEY` | *(empty)* | Optional API key for OpenRouter free tier models. |
| `AI_BASE_URL` | *(empty)* | Optional base URL for any OpenAI-compatible server (e.g. `http://localhost:11434/v1`). |
| `AI_API_KEY` | *(empty)* | Optional API key for OpenAI-compatible endpoint. |
| `AI_MODEL` | `default` | Model identifier for OpenAI-compatible endpoint. |

---

## 📡 REST API Reference

### 1. Create Archive Snapshot (Remote VPS Fetch)
Captures, strips, and unpaywalls a target web page using the server's headless Playwright Chromium.

- **Endpoint**: `GET /archive`
- **Authentication**: `X-API-Token` header, `Authorization: Bearer <token>`, or `?token=<token>` query param.
- **Parameters**:
  - `url` (required): Target web page URL to archive.
- **Example**:
  ```bash
  curl "http://YOUR_VPS_IP:8888/archive?url=https://example.com/article&token=YOUR_API_TOKEN"
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "snapshot_id": "20260908_090725_94bc8eb9b8cad5d6",
    "view_url": "http://YOUR_VPS_IP:8888/view/20260908_090725_94bc8eb9b8cad5d6",
    "reader_url": "http://YOUR_VPS_IP:8888/reader/20260908_090725_94bc8eb9b8cad5d6",
    "original_url": "https://example.com/article",
    "title": "Article Title",
    "timestamp": "2026-09-08 09:07:25 UTC"
  }
  ```
  *(Note: Browsers requesting `/archive` directly receive an animated loading screen that auto-redirects to `/view/{id}`).*

---

### 2. Direct DOM Push (Cloudflare & Paywall Bypass)
Directly ingests the client browser's rendered DOM. Used by the browser extension to bypass Cloudflare Turnstile captchas and capture articles when logged in.

- **Endpoint**: `POST /archive/push`
- **Authentication**: `X-API-Token` header, `Authorization: Bearer <token>`, or `?token=<token>` query param.
- **Request Body (JSON)**:
  ```json
  {
    "url": "https://forums.giantitp.com/showthread.php?12345",
    "html": "<!DOCTYPE html><html>...</html>",
    "title": "Page Title"
  }
  ```
- **Response**: Same JSON payload as `/archive`, returning `snapshot_id`, `view_url`, and `reader_url`.

---

### 3. View Raw Sanitized Snapshot
Renders the complete captured DOM with scripts stripped and paywall modals cleared.

- **Endpoint**: `GET /view/{snapshot_id}`
- **Authentication**: Public (no token needed, allows easy bookmarking and sharing).
- **Features**: Injects top floating navigation pill with links to original source and AI Reader View. Auto-heals broken CDN images via image proxy fallback.

---

### 4. AI Reader View
Renders an Apple Books-grade clean reading view with AI executive takeaways.

- **Endpoint**: `GET /reader/{snapshot_id}`
- **Parameters**:
  - `refresh` (optional): Set `?refresh=1` to force re-extraction and AI re-summarization.
- **Authentication**: Public.
- **Features**: Dynamic reading progress, 4 color themes, Serif/Sans typography controls, responsive figure captions, and clean Print-to-PDF styles.

---

### 5. Reverse Image Proxy
Fetches and caches images through the VPS network to bypass local ISP blocks.

- **Endpoint**: `GET /api/proxy/image`
- **Parameters**:
  - `url` (required): URL-encoded source image URL.
- **Example**:
  ```bash
  curl -I "http://YOUR_VPS_IP:8888/api/proxy/image?url=https%3A%2F%2Fi.dailymail.com%2F...%2Fimage.jpg"
  ```
- **Response**: Binary image stream with `Cache-Control: public, max-age=2592000` (30 days).

---

### 6. Snapshot Dashboard
Interactive web dashboard listing all recent snapshots and storage metrics.

- **Endpoint**: `GET /list`
- **Authentication**: Required (`API_TOKEN` or user token / cookie).

---

### 7. Health Check
System health status and snapshot count.

- **Endpoint**: `GET /health`
- **Authentication**: None.

---

### 8. User Management Admin API
Endpoints to manage multiple users, generate keys, and revoke access programmatically.

- **List Users**: `GET /api/admin/users` (Admin only)
- **Add User**: `POST /api/admin/users` (Admin only)
  ```json
  { "username": "bob", "role": "user", "token": "optional_custom_token" }
  ```
- **Revoke User**: `DELETE /api/admin/users/{username}` (Admin only)

---

## 👥 Multi-User Management & Sharing with Friends

VPS Archive Lens includes full multi-user support, allowing you to share your archiver with friends, family, and secondary devices while maintaining separate API tokens and authorship tracking.

### 🔑 Key Principles
1. **Independent Keys**: Each friend gets their own secret token (`lens_...`). You never need to share your root admin token.
2. **Authorship Attribution**: When a user pushes or archives an article (or downloads media), their username is saved with the snapshot metadata (`created_by: username`).
3. **Frictionless Sharing**: All article view links (`/view/{id}` and `/reader/{id}`) remain publicly viewable without authentication. Anyone with the link can read the unpaywalled article in their browser.
4. **Role Isolation**:
   - `admin`: Can create and revoke user accounts, view all snapshots, and manage server settings.
   - `user`: Can push snapshots, stream/download media, view snapshots, and filter by their own articles.

---

### Method A: Manage Users via Web Dashboard (GUI)
1. Open the VPS Power Hub dashboard (`/list` or `/`).
2. Click the **"👥 Access & Users"** tab.
3. Under **"Manage Users & Friends"**:
   - Enter your friend's username (e.g. `bob`).
   - Select their role (`User` or `Admin`).
   - Click **"➕ Add User"**.
4. Click **"📋 Copy Invite"** and send the pre-formatted invite snippet to your friend!

---

### Method B: Manage Users via CLI (`manage_users.py`)
Run the interactive admin CLI directly on your VPS:

```bash
# Add a friend with an auto-generated secure token
python3 server/manage_users.py add bob --role user

# Add an admin user with a custom token
python3 server/manage_users.py add alice --role admin --token my_custom_secret

# List all active users
python3 server/manage_users.py list

# Revoke access for a user immediately
python3 server/manage_users.py revoke bob
```

When you add a user, the CLI outputs a ready-to-send setup snippet:
```text
📋 Send this snippet to your friend to set up their browser extension:
  1. Load the extension in your browser (chrome://extensions -> Load Unpacked)
  2. In Extension Settings, set:
     - VPS Archiver URL: https://your-vps.example.com
     - Secret API Token: lens_xxxxxxxxxxxxxxxxxxxxxx
  3. Click 'Save Settings' and you're ready to archive!
```

---

### Method C: Environment Variable Seeding (`USER_TOKENS`)
You can optionally pre-seed multiple accounts directly in your `.env` or Docker configuration:
```env
USER_TOKENS="admin:admin_secret_123:admin, alice:alice_token_456:user, bob:bob_token_789:user"
```

---

## 🔒 Production Hardening & HTTPS

To protect your credentials and secure communications between your browser extension and VPS, put the archiver behind an HTTPS reverse proxy:

### Option 1: Cloudflare Tunnel (Zero Port Forwarding - Recommended)
With Cloudflare Tunnel, you do not need to open any firewall ports or expose your VPS IP address:
```bash
# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Run quick tunnel
cloudflared tunnel --url http://localhost:8888
```
Set `BASE_URL=https://your-tunnel-name.trycloudflare.com` in `.env`.

---

### Option 2: Caddy (Automatic Let's Encrypt SSL)
```caddy
archive.yourdomain.com {
    reverse_proxy localhost:8888
}
```

---

### Option 3: Nginx + Certbot
```nginx
server {
    listen 80;
    server_name archive.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## ❓ Troubleshooting & FAQ

### 1. Why do images fail on my local computer but load on the VPS?
Many regional internet service providers enforce country-level censorship or deep packet inspection (DPI) on foreign media CDNs (like `i.dailymail.com`). Your local ISP resets the connection during the TLS handshake (`curl: (35) Recv failure: Connection reset by peer`). 
VPS Archive Lens solves this automatically: all images in the **AI Reader View** are routed through the VPS reverse image proxy (`/api/proxy/image`), which bypasses your local ISP blocks and caches the images for fast local loading.

### 2. The extension says "Connection failed" during testing.
- Ensure the port (`8888`) is allowed in your VPS firewall:
  ```bash
  sudo ufw allow 8888/tcp
  ```
- Check that the daemon is running:
  ```bash
  sudo systemctl status vps-archive-lens
  # or
  docker compose ps
  ```
- Verify that `API_TOKEN` matches between your server `.env` and the extension options page.

### 3. Missing dependencies when running without Docker?
Playwright requires system graphical and font libraries. If Chromium fails to start, run:
```bash
sudo ./venv/bin/playwright install-deps chromium
```

### 4. What happens when a site is protected by Cloudflare Turnstile ("Verify you are human")?
Some websites (such as forums or heavily guarded blogs) configure Cloudflare WAF to challenge all connections originating from datacenter IP subnets (Hetzner, AWS, DigitalOcean) with an interactive Cloudflare Turnstile challenge.

When the VPS remote scraper encounters Turnstile, it raises an error explaining that interactive human verification is required from datacenter IPs.
**The Instant Fix**:
1. Open the page directly in your browser on your desktop or phone (your residential ISP connection will not be challenged or has already completed the check).
2. Click the **VPS Archive Lens** extension icon in your toolbar.
3. Click **"🚀 Push Tab DOM (Bypass Cloudflare)"**.
4. The extension extracts the verified, rendered DOM and uploads it to your VPS via `POST /archive/push`. The snapshot is stored and rendered instantly with complete images, full text, and AI Reader View support!

---

## 📄 License

VPS Archive Lens is open-source software licensed under the [MIT License](LICENSE).
