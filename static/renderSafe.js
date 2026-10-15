/**
 * Minimal HTML escaping for library metadata rendered through template strings.
 */
(function (root, factory) {
  const api = factory();
  root.SetaRenderSafe = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const HTML_ESCAPE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function html(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => HTML_ESCAPE[char]);
  }

  return { html, attr: html };
});
