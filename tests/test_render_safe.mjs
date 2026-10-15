import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { attr, html } = createRequire(import.meta.url)("../static/renderSafe.js");

test("html escapes markup-sensitive metadata characters", () => {
  assert.equal(html(`A&B <Track> "Mix" 'Dub'`), "A&amp;B &lt;Track&gt; &quot;Mix&quot; &#39;Dub&#39;");
});

test("attr uses the same escaping for quoted data attributes", () => {
  assert.equal(attr(`track"1&2`), "track&quot;1&amp;2");
});

test("nullish values render as empty strings", () => {
  assert.equal(html(null), "");
  assert.equal(attr(undefined), "");
});
