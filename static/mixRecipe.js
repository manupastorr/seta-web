/**
 * The default way two tracks blend on the Arrange page, counted in bars from B's start
 * (levels are linear band gains, 1 = flat):
 *
 *   One layer at a time, like an onion (values from DJ practice and studies of real mixes):
 *   start   B: highs 66%, mids 13%, lows killed (never two basslines)     A: flat
 *   0       B's fader comes up to 100% first             (2 bars, while the beats lock in)
 *   1       then B mids rise to 66%                      (4 bars)
 *   2       B highs and mids ramp up to 100% while A mids ramp to 50%, A highs to 75%   (8 bars)
 *   3       bass swap on the first phrase start (every 8 bars) after the blend where B has bass
 *           (else the first bar with bass): B lows 100%, A lows killed
 *   out     from the swap (or the blend's end without one) A ramps out over 8 bars
 *   end     then A's fader cuts (or on its last downbeat, if that comes first)
 *
 * Each line is a few key points with smooth ramps between them (`recipeLine`), so it can be edited
 * as a curve; `mixLevels` reads the same lines.
 * The EQ does the blend; the faders only move at the start and the end.
 * A mix shorter than 22 bars squeezes the steps to fit. Tested via Node.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.MixRecipe = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const B_START = { high: 0.66, mid: 0.13, low: 0 };
  const B_RISE_TO = 0.66;
  const A_BLEND = { mid: 0.5, high: 0.75 }; // A's vocals and leads make room for B's
  const A_LOW_AFTER_SWAP = 0;
  const PHRASE_BARS = 8; // the bass swap lands on a phrase start
  const EXIT_BARS = 8; // A ramps out over this many bars after the swap
  const RISE_BARS = 4;
  const BLEND_BARS = 8;
  const FADE_IN_BARS = 2;
  const CUT_BARS = 1 / 8; // A's fader drops over half a beat, so the cut does not click
  const OUT_BARS = 8; // room the exit gets when the mix is squeezed
  const FULL_BARS = FADE_IN_BARS + RISE_BARS + BLEND_BARS + OUT_BARS;


  /** Bar lengths of each step for a mix of `totalBars`, squeezed when it is short. */
  function phases(totalBars) {
    const f = Math.min(1, totalBars / FULL_BARS);
    return { fadeIn: FADE_IN_BARS * f, rise: (FADE_IN_BARS + RISE_BARS) * f, blendEnd: (FADE_IN_BARS + RISE_BARS + BLEND_BARS) * f, out: OUT_BARS * f };
  }

  /** Levels for B (`inc`) and A (`out`) at `bar` bars into the mix. `swapBar` is null when B has no bass in the mix. */
  function mixLevels(bar, totalBars, swapBar) {
    const level = (side) => Object.fromEntries(KEYS.map((key) => [key, valueAt(recipeLine(totalBars, swapBar, side, key), bar)]));
    return { inc: level("inc"), out: level("out") };
  }

  /** Bars where A starts stepping out (end of the blend) and where its fader cuts (its last downbeat). */
  function exitBars(totalBars, swapAt = null) {
    const start = swapAt ?? Math.ceil(phases(totalBars).blendEnd);
    const last = Math.max(start + 1, Math.floor(totalBars));
    return { start, cut: Math.min(last, start + EXIT_BARS) };
  }

  /** The bass swap bar: the first phrase start after the blend where B has bass (`hasLows(bar)`), else the first such bar, else null. */
  function swapBar(totalBars, hasLows) {
    const first = Math.ceil(phases(totalBars).blendEnd);
    const bars = [];
    for (let bar = first; bar < totalBars; bar += 1) bars.push(bar);
    return bars.find((bar) => bar % PHRASE_BARS === 0 && hasLows(bar)) ?? bars.find(hasLows) ?? null;
  }

  /** Linear gain to dB for the Web Audio EQ (a gain of 0 becomes a deep cut). */
  const gainToDb = (gain) => 20 * Math.log10(Math.max(0.001, gain));

  // ---------- editable curves ----------
  // A line is a list of points [{b, v, m?}]: b in bars from B's start, v a linear gain (0–1).
  // Between two points the value follows u^k, where `m` (default 0.5, a straight line) is the
  // value halfway, as a fraction of the way from one point to the next. Two points on the same
  // bar make a step.

  const round = (x) => Math.round(x * 1000) / 1000;
  const shape = (u, m = 0.5) => (m === 0.5 ? u : Math.pow(u, Math.log(m) / Math.log(0.5)));

  /** The value of a line at `bar`; before the first point it holds the first value, after the last the last. */
  function valueAt(points, bar) {
    if (!points.length) return 1;
    for (let i = points.length - 1; i >= 0; i -= 1) {
      const p = points[i];
      if (p.b > bar) continue;
      const q = points[i + 1];
      if (!q) return p.v;
      return p.v + (q.v - p.v) * shape((bar - p.b) / (q.b - p.b), p.m);
    }
    return points[0].v;
  }

  const KEYS = ["volume", "low", "mid", "high"];

  /**
   * The recipe for one line (`side` "inc" or "out", `key` volume/low/mid/high) as a few key points:
   * smooth ramps between them, a step (two points on one bar) only for the bass swap.
   */
  function recipeLine(totalBars, swapAt, side, key) {
    const { fadeIn, rise, blendEnd } = phases(totalBars);
    const { start, cut } = exitBars(totalBars, swapAt ?? null);
    const swap = swapAt === null || swapAt === undefined ? null : swapAt;
    const lines = {
      inc: {
        // sin-shaped fader: halfway through it is at sin(45°) ≈ 71%.
        volume: [{ b: 0, v: 0, m: Math.SQRT1_2 }, { b: fadeIn, v: 1 }],
        mid: [{ b: 0, v: B_START.mid }, { b: fadeIn, v: B_START.mid }, { b: rise, v: B_RISE_TO }, { b: blendEnd, v: 1 }],
        high: [{ b: 0, v: B_START.high }, { b: rise, v: B_START.high }, { b: blendEnd, v: 1 }],
        low: swap === null ? [{ b: 0, v: B_START.low }] : [{ b: 0, v: B_START.low }, { b: swap, v: B_START.low }, { b: swap, v: 1 }],
      },
      out: {
        volume: [{ b: 0, v: 1 }, { b: cut, v: 1 }, { b: cut + CUT_BARS, v: 0 }],
        mid: [{ b: 0, v: 1 }, { b: rise, v: 1 }, { b: blendEnd, v: A_BLEND.mid }, { b: start, v: A_BLEND.mid }, { b: cut, v: 0 }],
        high: [{ b: 0, v: 1 }, { b: rise, v: 1 }, { b: blendEnd, v: A_BLEND.high }, { b: start, v: A_BLEND.high }, { b: cut, v: 0 }],
        low: swap === null
          ? [{ b: 0, v: 1 }, { b: start, v: 1 }, { b: cut, v: 0 }]
          : [{ b: 0, v: 1 }, { b: swap, v: 1 }, { b: swap, v: A_LOW_AFTER_SWAP }],
      },
    };
    const points = lines[side][key].map((p) => ({ ...p, b: round(p.b) }));
    return points.filter((p, i) => !i || p.b !== points[i - 1].b || p.v !== points[i - 1].v);
  }

  /** Bar where a volume line reaches 0 for good (the fader cut), or null when it never does. */
  function silentFrom(points) {
    let from = null;
    for (const p of points) from = p.v <= 0.001 ? from ?? p.b : null;
    return from;
  }

  return { mixLevels, swapBar, exitBars, gainToDb, phases, valueAt, recipeLine, silentFrom, B_START, FULL_BARS };
});
