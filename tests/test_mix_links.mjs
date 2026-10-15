import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { layoutWithMixEdges, libraryHasMixEdges } = createRequire(import.meta.url)(
  "../static/mixLinks.js"
);

test("libraryHasMixEdges is false when edges are missing or empty", () => {
  assert.equal(libraryHasMixEdges(null), false);
  assert.equal(libraryHasMixEdges({}), false);
  assert.equal(libraryHasMixEdges({ edges: null }), false);
  assert.equal(libraryHasMixEdges({ edges: [] }), false);
});

test("libraryHasMixEdges is true when edges exist", () => {
  assert.equal(
    libraryHasMixEdges({ edges: [{ source: "a", target: "b", score: 0.9 }] }),
    true
  );
});

test("layoutWithMixEdges keeps mix map and drops explore without edges", () => {
  assert.equal(layoutWithMixEdges("mix", false), "mix");
  assert.equal(layoutWithMixEdges("mix", true), "mix");
  assert.equal(layoutWithMixEdges("explore", true), "explore");
  assert.equal(layoutWithMixEdges("explore", false), "mix");
});
