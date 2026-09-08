---
name: archive-lens
description: "Archive and unpaywall web articles, generate distraction-free AI Reader Views, and extract 3-bullet AI summaries using VPS Archive Lens."
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [archive, unpaywall, reader, news, summary, article, web, lens]
    related_skills: []
---

# VPS Archive Lens Skill

Use this skill whenever the user wants to archive, unpaywall, read, or summarize a web article or link (e.g. news sites, blogs, paywalled journalism, forums).

## When to Use

- "Archive this article: https://..."
- "Can you unpaywall this link: https://..."
- "Summarize and give me a reader link for: https://..."
- The user pastes an article URL and asks to "archive", "read", or "unpaywall" it.
- The user sends a link in Telegram and asks for a clean reading view or key takeaways.

## How to Execute

Run the `archive-lens` command via bash/terminal:

```bash
archive-lens "<URL>"
```

### Response Guidelines

The `archive-lens` CLI automatically captures the page, removes paywalls and tracking scripts, generates the AI key takeaways, and prints formatted Markdown containing:
1. Article Headline & Reading Time
2. 💡 3 AI Key Takeaways
3. 📖 Direct link to the distraction-free AI Reader View
4. 📸 Direct link to the raw captured DOM snapshot

Present this output directly to the user in your Telegram response.
