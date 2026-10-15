/**
 * Draws Rekordbox's color waveform preview (PWV4) and hot cue badges, the way Rekordbox's
 * Preview column does. Column math follows Beat Link's WaveformPreview.segmentHeight /
 * segmentColor. Pure helpers are tested via Node; `draw` needs a canvas.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.RbWaveform = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const ENTRY_BYTES = 6;
  // Rekordbox's default hot cue colors when a cue has no custom color.
  const HOT_CUE_COLORS = { A: "#e8336c", B: "#3fa9f5", C: "#7bd148" };
  const DEFAULT_HOT_CUE_COLOR = "#7bd148";
  const BADGE = 11;

  function decode(base64) {
    if (typeof atob === "function") {
      const raw = atob(base64);
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
      return bytes;
    }
    return new Uint8Array(Buffer.from(base64, "base64"));
  }

  /** One entry per column: back (dim, wider) and front (bright) heights and RGB colors. */
  function columns(bytes) {
    const out = [];
    for (let base = 0; base + ENTRY_BYTES <= bytes.length; base += ENTRY_BYTES) {
      const red = bytes[base + 3];
      const green = bytes[base + 4];
      const blue = bytes[base + 5];
      const back = Math.max(red, green, blue);
      const tint = (level) =>
        back === 0 ? [0, 0, 0] : [red, green, blue].map((v) => Math.floor((v * level) / back));
      out.push({ back, front: blue, backColor: tint(191), frontColor: tint(255) });
    }
    return out;
  }

  function maxHeight(cols) {
    return cols.reduce((max, col) => Math.max(max, col.back), 1);
  }

  function hotCueColor(letter) {
    return HOT_CUE_COLORS[letter] || DEFAULT_HOT_CUE_COLOR;
  }

  /** Column index range [from, to) shown at canvas x, for a time window inside the track. */
  function columnRange(x, width, count, durationMs, startMs, endMs) {
    const t0 = startMs + ((endMs - startMs) * x) / width;
    const t1 = startMs + ((endMs - startMs) * (x + 1)) / width;
    return columnsBetween(t0, t1, count, durationMs);
  }

  function columnsBetween(t0, t1, count, durationMs) {
    const from = Math.max(0, Math.min(count - 1, Math.floor((t0 / durationMs) * count)));
    const to = Math.max(from + 1, Math.min(count, Math.ceil((t1 / durationMs) * count)));
    return [from, to];
  }

  /**
   * Paint a waveform into a rectangle of a 2D context (CSS pixels). Options pick a time window
   * (startMs/endMs, default the whole track) and whether hot cue badges show. For a track whose
   * tempo changes along the rectangle, `timeAt(fraction)` gives the track ms at a fraction of the
   * width and `fractionAt(ms)` the inverse; the default is a straight line from startMs to endMs.
   */
  function paint(ctx, wave, rect, options = {}) {
    const cols = wave._cols || (wave._cols = columns(decode(wave.preview)));
    const top = maxHeight(cols);
    const duration = wave.duration_ms || 1;
    const startMs = options.startMs ?? 0;
    const endMs = options.endMs ?? duration;
    const timeAt = options.timeAt || ((f) => startMs + (endMs - startMs) * f);
    const fractionAt = options.fractionAt || ((ms) => (ms - startMs) / (endMs - startMs));
    const showCues = options.cues !== false;
    const badgeRoom = showCues ? BADGE + 2 : 0;
    const scale = (rect.h - badgeRoom) / top;
    const width = Math.max(1, Math.floor(rect.w));
    const bottom = rect.y + rect.h;

    for (let x = 0; x < width; x += 1) {
      const [from, to] = columnsBetween(timeAt(x / width), timeAt((x + 1) / width), cols.length, duration);
      let pick = cols[from];
      for (let i = from + 1; i < to; i += 1) if (cols[i].back > pick.back) pick = cols[i];
      for (const [height, color] of [
        [pick.back, pick.backColor],
        [pick.front, pick.frontColor],
      ]) {
        if (!height) continue;
        ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
        ctx.fillRect(rect.x + x, bottom - height * scale, 1, height * scale);
      }
    }

    if (!showCues) return;
    ctx.font = `bold ${BADGE - 2}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const cue of wave.cues || []) {
      if (!cue.hot || cue.ms < startMs || cue.ms > endMs) continue;
      const x = rect.x + fractionAt(cue.ms) * rect.w;
      const left = Math.min(Math.max(rect.x, x - BADGE / 2), rect.x + rect.w - BADGE);
      ctx.fillStyle = hotCueColor(cue.hot);
      ctx.fillRect(left, rect.y + 1, BADGE, BADGE);
      ctx.fillStyle = "#111";
      ctx.fillText(cue.hot, left + BADGE / 2, rect.y + 1 + BADGE / 2 + 0.5);
    }
  }

  /** Size a canvas to its CSS box (sharp on retina) and return its context, cleared. */
  function prepare(canvas) {
    const ratio = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    const width = canvas.clientWidth || canvas.width;
    const height = canvas.clientHeight || canvas.height;
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    return { ctx, width, height };
  }

  /** Draw a whole waveform (or a time window of it) into a canvas. */
  function draw(canvas, wave, options = {}) {
    const { ctx, width, height } = prepare(canvas);
    if (wave) paint(ctx, wave, { x: 0, y: 0, w: width, h: height }, options);
  }

  /**
   * Average strength of one band (low, mid or high) between two times, 0 to 1 against the
   * track's loudest column of that band. PWV4 bytes 3, 4, 5 carry low, mid and high energy.
   */
  function bandLevel(wave, startMs, endMs, band) {
    const offset = { low: 3, mid: 4, high: 5 }[band];
    const bytes = wave._bytes || (wave._bytes = decode(wave.preview));
    const count = Math.floor(bytes.length / ENTRY_BYTES);
    if (!count) return 0;
    wave._bandMax = wave._bandMax || {};
    if (wave._bandMax[band] === undefined) {
      let max = 1;
      for (let i = 0; i < count; i += 1) max = Math.max(max, bytes[i * ENTRY_BYTES + offset]);
      wave._bandMax[band] = max;
    }
    const duration = wave.duration_ms || 1;
    const from = Math.max(0, Math.min(count - 1, Math.floor((startMs / duration) * count)));
    const to = Math.max(from + 1, Math.min(count, Math.ceil((endMs / duration) * count)));
    let sum = 0;
    for (let i = from; i < to; i += 1) sum += bytes[i * ENTRY_BYTES + offset];
    return sum / (to - from) / wave._bandMax[band];
  }

  return { decode, columns, maxHeight, hotCueColor, columnRange, bandLevel, paint, prepare, draw, HOT_CUE_COLORS };
});
