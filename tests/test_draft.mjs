import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const Draft = createRequire(import.meta.url)("../static/draft.js");

function track(id, title, energy = 0.5, bpm = 120) {
  return { id, title, artist: "A", key: "8A", bpm, energy, path: `/tmp/${id}.wav` };
}

test("add and remove tracks from draft", () => {
  const draft = Draft.createDraft("Warm up");
  Draft.addTrackToDraft(draft, "a");
  Draft.addTrackToDraft(draft, "b");
  Draft.addTrackToDraft(draft, "a");
  assert.deepEqual(draft.trackIds, ["a", "b"]);
  Draft.removeTrackFromDraft(draft, "a");
  assert.deepEqual(draft.trackIds, ["b"]);
});

test("resolveDraftTracks sorts by energy then bpm", () => {
  const draft = Draft.createDraft("Test");
  draft.trackIds = ["low", "mid", "high"];
  draft.sortMode = "energy";
  const byId = new Map([
    ["low", track("low", "Low", 0.2, 110)],
    ["mid", track("mid", "Mid", 0.5, 118)],
    ["high", track("high", "High", 0.8, 112)],
  ]);
  const sorted = Draft.resolveDraftTracks(draft, byId);
  assert.deepEqual(sorted.map(t => t.id), ["low", "mid", "high"]);
});

test("resolveDraftTracks uses effective manual energy when present", () => {
  const low = track("low", "Low", 0.2, 120);
  const high = track("high", "High", 0.8, 121);
  low.energy_effective = 0.9;
  high.energy_manual = 0.1;
  const byId = new Map([low, high].map(t => [t.id, t]));
  const draft = Draft.createDraft();
  draft.trackIds = ["low", "high"];
  draft.sortMode = "energy";
  assert.deepEqual(Draft.resolveDraftTracks(draft, byId).map(t => t.id), ["high", "low"]);
});

test("exportDraftM3u includes paths", () => {
  const draft = Draft.createDraft("Export");
  draft.trackIds = ["a"];
  const byId = new Map([["a", track("a", "One", 0.4, 100)]]);
  const m3u = Draft.exportDraftM3u(draft, byId);
  assert.match(m3u, /^#EXTM3U/);
  assert.match(m3u, /\/tmp\/a\.wav/);
});

test("energyRampPoints returns svg path", () => {
  const tracks = [track("a", "A", 0.2), track("b", "B", 0.8)];
  const { path, points } = Draft.energyRampPoints(tracks);
  assert.ok(path.startsWith("M"));
  assert.equal(points.length, 2);
});

test("reorderDraftByDisplayIndex switches to manual order", () => {
  const draft = Draft.createDraft("Reorder");
  draft.trackIds = ["a", "b", "c"];
  draft.sortMode = "manual";
  const byId = new Map([
    ["a", track("a", "A", 0.9, 120)],
    ["b", track("b", "B", 0.5, 118)],
    ["c", track("c", "C", 0.2, 110)],
  ]);
  Draft.reorderDraftByDisplayIndex(draft, 0, 2, byId, "manual");
  assert.equal(draft.sortMode, "manual");
  assert.deepEqual(draft.trackIds, ["b", "c", "a"]);
});

test("reorderDraftByDisplayIndex uses current display order when sorted", () => {
  const draft = Draft.createDraft("Reorder");
  draft.trackIds = ["a", "b", "c"];
  draft.sortMode = "energy";
  const byId = new Map([
    ["a", track("a", "A", 0.9, 120)],
    ["b", track("b", "B", 0.5, 118)],
    ["c", track("c", "C", 0.2, 110)],
  ]);
  Draft.reorderDraftByDisplayIndex(draft, 0, 2, byId, "energy");
  assert.equal(draft.sortMode, "manual");
  assert.deepEqual(draft.trackIds, ["b", "a", "c"]);
});

test("load and save draft store roundtrip", () => {
  const storage = new Map();
  const shim = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  const store = { activeId: null, drafts: {} };
  const draft = Draft.createDraft("Fusion");
  draft.trackIds = ["x", "y"];
  draft.finalIds = ["x"];
  draft.notes = { x: "opener" };
  store.drafts[draft.id] = draft;
  store.activeId = draft.id;
  Draft.saveDraftStore(shim, store);
  const loaded = Draft.loadDraftStore(shim);
  assert.equal(loaded.activeId, draft.id);
  assert.deepEqual(loaded.drafts[draft.id].trackIds, ["x", "y"]);
  assert.deepEqual(loaded.drafts[draft.id].finalIds, ["x"]);
  assert.equal(loaded.drafts[draft.id].notes.x, "opener");
});
