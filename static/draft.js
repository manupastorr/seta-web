/**
 * Set draft (shortlist) helpers for Seta — tested via Node and used in the browser.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TrackGraphDraft = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DRAFT_STORAGE_KEY = "seta-drafts-v1";
  const DRAFT_SORT_MODES = ["manual", "energy", "bpm"];

  function newDraftId() {
    return `draft-${Date.now().toString(36)}`;
  }

  function createDraft(name = "Set draft") {
    return {
      id: newDraftId(),
      name,
      trackIds: [],
      finalIds: [],
      notes: {},
      sortMode: "energy",
      updatedAt: Date.now(),
    };
  }

  function normalizeDraft(raw) {
    if (!raw || typeof raw !== "object") return null;
    const trackIds = Array.isArray(raw.trackIds) ? raw.trackIds.filter(id => typeof id === "string") : [];
    const finalIds = Array.isArray(raw.finalIds)
      ? raw.finalIds.filter(id => typeof id === "string" && trackIds.includes(id))
      : [];
    const notes = raw.notes && typeof raw.notes === "object" ? { ...raw.notes } : {};
    const sortMode = DRAFT_SORT_MODES.includes(raw.sortMode) ? raw.sortMode : "energy";
    return {
      id: typeof raw.id === "string" ? raw.id : newDraftId(),
      name: typeof raw.name === "string" && raw.name.trim() ? raw.name.trim() : "Set draft",
      trackIds,
      finalIds,
      notes,
      sortMode,
      updatedAt: Number.isFinite(raw.updatedAt) ? raw.updatedAt : Date.now(),
    };
  }

  function loadDraftStore(storage) {
    const empty = { activeId: null, drafts: {} };
    if (!storage) return empty;
    try {
      const raw = storage.getItem(DRAFT_STORAGE_KEY);
      if (!raw) return empty;
      const parsed = JSON.parse(raw);
      const drafts = {};
      const list = Array.isArray(parsed?.drafts) ? parsed.drafts : [];
      for (const item of list) {
        const draft = normalizeDraft(item);
        if (draft) drafts[draft.id] = draft;
      }
      let activeId = typeof parsed?.activeId === "string" ? parsed.activeId : null;
      if (activeId && !drafts[activeId]) activeId = Object.keys(drafts)[0] || null;
      if (!activeId && Object.keys(drafts).length) activeId = Object.keys(drafts)[0];
      return { activeId, drafts };
    } catch (_) {
      return empty;
    }
  }

  function saveDraftStore(storage, store) {
    if (!storage) return;
    const drafts = Object.values(store.drafts || {}).map(draft => ({
      ...draft,
      finalIds: [...(draft.finalIds || [])],
      trackIds: [...(draft.trackIds || [])],
      notes: { ...(draft.notes || {}) },
    }));
    storage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({
      activeId: store.activeId,
      drafts,
    }));
  }

  function getActiveDraft(store) {
    if (!store?.activeId) return null;
    return store.drafts[store.activeId] || null;
  }

  function ensureActiveDraft(store, defaultName = "Set draft") {
    let draft = getActiveDraft(store);
    if (draft) return draft;
    draft = createDraft(defaultName);
    store.drafts[draft.id] = draft;
    store.activeId = draft.id;
    return draft;
  }

  function touchDraft(draft) {
    draft.updatedAt = Date.now();
    return draft;
  }

  function addTrackToDraft(draft, trackId) {
    if (!draft || !trackId || draft.trackIds.includes(trackId)) return draft;
    draft.trackIds.push(trackId);
    return touchDraft(draft);
  }

  function removeTrackFromDraft(draft, trackId) {
    if (!draft || !trackId) return draft;
    draft.trackIds = draft.trackIds.filter(id => id !== trackId);
    draft.finalIds = (draft.finalIds || []).filter(id => id !== trackId);
    if (draft.notes?.[trackId]) delete draft.notes[trackId];
    return touchDraft(draft);
  }

  function toggleFinalInDraft(draft, trackId) {
    if (!draft || !trackId || !draft.trackIds.includes(trackId)) return draft;
    const finals = new Set(draft.finalIds || []);
    if (finals.has(trackId)) finals.delete(trackId);
    else finals.add(trackId);
    draft.finalIds = [...finals];
    return touchDraft(draft);
  }

  function setDraftNote(draft, trackId, note) {
    if (!draft || !trackId) return draft;
    if (!draft.notes) draft.notes = {};
    const trimmed = (note || "").trim();
    if (trimmed) draft.notes[trackId] = trimmed;
    else delete draft.notes[trackId];
    return touchDraft(draft);
  }

  function setDraftSortMode(draft, sortMode) {
    if (!draft || !DRAFT_SORT_MODES.includes(sortMode)) return draft;
    draft.sortMode = sortMode;
    return touchDraft(draft);
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

  function compareTracks(a, b, sortMode) {
    if (sortMode === "bpm") {
      const da = a.bpm ?? Infinity;
      const db = b.bpm ?? Infinity;
      if (da !== db) return da - db;
      return effectiveEnergy(a, 0) - effectiveEnergy(b, 0);
    }
    if (sortMode === "energy") {
      const da = effectiveEnergy(a, 0);
      const db = effectiveEnergy(b, 0);
      if (da !== db) return da - db;
      return (a.bpm ?? 0) - (b.bpm ?? 0);
    }
    return 0;
  }

  function resolveDraftTracks(draft, tracksById, sortMode = draft?.sortMode) {
    if (!draft) return [];
    const list = draft.trackIds.map(id => tracksById.get(id)).filter(Boolean);
    if (sortMode === "manual") return list;
    return list.slice().sort((a, b) => compareTracks(a, b, sortMode));
  }

  function moveDraftTrack(draft, trackId, newIndex) {
    if (!draft || !trackId) return draft;
    const ids = draft.trackIds.filter(id => id !== trackId);
    const clamped = Math.max(0, Math.min(newIndex, ids.length));
    ids.splice(clamped, 0, trackId);
    draft.trackIds = ids;
    draft.sortMode = "manual";
    return touchDraft(draft);
  }

  function reorderDraftByDisplayIndex(draft, fromIndex, toIndex, tracksById, sortMode = draft?.sortMode) {
    if (!draft || fromIndex === toIndex) return draft;
    const tracks = resolveDraftTracks(draft, tracksById, sortMode);
    if (
      fromIndex < 0 || toIndex < 0
      || fromIndex >= tracks.length || toIndex >= tracks.length
    ) return draft;
    const ids = tracks.map(t => t.id);
    const [moved] = ids.splice(fromIndex, 1);
    ids.splice(toIndex, 0, moved);
    draft.trackIds = ids;
    draft.sortMode = "manual";
    return touchDraft(draft);
  }

  function exportDraftM3u(draft, tracksById, sortMode = draft?.sortMode) {
    const tracks = resolveDraftTracks(draft, tracksById, sortMode);
    const lines = ["#EXTM3U"];
    for (const track of tracks) {
      const title = `${track.artist || "Unknown"} - ${track.title || "Unknown"}`;
      lines.push(`#EXTINF:-1,${title}`);
      if (track.path) lines.push(track.path);
    }
    return `${lines.join("\n")}\n`;
  }

  function exportDraftText(draft, tracksById, sortMode = draft?.sortMode) {
    return resolveDraftTracks(draft, tracksById, sortMode)
      .map((track, index) => {
        const meta = [
          track.bpm != null ? `${Math.round(track.bpm)} BPM` : null,
          track.key || null,
          `E ${effectiveEnergy(track).toFixed(2)}`,
        ].filter(Boolean).join(" · ");
        const note = draft.notes?.[track.id];
        const star = (draft.finalIds || []).includes(track.id) ? "★ " : "";
        return `${index + 1}. ${star}${track.artist || "?"} — ${track.title || "?"}${meta ? ` (${meta})` : ""}${note ? ` — ${note}` : ""}`;
      })
      .join("\n");
  }

  function energyRampPoints(tracks, width = 200, height = 36, pad = 3) {
    if (!tracks.length) return { path: "", points: [] };
    const energies = tracks.map(t => effectiveEnergy(t, 0));
    const min = Math.min(...energies);
    const max = Math.max(...energies);
    const span = Math.max(max - min, 0.08);
    const innerW = width - pad * 2;
    const innerH = height - pad * 2;
    const points = tracks.map((track, index) => {
      const x = pad + (tracks.length === 1 ? innerW / 2 : (index / (tracks.length - 1)) * innerW);
      const y = pad + innerH - ((effectiveEnergy(track, 0) - min) / span) * innerH;
      return { x, y, id: track.id };
    });
    const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    return { path, points, min, max };
  }

  function draftMixScores(anchorId, draftTrackIds, tracks, mixScoreFn) {
    const anchor = tracks.find(t => t.id === anchorId);
    const pool = new Set(draftTrackIds);
    if (!anchor) return new Map();
    const scores = new Map();
    for (const track of tracks) {
      if (!pool.has(track.id) || track.id === anchorId) continue;
      scores.set(track.id, mixScoreFn(anchor, track));
    }
    return scores;
  }

  function buildDraftPlaybackSelection(draftPlayMode, draftTrackIds, sortMode) {
    return {
      draftPlayMode: !!draftPlayMode,
      draftTrackIds: draftPlayMode ? [...draftTrackIds] : [],
      draftSortMode: sortMode || "energy",
    };
  }

  return {
    DRAFT_STORAGE_KEY,
    DRAFT_SORT_MODES,
    createDraft,
    normalizeDraft,
    loadDraftStore,
    saveDraftStore,
    getActiveDraft,
    ensureActiveDraft,
    addTrackToDraft,
    removeTrackFromDraft,
    toggleFinalInDraft,
    setDraftNote,
    setDraftSortMode,
    effectiveEnergy,
    resolveDraftTracks,
    moveDraftTrack,
    reorderDraftByDisplayIndex,
    exportDraftM3u,
    exportDraftText,
    energyRampPoints,
    draftMixScores,
    buildDraftPlaybackSelection,
  };
});
