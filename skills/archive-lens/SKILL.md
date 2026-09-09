---
name: archive-lens
description: "Archive and unpaywall web articles, generate distraction-free AI Reader Views, and extract 3-bullet AI summaries using VPS Archive Lens."
version: 1.1.0
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [archive, unpaywall, reader, news, summary, article, web, lens]
  antigravity:
    tags: [archive, unpaywall, reader, news, summary, article, web, lens]
---

# VPS Archive Lens Skill

Use this skill whenever the user wants to archive, unpaywall, read, or summarize a web article or link (e.g. news sites, blogs, paywalled journalism, forums).

## When to Use

- "Archive this article: https://..."
- "Can you unpaywall this link: https://..."
- "Summarize and give me a reader link for: https://..."
- The user pastes an article URL and asks to "archive", "read", or "unpaywall" it.

## How to Execute

### Method 1: Direct API Call (Cross-Platform: Windows, macOS, Linux)
Call your VPS Archive Lens API using `curl.exe` (Windows built-in) or `curl`:

```bash
curl -s -X POST "<VPS_URL>/api/archive?url=<ENCODED_URL>&token=<YOUR_TOKEN>"
```

The server returns a JSON response:
```json
{
  "id": "20260909_071234_ab12cd34",
  "title": "Article Title",
  "url": "https://...",
  "view_url": "<VPS_URL>/view/20260909_071234_ab12cd34",
  "reader_url": "<VPS_URL>/reader/20260909_071234_ab12cd34"
}
```

### Method 2: CLI Wrapper (Linux / macOS / WSL)
If installed locally:
```bash
archive-lens "<URL>"
```

## Response Guidelines

Present the archived article cleanly to the user:
1. **Article Headline & Source**
2. 📖 **[AI Reader View](<reader_url>)** (Distraction-free, clean typography, 4 color themes)
3. 📸 **[Raw Captured Snapshot](<view_url>)** (Scripts and paywalls stripped, image proxy enabled)

