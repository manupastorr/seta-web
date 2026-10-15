import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { bandLevel, columns, columnRange, decode, hotCueColor, maxHeight, paint } = createRequire(import.meta.url)("../static/rbWaveform.js");

test("columns follow Beat Link's color preview math", () => {
  const [col] = columns(Uint8Array.from([0, 0, 0, 20, 10, 5]));
  assert.equal(col.back, 20);
  assert.equal(col.front, 5);
  assert.deepEqual(col.backColor, [191, 95, 47]);
  assert.deepEqual(col.frontColor, [255, 127, 63]);
});

test("silent columns stay black and the scale never divides by zero", () => {
  const cols = columns(new Uint8Array(12));
  assert.deepEqual(cols[0].backColor, [0, 0, 0]);
  assert.equal(maxHeight(cols), 1);
});

test("decode reads base64 into bytes", () => {
  assert.deepEqual([...decode("AAEC/w==")], [0, 1, 2, 255]);
});

test("columnRange maps a time window onto preview columns", () => {
  assert.deepEqual(columnRange(0, 100, 1200, 60000, 0, 60000), [0, 12]);
  assert.deepEqual(columnRange(99, 100, 1200, 60000, 0, 60000), [1188, 1200]);
  assert.deepEqual(columnRange(0, 10, 1200, 60000, 30000, 60000), [600, 660]);
});

test("hot cues use Rekordbox's letter colors", () => {
  assert.equal(hotCueColor("A"), "#e8336c");
  assert.equal(hotCueColor("G"), "#7bd148");
});

test("bandLevel averages one band against the track's loudest column", () => {
  // Two columns: low 10 then low 20 (byte 3 of each 6-byte entry).
  const bytes = Uint8Array.from([0, 0, 0, 10, 0, 0, 0, 0, 0, 20, 0, 0]);
  const wave = { preview: Buffer.from(bytes).toString("base64"), duration_ms: 2000 };
  assert.equal(bandLevel(wave, 0, 1000, "low"), 0.5);
  assert.equal(bandLevel(wave, 1000, 2000, "low"), 1);
  assert.equal(bandLevel(wave, 0, 2000, "low"), 0.75);
});

test("paint follows a custom time map, so a sped-up part of a track is drawn squeezed", () => {
  // Four columns over 4 s: only the last one is loud.
  const bytes = Uint8Array.from([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 200, 0, 0]);
  const wave = { preview: Buffer.from(bytes).toString("base64"), duration_ms: 4000 };
  const loudAt = (options) => {
    const xs = [];
    const ctx = { fillRect: (x) => xs.push(x), set fillStyle(_) {} };
    paint(ctx, wave, { x: 0, y: 0, w: 4, h: 10 }, { cues: false, ...options });
    return xs;
  };
  assert.deepEqual(loudAt({}), [3]);
  // Time runs twice as fast in the first half of the width: the last column now fills x 2 and 3.
  const timeAt = (f) => (f <= 0.5 ? f * 2 * 2000 * 1.5 : 3000 + (f - 0.5) * 2 * 1000);
  assert.deepEqual(loudAt({ timeAt }), [2, 3]);
});
