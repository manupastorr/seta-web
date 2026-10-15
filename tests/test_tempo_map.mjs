import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { tempoMap, nearestDownbeat, downbeatFrom, beatAt, timeAtBeat } = createRequire(import.meta.url)("../static/tempoMap.js");

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("an unsynced track plays at rate 1", () => {
  const map = tempoMap({ audioMs: 300000 });
  assert.equal(map.duration, 300000);
  assert.equal(map.audioAt(1234), 1234);
  assert.equal(map.rateAt(5000), 1);
});

test("hold, glide and native parts add up and invert", () => {
  // 120 BPM track entering a 125 BPM mix: rate 125/120 while holding.
  const map = tempoMap({ audioMs: 360000, startRate: 125 / 120, holdMs: 30000, glideMs: 32000 });
  close(map.rateAt(10000), 125 / 120);
  close(map.rateAt(30000 + 16000), (125 / 120 + 1) / 2);
  assert.equal(map.rateAt(100000), 1);
  close(map.audioAt(30000), 31250);
  close(map.audioAt(62000), 31250 + (32000 * (125 / 120 + 1)) / 2);
  for (const t of [5000, 30000, 45000, 62000, 200000]) close(map.setTimeAt(map.audioAt(t)), t, 1e-6);
  assert.ok(map.duration < 360000, "a faster start finishes the audio sooner");
  assert.equal(map.endRate, 1);
});

test("a short track that never finishes its glide ends mid-glide", () => {
  const map = tempoMap({ audioMs: 40000, startRate: 0.9, holdMs: 30000, glideMs: 32000 });
  assert.ok(map.endRate > 0.9 && map.endRate < 1);
  close(map.audioAt(map.duration), 40000, 1e-6);
});

test("downbeat helpers", () => {
  const downs = [100, 2100, 4100, 6100];
  assert.equal(downbeatFrom(downs, 2000), 2100);
  assert.equal(downbeatFrom([], 2000), 2000);
  const map = tempoMap({ audioMs: 10000 });
  // Track starts at set time 50000 with inMs 100: downbeats land at 50000, 52000, 54000 …
  assert.equal(nearestDownbeat(downs, 100, map, 50000, 52900), 52000);
  assert.equal(nearestDownbeat(downs, 100, map, 50000, 53100), 54000);
});

test("beat grid helpers map time to beats and back, also between and beyond beats", () => {
  const beats = [100, 600, 1100, 1650, 2200]; // tempo changes after beat 2
  assert.equal(beatAt(beats, 600), 1);
  assert.equal(beatAt(beats, 850), 1.5);
  close(beatAt(beats, 1375), 2.5);
  assert.equal(beatAt(beats, 2750), 5);
  assert.equal(beatAt(beats, -400), -1);
  for (const b of [-1, 0, 0.25, 2.5, 3.9, 6]) close(beatAt(beats, timeAtBeat(beats, b)), b);
});
