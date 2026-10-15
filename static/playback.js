/**
 * Pure play-queue helpers for Seta (tested via Node and used in the browser).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TrackGraphPlayback = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const MIX_MIN_SCORE = 0.55;

  function mixScore(a, b) {
    if (!a.key || !b.key || a.bpm == null || b.bpm == null) return 0;

    const ka = a.key.toUpperCase();
    const kb = b.key.toUpperCase();
    let harmonic = 0;
    if (ka === kb) harmonic = 1;
    else {
      const na = ka.slice(0, -1);
      const la = ka.slice(-1);
      const nb = kb.slice(0, -1);
      const lb = kb.slice(-1);
      if (na === nb && la !== lb) harmonic = 0.82;
      else {
        let diff = Math.abs(Number(na) - Number(nb));
        diff = Math.min(diff, 12 - diff);
        if (la === lb && diff === 1) harmonic = 0.72;
        else if (diff === 1) harmonic = 0.55;
      }
    }
    if (!harmonic) return 0;

    const diff = Math.abs(a.bpm - b.bpm);
    let bpmFactor = 0;
    if (diff <= 1) bpmFactor = 1;
    else if (diff <= 2) bpmFactor = 0.9;
    else if (diff <= 4) bpmFactor = 0.7;
    else if (diff <= 6) bpmFactor = 0.45;
    return harmonic * bpmFactor;
  }

  function mixNeighbors(trackId, tracks, minScore = MIX_MIN_SCORE) {
    const selected = tracks.find(t => t.id === trackId);
    if (!selected) return { ids: new Set([trackId]), list: [] };

    const list = tracks.filter(t => t.id !== trackId && mixScore(selected, t) >= minScore);
    list.sort((a, b) => mixScore(selected, b) - mixScore(selected, a));
    const ids = new Set([trackId, ...list.map(t => t.id)]);
    return { ids, list };
  }

  function effectiveEnergy(track, fallback = 0.5) {
    const candidates = [
      track?.energy_manual,
      track?.energy_effective,
      track?.energy_auto,
      track?.energy_main,
      track?.energy,
    ];
    for (const value of candidates) {
      if (Number.isFinite(value)) return Math.max(0, Math.min(1, value));
    }
    return fallback;
  }

  function sortDraftTracks(tracks, sortMode) {
    if (sortMode === "manual") return tracks.slice();
    return tracks.slice().sort((a, b) => {
      if (sortMode === "bpm") {
        const da = a.bpm ?? Infinity;
        const db = b.bpm ?? Infinity;
        if (da !== db) return da - db;
        return effectiveEnergy(a, 0) - effectiveEnergy(b, 0);
      }
      const da = effectiveEnergy(a, 0);
      const db = effectiveEnergy(b, 0);
      if (da !== db) return da - db;
      return (a.bpm ?? 0) - (b.bpm ?? 0);
    });
  }

  function buildDraftQueue(filtered, draftTrackIds, sortMode = "energy") {
    if (!Array.isArray(draftTrackIds) || !draftTrackIds.length) return [];
    const byId = new Map(filtered.map(t => [t.id, t]));
    const tracks = draftTrackIds.map(id => byId.get(id)).filter(Boolean);
    return sortDraftTracks(tracks, sortMode);
  }

  function buildNavigableTracks(filtered, selection) {
    const base = filtered;
    if (selection?.draftPlayMode && selection.draftTrackIds?.length) {
      return buildDraftQueue(base, selection.draftTrackIds, selection.draftSortMode || "energy");
    }
    if (selection?.highlightNeighbors && selection.neighborQueueAnchor) {
      const { list } = mixNeighbors(selection.neighborQueueAnchor, base);
      const anchor = base.find(t => t.id === selection.neighborQueueAnchor);
      if (!anchor) return base.slice();
      return [anchor, ...list];
    }
    return base.slice();
  }

  function queueSignature(queue) {
    return queue.map(t => t.id).join("\0");
  }

  function resolvePlayIndex(queue, trackId) {
    if (!queue.length) return -1;
    if (!trackId) return 0;
    const idx = queue.findIndex(t => t.id === trackId);
    return idx >= 0 ? idx : 0;
  }

  /** Advance by step from currentIndex; never returns the same index when length > 1. */
  function advancePlayIndex(queue, currentIndex, step) {
    if (!queue.length) return -1;
    const len = queue.length;
    if (len === 1) return 0;
    const base = currentIndex >= 0 && currentIndex < len ? currentIndex : 0;
    let idx = (base + step) % len;
    if (idx < 0) idx += len;
    if (idx === base) {
      idx = step >= 0 ? (base + 1) % len : (base - 1 + len) % len;
    }
    return idx;
  }

  function nextPlayIndex(queue, currentId, currentIndex, step) {
    const base = currentIndex >= 0 ? currentIndex : resolvePlayIndex(queue, currentId);
    return advancePlayIndex(queue, base, step);
  }

  function syncPlayQueueState(state, filtered, selection) {
    const queue = buildNavigableTracks(filtered, selection);
    const sig = queueSignature(queue);
    if (sig === state.playQueueSig && state.playQueue.length) {
      return { changed: false, queue: state.playQueue };
    }
    const preferred = state.playingId || state.selectedId;
    const playIndex = resolvePlayIndex(queue, preferred);
    state.playQueue = queue;
    state.playQueueSig = sig;
    state.playIndex = playIndex;
    return { changed: true, queue };
  }

  return {
    MIX_MIN_SCORE,
    mixScore,
    mixNeighbors,
    sortDraftTracks,
    effectiveEnergy,
    buildDraftQueue,
    buildNavigableTracks,
    queueSignature,
    resolvePlayIndex,
    advancePlayIndex,
    nextPlayIndex,
    syncPlayQueueState,
  };
});
