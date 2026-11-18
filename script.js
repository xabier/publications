/* publications.barandiaran.net: homepage behaviour (layout "B": highlighted cards,
 * search + Topic / Type / Sort dropdowns, list grouped by year).
 * Everything here is progressive enhancement: without JS the page is a complete,
 * year-grouped list whose titles and "Details" links lead to each landing page. */
(function () {
  "use strict";

  var list = document.getElementById("pub-list");
  if (!list) return;
  var items = Array.prototype.slice.call(list.querySelectorAll(".pub-item"));
  var groups = Array.prototype.slice.call(list.querySelectorAll(".year-group"));
  var searchInput = document.getElementById("pub-search");
  var topicSelect = document.getElementById("pub-topic");
  var typeSelect = document.getElementById("pub-type");
  var sortSelect = document.getElementById("pub-sort");
  var countEl = document.getElementById("results-count");
  var noResults = document.getElementById("no-results");
  var featuredBtns = Array.prototype.slice.call(document.querySelectorAll("[data-featured-filter]"));
  var countDefault = countEl ? countEl.innerHTML : "";

  var state = { q: "", topic: "", type: "all", featured: false, sort: "newest" };

  // remember each entry's home (its year list) and original position
  items.forEach(function (item, i) {
    item._order = i;
    item._home = item.parentNode;
    var parts = [];
    Array.prototype.forEach.call(item.querySelectorAll(".pub-head, .pub-byline, .pub-type"), function (el) {
      parts.push(el.textContent);
    });
    parts.push(item.getAttribute("data-kw") || "");
    item._hay = parts.join(" ").replace(/\s+/g, " ").toLowerCase();
  });

  // flat list used only for "Most cited" (years make no sense there)
  var flat = document.createElement("ol");
  flat.className = "year-list flat-list";
  flat.hidden = true;
  list.appendChild(flat);

  // ---- search text that is not in the page (abstracts, summaries) ----
  var searchIndexState = 0;
  function loadSearchIndex() {
    if (searchIndexState || !window.fetch) return;
    searchIndexState = 1;
    fetch("search-index.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (ix) {
      if (!ix) return;
      items.forEach(function (it) { if (ix[it.id]) it._hay += " " + ix[it.id]; });
      apply();
    }).catch(function () {});
  }

  function matches(item) {
    if (state.type !== "all" && item.getAttribute("data-type") !== state.type) return false;
    if (state.featured && item.getAttribute("data-featured") !== "true") return false;
    if (state.topic && (" " + (item.getAttribute("data-topics") || "") + " ").indexOf(" " + state.topic + " ") === -1) return false;
    if (state.q && item._hay.indexOf(state.q) === -1) return false;
    return true;
  }

  function citations(item) {
    var c = parseInt(item.getAttribute("data-citations"), 10);
    return isNaN(c) ? null : c;
  }

  function apply() {
    var visible = 0;
    items.forEach(function (item) {
      var show = matches(item);
      item.hidden = !show;
      if (show) visible++;
    });

    if (state.sort === "cited") {
      var ordered = items.slice().sort(function (a, b) {
        var ca = citations(a), cb = citations(b);
        if (ca === null && cb === null) return a._order - b._order;
        if (ca === null) return 1;
        if (cb === null) return -1;
        return cb !== ca ? cb - ca : a._order - b._order;
      });
      ordered.forEach(function (it) { flat.appendChild(it); });
      flat.hidden = false;
      groups.forEach(function (g) { g.hidden = true; });
    } else {
      items.forEach(function (it) { it._home.appendChild(it); });   // back to their year
      flat.hidden = true;
      var gs = state.sort === "oldest" ? groups.slice().reverse() : groups;
      gs.forEach(function (g) {
        var ol = g.querySelector(".year-list");
        var its = Array.prototype.slice.call(ol.querySelectorAll(".pub-item"));
        its.sort(function (a, b) { return state.sort === "oldest" ? b._order - a._order : a._order - b._order; });
        its.forEach(function (it) { ol.appendChild(it); });
        var n = its.filter(function (it) { return !it.hidden; }).length;
        g.hidden = n === 0;
        var c = g.querySelector(".year-count");
        if (c) c.textContent = n + (n === 1 ? " publication" : " publications");
        list.appendChild(g);                       // year order follows the sort
      });
      list.appendChild(flat);
    }

    var filtered = state.q || state.topic || state.type !== "all" || state.featured;
    if (countEl) {
      countEl.innerHTML = filtered
        ? "<strong>" + visible + " of " + items.length + " publications</strong> · <a href=\"#\" class=\"clear-all\">Clear filters</a>"
        : countDefault;
    }
    if (noResults) noResults.classList.toggle("show", visible === 0);
    if (clearBtn) clearBtn.hidden = !(searchInput && searchInput.value);
    if (sortNote) sortNote.hidden = state.sort !== "cited";
    featuredBtns.forEach(function (b) { b.setAttribute("aria-pressed", state.featured ? "true" : "false"); });
  }

  // ---- controls ----
  var clearBtn = null;
  if (searchInput) {
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
    clearBtn.addEventListener("click", function () { searchInput.value = ""; state.q = ""; apply(); searchInput.focus(); });
    searchInput.addEventListener("input", function () { state.q = searchInput.value.trim().toLowerCase(); loadSearchIndex(); apply(); });
    searchInput.addEventListener("focus", loadSearchIndex);
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && searchInput.value) { searchInput.value = ""; state.q = ""; apply(); }
    });
  }
  if (topicSelect) topicSelect.addEventListener("change", function () { state.topic = topicSelect.value; apply(); });
  if (typeSelect) typeSelect.addEventListener("change", function () { state.type = typeSelect.value; apply(); });
  if (sortSelect) sortSelect.addEventListener("change", function () { state.sort = sortSelect.value; apply(); });
  featuredBtns.forEach(function (b) {
    b.addEventListener("click", function () {
      state.featured = !state.featured;
      apply();
      if (state.featured && countEl) countEl.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a.clear-all") : null;
    if (!a) return;
    e.preventDefault();
    state = { q: "", topic: "", type: "all", featured: false, sort: state.sort };
    if (searchInput) searchInput.value = "";
    if (topicSelect) topicSelect.value = "";
    if (typeSelect) typeSelect.value = "all";
    apply();
  });

  // note shown only when ranking by citations
  var sortNote = document.createElement("p");
  sortNote.className = "sort-note";
  sortNote.hidden = true;
  sortNote.textContent = "Ranked by open citation data (OpenAlex / Semantic Scholar), which under-counts " +
    "books and some older work. Entries with no available count are listed last.";
  if (countEl && countEl.parentNode) countEl.parentNode.parentNode.insertBefore(sortNote, countEl.parentNode.nextSibling);

  // live citation counts arrive later (scholar-citations.js)
  document.addEventListener("citations:updated", function () { if (state.sort === "cited") apply(); });

  // deep links: ?q=term (keyword links on landing pages) and ?topic=id
  try {
    var params = new URLSearchParams(window.location.search);
    if (params.get("q") && searchInput) {
      searchInput.value = params.get("q");
      state.q = params.get("q").toLowerCase();
      loadSearchIndex();
    }
    if (params.get("topic") && topicSelect) { topicSelect.value = params.get("topic"); state.topic = topicSelect.value; }
  } catch (e) {}
  apply();

  // ---- expandable panels (Abstract, Summary, Talks): one open per entry,
  //      shown full-width below the button row; abstract/summary load on demand ----
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
      btn.setAttribute("aria-label", "Copy quote to clipboard");
      bq.insertBefore(btn, bq.firstChild);
    });
  }
  list.addEventListener("toggle", function (e) {
    var d = e.target;
    if (d.tagName !== "DETAILS" || !d.classList.contains("pub-details")) return;
    var parent = d.closest(".pub-item");
    if (d.open && parent) {
      Array.prototype.forEach.call(parent.querySelectorAll("details.pub-details"), function (o) {
        if (o !== d && o.open) o.open = false;
      });
    }
    if (d._panel) d._panel.hidden = !d.open;
    if (!d.open || !d.classList.contains("pub-lazy") || d._loaded || !window.fetch) return;
    loadRecord(d.getAttribute("data-src")).then(function (rec) {
      var field = d.getAttribute("data-field");
      if (field === "abstract" && rec.abstract) {
        d._panel.innerHTML = "";
        var p = document.createElement("p");
        p.textContent = rec.abstract;
        d._panel.appendChild(p);
      } else if (field === "summary" && rec.summary_html) {
        d._panel.innerHTML = rec.summary_html;   // the site's own generated HTML
        addQuoteButtons(d._panel);
      }
      d._loaded = true;
    }).catch(function () { /* keep the fallback link to the landing page */ });
  }, true);

  // copy button on summary quotes
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".copy-quote") : null;
    if (!btn) return;
    e.preventDefault();
    var bq = btn.closest(".summary-quote");
    var clone = bq.cloneNode(true);
    var b = clone.querySelector(".copy-quote"); if (b) b.parentNode.removeChild(b);
    var text = clone.textContent.replace(/\s+/g, " ").trim();
    var done = function () { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  });
})();
