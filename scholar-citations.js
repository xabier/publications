/*
 * Live citation counts for publications.barandiaran.net
 * Progressive enhancement: for every entry carrying a DOI, look up its citation
 * count from OpenAlex and Semantic Scholar (two batched requests total), show the
 * higher of the two as "Cited by N", and link it to that source's list of citing
 * works. Results are cached in localStorage for a day. Fails silently (e.g. offline
 * or opened as a local file:// where cross-origin fetch is blocked).
 */
(function () {
  "use strict";

  var CACHE_KEY = "pubCitations.v1";
  var TTL_MS = 24 * 60 * 60 * 1000; // 1 day
  var MAILTO = "xabier.academic@barandiaran.net";

  var items = Array.prototype.slice.call(document.querySelectorAll(".pub-item[data-doi]"));
  if (!items.length) return;

  var dois = [];
  var byDoi = {};
  items.forEach(function (el) {
    var d = (el.getAttribute("data-doi") || "").toLowerCase().trim();
    if (!d) return;
    if (!byDoi[d]) { byDoi[d] = []; dois.push(d); }
    byDoi[d].push(el);
  });

  function readCache() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return {};
      var obj = JSON.parse(raw);
      if (!obj || (Date.now() - obj.ts) > TTL_MS) return {};
      return obj.data || {};
    } catch (e) { return {}; }
  }
  function writeCache(data) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data: data })); } catch (e) {}
  }

  function chunk(arr, n) {
    var out = [];
    for (var i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
    return out;
  }

  // ---- OpenAlex (batched via doi filter, OR-joined) ----
  function fetchOpenAlex(list) {
    var results = {};
    var groups = chunk(list, 40);
    return Promise.all(groups.map(function (g) {
      var filter = "doi:" + g.join("|");
      var url = "https://api.openalex.org/works?per-page=50&select=id,doi,cited_by_count&mailto="
        + encodeURIComponent(MAILTO) + "&filter=" + encodeURIComponent(filter);
      return fetch(url).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !j.results) return;
        j.results.forEach(function (w) {
          if (!w.doi) return;
          var d = w.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").toLowerCase();
          var shortId = (w.id || "").split("/").pop();
          results[d] = {
            count: (typeof w.cited_by_count === "number") ? w.cited_by_count : null,
            url: shortId ? "https://openalex.org/works?filter=cites:" + shortId : null,
            source: "OpenAlex"
          };
        });
      }).catch(function () {});
    })).then(function () { return results; });
  }

  // ---- Semantic Scholar (single batch POST) ----
  function fetchSemanticScholar(list) {
    var results = {};
    var groups = chunk(list, 400); // S2 batch allows up to 500 ids
    return Promise.all(groups.map(function (g) {
      return fetch("https://api.semanticscholar.org/graph/v1/paper/batch?fields=citationCount,url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: g.map(function (d) { return "DOI:" + d; }) })
      }).then(function (r) { return r.ok ? r.json() : null; }).then(function (arr) {
        if (!Array.isArray(arr)) return;
        arr.forEach(function (p, i) {
          if (!p) return;
          results[g[i]] = {
            count: (typeof p.citationCount === "number") ? p.citationCount : null,
            url: p.url || null,
            source: "Semantic Scholar"
          };
        });
      }).catch(function () {});
    })).then(function () { return results; });
  }

  function best(oa, s2) {
    var cands = [];
    if (oa && typeof oa.count === "number") cands.push(oa);
    if (s2 && typeof s2.count === "number") cands.push(s2);
    if (!cands.length) return null;
    cands.sort(function (a, b) { return b.count - a.count; });
    return cands[0];
  }

  function render(doi, entry) {
    if (!entry || typeof entry.count !== "number") return;
    // expose the count for sorting (script.js reads data-citations), even when 0
    (byDoi[doi] || []).forEach(function (el) {
      el.dataset.citations = String(entry.count);
    });
    if (entry.count < 1) return;
    (byDoi[doi] || []).forEach(function (el) {
      var meta = el.querySelector(".pub-meta") || el.querySelector(".pub-actions");
      if (!meta || meta.querySelector(".pub-cited")) return;
      var node;
      if (entry.url) {
        node = document.createElement("a");
        node.href = entry.url;
        node.target = "_blank";
        node.rel = "noopener";
      } else {
        node = document.createElement("span");
      }
      node.className = "pub-cited";
      node.textContent = "Cited by " + entry.count;
      node.title = "Cited by " + entry.count + " (" + entry.source + ") — view citing works";
      var permalink = meta.querySelector(".pub-permalink");
      if (permalink) meta.insertBefore(node, permalink);
      else meta.appendChild(node);
    });
  }

  var cache = readCache();
  var need = dois.filter(function (d) { return !(d in cache); });

  // let listeners (e.g. the sorter in script.js) know counts changed
  function announce() {
    try { document.dispatchEvent(new CustomEvent("citations:updated")); } catch (e) {}
  }

  // paint whatever we already have cached, immediately
  dois.forEach(function (d) { if (cache[d]) render(d, cache[d]); });
  announce();

  if (!need.length) return;

  Promise.all([fetchOpenAlex(need), fetchSemanticScholar(need)]).then(function (res) {
    var oa = res[0], s2 = res[1];
    need.forEach(function (d) {
      var merged = best(oa[d], s2[d]);
      cache[d] = merged || { count: null }; // cache misses too, to avoid re-hammering
      if (merged) render(d, merged);
    });
    writeCache(cache);
    announce();
  }).catch(function () {});
})();
