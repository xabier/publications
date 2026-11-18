#!/usr/bin/env python3
"""Inject a prominent, clickable title heading (<h2 class="pub-title">) at the
top of every publication entry in index.html.

The title text + canonical link are read from the per-item JSON-LD (@graph),
so this stays in sync with the generated citations. The heading links to the
local PDF when one exists (pdfs/{slug}.pdf), otherwise to the item's URL/DOI.

Idempotent: re-running strips previously injected <!--TITLE-START-->..<!--TITLE-END-->
blocks first, so it is safe to run after every pipeline build (step 5c).
"""
import json, re, html, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
PDF_DIR = os.path.join(HERE, "pdfs")

def load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def main():
    doc = load(INDEX)

    # --- 1. build slug -> {title, url} from JSON-LD @graph ---
    m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                  doc, re.DOTALL)
    if not m:
        sys.exit("No JSON-LD block found; aborting.")
    graph = json.loads(m.group(1)).get("@graph", [])
    meta = {}
    for node in graph:
        atid = node.get("@id", "")
        slug = atid.split("#", 1)[1] if "#" in atid else None
        if not slug:
            continue
        meta[slug] = {
            "title": node.get("name", "").strip(),
            "url": (node.get("url") or "").strip(),
        }

    # --- 2. strip any previously injected title blocks (idempotency) ---
    doc = re.sub(r'<!--TITLE-START-->.*?<!--TITLE-END-->\s*', "", doc, flags=re.DOTALL)

    # --- 3. inject a title heading right after each <li ...> opening tag ---
    injected = 0
    missing = []

    def repl(mo):
        nonlocal injected
        opening = mo.group(0)
        slug = mo.group("slug")
        info = meta.get(slug)
        if not info or not info["title"]:
            missing.append(slug)
            return opening
        title = html.escape(info["title"])
        pdf_rel = f"pdfs/{slug}.pdf"
        if os.path.exists(os.path.join(PDF_DIR, f"{slug}.pdf")):
            href = pdf_rel
        else:
            href = info["url"]
        if href:
            heading = (f'<h2 class="pub-title">'
                       f'<a href="{html.escape(href)}" target="_blank" rel="noopener">'
                       f'{title}</a></h2>')
        else:
            heading = f'<h2 class="pub-title">{title}</h2>'
        injected += 1
        return f'{opening}\n      <!--TITLE-START-->{heading}<!--TITLE-END-->'

    doc = re.sub(r'<li class="pub-item"[^>]*\bid="(?P<slug>[^"]+)"[^>]*>',
                 repl, doc)

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(doc)

    print(f"Injected {injected} title headings.")
    if missing:
        print(f"WARNING: no JSON-LD title for {len(missing)} slug(s): {missing[:5]}")

if __name__ == "__main__":
    main()
