"""Citation helpers shared by build_site.py: RIS, BibTeX and COinS builders and
the derived-topic lexicon. Records use the field names of Zotero's CSV export
("Item Type", "Publication Title", "Manual Tags", ...), as written to
data/zotero.json by sync_zotero.py. (Extracted from the former
build_citations.py, now in _legacy/.)
"""
import re, html, urllib.parse


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
    if bt == "phdthesis" and re.search(r"\b(MSc|MA|Master)", field(r, "Type")):
        bt = "mastersthesis"
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
    if field(r, "Publisher"):
        if bt in ("phdthesis", "mastersthesis"): fields.append(("school", field(r, "Publisher")))
        elif bt == "techreport": fields.append(("institution", field(r, "Publisher")))
        else: fields.append(("publisher", field(r, "Publisher")))
    if field(r, "Type") and bt in ("phdthesis", "mastersthesis", "techreport"):
        fields.append(("type", field(r, "Type")))
    if field(r, "Number") and bt == "techreport": fields.append(("number", field(r, "Number")))
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
    body = ",\n".join(f"  {k} = {{{v if k in ('url', 'doi') else bib_escape(v)}}}" for k, v in fields)
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

