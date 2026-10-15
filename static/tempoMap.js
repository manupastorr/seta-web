/**
 * Tempo map for one track in a beat-matched set (used by the Arrange page, tested via Node).
 *
 * A track enters at the outgoing track's tempo (`startRate` = outgoing BPM / own BPM) and holds
 * it for `holdMs` of set time while the two overlap, then glides linearly back to its own tempo
 * (rate 1) over `glideMs`, and plays at rate 1 after that. `audioAt` maps set time inside the
 * track to milliseconds of its audio; `setTimeAt` is the inverse. Rate 1 everywhere is a plain,
 * unsynced track.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TempoMap = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function tempoMap({ audioMs, startRate = 1, holdMs = 0, glideMs = 0 }) {
    const r0 = startRate > 0 ? startRate : 1;
    const hold = Math.max(0, holdMs);
    const glide = r0 === 1 ? 0 : Math.max(0, glideMs);
    const holdAudio = r0 * hold;
    const glideAudio = (glide * (r0 + 1)) / 2;
    // In the glide, audio(u) = r0*u + k*u^2 with u = time since the glide began.
    const k = glide ? (1 - r0) / (2 * glide) : 0;

    function rateAt(t) {
      if (t <= hold) return r0;
      if (t <= hold + glide) return r0 + ((1 - r0) * (t - hold)) / glide;
      return 1;
    }

    function audioAt(t) {
      if (t <= 0) return 0;
      if (t <= hold) return r0 * t;
      if (t <= hold + glide) {
        const u = t - hold;
        return holdAudio + r0 * u + k * u * u;
      }
      return holdAudio + glideAudio + (t - hold - glide);
    }

    function setTimeAt(a) {
      if (a <= 0) return 0;
      if (a <= holdAudio) return a / r0;
      if (a <= holdAudio + glideAudio) {
        const rest = a - holdAudio;
        const u = Math.abs(k) < 1e-12 ? rest / r0 : (-r0 + Math.sqrt(r0 * r0 + 4 * k * rest)) / (2 * k);
        return hold + u;
      }
      return hold + glide + (a - holdAudio - glideAudio);
    }

    return { rateAt, audioAt, setTimeAt, duration: setTimeAt(audioMs), endRate: rateAt(setTimeAt(audioMs)) };
  }

  /** The downbeat (in set time) nearest to `target`, given downbeats in audio ms. */
  function nearestDownbeat(downbeatsMs, inMs, map, start, target) {
    let best = target;
    let bestDist = Infinity;
    for (const d of downbeatsMs) {
      if (d < inMs) continue;
      const t = start + map.setTimeAt(d - inMs);
      const dist = Math.abs(t - target);
      if (dist < bestDist) {
        best = t;
        bestDist = dist;
      } else if (t > target) {
        break;
      }
    }
    return best;
  }

  /** First downbeat at or after `ms`, or `ms` when the track has no beat grid. */
  function downbeatFrom(downbeatsMs, ms) {
    for (const d of downbeatsMs || []) if (d >= ms) return d;
    return ms;
  }

  /**
   * Fractional beat number at `ms` on a beat grid (beat 0 = the grid's first beat). Beyond the
   * grid's ends it continues at the nearest beat length.
   */
  function beatAt(beats, ms) {
    const n = beats.length;
    if (n < 2) return 0;
    if (ms <= beats[0]) return (ms - beats[0]) / (beats[1] - beats[0]);
    if (ms >= beats[n - 1]) return n - 1 + (ms - beats[n - 1]) / (beats[n - 1] - beats[n - 2]);
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (beats[mid] <= ms) lo = mid;
      else hi = mid;
    }
    return lo + (ms - beats[lo]) / (beats[hi] - beats[lo]);
  }

  /** The time (ms) of fractional beat `beat` on a beat grid; the inverse of beatAt. */
  function timeAtBeat(beats, beat) {
    const n = beats.length;
    if (n < 2) return 0;
    if (beat <= 0) return beats[0] + beat * (beats[1] - beats[0]);
    if (beat >= n - 1) return beats[n - 1] + (beat - (n - 1)) * (beats[n - 1] - beats[n - 2]);
    const i = Math.floor(beat);
    return beats[i] + (beat - i) * (beats[i + 1] - beats[i]);
  }

  return { tempoMap, nearestDownbeat, downbeatFrom, beatAt, timeAtBeat };
});
