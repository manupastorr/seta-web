import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const {
  advancePlayIndex,
  buildNavigableTracks,
  mixNeighbors,
  nextPlayIndex,
  queueSignature,
  resolvePlayIndex,
  sortDraftTracks,
  syncPlayQueueState,
} = createRequire(import.meta.url)("../static/playback.js");

function track(id, title, key = "8A", bpm = 128) {
  return { id, title, artist: "A", key, bpm };
}

const amalv = track("amalv", "Amalv (Original Mix)", "1A", 112);
const n1 = track("n1", "Neighbor One", "1A", 113);
const n2 = track("n2", "Neighbor Two", "2A", 114);
const n3 = track("n3", "Neighbor Three", "12A", 111);
const other = track("other", "Outside", "10A", 140);

test("buildNavigableTracks uses anchor plus mix neighbors only", () => {
  const filtered = [amalv, n1, n2, n3, other];
  const queue = buildNavigableTracks(filtered, {
    highlightNeighbors: true,
    neighborQueueAnchor: amalv.id,
  });
  assert.equal(queue.length, 4);
  assert.equal(queue[0].id, amalv.id);
  assert.deepEqual(queue.map(t => t.id), [amalv.id, ...mixNeighbors(amalv.id, filtered).list.map(t => t.id)]);
});

test("nextPlayIndex advances through neighbor queue (Amalv scenario)", () => {
  const filtered = [amalv, n1, n2, n3];
  const queue = buildNavigableTracks(filtered, {
    highlightNeighbors: true,
    neighborQueueAnchor: amalv.id,
  });
  assert.ok(queue.length > 1);

  let idx = resolvePlayIndex(queue, amalv.id);
  const seen = [queue[idx].id];
  idx = nextPlayIndex(queue, queue[idx].id, idx, 1);
  seen.push(queue[idx].id);
  idx = nextPlayIndex(queue, queue[idx].id, idx, 1);
  seen.push(queue[idx].id);

  assert.notEqual(seen[0], seen[1], "next should leave Amalv");
  assert.notEqual(seen[1], seen[2], "second next should change again");
  assert.equal(new Set(seen).size, 3);
});

test("prevPlayIndex walks backward without sticking on one track", () => {
  const queue = [amalv, n1, n2];
  let idx = resolvePlayIndex(queue, n2.id);
  idx = nextPlayIndex(queue, queue[idx].id, idx, -1);
  assert.equal(queue[idx].id, n1.id);
  idx = nextPlayIndex(queue, queue[idx].id, idx, -1);
  assert.equal(queue[idx].id, amalv.id);
});

test("advancePlayIndex never returns same index when queue length > 1", () => {
  const queue = [amalv, n1, n2];
  for (let i = 0; i < queue.length; i++) {
    const next = advancePlayIndex(queue, i, 1);
    assert.notEqual(next, i);
    const prev = advancePlayIndex(queue, i, -1);
    assert.notEqual(prev, i);
  }
});

test("filtered-only selection cycles all visible tracks", () => {
  const queue = buildNavigableTracks([amalv, n1, n2], { highlightNeighbors: false });
  assert.equal(queue.length, 3);
  let idx = 0;
  const ids = [];
  for (let i = 0; i < 3; i++) {
    ids.push(queue[idx].id);
    idx = advancePlayIndex(queue, idx, 1);
  }
  assert.equal(new Set(ids).size, 3);
});

test("syncPlayQueueState preserves index when filters unchanged", () => {
  const state = {
    playingId: n1.id,
    selectedId: amalv.id,
    playQueue: [],
    playQueueSig: "",
    playIndex: -1,
  };
  const filtered = [amalv, n1, n2];
  const selection = { highlightNeighbors: true, neighborQueueAnchor: amalv.id };
  syncPlayQueueState(state, filtered, selection);
  assert.equal(state.playIndex, 1);
  state.playIndex = 1;
  syncPlayQueueState(state, filtered, selection);
  assert.equal(state.playIndex, 1, "unchanged filter should keep playIndex");
});

test("syncPlayQueueState re-resolves index when queue signature changes", () => {
  const state = {
    playingId: n2.id,
    selectedId: amalv.id,
    playQueue: [],
    playQueueSig: "",
    playIndex: -1,
  };
  const selection = { highlightNeighbors: true, neighborQueueAnchor: amalv.id };
  syncPlayQueueState(state, [amalv, n1, n2, n3], selection);
  assert.equal(state.playQueue[state.playIndex].id, n2.id);
  syncPlayQueueState(state, [amalv, n1], selection);
  assert.equal(state.playQueue[state.playIndex].id, amalv.id, "dropped track falls back to anchor");
});

test("playRelative simulation never replays same id twice in a row", () => {
  const state = {
    playingId: amalv.id,
    selectedId: amalv.id,
    playQueue: [],
    playQueueSig: "",
    playIndex: -1,
  };
  const filtered = [amalv, n1, n2, n3];
  const selection = { highlightNeighbors: true, neighborQueueAnchor: amalv.id };
  syncPlayQueueState(state, filtered, selection);
  const firstId = state.playQueue[state.playIndex].id;
  const nextIdx = advancePlayIndex(state.playQueue, state.playIndex, 1);
  const secondId = state.playQueue[nextIdx].id;
  assert.notEqual(firstId, secondId);
  state.playIndex = nextIdx;
  state.playingId = secondId;
  const prevIdx = advancePlayIndex(state.playQueue, state.playIndex, -1);
  assert.equal(state.playQueue[prevIdx].id, firstId);
});

test("queue has unique ids (no false stuck navigation)", () => {
  const queue = buildNavigableTracks([amalv, n1, n2], {
    highlightNeighbors: true,
    neighborQueueAnchor: amalv.id,
  });
  assert.equal(queueSignature(queue), queue.map(t => t.id).join("\0"));
  assert.equal(new Set(queue.map(t => t.id)).size, queue.length);
});

test("buildNavigableTracks uses draft queue when draft play mode is on", () => {
  const low = track("low", "Low", "1A", 100);
  low.energy = 0.2;
  const high = track("high", "High", "2A", 110);
  high.energy = 0.8;
  const filtered = [high, low];
  const queue = buildNavigableTracks(filtered, {
    draftPlayMode: true,
    draftTrackIds: [high.id, low.id],
    draftSortMode: "energy",
  });
  assert.deepEqual(queue.map(t => t.id), [low.id, high.id]);
});

test("draft energy sorting uses effective manual energy", () => {
  const low = track("low", "Low", "1A", 100);
  low.energy = 0.2;
  low.energy_effective = 0.9;
  const high = track("high", "High", "2A", 110);
  high.energy = 0.8;
  high.energy_manual = 0.1;
  assert.deepEqual(sortDraftTracks([low, high], "energy").map(t => t.id), [high.id, low.id]);
});

test("buildNavigableTracks ignores draft queue when draft play mode is off", () => {
  const inDraft = track("in", "In draft", "1A", 100);
  const other = track("out", "Outside", "8A", 128);
  const filtered = [inDraft, other];
  const queue = buildNavigableTracks(filtered, {
    draftPlayMode: false,
    draftTrackIds: [inDraft.id],
    draftSortMode: "energy",
  });
  assert.deepEqual(queue.map(t => t.id), [inDraft.id, other.id]);
});
