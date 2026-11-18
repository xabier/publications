/* Download / play / talk click counting for GoatCounter.
 * Only loaded when analytics is switched on ("goatcounter" in data/site.json).
 * Each click on a PDF, HTML/text version, audio, podcast, BibTeX/RIS file, talk
 * video or DOI link is recorded as an event, e.g. "download/pdfs/2025-….pdf".
 * No cookies, no personal data (GoatCounter counts without identifiers). */
(function () {
  "use strict";
  var LOCAL = /(?:^|\/)(pdfs|html|txt|audio|podcasts|citations)\/([^?#]+)$/;
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || !window.goatcounter || !window.goatcounter.count) return;
    var url;
    try { url = new URL(a.getAttribute("href"), location.href); } catch (x) { return; }
    var m, path;
    if (url.host === location.host && (m = url.pathname.match(LOCAL))) {
      path = "download/" + m[1] + "/" + m[2];
    } else if (/youtube\.com|youtu\.be|panopto|vimeo\.com/.test(url.host)) {
      path = "talk/" + url.host + url.pathname + url.search;
    } else if (/doi\.org$/.test(url.host)) {
      path = "doi/" + url.pathname.slice(1);
    } else {
      return;
    }
    window.goatcounter.count({ path: path, title: a.textContent.trim().slice(0, 120), event: true });
  });
})();
