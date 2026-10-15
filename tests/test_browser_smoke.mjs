import assert from "node:assert/strict";
import test from "node:test";

const BASE_URL = process.env.SETA_BASE_URL || "http://127.0.0.1:8765";

async function serverAvailable() {
  try {
    const res = await fetch(`${BASE_URL}/api/library`);
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function localAssetsAvailable() {
  try {
    const res = await fetch(`${BASE_URL}/static/vendor/d3.min.js`, { method: "HEAD" });
    return res.ok;
  } catch (_) {
    return false;
  }
}

test("browser smoke: map, filters, and empty mix-link state", async (t) => {
  if (process.env.SETA_RUN_BROWSER_SMOKE !== "1") {
    t.skip("Set SETA_RUN_BROWSER_SMOKE=1 to run browser smoke coverage");
    return;
  }
  if (!(await serverAvailable())) {
    t.skip(`Seta server is not running at ${BASE_URL}`);
    return;
  }
  if (!(await localAssetsAvailable())) {
    t.skip("Bundled D3 asset is not reachable from the local server");
    return;
  }

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (_) {
    t.skip("Playwright is not available in this environment");
    return;
  }

  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  const pageIssues = [];
  page.on("console", msg => {
    if (["error", "warning"].includes(msg.type())) pageIssues.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on("pageerror", err => pageIssues.push(`pageerror: ${err.message}`));

  await page.goto(BASE_URL, { waitUntil: "load", timeout: 15000 });
  await page.waitForSelector("#graph", { state: "attached" });

  const state = await page.evaluate(async () => {
    const library = await fetch("/api/library").then(res => res.json());
    const hasEdges = Array.isArray(library.edges) && library.edges.length > 0;
    const explore = document.getElementById("layout-explore-btn");
    const note = document.getElementById("mix-links-note");
    return {
      hasEdges,
      title: document.title,
      graphPresent: !!document.getElementById("graph"),
      playerPresent: !!document.getElementById("player-dock"),
      camelotWheelPresent: !!document.querySelector(".camelot-wheel"),
      setZoneClouds: document.querySelectorAll(".moment-cloud").length,
      exploreDisabled: !!explore?.disabled,
      noteVisible: note ? !note.hidden : false,
      helperTextPresent: document.body.innerText.includes("Click a key to filter tracks")
        || document.body.innerText.includes("Click a zone to filter tracks"),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
      draftTabPresent: !!document.getElementById("mix-tab-draft"),
      draftAddBtnPresent: !!document.getElementById("draft-add-btn"),
      draftJsPresent: typeof TrackGraphDraft !== "undefined",
    };
  });

  assert.equal(state.title, "Seta 🍄");
  assert.equal(state.graphPresent, true);
  assert.equal(state.playerPresent, true);
  assert.equal(state.camelotWheelPresent, true);
  assert.ok(state.setZoneClouds > 0);
  assert.equal(state.helperTextPresent, false);
  assert.equal(state.horizontalOverflow, false);
  assert.equal(state.draftTabPresent, true);
  assert.equal(state.draftAddBtnPresent, true);
  assert.equal(state.draftJsPresent, true);
  if (!state.hasEdges) {
    assert.equal(state.exploreDisabled, true);
    assert.equal(state.noteVisible, true);
  }
  assert.deepEqual(pageIssues, []);
});

test("browser smoke: set draft add, persist, export, and draft-only filter", async (t) => {
  if (process.env.SETA_RUN_BROWSER_SMOKE !== "1") {
    t.skip("Set SETA_RUN_BROWSER_SMOKE=1 to run browser smoke coverage");
    return;
  }
  if (!(await serverAvailable())) {
    t.skip(`Seta server is not running at ${BASE_URL}`);
    return;
  }
  if (!(await localAssetsAvailable())) {
    t.skip("Bundled D3 asset is not reachable from the local server");
    return;
  }

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (_) {
    t.skip("Playwright is not available in this environment");
    return;
  }

  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  const pageIssues = [];
  page.on("console", msg => {
    if (msg.type() === "error") pageIssues.push(`error: ${msg.text()}`);
  });
  page.on("pageerror", err => pageIssues.push(`pageerror: ${err.message}`));

  await page.goto(BASE_URL, { waitUntil: "load", timeout: 15000 });
  await page.waitForSelector("#graph", { state: "attached" });

  await page.evaluate(() => {
    localStorage.removeItem("seta-drafts-v1");
    location.reload();
  });
  await page.waitForSelector("#graph", { state: "attached" });

  const trackCount = await page.evaluate(async () => {
    const library = await fetch("/api/library").then(res => res.json());
    return library.tracks?.length || 0;
  });

  if (trackCount < 1) {
    t.skip("Library has no tracks to exercise set draft flow");
    return;
  }

  await page.keyboard.press("d");
  await page.waitForSelector("#mix-dock.is-visible");
  await page.waitForSelector("#draft-pane:not([hidden])");

  await page.evaluate(async () => {
    const library = await fetch("/api/library").then(res => res.json());
    const track = library.tracks[0];
    window.__setaTestTrackId = track.id;
    window.__setaTestTrackTitle = track.title;
  });

  const trackId = await page.evaluate(() => window.__setaTestTrackId);

  await page.evaluate((id) => {
    const store = TrackGraphDraft.loadDraftStore(localStorage);
    const draft = TrackGraphDraft.ensureActiveDraft(store, "Browser test draft");
    draft.name = "Browser test draft";
    TrackGraphDraft.addTrackToDraft(draft, id);
    TrackGraphDraft.setDraftNote(draft, id, "warm opener");
    TrackGraphDraft.toggleFinalInDraft(draft, id);
    TrackGraphDraft.saveDraftStore(localStorage, store);
  }, trackId);

  await page.reload({ waitUntil: "load" });
  await page.waitForSelector("#graph", { state: "attached" });
  await page.waitForFunction(() => (document.getElementById("draft-tab-count")?.textContent || "").includes("1"));
  const draftPanelOpen = await page.evaluate(() => {
    const dock = document.getElementById("mix-dock");
    const pane = document.getElementById("draft-pane");
    return !!dock?.classList.contains("is-visible") && pane?.hidden === false;
  });
  if (!draftPanelOpen) {
    await page.click("#mix-tab-draft");
  }
  await page.waitForSelector("#mix-dock.is-visible");
  await page.waitForSelector("#draft-list .draft-row", { state: "visible" });

  const afterReload = await page.evaluate(() => {
    const store = TrackGraphDraft.loadDraftStore(localStorage);
    const draft = TrackGraphDraft.getActiveDraft(store);
    return {
      count: draft?.trackIds.length || 0,
      name: draft?.name || "",
      hasFinal: (draft?.finalIds || []).length > 0,
      note: draft?.notes?.[draft.trackIds[0]] || "",
      listItems: document.querySelectorAll("#draft-list .draft-row").length,
      rampVisible: document.getElementById("draft-ramp")?.hidden === false,
    };
  });

  assert.equal(afterReload.count, 1);
  assert.equal(afterReload.name, "Browser test draft");
  assert.equal(afterReload.hasFinal, true);
  assert.equal(afterReload.note, "warm opener");
  assert.equal(afterReload.listItems, 1);
  assert.equal(afterReload.rampVisible, true);

  await page.click("#draft-only-chip");
  await page.waitForFunction(() => document.getElementById("draft-only-chip")?.classList.contains("active"));

  const draftOnlyCount = await page.evaluate(async () => {
    const store = TrackGraphDraft.loadDraftStore(localStorage);
    const draft = TrackGraphDraft.getActiveDraft(store);
    const draftIds = new Set(draft?.trackIds || []);
    const library = await fetch("/api/library").then(res => res.json());
    const visibleNodes = document.querySelectorAll(".node.in-draft").length;
    const expected = library.tracks.filter(t => draftIds.has(t.id)).length;
    return { visibleNodes, expected };
  });
  assert.equal(draftOnlyCount.visibleNodes, draftOnlyCount.expected);

  const exportText = await page.evaluate(() => {
    const store = TrackGraphDraft.loadDraftStore(localStorage);
    const draft = TrackGraphDraft.getActiveDraft(store);
    const byId = new Map();
    return fetch("/api/library")
      .then(res => res.json())
      .then(library => {
        for (const track of library.tracks) byId.set(track.id, track);
        return TrackGraphDraft.exportDraftText(draft, byId);
      });
  });
  assert.match(exportText, /★/);
  assert.match(exportText, /warm opener/);

  await page.click("#draft-export-m3u-btn");
  await page.waitForTimeout(300);

  await page.click('[data-draft-remove]');
  await page.waitForFunction(() => {
    const store = TrackGraphDraft.loadDraftStore(localStorage);
    return (TrackGraphDraft.getActiveDraft(store)?.trackIds.length || 0) === 0;
  });

  assert.deepEqual(pageIssues, []);
});
