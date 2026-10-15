/**
 * Renders the key-locked part of a track for the Arrange page, ahead of playback.
 *
 * A synced track enters at the outgoing tempo (`startRate`), holds it for `holdMs`, then glides
 * back to its own tempo over `glideMs` (see tempoMap.js). This worker time-stretches exactly that
 * stretch of audio with SoundTouch (tempo changes, key stays), so playback can use plain,
 * sample-accurate buffers at rate 1 and the beats cannot drift.
 *
 * SoundTouch's output lags its input by a few ms. The lag is measured beat by beat (each beat's
 * sound in the input against the output around where the tempo map puts it; the median wins)
 * and trimmed off. Without a beat grid, the transients of the first 20 s are matched.
 */
import { SimpleFilter, SoundTouch } from "./vendor/soundtouch.js";

const BLOCK = 1024;
const SEQUENCE_MS = 40;
const SEEK_WINDOW_MS = 10;
const OVERLAP_MS = 8;
const MAX_LAG_MS = 120;
const BEAT_LAG_MS = 60;

function rateAt(ms, { startRate, holdMs, glideMs }) {
  if (ms <= holdMs) return startRate;
  if (ms <= holdMs + glideMs) return startRate + ((1 - startRate) * (ms - holdMs)) / glideMs;
  return 1;
}

function audioAt(ms, { startRate, holdMs, glideMs }) {
  if (ms <= holdMs) return startRate * ms;
  const u = Math.min(ms, holdMs + glideMs) - holdMs;
  const k = glideMs ? (1 - startRate) / (2 * glideMs) : 0;
  const inGlide = startRate * holdMs + startRate * u + k * u * u;
  return ms <= holdMs + glideMs ? inGlide : inGlide + (ms - holdMs - glideMs);
}

/**
 * Transient strength per millisecond of a stereo signal: the summed sample-to-sample change, which
 * peaks on attacks (kicks, hats) and stays low on pads, so beats line up sharply when matched.
 */
function envelope(left, right, sampleRate, startFrame, count, frameAt) {
  const perMs = sampleRate / 1000;
  const env = new Float32Array(count);
  for (let k = 0; k < count; k += 1) {
    const from = Math.floor(frameAt ? frameAt(k) : startFrame + k * perMs);
    let sum = 0;
    for (let i = 0; i < perMs; i += 1) {
      const j = from + i;
      if (j > 0 && j < left.length) sum += Math.abs(left[j] - left[j - 1]) + Math.abs(right[j] - right[j - 1]);
    }
    env[k] = sum;
  }
  return env;
}

/** Set time (ms) at which audio time `a` plays: the inverse of audioAt, by bisection. */
function setTimeAt(a, plan, totalMs) {
  let lo = 0;
  let hi = totalMs;
  for (let i = 0; i < 40; i += 1) {
    const mid = (lo + hi) / 2;
    if (audioAt(mid, plan) < a) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

/** Median lag (ms) of beats in `out` against `input`: each beat's 150 ms of sound, matched within ±BEAT_LAG_MS. */
function beatLag(inL, inR, outL, outR, sampleRate, beatsMs, plan, totalMs) {
  const lags = [];
  for (let n = 0; n < beatsMs.length; n += 2) {
    const a = beatsMs[n];
    const t = setTimeAt(a, plan, totalMs);
    if (t < 200 || t > totalMs - 200) continue;
    const reference = envelope(inL, inR, sampleRate, ((a - 75) / 1000) * sampleRate, 150);
    let best = -1;
    let bestLag = 0;
    for (let lag = -BEAT_LAG_MS; lag <= BEAT_LAG_MS; lag += 1) {
      const candidate = envelope(outL, outR, sampleRate, ((t - 75 + lag) / 1000) * sampleRate, 150);
      let score = 0;
      for (let k = 0; k < 150; k += 1) score += reference[k] * candidate[k];
      if (score > best) {
        best = score;
        bestLag = lag;
      }
    }
    lags.push(bestLag);
  }
  if (lags.length < 8) return null;
  lags.sort((x, y) => x - y);
  return lags[lags.length >> 1];
}

/** The lag (ms) at which `out` best matches `expected` (positive: `out` is late). */
function bestLag(out, expected) {
  let best = 0;
  let bestScore = -Infinity;
  for (let lag = -MAX_LAG_MS; lag <= MAX_LAG_MS; lag += 1) {
    let score = 0;
    for (let k = MAX_LAG_MS; k < expected.length - MAX_LAG_MS; k += 1) score += expected[k] * out[k + lag];
    if (score > bestScore) {
      bestScore = score;
      best = lag;
    }
  }
  return best;
}

self.onmessage = (event) => {
  const { id, left, right, sampleRate, startRate, holdMs, glideMs, beatsMs = [] } = event.data;
  const plan = { startRate, holdMs, glideMs };
  const totalMs = holdMs + glideMs;
  const outFrames = Math.round((totalMs / 1000) * sampleRate);
  const pad = Math.round((MAX_LAG_MS / 1000) * sampleRate);

  const source = {
    extract(target, numFrames, position) {
      const n = Math.max(0, Math.min(numFrames, left.length - position));
      for (let i = 0; i < n; i += 1) {
        target[i * 2] = left[position + i];
        target[i * 2 + 1] = right[position + i];
      }
      return n;
    },
  };
  const soundtouch = new SoundTouch();
  // Short splices keep beats within a few ms of where they belong (defaults allow ±14 ms).
  soundtouch.stretch.setParameters(sampleRate, SEQUENCE_MS, SEEK_WINDOW_MS, OVERLAP_MS);
  const filter = new SimpleFilter(source, soundtouch);
  const rawL = new Float32Array(outFrames + pad);
  const rawR = new Float32Array(outFrames + pad);
  const block = new Float32Array(BLOCK * 2);
  let done = 0;
  while (done < rawL.length) {
    soundtouch.tempo = rateAt((done / sampleRate) * 1000, plan);
    const n = filter.extract(block, Math.min(BLOCK, rawL.length - done));
    if (!n) break;
    for (let i = 0; i < n; i += 1) {
      rawL[done + i] = block[i * 2];
      rawR[done + i] = block[i * 2 + 1];
    }
    done += n;
  }

  // Beat by beat when there is a beat grid, else the first 20 s of loudness.
  const checkMs = Math.min(20000, Math.floor(totalMs) - 1);
  let lag = beatLag(left, right, rawL, rawR, sampleRate, beatsMs, plan, totalMs) ?? 0;
  if (!beatsMs.length && checkMs > 4 * MAX_LAG_MS) {
    const expected = envelope(left, right, sampleRate, 0, checkMs, (k) => (audioAt(k, plan) / 1000) * sampleRate);
    const out = envelope(rawL, rawR, sampleRate, 0, checkMs + MAX_LAG_MS);
    lag = bestLag(out, expected);
  }
  const shift = Math.round((lag / 1000) * sampleRate);
  const outL = new Float32Array(outFrames);
  const outR = new Float32Array(outFrames);
  for (let i = 0; i < outFrames; i += 1) {
    const j = i + shift;
    if (j >= 0 && j < done) {
      outL[i] = rawL[j];
      outR[i] = rawR[j];
    }
  }
  self.postMessage({ id, left: outL, right: outR, lagMs: lag }, [outL.buffer, outR.buffer]);
};
