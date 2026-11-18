/* Landing pages (p/{slug}/): copy buttons for the citation, BibTeX and summary quotes. */
(function () {
  "use strict";

  function copyText(text, btn, label) {
    var done = function () {
      btn.textContent = "Copied";
      btn.classList.add("copied");
      setTimeout(function () { btn.textContent = label; btn.classList.remove("copied"); }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  }
  function fallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }
  function cleanText(el) {
    var clone = el.cloneNode(true);
    Array.prototype.forEach.call(clone.querySelectorAll("button"), function (b) { b.parentNode.removeChild(b); });
    return clone.textContent.replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  }

  // "Copy citation" / "Copy BibTeX"
  Array.prototype.forEach.call(document.querySelectorAll(".copy-btn[data-copy]"), function (btn) {
    var label = btn.textContent;
    btn.addEventListener("click", function () {
      var target = document.querySelector(btn.getAttribute("data-copy"));
      if (!target) return;
      var text = target.tagName === "PRE" ? target.textContent.trim() : cleanText(target).replace(/\s+/g, " ");
      copyText(text, btn, label);
    });
  });

  // Copy button on each summary quote
  Array.prototype.forEach.call(document.querySelectorAll(".summary-quote"), function (bq) {
    if (bq.querySelector(".copy-quote")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-quote";
    btn.textContent = "Copy";
    btn.title = "Copy quote";
    btn.setAttribute("aria-label", "Copy quote to clipboard");
    bq.insertBefore(btn, bq.firstChild);
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      copyText(cleanText(bq).replace(/\s+/g, " "), btn, "Copy");
    });
  });
})();
