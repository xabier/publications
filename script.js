(function () {
  "use strict";

  var list = document.getElementById("pub-list");
  if (!list) return;
  var items = Array.prototype.slice.call(list.querySelectorAll(".pub-item"));
  var searchInput = document.getElementById("pub-search");
  // only real type filters — NOT the ★ Highlighted toggle or the sort pills,
  // which also carry .type-filter for styling but have no data-type-filter
  var typeButtons = Array.prototype.slice.call(document.querySelectorAll(".type-filter[data-type-filter]"));
  var countEl = document.getElementById("results-count");
  var noResults = document.getElementById("no-results");
  var featuredBtn = document.querySelector("[data-featured-filter]");

  var activeType = "all";
  var featuredOnly = false;
  var clearBtn = null;
  var currentSort = "newest";

  // remember the original DOM order (highlighted-first, then reverse-chronological)
  items.forEach(function (item, i) { item._order = i; });

  // Search text per entry, built once from the entry's own content (title, citation,
  // type, year, keywords, abstract/summary). This replaces the old data-search
  // attribute, which duplicated all of that text inside index.html.
  items.forEach(function (item) {
    var parts = [];
    Array.prototype.forEach.call(item.querySelectorAll(
      ".pub-ref, .pub-title, .pub-citation, .pub-type, .pub-year, .pub-keywords, " +
      "details.pub-details:not(.pub-cite):not(.pub-talks) .pub-panel"
    ), function (el) { parts.push(el.textContent); });
    parts.push(item.getAttribute("data-kw") || "");
    item._hay = parts.join(" ").replace(/\s+/g, " ").toLowerCase();
  });

  // Abstracts and summaries are not in this page (to keep it short enough for AI
  // agents); their text for searching comes from search-index.json, loaded the
  // first time the search box is used.
  var searchIndexState = 0;
  function loadSearchIndex() {
    if (searchIndexState || !window.fetch) return;
    searchIndexState = 1;
    fetch("search-index.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (ix) {
      if (!ix) return;
      items.forEach(function (it) { if (ix[it.id]) it._hay += " " + ix[it.id]; });
      searchIndexState = 2;
      applyFilters();
    }).catch(function () {});
  }

  // Abstract / Summary panels: fill them from the publication's JSON record on first open
  var recordCache = {};
  function loadRecord(url) {
    if (!recordCache[url]) {
      recordCache[url] = fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    }
    return recordCache[url];
  }
  function addQuoteButtons(root) {
    Array.prototype.forEach.call(root.querySelectorAll(".summary-quote"), function (bq) {
      if (bq.querySelector(".copy-quote")) return;
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "copy-quote"; btn.textContent = "Copy";
      btn.title = "Copy quote"; btn.setAttribute("aria-label", "Copy quote to clipboard");
      bq.insertBefore(btn, bq.firstChild);
    });
  }
  list.addEventListener("toggle", function (e) {
    var d = e.target;
    if (d.tagName !== "DETAILS" || !d.open || !d.classList.contains("pub-lazy") || d._loaded || !window.fetch) return;
    var panel = d._panel || d.querySelector(".pub-panel");
    loadRecord(d.getAttribute("data-src")).then(function (rec) {
      var field = d.getAttribute("data-field");
      if (field === "abstract" && rec.abstract) {
        panel.innerHTML = "";
        var p = document.createElement("p");
        p.textContent = rec.abstract;
        panel.appendChild(p);
      } else if (field === "summary" && rec.summary_html) {
        panel.innerHTML = rec.summary_html;   // our own generated HTML
        addQuoteButtons(panel);
      }
      d._loaded = true;
    }).catch(function () { /* keep the fallback link to the landing page */ });
  }, true);

  function citationCount(item) {
    var c = parseInt(item.getAttribute("data-citations"), 10);
    return isNaN(c) ? null : c;
  }

  // Reorder the list in the DOM. "newest" restores the original order;
  // "cited" ranks by citation count (desc), with entries that have no count
  // falling to the bottom in their original chronological order.
  function applySort() {
    var ordered;
    if (currentSort === "cited") {
      ordered = items.slice().sort(function (a, b) {
        var ca = citationCount(a), cb = citationCount(b);
        if (ca === null && cb === null) return a._order - b._order;
        if (ca === null) return 1;   // a to the bottom
        if (cb === null) return -1;  // b to the bottom
        if (cb !== ca) return cb - ca;
        return a._order - b._order;  // tie-break: keep chronological
      });
    } else {
      ordered = items.slice().sort(function (a, b) { return a._order - b._order; });
    }
    var frag = document.createDocumentFragment();
    ordered.forEach(function (item) { frag.appendChild(item); });
    list.appendChild(frag);
  }

  function normalize(s) {
    return (s || "").toLowerCase();
  }

  function applyFilters() {
    var query = normalize(searchInput ? searchInput.value : "");
    var visible = 0;

    items.forEach(function (item) {
      var type = item.getAttribute("data-type");
      var haystack = item._hay || "";
      var matchesType = activeType === "all" || type === activeType;
      var matchesQuery = query === "" || haystack.indexOf(query) !== -1;
      var matchesFeatured = !featuredOnly || item.getAttribute("data-featured") === "true";
      var show = matchesType && matchesQuery && matchesFeatured;
      item.style.display = show ? "" : "none";
      if (show) visible++;
    });

    if (countEl) {
      countEl.textContent = visible + " of " + items.length + " publications";
    }
    if (noResults) {
      noResults.classList.toggle("show", visible === 0);
    }
    if (clearBtn) {
      clearBtn.hidden = !(searchInput && searchInput.value);
    }
    markKeywords();
  }

  // highlight the keyword chip(s) matching the current search term
  function markKeywords() {
    var q = normalize(searchInput ? searchInput.value : "").trim();
    Array.prototype.forEach.call(document.querySelectorAll("a.pub-kw"), function (k) {
      var kw = normalize(k.getAttribute("data-kw") || k.textContent).trim();
      k.classList.toggle("active", q !== "" && kw === q);
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
    searchInput.addEventListener("focus", loadSearchIndex);
    searchInput.addEventListener("input", loadSearchIndex);

    // Inject a Clear (×) button inside the search box. Done in JS so it
    // survives pipeline rebuilds of index.html (script.js is not regenerated).
    var wrap = document.createElement("span");
    wrap.className = "search-wrap";
    searchInput.parentNode.insertBefore(wrap, searchInput);
    wrap.appendChild(searchInput);

    clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "clear-search";
    clearBtn.setAttribute("aria-label", "Clear search");
    clearBtn.innerHTML = "&times;";
    clearBtn.hidden = true;
    wrap.appendChild(clearBtn);

    clearBtn.addEventListener("click", function () {
      searchInput.value = "";
      applyFilters();
      searchInput.focus();
    });

    // Esc clears the box when it's focused
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && searchInput.value) {
        searchInput.value = "";
        applyFilters();
      }
    });
  }

  function setActiveType(type) {
    activeType = type;
    typeButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-type-filter") === type ? "true" : "false");
    });
    applyFilters();
  }

  typeButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var clicked = btn.getAttribute("data-type-filter");
      // clicking the already-active category (other than "all") unselects it
      if (clicked === activeType && clicked !== "all") {
        setActiveType("all");
      } else {
        setActiveType(clicked);
      }
    });
  });

  if (featuredBtn) {
    featuredBtn.addEventListener("click", function () {
      featuredOnly = !featuredOnly;
      featuredBtn.setAttribute("aria-pressed", featuredOnly ? "true" : "false");
      applyFilters();
    });
  }

  // ---- Sort control (Newest / Most cited) ----
  // Built in JS so it survives pipeline rebuilds of index.html.
  var sortButtons = [];
  var sortNote = null;
  function setSort(mode) {
    currentSort = mode;
    sortButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-sort") === mode ? "true" : "false");
    });
    if (sortNote) sortNote.hidden = mode !== "cited";
    applySort();
  }
  (function buildSortControl() {
    var controls = document.querySelector(".controls");
    if (!controls) return;
    var wrap = document.createElement("span");
    wrap.className = "sort-control";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Sort order");
    var label = document.createElement("span");
    label.className = "sort-label";
    label.textContent = "Sort:";
    wrap.appendChild(label);
    [["newest", "Newest"], ["cited", "Most cited"]].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "type-filter sort-btn";
      b.setAttribute("data-sort", pair[0]);
      b.setAttribute("aria-pressed", pair[0] === currentSort ? "true" : "false");
      b.textContent = pair[1];
      b.addEventListener("click", function () { setSort(pair[0]); });
      sortButtons.push(b);
      wrap.appendChild(b);
    });
    // place just before the results counter (which is pushed to the right)
    if (countEl && countEl.parentNode === controls) controls.insertBefore(wrap, countEl);
    else controls.appendChild(wrap);

    // explanatory note, shown only in "Most cited" mode
    sortNote = document.createElement("p");
    sortNote.className = "sort-note";
    sortNote.hidden = true;
    sortNote.textContent = "Ranked by open citation data (OpenAlex / Semantic Scholar), " +
      "which under-counts books and some older work. Entries with no available count — " +
      "including several books — are listed last.";
    if (controls.parentNode) controls.parentNode.insertBefore(sortNote, controls.nextSibling);
  })();

  // when live citation counts load (or update), re-sort if we're ranking by them
  document.addEventListener("citations:updated", function () {
    if (currentSort === "cited") applySort();
  });

  // Deep link: ?q=term pre-fills the search box (keyword links on the
  // per-publication pages point here, e.g. /?q=Autonomy)
  try {
    var q0 = new URLSearchParams(window.location.search).get("q");
    if (q0 && searchInput) { searchInput.value = q0; loadSearchIndex(); }
  } catch (e) {}

  applyFilters();

  // --- Hover tooltips on action buttons that don't already carry one ---
  var ACTION_TIPS = {
    "abstract": "Read the paper's abstract",
    "summary": "Read an extended summary with key quotes",
    "html": "Read the full text as a web page (new tab)",
    "full pdf": "Open the full published PDF (new tab)",
    "preprint": "Open the preprint PDF (new tab)",
    "cite": "Download the citation (RIS / BibTeX), or import it with a Zotero/Mendeley browser connector",
    "talk": "Watch related talks and video recordings",
    "talks": "Watch related talks and video recordings"
  };
  Array.prototype.forEach.call(document.querySelectorAll(".pub-action, .pub-action-btn"), function (el) {
    if (el.getAttribute("title")) return;
    var label = el.textContent.replace(/[▾▸]/g, "").replace(/\(\d+\)/g, "").replace(/soon/i, "").trim().toLowerCase();
    if (ACTION_TIPS[label]) el.setAttribute("title", ACTION_TIPS[label]);
  });

  // --- "Keywords:" label + clickable-filter hints on each keyword line ---
  Array.prototype.forEach.call(document.querySelectorAll(".pub-keywords"), function (kw) {
    if (!kw.querySelector(".pub-kw-label")) {
      var lab = document.createElement("span");
      lab.className = "pub-kw-label";
      lab.textContent = "Keywords:";
      lab.title = "Click any keyword to filter the list by that topic";
      kw.insertBefore(document.createTextNode(" "), kw.firstChild);
      kw.insertBefore(lab, kw.firstChild);
    }
    Array.prototype.forEach.call(kw.querySelectorAll("a.pub-kw"), function (k) {
      if (!k.getAttribute("title")) k.setAttribute("title", "Filter the list by “" + k.textContent.trim() + "”");
    });
  });

  // --- Copy button on each summary quote ---
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }
  Array.prototype.forEach.call(document.querySelectorAll(".summary-quote"), function (bq) {
    if (bq.querySelector(".copy-quote")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-quote";
    btn.textContent = "Copy";
    btn.title = "Copy quote";
    btn.setAttribute("aria-label", "Copy quote to clipboard");
    bq.insertBefore(btn, bq.firstChild);
  });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".copy-quote") : null;
    if (!btn) return;
    e.preventDefault();
    var bq = btn.closest(".summary-quote");
    if (!bq) return;
    var clone = bq.cloneNode(true);
    var b = clone.querySelector(".copy-quote"); if (b) b.parentNode.removeChild(b);
    var text = clone.textContent.replace(/\s+/g, " ").trim();
    var done = function () {
      btn.textContent = "Copied"; btn.classList.add("copied");
      setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  });

  // Clicking a keyword chip searches for it; clicking the active one again clears it (toggle)
  document.addEventListener("click", function (e) {
    var chip = e.target.closest ? e.target.closest("a.pub-kw") : null;
    if (!chip || !searchInput) return;
    e.preventDefault();
    var kw = (chip.getAttribute("data-kw") || chip.textContent).trim();
    var current = searchInput.value.trim().toLowerCase();
    if (current === kw.toLowerCase()) {
      searchInput.value = "";                 // same keyword clicked again -> unselect
    } else {
      searchInput.value = kw;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    applyFilters();
    searchInput.focus();
  });

  // --- Expandable panels: keep the button row aligned, drop the panel below it ---
  // Progressive enhancement: move each panel out of its <details> into a full-width
  // holder placed after the button row. The triggering button stays in place (and is
  // highlighted via CSS on [open]); the panel appears below the whole row, clearly
  // associated, without pushing the other buttons around. Works the same on mobile.
  // With JS off, the native <details> still expand inline, so nothing is lost.
  items.forEach(function (item) {
    var actions = item.querySelector(".pub-actions");
    if (!actions) return;
    var holder = document.createElement("div");
    holder.className = "pub-panels";
    actions.parentNode.insertBefore(holder, actions.nextSibling);
    Array.prototype.forEach.call(actions.querySelectorAll("details.pub-details"), function (d) {
      var panel = d.querySelector(".pub-panel");
      if (!panel) return;
      d._panel = panel;
      panel.hidden = !d.open;
      holder.appendChild(panel);
    });
  });
  list.classList.add("js-panels");

  // Drive the relocated panels from each <details>'s open/close state, and keep only
  // one panel open per entry.
  list.addEventListener("toggle", function (e) {
    var d = e.target;
    if (d.tagName !== "DETAILS" || !d.classList.contains("pub-details")) return;
    var parent = d.closest(".pub-item");
    if (!parent) return;
    if (d.open) {
      parent.querySelectorAll("details.pub-details").forEach(function (o) {
        if (o !== d && o.open) o.open = false;
      });
      if (d._panel) d._panel.hidden = false;
    } else if (d._panel) {
      d._panel.hidden = true;
    }
  }, true);
})();
