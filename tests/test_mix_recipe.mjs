import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const MixRecipe = createRequire(import.meta.url)("../static/mixRecipe.js");
const { exitBars, mixLevels, swapBar, gainToDb } = MixRecipe;

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("B enters with highs 66%, mids 13%, lows killed; A is flat", () => {
  const { inc, out } = mixLevels(0, 32, null);
  assert.deepEqual([inc.high, inc.mid, inc.low], [0.66, 0.13, 0]);
  assert.deepEqual([out.high, out.mid, out.low, out.volume], [1, 1, 1, 1]);
});

test("onion: B's fader comes up first (bars 0-2), then its mids rise to 66% (bars 2-6)", () => {
  assert.equal(mixLevels(1, 32, null).inc.mid, 0.13, "mids wait for the fader");
  assert.equal(mixLevels(2, 32, null).inc.volume, 1);
  close(mixLevels(4, 32, null).inc.mid, (0.13 + 0.66) / 2);
  close(mixLevels(6, 32, null).inc.mid, 0.66);
});

test("the blend ramps B highs and mids to 100% while A mids go to 50% and A highs to 75%", () => {
  close(mixLevels(10, 32, null).inc.high, (0.66 + 1) / 2);
  close(mixLevels(10, 32, null).out.mid, (1 + 0.5) / 2);
  const end = mixLevels(14, 32, 16);
  assert.deepEqual([end.inc.high, end.inc.mid, end.out.mid, end.out.high], [1, 1, 0.5, 0.75]);
  assert.equal(end.inc.low, 0, "no bass from B before the swap");
});

test("bass swap on the first phrase start (every 8 bars) after the blend where B has bass", () => {
  assert.equal(swapBar(32, (bar) => bar >= 13), 16, "bar 14 has bass, but the phrase starts at 16");
  assert.equal(swapBar(32, (bar) => bar >= 17), 24);
  assert.equal(swapBar(32, (bar) => bar === 15), 15, "no phrase start with bass: the first bar with bass");
  assert.equal(swapBar(32, () => false), null);
  const before = mixLevels(15.9, 32, 16);
  const after = mixLevels(16, 32, 16);
  assert.deepEqual([before.inc.low, before.out.low], [0, 1]);
  assert.deepEqual([after.inc.low, after.out.low], [1, 0], "never two basslines");
});

test("A ramps out over 8 bars from the swap, then its fader cuts", () => {
  assert.deepEqual(exitBars(32, 16), { start: 16, cut: 24 });
  const at = (bar) => mixLevels(bar, 32, 16).out;
  assert.deepEqual([at(16).mid, at(16).high], [0.5, 0.75]);
  close(at(20).mid, 0.25);
  close(at(20).high, 0.375);
  assert.equal(at(24).mid, 0);
  assert.equal(at(23.9).volume, 1);
  assert.equal(at(24.2).volume, 0);
  // Without a swap A's lows ramp out with the rest, from the end of the blend.
  assert.deepEqual(exitBars(32, null), { start: 14, cut: 22 });
  close(mixLevels(18, 32, null).out.low, 0.5);
  // A's last downbeat comes first when the mix is short.
  assert.deepEqual(exitBars(20, 16), { start: 16, cut: 20 });
});

test("a short mix squeezes the steps", () => {
  const { inc } = mixLevels(7, 11, null); // half-length mix: blend done at bar 7
  assert.equal(inc.mid, 1);
  assert.equal(swapBar(11, () => true), 8, "the phrase start at bar 8");
  assert.deepEqual(exitBars(11), { start: 7, cut: 11 });
});

test("gains convert to dB", () => {
  close(gainToDb(1), 0);
  close(gainToDb(0.25), 20 * Math.log10(0.25));
  assert.equal(gainToDb(0), -60);
});

test("recipe lines are a few key points each, so they edit as curves", () => {
  const { recipeLine } = MixRecipe;
  for (const [total, swap] of [[24, 15], [16, null], [40, 20], [6, null]]) {
    for (const side of ["inc", "out"]) {
      for (const key of ["volume", "low", "mid", "high"]) {
        const line = recipeLine(total, swap, side, key);
        assert.ok(line.length >= 1 && line.length <= 5, `${side}.${key} has ${line.length} points`);
        for (let n = 1; n < line.length; n += 1) assert.ok(line[n].b >= line[n - 1].b, "points in time order");
      }
    }
  }
});

test("lines interpolate, step on a shared bar, bend through the halfway value and hold at the ends", () => {
  const { valueAt, silentFrom } = MixRecipe;
  const line = [{ b: 0, v: 0 }, { b: 4, v: 1, m: 0.25 }, { b: 8, v: 0.5 }, { b: 8, v: 0 }];
  assert.equal(valueAt(line, -1), 0);
  assert.equal(valueAt(line, 2), 0.5);
  assert.ok(Math.abs(valueAt(line, 6) - (1 - 0.5 * 0.25)) < 1e-9);
  assert.equal(valueAt(line, 8), 0);
  assert.equal(valueAt(line, 99), 0);
  assert.equal(silentFrom(line), 8);
  assert.equal(silentFrom([{ b: 0, v: 0 }, { b: 2, v: 1 }]), null);
});
