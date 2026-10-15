/**
 * Integrated loudness (LUFS) of a track, per ITU-R BS.1770-4 / EBU R128: K-weighting (a high
 * shelf for the head's effect, then a high-pass), mean square over 400 ms blocks every 100 ms,
 * an absolute gate at -70 LUFS and a relative gate 10 LU under the gated mean. The filters are
 * designed for any sample rate the way libebur128 does it. The Arrange page matches track levels
 * with it; tested via Node.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.Loudness = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  /** Biquad coefficients [b0, b1, b2, a1, a2] of the two K-weighting stages at `rate` (libebur128's design). */
  function kWeighting(rate) {
    let K = Math.tan((Math.PI * 1681.974450955533) / rate);
    let Q = 0.7071752369554196;
    const Vh = Math.pow(10, 3.999843853973347 / 20);
    const Vb = Math.pow(Vh, 0.4996667741545416);
    let a0 = 1 + K / Q + K * K;
    const shelf = [(Vh + (Vb * K) / Q + K * K) / a0, (2 * (K * K - Vh)) / a0, (Vh - (Vb * K) / Q + K * K) / a0, (2 * (K * K - 1)) / a0, (1 - K / Q + K * K) / a0];
    K = Math.tan((Math.PI * 38.13547087602444) / rate);
    Q = 0.5003270373238773;
    a0 = 1 + K / Q + K * K;
    const highPass = [1, -2, 1, (2 * (K * K - 1)) / a0, (1 - K / Q + K * K) / a0];
    return [shelf, highPass];
  }

  /** Sum of K-weighted squares of one channel per 100 ms step (both filters in one pass, no copies). */
  function stepEnergy(samples, rate, step) {
    const [[b0, b1, b2, a1, a2], [c0, c1, c2, d1, d2]] = kWeighting(rate);
    const out = new Float64Array(Math.floor(samples.length / step));
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0, z1 = 0, z2 = 0;
    for (let k = 0, i = 0; k < out.length; k += 1) {
      let sum = 0;
      for (const end = i + step; i < end; i += 1) {
        const x = samples[i];
        const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        const z = c0 * y + c1 * y1 + c2 * y2 - d1 * z1 - d2 * z2;
        x2 = x1; x1 = x; y2 = y1; y1 = y; z2 = z1; z1 = z;
        sum += z * z;
      }
      out[k] = sum;
    }
    return out;
  }

  /** Integrated loudness in LUFS of `channels` (arrays of samples, L and R weighted 1), or -Infinity for silence. */
  function integratedLufs(channels, rate) {
    const step = Math.round(rate / 10);
    const steps = channels.map((c) => stepEnergy(c, rate, step));
    const count = Math.min(...steps.map((s) => s.length)) - 3;
    const blocks = [];
    for (let k = 0; k < count; k += 1) {
      let sum = 0;
      for (const s of steps) sum += (s[k] + s[k + 1] + s[k + 2] + s[k + 3]) / (4 * step);
      blocks.push(sum);
    }
    const lufs = (ms) => -0.691 + 10 * Math.log10(ms);
    const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    const audible = blocks.filter((z) => lufs(z) > -70);
    if (!audible.length) return -Infinity;
    const relative = lufs(mean(audible)) - 10;
    const gated = audible.filter((z) => lufs(z) > relative);
    return lufs(mean(gated));
  }

  return { integratedLufs, kWeighting };
});
