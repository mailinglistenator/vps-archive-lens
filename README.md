# ⚡ VPS Archive Lens

> **Self-hosted, lightweight web archiver and paywall/region bypass service with a companion right-click browser extension.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Manifest V3](https://img.shields.io/badge/Extension-Manifest%20V3-orange)](extension/)

**VPS Archive Lens** is an open-source alternative to public archiving services like `archive.ph` designed specifically for **personal use**. Instead of permanently storing petabytes of data, it focuses on **immediate, clean readability**:

1. **Evades Paywalls & Region Blocks**: Bypasses ISP/country blocks by routing through your VPS IP. Uses isolated incognito browser contexts to reset metered article counts.
2. **Strips Tracking & Paywall Modals**: Renders the complete DOM via headless Chromium, then strips `<script>` tags, paywall overlays (Piano, Tinypass, Evolok), and scroll-locks so paywalls cannot execute on playback.
3. **Auto-Pruning (Default: 90 Days)**: Automatically deletes snapshots older than 90 days in the background. Zero maintenance, zero runaway disk usage.
4. **Right-Click Browser Extension**: Integrates directly into Chrome, Brave, Edge, and Firefox. Right-click any link or article and click *"Archive & Unpaywall with VPS"*.

---

## 🏗️ Architecture

```
[Browser (You)] ──(Right-Click Link/Tab)──> [VPS Archive Lens Extension]
                                                    │
                                                    ▼
                                    [VPS Archiver Service (Port 8888)]
                                                    │
                                         ┌──────────┴──────────┐
                                         │  Headless Chromium  │
                                         │  - Google Referer   │
                                         │  - Block Trackers   │
                                         │  - Strip <script>   │
                                         └──────────┬──────────┘
                                                    │
                                                    ▼
                                          [Clean HTML Snapshot]
                                                    │
                                         (Auto-pruned after 90 days)
```

---

## 🚀 Quickstart (Docker Compose - Recommended)

### 1. Clone the repository on your VPS
```bash
git clone https://github.com/mailinglistenator/vps-archive-lens.git
cd vps-archive-lens
```

### 2. Configure Environment
```bash
cp .env.example .env
```

Edit `.env`:
```ini
PORT=8888
# Generate a secret token with: openssl rand -hex 20
API_TOKEN=your_secure_random_token_here
BASE_URL=http://YOUR_VPS_IP:8888
RETENTION_DAYS=90
```

### 3. Start the Container
```bash
docker compose up -d
```

Your service is now running at `http://YOUR_VPS_IP:8888`. Verify by visiting `http://YOUR_VPS_IP:8888/health`.

---

## 🛠️ Native Installation (Without Docker)

If you prefer running directly on Ubuntu/Debian:

```bash
# 1. Install dependencies
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# 2. Setup directory and virtual environment
cd server
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
sudo ./venv/bin/playwright install-deps chromium

# 3. Create .env
cp ../.env.example .env
nano .env

# 4. Run the server
./venv/bin/uvicorn app:app --host 0.0.0.0 --port 8888
```

### (Optional) Setup Systemd Service
```ini
# /etc/systemd/system/vps-archive-lens.service
[Unit]
Description=VPS Archive Lens Daemon
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/vps-archive-lens/server
ExecStart=/opt/vps-archive-lens/server/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8888
Restart=always
EnvironmentFile=/opt/vps-archive-lens/.env

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vps-archive-lens
```

---

## 🧩 Browser Extension Setup

The browser extension works on any Chromium-based browser (Chrome, Brave, Edge, Arc) and Firefox.

### Chrome / Brave / Edge
1. Download or clone this repository to your computer.
2. Open your browser and navigate to:
   - **Chrome**: `chrome://extensions`
   - **Brave**: `brave://extensions`
   - **Edge**: `edge://extensions`
3. Toggle **Developer mode** on (top-right corner).
4. Click **Load unpacked** (top-left corner).
5. Select the `extension/` directory inside this repository.
6. The Settings page will automatically open. Enter:
   - **VPS Archiver Endpoint URL**: `http://YOUR_VPS_IP:8888` (or your domain/tunnel)
   - **Secret API Token**: The `API_TOKEN` configured in your `.env`
7. Click **Save Settings**.

### Firefox
1. Go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...** and choose `extension/manifest.json`.
3. Configure settings via the extension options.

---

## 🔒 Security & Reverse Proxy

To keep your VPS secure and use HTTPS:

### Option A: Cloudflare Tunnel (Zero Port Forwarding)
```bash
cloudflared tunnel --url http://localhost:8888
```
Set `BASE_URL=https://your-tunnel-name.trycloudflare.com` in `.env`.

### Option B: Caddy (Automatic HTTPS)
```caddy
archive.yourdomain.com {
    reverse_proxy localhost:8888
}
```

### Option C: Nginx
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

## ⚙️ Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8888` | Port the FastAPI daemon listens on |
| `API_TOKEN` | *(empty)* | Secret key required in headers or query params (`?token=`) |
| `BASE_URL` | `http://localhost:8888` | Base URL used to generate snapshot view links |
| `STORAGE_DIR` | `./snapshots` | Path where HTML snapshots are stored |
| `RETENTION_DAYS` | `90` | Number of days to keep snapshots before auto-deletion |

---

## 📄 License
Released under the [MIT License](LICENSE).
