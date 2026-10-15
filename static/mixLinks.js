/**
 * Mix-link layout helpers for Seta (tested via Node and used in the browser).
 */
(function (root, factory) {
  const api = factory();
  root.MixLinksUi = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function libraryHasMixEdges(data) {
    return Array.isArray(data?.edges) && data.edges.length > 0;
  }

  /** Explore layout requires precomputed edges; otherwise fall back to mix map. */
  function layoutWithMixEdges(layout, hasEdges) {
    return hasEdges || layout !== "explore" ? layout : "mix";
  }

  return {
    libraryHasMixEdges,
    layoutWithMixEdges,
  };
});
