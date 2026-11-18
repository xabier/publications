#!/usr/bin/env python3
"""Build the whole site from Zotero data. One command after syncing:

    python3 sync_zotero.py      # Zotero MY_PUBLICATIONS -> data/zotero.json
    python3 build_site.py       # everything below

Reads
  data/zotero.json        metadata (from sync_zotero.py)
  data/site.json          hand-curated: slugs, highlighted, talks, extra media,
                          excluded items, redirects for renamed slugs
  data/keywords.json      the authors' own keywords (extract_keywords.py adds new ones)
  data/summaries/{slug}.html   optional extended summaries
  pdfs/{slug}.pdf, html/{slug}.html   full texts, found by slug
Writes
  index.html              publication list, filter counts, head JSON-LD
  citations/{slug}.bib|.ris
  then runs build_pages.py: landing pages p/{slug}/, llms.txt, llms-full.txt,
  publications.json, CSL-JSON, all.bib/.ris, sitemap.xml

Entry layout: the APA citation is the entry heading, with the title in bold
linking to the publication's landing page.
"""
import datetime
import html
import json
import os
import re
import sys
import unicodedata

import citelib

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
INDEX = os.path.join(ROOT, "index.html")
BASE = "https://publications.barandiaran.net"

TYPE_ORDER = ["journalArticle", "book", "bookSection", "conferencePaper", "report",
              "thesis", "preprint", "document"]
TYPE_LABEL = {"journalArticle": "Journal Article", "book": "Book", "bookSection": "Book Chapter",
              "conferencePaper": "Conference Paper", "report": "Report", "thesis": "Thesis",
              "preprint": "Preprint", "document": "Document"}
TYPE_PLURAL = {"journalArticle": "Journal Articles", "book": "Books", "bookSection": "Book Chapters",
               "conferencePaper": "Conference Papers", "report": "Reports", "thesis": "Theses",
               "preprint": "Preprints", "document": "Documents"}
ITALIC_TITLE = {"book", "report", "thesis", "preprint", "document"}
MEDIA = [  # (kind, label, tooltip)
    ("html", "HTML", "Read the full text as a web page (new tab)"),
    ("pdf", "Full PDF", "Open the full PDF (new tab)"),
    ("txt", "Text", "Plain text adapted for text-to-speech / screen readers"),
    ("audio", "Audio", "Audio narration of the full paper (M4B)"),
    ("podcast", "Podcast", "Podcast summary (M4A)"),
]


def esc(s):
    return html.escape(s or "", quote=True)


def load(name, default):
    p = os.path.join(DATA, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


# =================================================================== slugs

def slugify(year, title, n=6):
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", t)[:n]
    return "-".join([year or "nd"] + words)


# =================================================================== APA

def initials(given):
    out = []
    for part in given.split():
        if part.endswith(".") and len(part) <= 3 and "-" not in part:
            out.append(part)
            continue
        out.append("-".join(p[0] + "." for p in part.split("-") if p))
    return " ".join(out)


def apa_name(p):
    if "literal" in p:
        return p["literal"]
    return f"{p['family']}, {initials(p['given'])}" if p["given"] else p["family"]


def apa_name_fwd(p):  # editors inside a chapter reference: "X. E. Barandiaran"
    if "literal" in p:
        return p["literal"]
    return f"{initials(p['given'])} {p['family']}".strip()


def join_names(names):
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def end(s):
    s = s.strip()
    return s if s[-1:] in ".?!" else s + "."


def apa_parts(r, slug):
    """Return (lead, title_html, rest) of the APA reference, all HTML-escaped.
    The title is linked to the landing page and styled bold by CSS."""
    typ = r["Item Type"]
    authors = [p for p in r["creators"] if p["type"] == "author"]
    editors = [p for p in r["creators"] if p["type"] == "editor"]
    year = r["Publication Year"] or "n.d."
    if authors:
        who = join_names([apa_name(p) for p in authors])
    elif editors:
        who = join_names([apa_name(p) for p in editors]) + (" (Eds.)" if len(editors) > 1 else " (Ed.)")
    else:
        who = ""
    lead = esc(f"{who} ({year}).".strip())
    title = r["Title"].strip()
    if typ in ("report", "thesis", "preprint"):
        title = title.rstrip(".")  # a bracket/parenthesis follows the title
    t = esc(title)
    if typ in ITALIC_TITLE or typ == "book":
        t = f"<em>{t}</em>"
    title_html = f'<a class="pub-ref-title" href="p/{slug}/" title="Open this publication’s page">{t}</a>'
    venue, pages = r["Publication Title"].strip().rstrip("."), r["Pages"]
    rest = []
    if typ == "journalArticle":
        v = f"<em>{esc(venue)}</em>" if venue else ""
        if r["Volume"]:
            v += f", <em>{esc(r['Volume'])}</em>" + (f"({esc(r['Issue'])})" if r["Issue"] else "")
        elif r["Issue"]:
            v += f", ({esc(r['Issue'])})"
        if pages:
            v += f", {esc(pages)}"
        if v:
            rest.append(v + ".")
    elif typ in ("bookSection", "conferencePaper"):
        book = venue or r.get("Conference Name", "").strip().rstrip(".")
        s = "In "
        if editors and typ == "bookSection":
            s += esc(join_names([apa_name_fwd(p) for p in editors])) + \
                (" (Eds.), " if len(editors) > 1 else " (Ed.), ")
        s += f"<em>{esc(book)}</em>" if book else ""
        if pages:
            s += f" (pp. {esc(pages)})"
        if s.strip() != "In":
            rest.append(s + ".")
        if r["Publisher"]:
            rest.append(esc(end(r["Publisher"])))
    elif typ == "report":
        bits = ", ".join(x for x in (r["Type"], r["Number"]) if x)
        if bits:
            title_html += f" ({esc(bits)})"
        if r["Publisher"]:
            rest.append(esc(end(r["Publisher"])))
    elif typ == "thesis":
        bits = ", ".join(x for x in (r["Type"] or "Thesis", r["Publisher"]) if x)
        title_html += f" [{esc(bits)}]"
    elif typ == "preprint":
        title_html += " [Preprint]"
        if r["Publisher"]:
            rest.append(esc(end(r["Publisher"])))
    else:  # book, document
        if r["Publisher"]:
            rest.append(esc(end(r["Publisher"])))
    link = f"https://doi.org/{r['DOI']}" if r["DOI"] else r["Url"]
    if link:
        rest.append(f'<a href="{esc(link)}">{esc(link)}</a>')
    # sentence-final period after the title (unless it ends in ?/!/.)
    tail = "" if title[-1:] in ".?!" and typ not in ("report", "thesis", "preprint") else "."
    return lead, title_html + tail, " ".join(rest)


def apa_html(r, slug):
    lead, t, rest = apa_parts(r, slug)
    return f"{lead} {t} {rest}".strip()


# =================================================================== entries

def coins_row(r, kws):
    row = dict(r)
    row["Manual Tags"] = "; ".join(kws)
    row["Automatic Tags"] = ""
    return row


def entry_html(r, e):
    slug = e["slug"]
    meta = [f'<span class="pub-type">{esc(e["type_label"])}</span>',
            f'<span class="pub-year">{esc(e["year"])}</span>']
    if e["featured"]:
        meta.append('<span class="pub-featured" title="Highlighted publication">★ Highlighted</span>')
    for old in e["old_slugs"]:
        meta.append(f'<span id="{esc(old)}" class="old-anchor"></span>')
    lead, t, rest = apa_parts(r, slug)
    L = [f'<li class="pub-item" id="{esc(slug)}" data-type="{esc(r["Item Type"])}"'
         f' data-kw="{esc(" ".join(k.lower() for k in e["keywords"] or e["topics"]))}"'
         + (' data-featured="true"' if e["featured"] else "")
         + (f' data-doi="{esc(citelib.norm_doi(r["DOI"]))}"' if r["DOI"] else "") + ">",
         '      <div class="pub-meta">\n        ' + "\n        ".join(meta) + "\n      </div>",
         f'      <h2 class="pub-ref">{lead} {t} <span class="pub-source">{rest}</span></h2>']
    kws, label = (e["keywords"], "Keywords") if e["keywords"] else (e["topics"], "Topics")
    if kws:
        tip = ("The authors’ keywords" if label == "Keywords"
               else "Topics assigned by this site (the publication has no author keywords)")
        chips = ' <span class="kw-sep">·</span> '.join(
            f'<a class="pub-kw" href="#" data-kw="{esc(k)}">{esc(k)}</a>' for k in kws)
        L.append(f'      <div class="pub-keywords"><span class="pub-kw-label" title="{tip}">'
                 f'{label}:</span> {chips}</div>')
    acts = [f'<a class="pub-action pub-page-link" href="p/{slug}/" '
            f'title="This publication’s page: abstract, files, talks, citation">Details ›</a>']
    # Abstract and summary are loaded on demand from p/{slug}/index.json (script.js),
    # keeping this page short enough for AI agents to read whole. Without JS the
    # panel links to the landing page, which carries the full text.
    for field, label, extra in (("abstract", "Abstract", ""), ("summary", "Summary", " summary-panel")):
        if (field == "abstract" and e["abstract"]) or (field == "summary" and e["summary_html"]):
            acts.append(f'<details class="pub-details pub-lazy" data-src="p/{slug}/index.json" data-field="{field}">'
                        f'<summary class="pub-action-btn">{label}</summary>'
                        f'<div class="pub-panel{extra}"><p class="lazy-note"><a href="p/{slug}/#{field}">'
                        f'Read the {label.lower()} on the publication’s page</a></p></div></details>')
    for kind, label_, tip in MEDIA:
        if kind in e["links"]:
            lab = "Preprint" if (kind == "pdf" and r["Item Type"] == "preprint") else label_
            acts.append(f'<a class="pub-action" href="{esc(e["links"][kind])}" target="_blank" '
                        f'rel="noopener" title="{esc(tip)}">{lab}</a>')
    if not any(k in e["links"] for k in ("pdf", "html", "txt")):
        acts.append('<span class="pub-action-none">No open-access version available yet</span>')
    if e["talks"]:
        rows = []
        for tk in e["talks"]:
            m = tk["date"] + (f" · {tk['host']}" if tk.get("host") else "") + (f" · {tk['lang']}" if tk.get("lang") else "")
            rows.append(f'<li><a href="{esc(tk["url"])}" target="_blank" rel="noopener">{esc(tk["title"])}</a> '
                        f'<span class="talk-meta">{esc(m)}</span></li>')
        lab = "Talk" if len(rows) == 1 else f"Talks ({len(rows)})"
        acts.append(f'<details class="pub-details pub-talks"><summary class="pub-action-btn">{lab} ▾</summary>'
                    f'<div class="pub-panel pub-talks-panel"><ul class="talk-list">{"".join(rows)}</ul></div></details>')
    L.append('      <div class="pub-actions">\n        ' + "\n        ".join(acts) + "\n      </div>")
    L.append("      " + e["coins"])
    L.append("    </li>")
    return "\n".join(L)


def sort_key(r):
    d = r["Date"] or r["Publication Year"] or "0000"
    return (r["Publication Year"] or "0000", d)


# =================================================================== analytics

def set_analytics(doc, code, prefix):
    """Insert (or remove) the GoatCounter snippet + download-click tracker.
    prefix: relative path to the site root ("" or "../../")."""
    doc = re.sub(r"\s*<!--ANALYTICS-START-->.*?<!--ANALYTICS-END-->", "", doc, flags=re.S)
    if not code:
        return doc
    snippet = (f'\n<!--ANALYTICS-START--><script data-goatcounter="https://{code}.goatcounter.com/count" '
               f'async src="//gc.zgo.at/count.js"></script>'
               f'<script src="{prefix}track.js" defer></script><!--ANALYTICS-END-->')
    return doc.replace("</head>", snippet + "\n</head>", 1)


# =================================================================== main

def main():
    zot = load("zotero.json", None)
    if zot is None:
        sys.exit("data/zotero.json missing: run sync_zotero.py first.")
    site = load("site.json", {})
    kwdb = load("keywords.json", {})
    exclude = set(site.get("exclude", {}))
    zot = [r for r in zot if r["Key"] not in exclude]
    slugs = site.setdefault("slugs", {})
    featured = set(site.get("featured", []))
    media = site.get("media", {})
    talks = site.get("talks", {})
    redirects = site.get("redirects", {})
    old_by_new = {}
    for old, new in redirects.items():
        old_by_new.setdefault(new, []).append(old)

    # stable slugs: assign once, then frozen in data/site.json
    used = set(slugs.values())
    new_slugs = []
    for r in zot:
        if r["Key"] not in slugs:
            s = slugify(r["Publication Year"], r["Title"])
            base, i = s, 2
            while s in used:
                s = f"{base}-{i}"
                i += 1
            slugs[r["Key"]] = s
            used.add(s)
            new_slugs.append(s)
    if new_slugs:
        json.dump(site, open(os.path.join(DATA, "site.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    zot.sort(key=sort_key, reverse=True)
    zot = [r for r in zot if r["Key"] in featured] + [r for r in zot if r["Key"] not in featured]

    citelib._used_keys.clear()
    entries, li = [], []
    for r in zot:
        k, slug = r["Key"], slugs[r["Key"]]
        kws = (kwdb.get(k) or {}).get("keywords", [])
        topics = [] if kws else citelib.compute_keywords(r)
        links = {}
        for kind, path in (("pdf", f"pdfs/{slug}.pdf"), ("html", f"html/{slug}.html")):
            if os.path.exists(os.path.join(ROOT, path)):
                links[kind] = path
        for kind, path in media.get(k, {}).items():
            if os.path.exists(os.path.join(ROOT, path)):
                links[kind] = path
        sp = os.path.join(DATA, "summaries", f"{slug}.html")
        crow = coins_row(r, kws)
        bib = citelib.build_bib(crow, slug)
        with open(os.path.join(ROOT, "citations", f"{slug}.bib"), "w", encoding="utf-8") as fh:
            fh.write(bib)
        with open(os.path.join(ROOT, "citations", f"{slug}.ris"), "w", encoding="utf-8") as fh:
            fh.write(citelib.build_ris(crow))
        e = {
            "slug": slug, "key": k, "type": r["Item Type"],
            "type_label": TYPE_LABEL.get(r["Item Type"], "Document"),
            "year": r["Publication Year"], "featured": k in featured,
            "doi": r["DOI"], "title": r["Title"].strip(),
            "citation_html": apa_html(r, slug).replace(f'href="p/{slug}/"', f'href="{BASE}/p/{slug}/"'),
            "keywords": kws, "topics": topics,
            "keywords_note": (kwdb.get(k) or {}).get("note", ""),
            "abstract": r["Abstract Note"].strip(),
            "abstract_html": "",
            "summary_html": open(sp, encoding="utf-8").read().strip() if os.path.exists(sp) else "",
            "talks": talks.get(k, []),
            "links": links,
            "is_preprint_pdf": r["Item Type"] == "preprint",
            "coins": citelib.build_coins(crow, slug),
            "old_slugs": old_by_new.get(slug, []),
        }
        entries.append((e, r))
        li.append("    " + entry_html(r, e))

    doc = open(INDEX, encoding="utf-8").read()
    # 1. the list
    m = re.search(r'(<ol class="pub-list"[^>]*>)(.*?)(\n\s*</ol>)', doc, re.S)
    doc = doc[:m.end(1)] + "\n" + "\n".join(li) + doc[m.start(3):]
    # 2. compact head JSON-LD (full records live on the landing pages)
    graph = []
    for e, r in entries:
        node = {"@type": "Book" if r["Item Type"] == "book" else
                "Chapter" if r["Item Type"] == "bookSection" else
                "ScholarlyArticle" if r["Item Type"] in ("journalArticle", "conferencePaper", "preprint")
                else "CreativeWork",
                "@id": f"{BASE}/#{e['slug']}", "name": e["title"],
                "author": "; ".join(apa_name(p) for p in r["creators"] if p["type"] == "author")
                or "; ".join(apa_name(p) for p in r["creators"]),
                "datePublished": r["Date"] or r["Publication Year"],
                "mainEntityOfPage": f"{BASE}/p/{e['slug']}/"}
        if r["DOI"] or r["Url"]:
            node["sameAs"] = f"https://doi.org/{r['DOI']}" if r["DOI"] else r["Url"]
        graph.append(node)
    owner, profiles = site.get("owner", {}), site.get("profiles", [])
    if owner:
        person = {"@type": "Person", "@id": f"{BASE}/#author", "name": owner.get("name", ""),
                  "url": owner.get("url", ""), "sameAs": [p["url"] for p in profiles]}
        person["identifier"] = [{"@type": "PropertyValue", "propertyID": p["name"], "value": p["id"]}
                                for p in profiles]
        graph.insert(0, person)
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    doc = re.sub(r'(<script type="application/ld\+json">\s*).*?(\s*</script>)',
                 lambda mo: mo.group(1) + ld + mo.group(2), doc, count=1, flags=re.S)
    # 3. search / sort / filter panel, rebuilt every time (counts are live)
    counts = {t: sum(1 for e, _ in entries if e["type"] == t) for t in TYPE_ORDER}
    n = len(entries)
    nfeat = sum(1 for e, _ in entries if e["featured"])
    btns = [f'<button type="button" class="type-filter" data-type-filter="all" aria-pressed="true">All ({n})</button>']
    btns += [f'<button type="button" class="type-filter" data-type-filter="{t}" aria-pressed="false">'
             f'{TYPE_PLURAL[t]} ({c})</button>' for t, c in counts.items() if c]
    btns.append('<button type="button" class="type-filter featured-toggle" data-featured-filter aria-pressed="false" '
                f'title="Show only highlighted publications">★ Highlighted ({nfeat})</button>')
    panel = (
        '<div class="controls" role="search" aria-label="Search, sort and filter publications">\n'
        '      <div class="controls-row controls-top">\n'
        '        <input type="search" id="pub-search" placeholder="Search titles, keywords, abstracts…" '
        'aria-label="Search publications by title, keyword, abstract, author or year">\n'
        '        <span class="sort-select"><label for="pub-sort">Sort by</label>\n'
        '          <select id="pub-sort">\n'
        '            <option value="newest">Newest first</option>\n'
        '            <option value="oldest">Oldest first</option>\n'
        '            <option value="cited">Most cited first</option>\n'
        '          </select></span>\n'
        '      </div>\n'
        '      <div class="controls-row controls-filters" role="group" aria-label="Filter by type">\n'
        '        <span class="controls-label">Show:</span>\n        ' + "\n        ".join(btns) + "\n"
        '      </div>\n'
        f'      <p class="results-count" id="results-count" aria-live="polite">{n} of {n} publications</p>\n'
        '    </div>')
    doc = re.sub(r'<div class="controls".*?</div>(?=\s*(?:<p class="sort-note"[^>]*>.*?</p>\s*)?<ol class="pub-list")',
                 lambda mo: panel, doc, count=1, flags=re.S)
    doc = re.sub(r"\d+ items, reverse-chronological", f"{n} items, reverse-chronological", doc)
    # 3b. researcher profiles in the header (data/site.json -> profiles)
    doc = re.sub(r"\s*<!--PROFILES-START-->.*?<!--PROFILES-END-->", "", doc, flags=re.S)
    if profiles:
        rows = "\n".join(
            f'          <li><a href="{esc(p["url"])}" rel="me" target="_blank">{esc(p["name"])}</a> '
            f'<span class="pid">{esc(p["id"])}</span></li>' for p in profiles)
        box = ('\n    <!--PROFILES-START--><aside class="site-profiles" aria-label="Researcher profiles">\n'
               '        <p class="profiles-title">Researcher profiles</p>\n'
               f'        <ul>\n{rows}\n        </ul>\n      </aside><!--PROFILES-END-->')
        doc = doc.replace('<header class="site-header">', '<header class="site-header">' + box, 1)
    # 4. optional analytics (GoatCounter): off unless data/site.json has "goatcounter"
    doc = set_analytics(doc, site.get("goatcounter", ""), "")
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(doc)
    # search text that is no longer in the page (abstracts, summaries), loaded by
    # script.js the first time someone uses the search box
    six = {}
    for e, r in entries:
        t = " ".join([e["abstract"], re.sub(r"<[^>]+>", " ", e["summary_html"])])
        t = re.sub(r"\s+", " ", html.unescape(t)).strip().lower()
        if t:
            six[e["slug"]] = t
    with open(os.path.join(ROOT, "search-index.json"), "w", encoding="utf-8") as f:
        json.dump(six, f, ensure_ascii=False, separators=(",", ":"))

    print(f"index.html: {n} publications ({', '.join(f'{c} {TYPE_PLURAL[t].lower()}' for t, c in counts.items() if c)})")
    print(f"Author keywords: {sum(1 for e, _ in entries if e['keywords'])}; "
          f"derived topics only: {sum(1 for e, _ in entries if not e['keywords'])}")
    if new_slugs:
        print(f"New slugs (now frozen in data/site.json): {new_slugs}")
    no_kw = [e["slug"] for e, r in entries if not e["keywords"] and r["Key"] not in kwdb]
    missing_pdf = [e["slug"] for e, _ in entries if "pdf" not in e["links"]]
    print(f"No PDF on the site: {missing_pdf or 'none'}")

    import build_pages
    build_pages.ANALYTICS = site.get("goatcounter", "")
    build_pages.OWNER_ID = {"family": site.get("owner", {}).get("family", ""),
                            "sameAs": [p["url"] for p in site.get("profiles", [])]}
    build_pages.run(entries)


if __name__ == "__main__":
    main()
