#!/usr/bin/env python3
"""Generate per-item RIS + BibTeX files from the Zotero CSV and inject
Export buttons + COinS auto-detect metadata into index.html.

Idempotent: re-running removes previously injected blocks first.
"""
import csv, re, html, sys, os, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "..", "my_publications", "Exported Items.csv")
# When run from the mounted workspace the CSV sibling folder differs; allow override
if not os.path.exists(CSV_PATH):
    alt = os.environ.get("ZOTERO_CSV")
    if alt and os.path.exists(alt):
        CSV_PATH = alt
INDEX = os.path.join(HERE, "index.html")
CITE_DIR = os.path.join(HERE, "citations")
os.makedirs(CITE_DIR, exist_ok=True)

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def norm_doi(s):
    if not s: return ""
    s = s.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    return s.strip()

# ---- RIS / BibTeX type maps ----
RIS_TY = {
    "journalArticle": "JOUR", "book": "BOOK", "bookSection": "CHAP",
    "conferencePaper": "CPAPER", "report": "RPRT", "thesis": "THES",
    "preprint": "GEN", "document": "GEN", "magazineArticle": "MGZN",
}
BIB_TY = {
    "journalArticle": "article", "book": "book", "bookSection": "incollection",
    "conferencePaper": "inproceedings", "report": "techreport", "thesis": "phdthesis",
    "preprint": "misc", "document": "misc", "magazineArticle": "article",
}

# ---- load CSV ----
records = []
with open(CSV_PATH, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        records.append(row)

by_doi, by_title = {}, {}
for r in records:
    d = norm_doi(r.get("DOI"))
    if d: by_doi[d] = r
    t = norm(r.get("Title"))
    if t: by_title.setdefault(t, r)

def authors_list(r):
    a = (r.get("Author") or "").strip()
    if not a:
        a = (r.get("Editor") or "").strip()
    return [x.strip() for x in a.split(";") if x.strip()]

def field(r, k):
    return (r.get(k) or "").strip()

def build_ris(r):
    ty = RIS_TY.get(field(r, "Item Type"), "GEN")
    lines = [f"TY  - {ty}"]
    for au in authors_list(r):
        lines.append(f"AU  - {au}")
    if field(r, "Author"):  # only add editors separately when authors are distinct
        for ed in [e.strip() for e in field(r, "Editor").split(";") if e.strip()]:
            lines.append(f"ED  - {ed}")
    if field(r, "Publication Year"): lines.append(f"PY  - {field(r,'Publication Year')}")
    if field(r, "Date"): lines.append(f"DA  - {field(r,'Date')}")
    if field(r, "Title"): lines.append(f"TI  - {field(r,'Title')}")
    if field(r, "Publication Title"): lines.append(f"T2  - {field(r,'Publication Title')}")
    if field(r, "Series"): lines.append(f"T3  - {field(r,'Series')}")
    if field(r, "Volume"): lines.append(f"VL  - {field(r,'Volume')}")
    if field(r, "Issue"): lines.append(f"IS  - {field(r,'Issue')}")
    pages = field(r, "Pages")
    if pages:
        m = re.match(r"\s*(\S+?)\s*[-–]{1,2}\s*(\S+)\s*$", pages)
        if m:
            lines.append(f"SP  - {m.group(1)}")
            lines.append(f"EP  - {m.group(2)}")
        else:
            lines.append(f"SP  - {pages}")
    if field(r, "Publisher"): lines.append(f"PB  - {field(r,'Publisher')}")
    if field(r, "Place"): lines.append(f"CY  - {field(r,'Place')}")
    if field(r, "ISSN"): lines.append(f"SN  - {field(r,'ISSN')}")
    elif field(r, "ISBN"): lines.append(f"SN  - {field(r,'ISBN')}")
    if field(r, "DOI"): lines.append(f"DO  - {field(r,'DOI')}")
    url = field(r, "Url") or (f"https://doi.org/{field(r,'DOI')}" if field(r,'DOI') else "")
    if url: lines.append(f"UR  - {url}")
    if field(r, "Abstract Note"):
        lines.append(f"AB  - {field(r,'Abstract Note')}")
    tags = []
    for col in ("Manual Tags", "Automatic Tags"):
        tags += [t.strip() for t in field(r, col).split(";") if t.strip()]
    for t in dict.fromkeys(tags):
        lines.append(f"KW  - {t}")
    lines.append("ER  - ")
    return "\r\n".join(lines) + "\r\n"

STOP = {"the","a","an","of","on","and","in","to","for","de","la","el","los","las","un","una","y"}
def bib_key(r, slug):
    au = authors_list(r)
    last = norm(au[0].split(",")[0]).replace(" ", "") if au else "anon"
    yr = field(r, "Publication Year") or "nd"
    word = ""
    for w in norm(field(r, "Title")).split():
        if w not in STOP and len(w) > 2:
            word = w; break
    return f"{last}{yr}{word}"

def bib_escape(s):
    return s.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")

_used_keys = {}
def unique_key(base):
    if base not in _used_keys:
        _used_keys[base] = 1
        return base
    _used_keys[base] += 1
    # append b, c, d ...
    return base + chr(ord('a') + _used_keys[base] - 1)

def build_bib(r, slug):
    bt = BIB_TY.get(field(r, "Item Type"), "misc")
    key = unique_key(bib_key(r, slug))
    fields = []
    au = authors_list(r)
    has_real_author = bool(field(r, "Author"))
    if au: fields.append(("author", " and ".join(au)))
    ed = [e.strip() for e in field(r, "Editor").split(";") if e.strip()]
    # only list editors separately when they differ from the (fallback) author line
    if ed and has_real_author: fields.append(("editor", " and ".join(ed)))
    if field(r, "Title"): fields.append(("title", field(r, "Title")))
    if field(r, "Publication Year"): fields.append(("year", field(r, "Publication Year")))
    pubt = field(r, "Publication Title")
    if pubt:
        if bt == "article": fields.append(("journal", pubt))
        elif bt in ("incollection", "inproceedings"): fields.append(("booktitle", pubt))
        else: fields.append(("journal", pubt))
    if field(r, "Volume"): fields.append(("volume", field(r, "Volume")))
    if field(r, "Issue"): fields.append(("number", field(r, "Issue")))
    if field(r, "Pages"): fields.append(("pages", field(r, "Pages").replace("–", "--")))
    if field(r, "Publisher"): fields.append(("publisher", field(r, "Publisher")))
    if field(r, "Place"): fields.append(("address", field(r, "Place")))
    if field(r, "ISSN"): fields.append(("issn", field(r, "ISSN")))
    if field(r, "ISBN"): fields.append(("isbn", field(r, "ISBN")))
    if field(r, "DOI"): fields.append(("doi", field(r, "DOI")))
    url = field(r, "Url") or (f"https://doi.org/{field(r,'DOI')}" if field(r,'DOI') else "")
    if url: fields.append(("url", url))
    if field(r, "Abstract Note"): fields.append(("abstract", field(r, "Abstract Note")))
    tags = []
    for col in ("Manual Tags", "Automatic Tags"):
        tags += [t.strip() for t in field(r, col).split(";") if t.strip()]
    tags = list(dict.fromkeys(tags))
    if tags: fields.append(("keywords", ", ".join(tags)))
    body = ",\n".join(f"  {k} = {{{bib_escape(v)}}}" for k, v in fields)
    return f"@{bt}{{{key},\n{body}\n}}\n"

def build_coins(r, slug):
    """Minimal OpenURL ContextObject (COinS) for Zotero/Mendeley auto-detection."""
    it = field(r, "Item Type")
    params = []
    def add(k, v):
        if v: params.append((k, v))
    add("ctx_ver", "Z39.88-2004")
    add("rfr_id", "info:sid/publications.barandiaran.net:generator")
    if it == "journalArticle":
        add("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal")
        add("rft.genre", "article")
        add("rft.atitle", field(r, "Title"))
        add("rft.jtitle", field(r, "Publication Title"))
        add("rft.volume", field(r, "Volume"))
        add("rft.issue", field(r, "Issue"))
        add("rft.issn", field(r, "ISSN"))
    elif it in ("book",):
        add("rft_val_fmt", "info:ofi/fmt:kev:mtx:book")
        add("rft.genre", "book")
        add("rft.btitle", field(r, "Title"))
        add("rft.isbn", field(r, "ISBN"))
    elif it in ("bookSection", "conferencePaper"):
        add("rft_val_fmt", "info:ofi/fmt:kev:mtx:book")
        add("rft.genre", "bookitem" if it == "bookSection" else "proceeding")
        add("rft.atitle", field(r, "Title"))
        add("rft.btitle", field(r, "Publication Title"))
        add("rft.isbn", field(r, "ISBN"))
    else:
        add("rft_val_fmt", "info:ofi/fmt:kev:mtx:dc")
        add("rft.type", it)
        add("rft.title", field(r, "Title"))
    add("rft.date", field(r, "Publication Year"))
    pages = field(r, "Pages")
    if pages:
        m = re.match(r"\s*(\S+?)\s*[-–]{1,2}\s*(\S+)\s*$", pages)
        if m:
            add("rft.spage", m.group(1)); add("rft.epage", m.group(2))
        else:
            add("rft.pages", pages)
    if field(r, "DOI"):
        add("rft_id", f"info:doi/{field(r,'DOI')}")
    for au in authors_list(r):
        if "," in au:
            last, first = [x.strip() for x in au.split(",", 1)]
            add("rft.aulast", last); add("rft.aufirst", first)
        else:
            add("rft.au", au)
        break  # first author is enough for the title attr; add rest generically
    for au in authors_list(r)[1:]:
        add("rft.au", au)
    # canonical OpenURL: fully percent-encode every value (Wikipedia-style COinS)
    q = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params)
    return f'<span class="Z3988" title="{html.escape(q, quote=True)}"></span>'

# ---- keyword deduction ----
# Domain vocabulary for this corpus (philosophy of mind/biology, ALife, cognition,
# autonomy, technopolitics). Maps a display label -> list of match patterns (regex,
# matched with word boundaries, case-insensitive) against title+abstract.
LEXICON = {
    "Autonomy": [r"autonom(?:y|ous)"],
    "Autonomous systems": [r"autonomous systems?"],
    "Autopoiesis": [r"autopoie(?:sis|tic)"],
    "Self-organization": [r"self-?organi[sz]"],
    "Self-maintenance": [r"self-?maintain", r"self-?maintenance", r"self-?producing"],
    "Metabolism": [r"metaboli"],
    "Artificial life": [r"artificial life", r"\balife\b", r"a-life"],
    "Minimal cognition": [r"minimal cognition", r"minimally cognitive"],
    "Cognition": [r"cogniti"],
    "Cognitive science": [r"cognitive science"],
    "Philosophy of mind": [r"philosophy of mind", r"mind & body", r"mind and body"],
    "Enactivism": [r"enactiv", r"enaction", r"enactive"],
    "Sensorimotor": [r"sensori-?motor"],
    "Embodiment": [r"embodi"],
    "Perception": [r"percepti"],
    "Agency": [r"\bagency\b", r"\bagent(s)?\b"],
    "Normativity": [r"normativ", r"\bnorms?\b", r"natural norms?"],
    "Normative function": [r"normative function"],
    "Biological function": [r"biological function", r"function(?:al|ing) attribution", r"teleolog"],
    "Malfunction": [r"malfunction"],
    "Dysfunction": [r"dysfunction"],
    "Viability": [r"viabilit", r"viability space", r"viability theory"],
    "Adaptive behavior": [r"adaptive behaviou?r"],
    "Adaptivity": [r"adaptivit"],
    "Habits": [r"\bhabits?\b"],
    "Dynamical systems": [r"dynamical systems?"],
    "Complexity": [r"complexit"],
    "Self-organized criticality": [r"self-?organi[sz]ed criticality", r"criticality"],
    "Neuroscience": [r"neuroscience", r"neural", r"neurodynamic"],
    "Robotics": [r"robot"],
    "Evolution": [r"evolution"],
    "Coordination dynamics": [r"coordination dynamics", r"metastab", r"\bhkb\b", r"oscillat"],
    "Value systems": [r"value systems?"],
    "Individuality": [r"individualit"],
    "Mental life": [r"mental life"],
    "Extended mind": [r"extended mind", r"extended cognition"],
    "Technopolitics": [r"technopolit", r"tecnopol[ií]t"],
    "Digital democracy": [r"digital democracy", r"democracia digital"],
    "Participatory democracy": [r"participat(?:ory|ive) democracy", r"participaci[óo]n"],
    "Decidim": [r"decidim"],
    "Collective intelligence": [r"collective intelligence"],
    "Collective identity": [r"collective identit", r"identidad(?:es)? colectiv"],
    "Social movements": [r"social movements?", r"15m", r"movimientos? social"],
    "Free software": [r"free software", r"software libre", r"\bflok\b", r"floss?\b"],
    "Open access": [r"open access", r"acceso abierto"],
    "Commons": [r"\bcommons\b", r"procom[uú]n", r"buen conocer"],
    "Hacktivism": [r"hacklab", r"hacktivis", r"activismo digital"],
    "Network analysis": [r"network analysis", r"social network", r"\bredes\b"],
    "Artificial intelligence": [r"artificial intelligence", r"\bai\b"],
    "Mental health": [r"mental health", r"psychopatholog", r"salud mental"],
}
LEX_COMPILED = {disp: [re.compile(p, re.I) for p in pats] for disp, pats in LEXICON.items()}

TITLE_STOP = set("""a an the of on in to for and or but with without within from into as at by is are be
that this these those it its their his her our your not no can could may might must should would will
what which who whom whose how why when where del la el los las un una y o de en con sin para por segun
sobre entre hacia desde una uno como mas menos toward towards beyond via versus vs.
concept concepts idea ideas fleshing approach approaches case cases study studies notion notions
account accounts framework frameworks perspective perspectives proposal proposals introduction
overview limits mode modes route milestone impact paradigm foundational very using towards
between within beyond making sense role nature aspects features characteristics""".split())

def clean_manual(tag):
    # BISAC-style "Philosophy / Mind & Body" -> "Mind & Body"
    if " / " in tag:
        tag = tag.split(" / ")[-1].strip()
    return tag

def title_terms(title, k=2):
    words = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ][\w-]+", title)
    sig = [w for w in words if w.lower() not in TITLE_STOP and len(w) > 3]
    # build up to k phrases of 1-2 consecutive significant words
    phrases, i = [], 0
    kept = []
    for w in sig:
        kept.append(w)
    # prefer distinctive single significant words, title-cased
    seen = set()
    out = []
    for w in kept:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(w if w[:1].isupper() else w.capitalize())
        if len(out) >= k:
            break
    return out

def compute_keywords(rec, cap=6):
    title = field(rec, "Title")
    abstract = field(rec, "Abstract Note")
    text = f"{title} {abstract}"
    kws, seen = [], set()
    def push(t):
        t = t.strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key); kws.append(t)
    # 1) curated manual tags (trusted)
    for t in [x.strip() for x in field(rec, "Manual Tags").split(";") if x.strip()]:
        push(clean_manual(t))
    # 2) domain vocabulary matched in title/abstract
    for disp, pats in LEX_COMPILED.items():
        if any(p.search(text) for p in pats):
            push(disp)
        if len(kws) >= cap:
            break
    # 3) fallback: distinctive title terms if we still have too few
    if len(kws) < 2:
        for t in title_terms(title, k=3):
            push(t)
    return kws[:cap]

# ---- talks (video recordings) linked to publications ----
_T_PANOPTO = {"date": "2026-04-14",
    "title": "Transforming agency through generative midtended cognition. Digital thinging with thinging things",
    "url": "https://sussex.cloud.panopto.eu/Panopto/Pages/Viewer.aspx?id=f6d678b6-14d1-47e0-a708-b42c0122f316",
    "host": "University of Sussex"}
TALKS = {
    "2025-transforming-agency-on-the-mode-of": [
        {"date": "2024-12-16",
         "title": "Transformar la Humanidad: El modo de existencia de la IA generativa en la sociedad",
         "url": "https://www.youtube.com/watch?v=PczZ4_L-cQ0", "lang": "ES"},
        {"date": "2025-11-16", "title": "Transforming Agency: LLMs in a human world",
         "url": "https://youtu.be/i_0fmzIBsyU?si=q6uvjEXogKcXhnTT&t=169"},
        _T_PANOPTO,
    ],
    "2025-generative-midtended-cognition-and-artificial-intelligence": [
        {"date": "2025-12-04", "title": "Generative midtended cognition and Artificial Intelligence",
         "url": "https://www.youtube.com/watch?v=PkcUrHLOuxk"},
        _T_PANOPTO,
    ],
    "2025-sensorimotor-teleology-and-goal-directedness-an": [
        {"date": "2024-08-25", "title": "An Organismic Approach to Cognitive Normativity",
         "url": "https://www.youtube.com/watch?v=wbmHfsJbOiI", "host": "Metanoia"},
    ],
}

# ---- highlighted / featured publications ----
FEATURED = {
    "2025-sensorimotor-teleology-and-goal-directedness-an",
    "2026-organizational-accounts-of-malfunction-the-dual",
    "2025-transforming-agency-on-the-mode-of",
    "2025-generative-midtended-cognition-and-artificial-intelligence",
    "2026-outonomy-fleshing-out-the-concept-of",
}

def build_talks(slug):
    talks = TALKS.get(slug)
    if not talks:
        return ""
    rows = []
    for t in talks:
        meta = t["date"]
        if t.get("host"):
            meta += " · " + t["host"]
        if t.get("lang"):
            meta += " · " + t["lang"]
        rows.append(
            f'<li><a href="{html.escape(t["url"], quote=True)}" target="_blank" rel="noopener">'
            f'{html.escape(t["title"])}</a> <span class="talk-meta">{html.escape(meta)}</span></li>')
    label = "Talk" if len(talks) == 1 else f"Talks ({len(talks)})"
    return ('<!--TALK-START--><details class="pub-details pub-talks">'
            f'<summary class="pub-action-btn">{label} ▾</summary>'
            '<div class="pub-panel pub-talks-panel"><ul class="talk-list">'
            + "".join(rows) + '</ul></div></details><!--TALK-END-->')

# ---- process index.html ----
with open(INDEX, encoding="utf-8") as f:
    doc = f.read()

# strip any previously injected blocks (idempotency).
# Bounded so a missing END marker can't gobble across into the next block/entry.
doc = re.sub(r"[ \t]*<!--CITE-START-->(?:(?!<!--CITE-START-->).)*?<!--CITE-END-->\n?", "", doc, flags=re.S)
doc = re.sub(r"[ \t]*<span class=\"Z3988\"[^>]*></span>\n?", "", doc)
doc = re.sub(r"[ \t]*<div class=\"pub-keywords\">(?:(?!<div class=\"pub-keywords\">).)*?</div>\n?", "", doc, flags=re.S)
doc = re.sub(r"[ \t]*<!--TALK-START-->(?:(?!<!--TALK-START-->).)*?<!--TALK-END-->\n?", "", doc, flags=re.S)
doc = re.sub(r'\s*<span class="pub-featured"[^>]*>.*?</span>', "", doc, flags=re.S)
# remove li attributes we manage (pub-keywords divs already stripped above, so any
# remaining data-kw/data-featured live only on <li> open tags — safe to drop globally)
doc = re.sub(r'\s+data-kw="[^"]*"', "", doc)
doc = re.sub(r'\s+data-featured="[^"]*"', "", doc)
doc = re.sub(r'\s+data-doi="[^"]*"', "", doc)
# also drop the earlier hand-added keyword tokens appended to the malfunction data-search
doc = doc.replace(" autonomous organization dysfunction malfunction natural norms normative field normative function\">", "\">")

li_re = re.compile(r'(<li class="pub-item" id="([^"]+)"[^>]*>)(.*?)(</li>)', re.S)

matched, unmatched = 0, []

def find_record(slug, body):
    m = re.search(r'href="https?://(?:dx\.)?doi\.org/([^"]+)"', body)
    if m:
        rec = by_doi.get(norm_doi(m.group(1)))
        if rec: return rec
    # title fallback: pull citation text title between the year and the venue is hard;
    # use JSON-LD name matched by slug from head graph
    nm = slug_to_name.get(slug)
    if nm:
        rec = by_title.get(norm(nm))
        if rec: return rec
        # loose contains match
        key = norm(nm)
        for t, rec in by_title.items():
            if key and (key in t or t in key):
                return rec
    return None

# map slug -> name from JSON-LD head
slug_to_name = {}
for m in re.finditer(r'"@id":\s*"[^"]*#([^"]+)",\s*"name":\s*"((?:[^"\\]|\\.)*)"', doc):
    slug_to_name[m.group(1)] = html.unescape(m.group(2).replace('\\"', '"'))

def inject(m):
    global matched
    open_tag, slug, body, close = m.groups()
    rec = find_record(slug, body)
    if not rec:
        unmatched.append(slug)
        return m.group(0)
    matched += 1
    ris = build_ris(rec); bib = build_bib(rec, slug)
    with open(os.path.join(CITE_DIR, slug + ".ris"), "w", encoding="utf-8") as fh:
        fh.write(ris)
    with open(os.path.join(CITE_DIR, slug + ".bib"), "w", encoding="utf-8") as fh:
        fh.write(bib)
    coins = build_coins(rec, slug)
    # keywords as a compact, clickable, middot-separated inline line
    kws = compute_keywords(rec)
    if kws:
        chips = ' <span class="kw-sep">·</span> '.join(
            f'<a class="pub-kw" href="#" data-kw="{html.escape(k, quote=True)}">{html.escape(k)}</a>'
            for k in kws)
        kw_block = f'      <div class="pub-keywords">{chips}</div>\n'
        data_kw = " ".join(k.lower() for k in kws)
        open_tag = open_tag[:-1] + f' data-kw="{html.escape(data_kw, quote=True)}">'
        body = body.replace('      <div class="pub-actions">',
                            kw_block + '      <div class="pub-actions">', 1)
    # featured badge + attribute
    if slug in FEATURED:
        open_tag = open_tag[:-1] + ' data-featured="true">'
        body = body.replace('<a class="pub-permalink"',
                            '<span class="pub-featured" title="Highlighted publication">★ Highlighted</span>\n        <a class="pub-permalink"', 1)
    # DOI attribute for live citation-count lookup (OpenAlex + Semantic Scholar)
    doi = norm_doi(field(rec, "DOI"))
    if doi:
        open_tag = open_tag[:-1] + f' data-doi="{html.escape(doi, quote=True)}">'
    talks_block = build_talks(slug)
    export = (
        '<!--CITE-START--><details class="pub-details pub-cite">'
        '<summary class="pub-action-btn">Cite ▾</summary>'
        '<div class="pub-panel pub-cite-panel">'
        '<p class="cite-lead">Import into Zotero, Mendeley, EndNote, Papers or any reference manager:</p>'
        f'<a class="pub-action" href="citations/{slug}.ris" download>Download RIS</a> '
        f'<a class="pub-action" href="citations/{slug}.bib" download>Download BibTeX</a>'
        '<p class="cite-note">Tip: with the Zotero or Mendeley browser connector installed, '
        'this page is auto-detected — one click saves the citation (and its PDF) directly to your library.</p>'
        '</div></details><!--CITE-END-->'
    )
    # insert talks + export button before closing </div> of pub-actions, coins before </li>
    inserts = (("        " + talks_block + "\n") if talks_block else "") + "        " + export
    if "</div>" in body:
        idx = body.rfind("</div>")
        body = body[:idx] + inserts + "\n      " + body[idx:]
    else:
        body = body + inserts
    body = body + "      " + coins + "\n    "
    return open_tag + body + close

doc = li_re.sub(inject, doc)

# ---- reorder: highlighted publications first, then the rest (reverse-chronological) ----
# Split on entry-start boundaries (NOT on </li>) so nested <li> inside talk lists
# can never truncate an entry.
mlist = re.search(r'(<ol class="pub-list"[^>]*>)(.*?)(</ol>)', doc, re.S)
inner = mlist.group(2)
starts = [m.start() for m in re.finditer(r'<li class="pub-item"', inner)]
segs = [inner[starts[i]:(starts[i + 1] if i + 1 < len(starts) else len(inner))]
        for i in range(len(starts))]
def _seg_slug(seg):
    m = re.search(r'id="([^"]+)"', seg)
    return m.group(1) if m else ""
featured_segs = [s for s in segs if _seg_slug(s) in FEATURED]
rest_segs = [s for s in segs if _seg_slug(s) not in FEATURED]
new_inner = inner[:starts[0]] + "".join(featured_segs + rest_segs) if starts else inner
doc = doc[:mlist.start(2)] + new_inner + doc[mlist.end(2):]

# ---- stamp the last-updated date ----
import datetime
today = datetime.date.today()
stamp = today.strftime("%-d %B %Y") if os.name != "nt" else today.strftime("%d %B %Y")
doc = re.sub(r'(<time id="last-updated" datetime=")[^"]*(">)[^<]*(</time>)',
             rf'\g<1>{today.isoformat()}\g<2>{stamp}\g<3>', doc)

with open(INDEX, "w", encoding="utf-8") as f:
    f.write(doc)

print(f"Matched & generated: {matched}")
print(f"Unmatched ({len(unmatched)}): {unmatched}")
print(f"Reordered: {len(featured_segs)} highlighted first, then {len(rest_segs)}")
print(f"Last-updated stamp: {stamp}")
