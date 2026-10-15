import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { integratedLufs } = createRequire(import.meta.url)("../static/loudness.js");

const sine = (hz, amp, seconds, rate) => Float32Array.from({ length: seconds * rate }, (_, i) => amp * Math.sin((2 * Math.PI * hz * i) / rate));

test("a full-scale 997 Hz sine in one channel reads -3.01 LUFS (BS.1770 calibration)", () => {
  for (const rate of [44100, 48000]) {
    const left = sine(997, 1, 10, rate);
    const lufs = integratedLufs([left, new Float32Array(left.length)], rate);
    assert.ok(Math.abs(lufs - -3.01) < 0.05, `${rate} Hz: ${lufs}`);
  }
});

test("-20 dB is 20 LU quieter, silence is -Infinity, and gating ignores a silent half", () => {
  const rate = 48000;
  const loud = integratedLufs([sine(997, 0.1, 10, rate), sine(997, 0.1, 10, rate)], rate);
  assert.ok(Math.abs(loud - (-3.01 + 3.01 - 20)) < 0.05, String(loud));
  assert.equal(integratedLufs([new Float32Array(rate * 2), new Float32Array(rate * 2)], rate), -Infinity);
  const half = Float32Array.from({ length: rate * 20 }, (_, i) => (i < rate * 10 ? 0.1 * Math.sin((2 * Math.PI * 997 * i) / rate) : 0));
  assert.ok(Math.abs(integratedLufs([half, half], rate) - loud) < 0.1);
});
