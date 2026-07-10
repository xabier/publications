#!/usr/bin/env python3
"""Generate sitemap.xml and llms.txt from index.html's JSON-LD.

Run after build_citations.py + inject_titles.py:
    python3 build_sitemap.py

- sitemap.xml : homepage + every crawlable asset (html/, pdfs/, txt/,
  citations/) with lastmod from file mtime.
- llms.txt    : markdown index for AI systems (https://llmstxt.org),
  one line per publication with links to permalink, PDF, HTML and text
  versions when present.
"""

import json
import os
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

BASE = "https://publications.barandiaran.net"
ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- helpers

def load_graph():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    block = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )[0]
    return json.loads(block)["@graph"]


def mtime_iso(path):
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- sitemap

def build_sitemap():
    urls = [("/", mtime_iso(os.path.join(ROOT, "index.html")), "1.0")]
    for folder, prio in (("html", "0.8"), ("pdfs", "0.7"),
                         ("txt", "0.5"), ("citations", "0.3")):
        d = os.path.join(ROOT, folder)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                urls.append((f"/{folder}/{f}", mtime_iso(p), prio))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, prio in urls:
        lines.append(
            "  <url><loc>%s%s</loc><lastmod>%s</lastmod>"
            "<priority>%s</priority></url>"
            % (BASE, escape(loc), lastmod, prio)
        )
    lines.append("</urlset>")
    out = os.path.join(ROOT, "sitemap.xml")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"sitemap.xml: {len(urls)} URLs")


# ---------------------------------------------------------------- llms.txt

def build_llms(graph):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    head = f"""# Publications of Xabier E. Barandiaran

> Complete, open-access list of academic publications by Xabier E.
> Barandiaran (philosophy of cognitive science, enactivism, autonomy,
> agency, technopolitics, digital democracy). {len(graph)} items,
> reverse-chronological. Content licensed CC BY-SA 4.0 / GNU FDL 1.3;
> reuse encouraged. Last updated {today}.

The main page ({BASE}/) is a single semantic HTML document: every entry
carries an APA citation, abstract, keywords, JSON-LD and COinS metadata,
plus per-item BibTeX/RIS at {BASE}/citations/. Full texts: typeset PDFs
in /pdfs/, HTML reading versions in /html/, plain text (TTS-friendly)
in /txt/. All crawling — including AI training and agents — is welcome.

## Publications
"""
    lines = [head]
    for it in graph:
        slug = it["@id"].split("#", 1)[-1]
        year = it.get("datePublished", "")
        title = it.get("name", "").strip()
        authors = it.get("author", "")
        links = [f"[page]({BASE}/#{slug})"]
        for folder, ext, label in (("pdfs", ".pdf", "PDF"),
                                   ("html", ".html", "HTML")):
            if os.path.isfile(os.path.join(ROOT, folder, slug + ext)):
                links.append(f"[{label}]({BASE}/{folder}/{slug}{ext})")
        if it.get("url", "").startswith("http"):
            links.append(f"[DOI/URL]({it['url']})")
        lines.append(f"- **{title}** ({authors}, {year}) — "
                     + " · ".join(links))
    out = os.path.join(ROOT, "llms.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"llms.txt: {len(graph)} publications")


if __name__ == "__main__":
    g = load_graph()
    build_sitemap()
    build_llms(g)
