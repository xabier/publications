#!/usr/bin/env python3
"""Landing pages and machine-readable indexes. Called by build_site.py with
the records it has just built (running this file directly runs build_site.py):

    python3 sync_zotero.py
    python3 build_site.py           # calls build_pages.run(entries)

Reads    the entries built by build_site.py (Zotero record + site extras)
         and citations/{slug}.bib

Writes
  p/{slug}/index.html   landing page (people, Google Scholar, Zotero, agents)
  p/{slug}/index.md     the same content as Markdown (AI agents)
  p/{slug}/index.json   the same record as JSON
  publications.json     every record, structured
  publications.csl.json CSL-JSON (Zotero, pandoc, citation tools)
  all.bib / all.ris     every citation in one file
  llms.txt              short index for AI systems (https://llmstxt.org)
  llms-full.txt         every record with abstract and keywords, one file
  sitemap.xml
and rewrites index.html in place (idempotent; safe to re-run):
  - drops the bulky data-search attributes (script.js builds search text)
  - trims the head JSON-LD to an index (full records live on landing pages)
  - adds a "Details" button per entry linking to its landing page
  - adds machine-readable links to <head> and the header
"""

import csv
import datetime
import html
import json
import os
import re
import shutil
import sys
from xml.sax.saxutils import escape as xml_escape

BASE = "https://publications.barandiaran.net"
ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")
PAGES_DIR = os.path.join(ROOT, "p")
SITE_NAME = "Xabier E. Barandiaran — Publications"
OWNER = "Xabier E. Barandiaran"
LICENSES = [
    ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    ("GNU FDL 1.3", "https://www.gnu.org/licenses/fdl-1.3.html"),
]
LOGO = "https://xabier.barandiaran.net/wp-content/uploads/2020/03/cropped-logo-rojo.png"

TYPE_LABEL = {
    "journalArticle": "Journal Article", "book": "Book",
    "bookSection": "Book Chapter", "conferencePaper": "Conference Paper",
    "report": "Report", "thesis": "Thesis", "preprint": "Preprint",
    "document": "Document",
}
SCHEMA_TYPE = {
    "journalArticle": "ScholarlyArticle", "book": "Book", "bookSection": "Chapter",
    "conferencePaper": "ScholarlyArticle", "report": "Report", "thesis": "Thesis",
    "preprint": "ScholarlyArticle", "document": "CreativeWork",
}
CSL_TYPE = {
    "journalArticle": "article-journal", "book": "book", "bookSection": "chapter",
    "conferencePaper": "paper-conference", "report": "report", "thesis": "thesis",
    "preprint": "article", "document": "document",
}
LANG = {"en": "en", "english": "en", "eng": "en", "spanish, español": "es",
        "es": "es", "español": "es", "spanish": "es", "italiano": "it",
        "italian": "it", "it": "it"}


# =================================================================== helpers

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def esc(s):
    return html.escape(s or "", quote=True)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def norm_doi(s):
    s = (s or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", s)


def strip_tags(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def squash(s):
    return re.sub(r"\s+", " ", s or "").strip()


def shorten(s, n=300):
    s = squash(s)
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.") + "…"


def html_to_md(fragment):
    """Small HTML -> Markdown converter for the markup this site uses
    (p, h3/h4, blockquote+cite, em/i, strong/b, a, ul/li, br)."""
    s = fragment or ""
    s = re.sub(r"<button[^>]*>.*?</button>", "", s, flags=re.S)
    s = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
               lambda m: f"[{strip_tags(m.group(2)).strip()}]({html.unescape(m.group(1))})"
               if strip_tags(m.group(2)).strip() != html.unescape(m.group(1))
               else html.unescape(m.group(1)), s, flags=re.S)
    s = re.sub(r"</?(em|i)>", "*", s)
    s = re.sub(r"</?(strong|b)>", "**", s)
    s = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>",
               lambda m: f"\n\n### {squash(strip_tags(m.group(1)))}\n\n", s, flags=re.S)

    def bq(m):
        inner = m.group(1)
        cite = ""
        c = re.search(r"<cite[^>]*>(.*?)</cite>", inner, re.S)
        if c:
            cite = squash(strip_tags(c.group(1)))
            inner = inner[:c.start()] + inner[c.end():]
        text = squash(strip_tags(inner))
        out = f"\n\n> {text}"
        if cite:
            out += f"\n> {cite}"
        return out + "\n\n"
    s = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>", bq, s, flags=re.S)
    s = re.sub(r"<li[^>]*>(.*?)</li>", lambda m: f"\n- {squash(strip_tags(m.group(1)))}", s, flags=re.S)
    s = re.sub(r"</?(ul|ol)[^>]*>", "\n", s)
    s = re.sub(r"<p[^>]*>(.*?)</p>", lambda m: f"\n\n{squash(strip_tags(m.group(1)))}\n\n", s, flags=re.S)
    s = strip_tags(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def citation_text(cit_html):
    """APA citation HTML -> plain text and Markdown."""
    md = re.sub(r"<a [^>]*>(.*?)</a>", r"\1", cit_html, flags=re.S)
    md = re.sub(r"</?em>", "*", md)
    md = squash(strip_tags(md))
    plain = md.replace("*", "")
    return plain, md


def f(rec, k):
    return (rec.get(k) or "").strip()


def split_people(s):
    out = []
    for p in [x.strip() for x in (s or "").split(";") if x.strip()]:
        if "," in p:
            fam, giv = [x.strip() for x in p.split(",", 1)]
            out.append({"family": fam, "given": giv})
        else:
            out.append({"literal": p})
    return out


def person_name(p):
    if "literal" in p:
        return p["literal"]
    return f"{p['given']} {p['family']}".strip()


def person_inverted(p):
    if "literal" in p:
        return p["literal"]
    return f"{p['family']}, {p['given']}"


# =================================================================== build records

def build_record(e, rec, node):
    slug = e["slug"]
    page = f"{BASE}/p/{slug}/"
    authors = split_people(f(rec, "Author"))
    editors = split_people(f(rec, "Editor"))
    if not authors and node.get("author"):
        authors = [{"literal": node["author"]}]
    doi = f(rec, "DOI") or e["doi"]
    url = f(rec, "Url") or (f"https://doi.org/{doi}" if doi else node.get("url", ""))
    abstract = e.get("abstract") or squash(strip_tags(e["abstract_html"])) or f(rec, "Abstract Note") \
        or node.get("description", "")
    date = f(rec, "Date") or e["year"]
    lang = LANG.get(f(rec, "Language").lower(), "")
    cit_plain, cit_md = citation_text(e["citation_html"])
    links = {"landing": page, "markdown": page + "index.md", "json": page + "index.json"}
    for k in ("pdf", "postprint", "html", "txt", "audio", "podcast"):
        if k in e["links"]:
            links[k] = f"{BASE}/{e['links'][k]}"
    for k, ext in (("bibtex", "bib"), ("ris", "ris")):
        if os.path.exists(os.path.join(ROOT, "citations", f"{slug}.{ext}")):
            links[k] = f"{BASE}/citations/{slug}.{ext}"
    if url:
        links["publisher"] = url
    return {
        "slug": slug,
        "id": page,
        "type": e["type"],
        "type_label": e["type_label"],
        "title": e["title"] or f(rec, "Title"),
        "authors": authors,
        "author_string": "; ".join(person_inverted(a) for a in authors),
        "editors": editors,
        "year": e["year"] or f(rec, "Publication Year"),
        "date": date,
        "venue": f(rec, "Publication Title"),
        "series": f(rec, "Series"),
        "volume": f(rec, "Volume"),
        "issue": f(rec, "Issue"),
        "pages": f(rec, "Pages"),
        "publisher": f(rec, "Publisher"),
        "place": f(rec, "Place"),
        "note": f(rec, "Note"),
        "isbn": f(rec, "ISBN"),
        "issn": f(rec, "ISSN"),
        "doi": doi,
        "url": url,
        "language": lang,
        "abstract": abstract,
        "keywords": e["keywords"],
        "topics": e["topics"],
        "keywords_note": e.get("keywords_note", ""),
        "featured": e["featured"],
        "talks": [{"url": t["url"], "title": t["title"],
                   "meta": t.get("meta") or " · ".join(x for x in (t.get("date"), t.get("host"), t.get("lang")) if x)}
                  for t in e["talks"]],
        "has_summary": bool(e["summary_html"]),
        "citation_apa": cit_plain,
        "links": links,
        "_citation_html": e["citation_html"],
        "_citation_md": cit_md,
        "_summary_html": e["summary_html"],
        "_abstract_html": e["abstract_html"],
        "_local": e["links"],
        "_is_preprint_pdf": e.get("is_preprint_pdf", False),
    }


def public(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def csl(r):
    item = {"id": r["slug"], "type": CSL_TYPE.get(r["type"], "document"),
            "title": r["title"]}
    if r["authors"]:
        item["author"] = r["authors"]
    if r["editors"] and r["type"] in ("bookSection", "book", "conferencePaper"):
        item["editor"] = r["editors"]
    parts = [int(x) for x in re.findall(r"\d+", r["date"])[:3]] if r["date"] else []
    if parts and parts[0] > 999:
        item["issued"] = {"date-parts": [parts]}
    elif r["year"].isdigit():
        item["issued"] = {"date-parts": [[int(r["year"])]]}
    for k, ck in (("venue", "container-title"), ("volume", "volume"), ("issue", "issue"),
                  ("pages", "page"), ("publisher", "publisher"), ("place", "publisher-place"),
                  ("isbn", "ISBN"), ("issn", "ISSN"), ("doi", "DOI"), ("url", "URL"),
                  ("abstract", "abstract"), ("language", "language"),
                  ("series", "collection-title"), ("note", "note")):
        if r[k]:
            item[ck] = r[k]
    if r["keywords"]:
        item["keyword"] = ", ".join(r["keywords"])
    return item


def jsonld(r):
    node = {"@context": "https://schema.org",
            "@type": SCHEMA_TYPE.get(r["type"], "CreativeWork"),
            "@id": r["id"], "url": r["id"], "mainEntityOfPage": r["id"],
            "name": r["title"], "headline": r["title"][:110]}
    if r["authors"]:
        node["author"] = [{"@type": "Person", "name": person_name(a),
                           **({"familyName": a["family"], "givenName": a["given"]}
                              if "family" in a else {}),
                           # the site owner: link to his researcher profiles (ORCID etc.)
                           **({"@id": f"{BASE}/#author", "sameAs": OWNER_ID["sameAs"]}
                              if OWNER_ID.get("family") and a.get("family") == OWNER_ID["family"] else {})}
                          for a in r["authors"]]
    if r["editors"] and r["type"] in ("book", "bookSection"):
        node["editor"] = [{"@type": "Person", "name": person_name(a)} for a in r["editors"]]
    node["datePublished"] = r["date"] or r["year"]
    if r["abstract"]:
        node["abstract"] = r["abstract"]
        node["description"] = shorten(r["abstract"], 300)
    if r["keywords"]:
        node["keywords"] = r["keywords"]
    if r["language"]:
        node["inLanguage"] = r["language"]
    if r["venue"]:
        if r["type"] == "journalArticle":
            node["isPartOf"] = {"@type": "Periodical", "name": r["venue"],
                                **({"issn": r["issn"]} if r["issn"] else {})}
        elif r["type"] == "bookSection":
            node["isPartOf"] = {"@type": "Book", "name": r["venue"],
                                **({"isbn": r["isbn"]} if r["isbn"] else {})}
        else:
            node["isPartOf"] = {"@type": "CreativeWork", "name": r["venue"]}
    if r["type"] == "book" and r["isbn"]:
        node["isbn"] = r["isbn"]
    if r["pages"]:
        node["pagination"] = r["pages"]
    if r["publisher"]:
        node["publisher"] = {"@type": "Organization", "name": r["publisher"]}
    if r["doi"]:
        node["identifier"] = {"@type": "PropertyValue", "propertyID": "DOI", "value": r["doi"]}
        node["sameAs"] = f"https://doi.org/{r['doi']}"
    elif r["url"]:
        node["sameAs"] = r["url"]
    media = []
    for k, fmt in (("pdf", "application/pdf"), ("postprint", "application/pdf"), ("html", "text/html"), ("txt", "text/plain"),
                   ("audio", "audio/mp4"), ("podcast", "audio/mp4")):
        if k in r["links"]:
            media.append({"@type": "MediaObject", "contentUrl": r["links"][k], "encodingFormat": fmt})
    if media:
        node["associatedMedia"] = media
    if "pdf" in r["links"]:
        node["isAccessibleForFree"] = True
    if cover_path(r["slug"]):
        node["image"] = f"{BASE}/{cover_path(r['slug'])}"
    if r["talks"]:
        node["subjectOf"] = [{"@type": "VideoObject", "name": t["title"], "url": t["url"]}
                             for t in r["talks"]]
    return node


# =================================================================== landing page (HTML)

def highwire(r):
    tags = [("citation_title", r["title"])]
    for a in r["authors"]:
        tags.append(("citation_author", person_inverted(a)))
    d = r["date"] or r["year"]
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", d or "")
    if m:
        tags.append(("citation_publication_date", "/".join(x for x in m.groups() if x)))
    t = r["type"]
    if r["venue"]:
        key = {"journalArticle": "citation_journal_title",
               "conferencePaper": "citation_conference_title",
               "bookSection": "citation_inbook_title"}.get(t)
        if key:
            tags.append((key, r["venue"]))
    if t == "thesis" and r["publisher"]:
        tags.append(("citation_dissertation_institution", r["publisher"]))
    if t == "report" and r["publisher"]:
        tags.append(("citation_technical_report_institution", r["publisher"]))
    for k, hk in (("volume", "citation_volume"), ("issue", "citation_issue"),
                  ("publisher", "citation_publisher"), ("doi", "citation_doi"),
                  ("isbn", "citation_isbn"), ("issn", "citation_issn"),
                  ("language", "citation_language")):
        if r[k]:
            tags.append((hk, r[k]))
    pm = re.match(r"\s*(\S+?)\s*[-–]{1,2}\s*(\S+)\s*$", r["pages"] or "")
    if pm:
        tags += [("citation_firstpage", pm.group(1)), ("citation_lastpage", pm.group(2))]
    if r["keywords"]:
        tags.append(("citation_keywords", "; ".join(r["keywords"])))
    if "pdf" in r["links"]:
        tags.append(("citation_pdf_url", r["links"]["pdf"]))
    if "html" in r["links"]:
        tags.append(("citation_fulltext_html_url", r["links"]["html"]))
    tags.append(("citation_abstract_html_url", r["id"]))
    return "\n".join(f'<meta name="{k}" content="{esc(v)}">' for k, v in tags)


def coins_span(slug):
    m = COINS.get(slug)
    return m or ""


def venue_line(r):
    bits = []
    if r["venue"]:
        v = f"<em>{esc(r['venue'])}</em>"
        if r["volume"]:
            v += f", {esc(r['volume'])}"
            if r["issue"]:
                v += f"({esc(r['issue'])})"
        elif r["issue"]:
            v += f", no. {esc(r['issue'])}"
        if r["pages"]:
            v += f", {esc(r['pages'])}"
        bits.append(("In " if r["type"] == "bookSection" else "") + v)
    if r["note"]:
        bits.append(esc(r["note"]))
    if r["publisher"]:
        bits.append(esc(r["publisher"]) + (f", {esc(r['place'])}" if r["place"] else ""))
    return " · ".join(bits)


def details_rows(r):
    rows = [("Type", esc(r["type_label"]))]
    if r["authors"]:
        rows.append(("Authors" if len(r["authors"]) > 1 else "Author",
                     esc("; ".join(person_inverted(a) for a in r["authors"]))))
    if r["editors"] and r["type"] in ("book", "bookSection", "conferencePaper"):
        rows.append(("Editors" if len(r["editors"]) > 1 else "Editor",
                     esc("; ".join(person_inverted(a) for a in r["editors"]))))
    label = {"journalArticle": "Journal", "bookSection": "Book",
             "conferencePaper": "Proceedings"}.get(r["type"], "Published in")
    for k, lab in (("venue", label), ("series", "Series"), ("volume", "Volume"),
                   ("issue", "Issue"), ("pages", "Pages"), ("publisher", "Publisher"),
                   ("place", "Place"), ("date", "Date"), ("isbn", "ISBN"),
                   ("issn", "ISSN"), ("language", "Language"), ("note", "Status")):
        if r[k]:
            v = {"en": "English", "es": "Spanish", "it": "Italian"}.get(r[k], r[k]) \
                if k == "language" else r[k]
            rows.append((lab, esc(v)))
    if r["doi"]:
        rows.append(("DOI", f'<a href="https://doi.org/{esc(r["doi"])}">{esc(r["doi"])}</a>'))
    elif r["url"]:
        rows.append(("URL", f'<a href="{esc(r["url"])}">{esc(r["url"])}</a>'))
    return "\n".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)


ACTION_DEFS = [
    ("pdf", "Full PDF", "Open the full published PDF"),
    ("html", "HTML", "Read the full text as a web page"),
    ("txt", "Text", "Plain text adapted for text-to-speech / screen readers"),
    ("audio", "Audio", "Audio narration of the full paper (M4B)"),
    ("podcast", "Podcast", "Podcast summary (M4A)"),
]


def fsize(path):
    try:
        n = os.path.getsize(os.path.join(ROOT, path))
    except OSError:
        return ""
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, n // 1024)} KB"


def resource_index(r):
    """The 'Available' block at the top of a landing page: one tile per thing a
    reader can open (full texts, audio, talks, summary, citation, publisher),
    then a one-line table of contents of the page."""
    L, slug = r["_local"], r["slug"]
    tiles = []  # (kind, name, note, href, external)
    if "pdf" in L:
        tiles.append(("Read", "Preprint PDF" if r["_is_preprint_pdf"] else "Full PDF",
                      " · ".join(x for x in ("Preprint" if r["_is_preprint_pdf"] else "Full text",
                                              fsize(L["pdf"])) if x), "../../" + L["pdf"], True))
    if "postprint" in L:
        tiles.append(("Read", "Improved postprint",
                      " · ".join(x for x in ("Revised version", fsize(L["postprint"])) if x),
                      "../../" + L["postprint"], True))
    if "html" in L:
        tiles.append(("Read", "Web version", "Full text as a web page", "../../" + L["html"], True))
    if "txt" in L:
        tiles.append(("Read", "Plain text", "For screen readers and text-to-speech", "../../" + L["txt"], True))
    if "audio" in L:
        tiles.append(("Listen", "Audio narration", " · ".join(x for x in ("Full paper", fsize(L["audio"])) if x),
                      "../../" + L["audio"], True))
    if "podcast" in L:
        tiles.append(("Listen", "Podcast", " · ".join(x for x in ("Short audio summary", fsize(L["podcast"])) if x),
                      "../../" + L["podcast"], True))
    if r["talks"]:
        n = len(r["talks"])
        tiles.append(("Watch", "Talk" if n == 1 else f"{n} talks", "Video recordings", "#talks", False))
    if r["_summary_html"]:
        tiles.append(("Summary", "Extended summary", "Key ideas with quotes", "#summary", False))
    tiles.append(("Cite", "Cite", "APA · BibTeX · RIS", "#cite", False))
    if r["url"]:
        host = re.sub(r"^https?://(www\.)?", "", r["url"]).split("/")[0]
        tiles.append(("Publisher", "DOI" if r["doi"] else "Publisher’s page",
                      r["doi"] if r["doi"] else host, r["url"], True))
    cards = []
    for kind, name, note, href, ext in tiles:
        tgt = ' target="_blank" rel="noopener"' if ext else ""
        arrow = " ↗" if ext and kind == "Publisher" else ""
        # file links carry the paper's title in their link text (hidden visually),
        # so search engines know what each PDF/HTML/audio file is
        hidden = (f'<span class="visually-hidden">: {esc(r["title"])}</span>'
                  if kind in ("Read", "Listen") else "")
        cards.append(f'<a class="res res-{kind.lower()}" href="{esc(href)}"{tgt}>'
                     f'<span class="res-kind">{kind}</span><span class="res-name">{esc(name)}{hidden}{arrow}</span>'
                     f'<span class="res-note">{esc(note)}</span></a>')
    if not any(k in L for k in ("pdf", "html", "txt")):
        cards.insert(0, '<span class="res res-none"><span class="res-kind">Read</span>'
                        '<span class="res-name">No open-access version yet</span>'
                        '<span class="res-note">See the publisher’s page</span></span>')
    toc = []
    if r["abstract"]:
        toc.append(("abstract", "Abstract"))
    if r["keywords"] or r["topics"]:
        toc.append(("keywords", "Keywords" if r["keywords"] else "Topics"))
    if r["_summary_html"]:
        toc.append(("summary", "Extended summary"))
    if r["talks"]:
        toc.append(("talks", "Talks"))
    toc += [("cite", "Cite"), ("details", "Publication details")]
    return ('<nav class="pub-index" aria-label="Available for this publication">\n'
            '        <div class="res-grid">\n          ' + "\n          ".join(cards) + "\n        </div>\n"
            '        <p class="pub-toc"><span>On this page:</span> '
            + " · ".join(f'<a href="#{a}">{b}</a>' for a, b in toc) + "</p>\n      </nav>")


def cover_path(slug):
    """covers/{slug}.jpg (or .png / .webp) if the publication has a cover image."""
    for ext in ("jpg", "png", "webp"):
        if os.path.exists(os.path.join(ROOT, "covers", f"{slug}.{ext}")):
            return f"covers/{slug}.{ext}"
    return ""


def render_page(r, newer, older, bibtex):
    slug = r["slug"]
    cover = cover_path(slug)
    cover_img = ""
    if cover:
        href = "../../" + r["_local"]["pdf"] if "pdf" in r["_local"] else "../../" + cover
        cover_img = (f'<a class="pub-cover-link" href="{esc(href)}" target="_blank" rel="noopener">'
                     f'<img class="pub-cover" src="../../{cover}" alt="Cover of {esc(r["title"])}" '
                     'width="180" loading="eager"></a>')
    title = esc(r["title"])
    desc = esc(shorten(r["abstract"] or r["citation_apa"], 300))
    meta = [f'<span class="pub-type">{esc(r["type_label"])}</span>',
            f'<span class="pub-year">{esc(r["year"])}</span>']
    if r["featured"]:
        meta.append('<span class="pub-featured" title="Highlighted publication">★ Highlighted</span>')

    sections = []
    if r["abstract"]:
        body = r["_abstract_html"] or f"<p>{esc(r['abstract'])}</p>"
        sections.append(f'<section id="abstract" class="pub-section">\n<h2>Abstract</h2>\n{body}\n</section>')
    kwl, head = (r["keywords"], "Keywords") if r["keywords"] else (r["topics"], "Topics")
    if kwl:
        kws = ' <span class="kw-sep">·</span> '.join(
            f'<a class="pub-kw" href="../../?q={esc(k)}" title="All publications on “{esc(k)}”">{esc(k)}</a>'
            for k in kwl)
        note = r["keywords_note"] or ("" if r["keywords"] else
                                      "This publication has no author keywords; these topics were assigned by this site.")
        sections.append(f'<section id="keywords" class="pub-section">\n<h2>{head}</h2>\n'
                        f'<p class="pub-keywords">{kws}</p>\n'
                        + (f'<p class="kw-note">{esc(note)}</p>\n' if note else "") + '</section>')
    if r["_summary_html"]:
        s = re.sub(r"<h4", "<h3", r["_summary_html"])
        s = s.replace("</h4>", "</h3>")
        sections.append(f'<section id="summary" class="pub-section pub-summary">\n'
                        f'<h2>Extended summary</h2>\n{s}\n</section>')
    if r["talks"]:
        items = "\n".join(
            f'<li><a href="{esc(t["url"])}" target="_blank" rel="noopener">{esc(t["title"])}</a>'
            + (f' <span class="talk-meta">{esc(t["meta"])}</span>' if t["meta"] else "") + "</li>"
            for t in r["talks"])
        sections.append(f'<section id="talks" class="pub-section">\n<h2>Talks and video</h2>\n'
                        f'<ul class="talk-list">\n{items}\n</ul>\n</section>')
    cite = [f'<section id="cite" class="pub-section">\n<h2>Cite</h2>',
            f'<p class="pub-citation" id="apa">{r["_citation_html"]}</p>',
            '<p class="cite-buttons">'
            '<button type="button" class="pub-action copy-btn" data-copy="#apa">Copy citation</button> ']
    if "bibtex" in r["links"]:
        cite[-1] += f'<a class="pub-action" href="../../citations/{slug}.bib" download>BibTeX</a> '
    if "ris" in r["links"]:
        cite[-1] += f'<a class="pub-action" href="../../citations/{slug}.ris" download>RIS</a>'
    cite[-1] += "</p>"
    cite.append('<p class="cite-note">With the Zotero or Mendeley browser connector this page is '
                'detected automatically: one click saves the reference, and the PDF when available.</p>\n</section>')
    sections.append("\n".join(cite))
    sections.append(f'<section id="details" class="pub-section">\n<h2>Publication details</h2>\n'
                    f'<dl class="pub-dl">\n{details_rows(r)}\n</dl>\n</section>')
    sections.append(
        '<section id="machine" class="pub-section pub-machine">\n<h2>Machine-readable</h2>\n<p>'
        f'<a href="index.md" type="text/markdown">Markdown</a> · '
        f'<a href="index.json" type="application/json">JSON</a>'
        + (f' · <a href="../../citations/{slug}.bib">BibTeX</a>' if "bibtex" in r["links"] else "")
        + (f' · <a href="../../citations/{slug}.ris">RIS</a>' if "ris" in r["links"] else "")
        + ' · <a href="../../llms.txt">llms.txt</a> (index of all publications)</p>\n</section>')

    pager = []
    if newer:
        pager.append(f'<a class="pager-newer" href="../{esc(newer["slug"])}/" rel="prev">'
                     f'<span>← Newer</span> {esc(newer["title"])}</a>')
    if older:
        pager.append(f'<a class="pager-older" href="../{esc(older["slug"])}/" rel="next">'
                     f'<span>Older →</span> {esc(older["title"])}</a>')
    by = esc(", ".join(person_name(a) for a in r["authors"]))
    if not by and r["editors"]:   # edited volume: show the editors
        by = esc(", ".join(person_name(a) for a in r["editors"])) + (" (eds.)" if len(r["editors"]) > 1 else " (ed.)")
    lic = " and ".join(f'<a rel="license" href="{u}">{n}</a>' for n, u in LICENSES)
    ld = json.dumps(jsonld(r), ensure_ascii=False, indent=1).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="{esc(r['language'] or 'en')}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {esc(OWNER)}</title>
<meta name="description" content="{desc}">
<meta name="author" content="{by}">
<link rel="canonical" href="{r['id']}">
<link rel="alternate" type="text/markdown" href="index.md" title="Markdown version">
<link rel="alternate" type="application/json" href="index.json" title="JSON record">
<link rel="license" href="{LICENSES[0][1]}">
<link rel="license" href="{LICENSES[1][1]}">
<link rel="icon" href="{LOGO}?w=32" sizes="32x32">
<link rel="apple-touch-icon" href="{LOGO}?w=180">
<link rel="stylesheet" href="../../style.css">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{r['id']}">
{f'<meta property="og:image" content="{BASE}/{cover}">' if cover else ''}
<meta name="twitter:card" content="summary">
{highwire(r)}
<script type="application/ld+json">
{ld}
</script>
</head>
<body class="pub-page-body">
<a class="skip-link" href="#content">Skip to content</a>
<div class="site">

  <header class="site-header site-header-compact">
    <div class="site-branding">
      <img class="site-logo" src="{LOGO}?w=192" alt="" width="48" height="48">
      <div>
        <p class="site-title"><a href="../../">Xabier E. Barandiaran</a></p>
        <p class="site-description">Publications &#8212; philosophy, autonomy, mind, life, machines, politics</p>
      </div>
    </div>
    <p class="site-backlink"><a href="../../#{esc(slug)}">&#8592; All publications</a></p>
  </header>

  <main id="content">
    <article class="pub-page pub-item" id="{esc(slug)}"{f' data-doi="{esc(norm_doi(r["doi"]))}"' if r["doi"] else ""}>
      <div class="pub-hero{' has-cover' if cover else ''}">
        {cover_img}
        <div class="pub-hero-text">
      <div class="pub-meta">
        {' '.join(meta)}
      </div>
      <h1 class="pub-page-title">{title}</h1>
      <p class="pub-authors">{by}{f' ({esc(r["year"])})' if r["year"] else ""}</p>
      {f'<p class="pub-venue">{venue_line(r)}</p>' if venue_line(r) else ''}
        </div>
      </div>
      {resource_index(r)}
{chr(10).join(sections)}
      {coins_span(slug)}
    </article>
    <nav class="pub-pager" aria-label="More publications">
      {' '.join(pager)}
    </nav>
  </main>

  <footer class="site-footer">
    <p class="site-license">This page and its metadata are free content under {lic}. Linked publisher PDFs keep their own terms.</p>
    <p><a href="../../">All publications</a> &middot; <a href="https://xabier.barandiaran.net/">xabier.barandiaran.net</a> &middot; <a href="mailto:xabier.academic@barandiaran.net">xabier.academic@barandiaran.net</a></p>
  </footer>

</div>
<script src="../../page.js" defer></script>
<script src="../../scholar-citations.js" defer></script>
</body>
</html>
"""


# =================================================================== landing page (Markdown)

def render_md(r, bibtex=None, full=True, heading="#"):
    L = [f"{heading} {r['title']}", ""]
    if r["authors"]:
        L.append(f"- **Authors:** {', '.join(person_name(a) for a in r['authors'])}")
    elif r["editors"]:
        L.append(f"- **Editors:** {', '.join(person_name(a) for a in r['editors'])}")
    L.append(f"- **Year:** {r['year']}")
    L.append(f"- **Type:** {r['type_label']}")
    if r["venue"]:
        v = r["venue"]
        if r["volume"]:
            v += f", {r['volume']}" + (f"({r['issue']})" if r["issue"] else "")
        if r["pages"]:
            v += f", {r['pages']}"
        L.append(f"- **Published in:** {v}" + (f" ({r['note']})" if r["note"] else ""))
    if r["publisher"]:
        L.append(f"- **Publisher:** {r['publisher']}" + (f", {r['place']}" if r["place"] else ""))
    if r["doi"]:
        L.append(f"- **DOI:** [{r['doi']}](https://doi.org/{r['doi']})")
    elif r["url"]:
        L.append(f"- **URL:** {r['url']}")
    if r["keywords"]:
        L.append(f"- **Keywords:** {', '.join(r['keywords'])}")
    elif r["topics"]:
        L.append(f"- **Topics (assigned by the site; no author keywords):** {', '.join(r['topics'])}")
    if r["featured"]:
        L.append("- **Highlighted:** yes (one of the author’s featured publications)")
    L.append(f"- **Landing page:** {r['id']}")
    ft = [f"[{lab}]({r['links'][k]})" for k, lab in
          (("pdf", "PDF"), ("postprint", "improved postprint (PDF)"), ("html", "HTML"), ("txt", "plain text"))
          if k in r["links"]]
    if ft:
        L.append(f"- **Open full text:** {' · '.join(ft)}")
    au = [f"[{lab}]({r['links'][k]})" for k, lab in (("audio", "narration"), ("podcast", "podcast"))
          if k in r["links"]]
    if au:
        L.append(f"- **Audio:** {' · '.join(au)}")
    L.append("")
    sub = heading + "#"
    if r["abstract"]:
        L += [f"{sub} Abstract", "", r["abstract"], ""]
    if full and r["_summary_html"]:
        L += [f"{sub} Extended summary", "", html_to_md(r["_summary_html"]).replace("\n### ", f"\n{sub}# "), ""]
    if r["talks"]:
        L += [f"{sub} Talks and video", ""]
        L += [f"- [{t['title']}]({t['url']})" + (f" — {t['meta']}" if t["meta"] else "")
              for t in r["talks"]]
        L.append("")
    L += [f"{sub} Cite", "", r["_citation_md"], ""]
    if full and "bibtex" in r["links"] and heading == "#":
        L += [f"BibTeX: {r['links']['bibtex']}" + (f" · RIS: {r['links']['ris']}" if "ris" in r["links"] else ""), ""]
    return "\n".join(L)


# =================================================================== llms.txt

def build_llms(records, today, parts=()):
    feat = [r for r in records if r["featured"]]
    n = len(records)
    head = f"""# Publications of {OWNER}

> Complete, open-access list of {n} academic publications by {OWNER}:
> philosophy of cognitive science, enactivism, autonomy, agency, normativity,
> artificial life, AI, technopolitics and digital democracy. Free content
> (CC BY-SA 4.0 / GNU FDL 1.3); reuse encouraged. Last updated {today}.

How to read this site (for AI agents and crawlers):

- Every publication has its own landing page at `{BASE}/p/{{slug}}/` with a
  Markdown twin at `{BASE}/p/{{slug}}/index.md` (abstract, keywords, extended
  summary when available, talks, APA citation, BibTeX/RIS links) and a JSON record at
  `{BASE}/p/{{slug}}/index.json`. The links below point to the Markdown twins.
- All records with abstracts in one file: [llms-full.txt]({BASE}/llms-full.txt)
  (~{{FULL_K}}K characters), or the same split into parts small enough for a
  single fetch each: {{PARTS}}.
- Structured data: [publications.json]({BASE}/publications.json),
  [CSL-JSON]({BASE}/publications.csl.json), [BibTeX]({BASE}/all.bib), [RIS]({BASE}/all.ris).
- The homepage ({BASE}/) is a long human-oriented list; prefer the files above.
"""
    head = head.replace("{FULL_K}", str(FULL_CHARS // 1000)).replace(
        "{PARTS}", " · ".join(f"[part {i}]({BASE}/{fn})" for i, fn in enumerate(parts, 1)) or "n/a")
    L = [head]
    if feat:
        L.append("## Highlighted publications\n")
        for r in feat:
            L.append(f"- [{r['title']}]({r['links']['markdown']}): "
                     f"{short_authors(r)} ({r['year']}). {r['type_label']}"
                     + (f", {r['venue']}" if r["venue"] else "") + ".")
        L.append("")
    L.append("## All publications (newest first)\n")
    for r in sorted(records, key=lambda x: x["_order"]):
        extra = []
        if "pdf" in r["links"]:
            extra.append("open PDF")
        if r["has_summary"]:
            extra.append("extended summary")
        if r["talks"]:
            extra.append("talks")
        L.append(f"- [{r['title']}]({r['links']['markdown']}): "
                 f"{short_authors(r)} ({r['year']}). {r['type_label']}"
                 + (f", {r['venue']}" if r["venue"] else "") + "."
                 + (f" Keywords: {', '.join(r['keywords'])}." if r["keywords"]
                    else f" Topics: {', '.join(r['topics'])}." if r["topics"] else "")
                 + (f" [{', '.join(extra)}]" if extra else ""))
    L += ["", "## Optional", "",
          f"- [Homepage]({BASE}/): the full human-oriented list (large HTML page with filters)",
          f"- [Sitemap]({BASE}/sitemap.xml)",
          f"- [Author’s website](https://xabier.barandiaran.net/)", ""]
    return "\n".join(L)


def short_authors(r):
    a = r["authors"]
    if not a:
        return r["author_string"]
    names = [person_name(x) for x in a]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]} et al."


def build_llms_full(records, today):
    L = [f"# Publications of {OWNER} — full records", "",
         f"> All {len(records)} publications with metadata, abstracts, keywords and "
         f"citations, newest first. Generated {today} from {BASE}/. Each record's "
         f"landing page (with BibTeX) is linked under it. Free content "
         f"(CC BY-SA 4.0 / GNU FDL 1.3).", ""]
    for r in sorted(records, key=lambda x: x["_order"]):
        L.append(render_md(r, bibtex=None, full=True, heading="##"))
        L.append("---\n")
    return "\n".join(L)


FULL_CHARS = 0


def build_llms_parts(records, today, limit=85000):
    """llms-full.txt split into parts below `limit` characters (one fetch each)."""
    chunks, cur, size = [], [], 0
    for r in sorted(records, key=lambda x: x["_order"]):
        md = render_md(r, bibtex=None, full=True, heading="##") + "\n---\n"
        if cur and size + len(md) > limit:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(md)
        size += len(md)
    if cur:
        chunks.append(cur)
    n = len(chunks)
    out = []
    for i, ch in enumerate(chunks, 1):
        nxt = f" Next: {BASE}/llms-full-{i + 1}.txt." if i < n else " This is the last part."
        head = (f"# Publications of {OWNER} — full records, part {i} of {n}\n\n"
                f"> Newest first. Generated {today}. Index of all publications: {BASE}/llms.txt."
                f"{nxt}\n\n")
        out.append((f"llms-full-{i}.txt", head + "\n".join(ch)))
    return out


# =================================================================== sitemap

def mtime_iso(path):
    ts = os.path.getmtime(path)
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")


def build_sitemap(records):
    urls = [("/", mtime_iso(INDEX), "1.0")]
    for r in records:
        urls.append((f"/p/{r['slug']}/", mtime_iso(os.path.join(PAGES_DIR, r["slug"], "index.html")), "0.9"))
    extra = sorted(f for f in os.listdir(ROOT) if re.match(r"llms-full-\d+\.txt$", f))
    for fn, prio in [("llms.txt", "0.6"), ("llms-full.txt", "0.6")] + [(f, "0.6") for f in extra] + \
                    [("publications.json", "0.5"), ("all.bib", "0.4")]:
        if os.path.exists(os.path.join(ROOT, fn)):
            urls.append((f"/{fn}", mtime_iso(os.path.join(ROOT, fn)), prio))
    for folder, prio in (("html", "0.8"), ("pdfs", "0.7"), ("txt", "0.5"), ("citations", "0.3")):
        d = os.path.join(ROOT, folder)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                urls.append((f"/{folder}/{fn}", mtime_iso(p), prio))
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, prio in urls:
        L.append(f"  <url><loc>{BASE}{xml_escape(loc)}</loc><lastmod>{lastmod}</lastmod>"
                 f"<priority>{prio}</priority></url>")
    L.append("</urlset>")
    write(os.path.join(ROOT, "sitemap.xml"), "\n".join(L) + "\n")
    return len(urls)


# =================================================================== slim index.html

def slim_index(doc, records):
    bysl = {r["slug"]: r for r in records}
    # 1. drop the duplicated search text (script.js now builds it from the DOM)
    doc = re.sub(r'\s+data-search="[^"]*"', "", doc)
    # 2. head JSON-LD -> compact index; full records are on the landing pages.
    #    Key order is kept (@type, @id, name, ...) because build_citations.py and
    #    inject_titles.py read @id/name/url from this block.
    m = re.search(r'(<script type="application/ld\+json">\s*)(\{.*?\})(\s*</script>)', doc, re.S)
    if m:
        data = json.loads(m.group(2))
        for node in data.get("@graph", []):
            node.pop("description", None)
            slug = node.get("@id", "").split("#", 1)[-1]
            if slug in bysl:
                node["mainEntityOfPage"] = bysl[slug]["id"]
        doc = doc[:m.start(2)] + json.dumps(data, ensure_ascii=False, indent=1) + doc[m.end(2):]
    # 3. (old "Details" buttons: the title in each reference now links to the landing page)
    doc = re.sub(r"<!--PAGE-START-->.*?<!--PAGE-END-->\s*", "", doc, flags=re.S)
    # 4. machine-readable links in <head> and in the header (top of the HTML,
    #    so even a truncated fetch sees them)
    doc = re.sub(r"\s*<!--MACHINE-HEAD-START-->.*?<!--MACHINE-HEAD-END-->", "", doc, flags=re.S)
    doc = re.sub(r"\s*<!--MACHINE-START-->.*?<!--MACHINE-END-->", "", doc, flags=re.S)
    head_links = (
        "\n<!--MACHINE-HEAD-START-->"
        '\n<link rel="alternate" type="text/markdown" href="llms.txt" title="Index for AI agents (llms.txt)">'
        '\n<link rel="alternate" type="text/markdown" href="llms-full.txt" title="All records with abstracts (Markdown)">'
        '\n<link rel="alternate" type="application/json" href="publications.json" title="All publications (JSON)">'
        '\n<link rel="alternate" type="application/x-bibtex" href="all.bib" title="All publications (BibTeX)">'
        "\n<!--MACHINE-HEAD-END-->")
    doc = doc.replace('<link rel="stylesheet" href="style.css">',
                      '<link rel="stylesheet" href="style.css">' + head_links, 1)
    machine = (
        '\n    <!--MACHINE-START--><p class="site-machine visually-hidden">For machines and AI agents: '
        '<a href="llms.txt">llms.txt</a> &middot; <a href="llms-full.txt">llms-full.txt</a> &middot; '
        '<a href="publications.json">JSON</a> &middot; <a href="all.bib">BibTeX</a> &middot; '
        '<a href="all.ris">RIS</a>. Every publication also has its own page '
        '(<code>/p/&lt;slug&gt;/</code>, with a Markdown twin at <code>index.md</code>).</p><!--MACHINE-END-->')
    doc = re.sub(r'(<p class="site-(?:updated site-updated-top|backlink)">.*?</p>)', lambda mo: mo.group(1) + machine,
                 doc, count=1, flags=re.S)
    # 6. stamp the last-updated date
    today = datetime.date.today()
    doc = re.sub(r'(<time id="last-updated" datetime=")[^"]*(">)[^<]*(</time>)',
                 rf'\g<1>{today.isoformat()}\g<2>{today.day} {today.strftime("%B %Y")}\g<3>', doc)
    # 6b. small visible "for machines" line in the footer (the header copy is visually hidden)
    doc = re.sub(r"\s*<!--MACHINE-FOOT-START-->.*?<!--MACHINE-FOOT-END-->", "", doc, flags=re.S)
    doc = doc.replace(
        '<footer class="site-footer">',
        '<footer class="site-footer">\n    <!--MACHINE-FOOT-START--><p class="site-machine-foot">For machines and AI agents: '
        '<a href="llms.txt">llms.txt</a> &middot; <a href="llms-full-1.txt">full records</a> &middot; '
        '<a href="publications.json">JSON</a> &middot; <a href="all.bib">BibTeX</a> &middot; '
        '<a href="all.ris">RIS</a></p><!--MACHINE-FOOT-END-->', 1)
    # 7. one site-wide Zotero tip in the footer (no longer repeated in every Cite panel)
    doc = re.sub(r"\s*<!--ZTIP-START-->.*?<!--ZTIP-END-->", "", doc, flags=re.S)
    doc = doc.replace(
        '<footer class="site-footer">',
        '<footer class="site-footer">\n    <!--ZTIP-START--><p class="cite-note">Tip: with the Zotero or '
        'Mendeley browser connector installed, this page is detected automatically and you can save any '
        'or all of these references (with their PDFs) in one click.</p><!--ZTIP-END-->', 1)
    return doc


# =================================================================== main

COINS = {}
OWNER_ID = {}    # {"family": ..., "sameAs": [...]}, set by build_site.py
ANALYTICS = ""   # GoatCounter site code, set by build_site.py from data/site.json


def analytics_snippet(prefix):
    return (f'<!--ANALYTICS-START--><script data-goatcounter="https://{ANALYTICS}.goatcounter.com/count" '
            f'async src="//gc.zgo.at/count.js"></script>'
            f'<script src="{prefix}track.js" defer></script><!--ANALYTICS-END-->')


def run(entries):
    """entries: list of (entry, zotero_record) pairs from build_site.py,
    in homepage order (highlighted first)."""
    doc = read(INDEX)
    records = []
    for i, (e, rec) in enumerate(entries):
        COINS[e["slug"]] = e["coins"]
        r = build_record(e, rec, {})
        r["_order_dom"] = i
        r["_old_slugs"] = e.get("old_slugs", [])
        records.append(r)
    # chronological order for pager / llms: newest first by year (stable on DOM order),
    # i.e. the homepage order without the highlighted-first block
    chron = sorted(records, key=lambda r: (-int(r["year"]) if r["year"].isdigit() else 0, r["_order_dom"]))
    for i, r in enumerate(chron):
        r["_order"] = i

    # ---- landing pages
    live = set()
    for i, r in enumerate(chron):
        bibp = os.path.join(ROOT, "citations", f"{r['slug']}.bib")
        bibtex = read(bibp) if os.path.exists(bibp) else ""
        newer = chron[i - 1] if i > 0 else None
        older = chron[i + 1] if i + 1 < len(chron) else None
        d = os.path.join(PAGES_DIR, r["slug"])
        write(os.path.join(d, "index.md"), render_md(r, bibtex=bibtex) + "\n")
        page = render_page(r, newer, older, bibtex)
        if ANALYTICS:
            page = page.replace("</head>", analytics_snippet("../../") + "\n</head>", 1)
        write(os.path.join(d, "index.html"), page)
        rec = public(r)
        if r["_summary_html"]:
            rec["summary_html"] = r["_summary_html"]  # loaded on demand by the homepage
        write(os.path.join(d, "index.json"), json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
        live.add(r["slug"])
    # renamed publications: keep their old landing-page URL working
    for r in chron:
        for old in r["_old_slugs"]:
            write(os.path.join(PAGES_DIR, old, "index.html"),
                  f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
                  f'<title>Moved: {esc(r["title"])}</title>'
                  f'<link rel="canonical" href="{r["id"]}">'
                  f'<meta http-equiv="refresh" content="0; url=../{r["slug"]}/">'
                  f'<meta name="robots" content="noindex"></head><body>'
                  f'<p>This page moved to <a href="../{r["slug"]}/">{esc(r["title"])}</a>.</p></body></html>\n')
            live.add(old)
    # remove pages of publications that no longer exist (renamed slugs etc.)
    stale = []
    if os.path.isdir(PAGES_DIR):
        for name in os.listdir(PAGES_DIR):
            if name not in live and os.path.isdir(os.path.join(PAGES_DIR, name)):
                stale.append(name)
                try:
                    shutil.rmtree(os.path.join(PAGES_DIR, name))
                except OSError:
                    pass

    # ---- machine-readable indexes
    today = datetime.date.today().isoformat()
    out = {"title": f"Publications of {OWNER}", "homepage": BASE + "/",
           "generated": today, "license": [u for _, u in LICENSES],
           "count": len(chron), "items": [public(r) for r in chron]}
    write(os.path.join(ROOT, "publications.json"), json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    write(os.path.join(ROOT, "publications.csl.json"),
          json.dumps([csl(r) for r in chron], ensure_ascii=False, indent=1) + "\n")
    for ext in ("bib", "ris"):
        parts = []
        for r in chron:
            p = os.path.join(ROOT, "citations", f"{r['slug']}.{ext}")
            if os.path.exists(p):
                parts.append(read(p).strip())
        sep = "\n\n" if ext == "bib" else "\n"
        write(os.path.join(ROOT, f"all.{ext}"), sep.join(parts) + "\n")
    global FULL_CHARS
    full = build_llms_full(chron, today)
    FULL_CHARS = len(full)
    write(os.path.join(ROOT, "llms-full.txt"), full)
    parts = build_llms_parts(chron, today)
    for fn, text in parts:
        write(os.path.join(ROOT, fn), text)
    k = len(parts) + 1
    while os.path.exists(os.path.join(ROOT, f"llms-full-{k}.txt")):   # leftovers from a longer split
        try:
            os.remove(os.path.join(ROOT, f"llms-full-{k}.txt"))
        except OSError:
            break
        k += 1
    write(os.path.join(ROOT, "llms.txt"), build_llms(chron, today, [fn for fn, _ in parts]))

    # ---- slim + link index.html, then sitemap (needs final mtimes)
    write(INDEX, slim_index(doc, chron))
    n_urls = build_sitemap(chron)

    size = lambda fn: os.path.getsize(os.path.join(ROOT, fn)) // 1024
    print(f"Landing pages: {len(live)} in p/  (stale removed: {stale or 'none'})")
    print(f"index.html {size('index.html')} KB · llms.txt {size('llms.txt')} KB · "
          f"llms-full.txt {size('llms-full.txt')} KB · publications.json {size('publications.json')} KB")
    print(f"llms-full.txt split into {len(parts)} parts: "
          + ", ".join(f"{fn} {len(t) // 1000}K chars" for fn, t in parts))
    print(f"sitemap.xml: {n_urls} URLs")


if __name__ == "__main__":
    import build_site
    build_site.main()
