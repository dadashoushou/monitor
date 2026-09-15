---
name: site-crawl-strategy
description: Diagnose and implement reusable crawl strategies for sites where article lists, anti-bot protection, or正文 extraction differ by site.
metadata:
  short-description: Diagnose site-specific crawl and article-content strategies
---

# Site Crawl Strategy

Use this skill when a monitored site can expose article titles or URLs but article pages fail, return anti-bot pages, or use a nonstandard content container.

## Workflow

1. Inspect the existing site entry, crawl mode, list selectors, historical results, and the shared crawler before editing anything.
2. Test the actual configured entry page with multiple article samples. Check:
   - list URL yield and duplicate behavior;
   - article URL shape;
   - static, dynamic, or stealth access;
   - whether the response is an anti-bot page;
   - whether usable text exists in raw HTML even when Scrapling's `.text` is empty.
3. Prefer a site configuration change when the existing crawler already supports the required behavior.
4. When a site uses a stable custom article container, add a reusable `content_selector` configuration instead of hard-coding the domain in crawler logic.
5. Keep list extraction and article-content extraction conceptually separate. A site may need a category/archive URL for lists and a stronger fetcher for detail pages.
6. Before changing configuration, report multi-article test results and ask for user approval when the user requested approval-gated changes.

## Project Conventions

- `crawl_mode` controls the fetcher: `html`, `js`, or `stealth`.
- `selectors` controls article-list extraction, including `css_selector`, `url_pattern`, and optional time extraction.
- `content_selector` controls a site-specific article-body container. The crawler should try this against raw HTML first, then fall back to the shared Scrapling content selectors.
- For Cloudflare-like sites, test `stealth` before concluding that the article has no content.
- Do not declare success from one article. Use several samples from the configured list page, preferably across different article layouts or dates.
- Do not write a site configuration change until the user approves it when approval was requested.

## Validation

After implementation:

- run the focused crawler tests;
- run the full test suite;
- if network/browser access is available, test several live articles from the configured list page;
- report whether content was extracted from the configured selector and whether any remaining failures are network or browser-environment limitations.
