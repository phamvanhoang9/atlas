"use strict";
// Pure-logic tests for the highlight-to-explain feature (frontend/highlight_explain.js).
// No DOM/browser dependency - run with `node --test tests/frontend/`.

const test = require("node:test");
const assert = require("node:assert/strict");
const {
    isLongEnough,
    truncatePassage,
    extractContext,
    computeButtonPosition,
    isSameContainer,
} = require("../../frontend/highlight_explain.js");

// --------------------------------------------------------------- isLongEnough

test("isLongEnough: rejects an empty string", () => {
    assert.equal(isLongEnough(""), false);
});

test("isLongEnough: rejects a whitespace-only string", () => {
    assert.equal(isLongEnough("   "), false);
});

test("isLongEnough: rejects text shorter than the default minimum", () => {
    assert.equal(isLongEnough("ab"), false);
});

test("isLongEnough: accepts text at the default minimum", () => {
    assert.equal(isLongEnough("abc"), true);
});

test("isLongEnough: trims surrounding whitespace before measuring", () => {
    assert.equal(isLongEnough("  abc  "), true);
});

test("isLongEnough: honors a custom minChars", () => {
    assert.equal(isLongEnough("ab", 1), true);
});

// -------------------------------------------------------------- truncatePassage

test("truncatePassage: leaves short text unchanged", () => {
    assert.equal(truncatePassage("short"), "short");
});

test("truncatePassage: caps text at the default 4000 chars", () => {
    const result = truncatePassage("a".repeat(5000));
    assert.equal(result.length, 4000);
});

test("truncatePassage: honors a custom maxChars", () => {
    assert.equal(truncatePassage("aaaaaaaaaa", 5), "aaaaa");
});

// --------------------------------------------------------------- extractContext

test("extractContext: returns empty when the block is exactly the highlight", () => {
    assert.equal(extractContext("Hello world", "Hello world"), "");
});

test("extractContext: returns empty for a falsy block", () => {
    assert.equal(extractContext("", "abc"), "");
});

test("extractContext: returns the trimmed block when it adds real context", () => {
    assert.equal(
        extractContext("The quick brown fox jumps.", "quick brown"),
        "The quick brown fox jumps."
    );
});

test("extractContext: ignores surrounding whitespace when comparing to the highlight", () => {
    assert.equal(extractContext("  Hello world  ", "Hello world"), "");
});

test("extractContext: truncates a long block to maxChars", () => {
    const result = extractContext("a".repeat(2000), "hi", 1000);
    assert.equal(result.length, 1000);
});

// ---------------------------------------------------------- computeButtonPosition

test("computeButtonPosition: centers the button above the selection when there's room", () => {
    const pos = computeButtonPosition({
        rect: { left: 100, right: 300, top: 200, bottom: 220, width: 200 },
        btnWidth: 80,
        btnHeight: 32,
        viewportWidth: 1280,
        viewportHeight: 800,
    });
    assert.equal(pos.left, 100 + (200 - 80) / 2);
    assert.equal(pos.top, 200 - 32 - 8);
});

test("computeButtonPosition: flips below the selection when there's no room above", () => {
    const pos = computeButtonPosition({
        rect: { left: 100, right: 300, top: 10, bottom: 30, width: 200 },
        btnWidth: 80,
        btnHeight: 32,
        viewportWidth: 1280,
        viewportHeight: 800,
    });
    assert.equal(pos.top, 30 + 8);
});

test("computeButtonPosition: clamps left so the button never goes past the left edge", () => {
    const pos = computeButtonPosition({
        rect: { left: 0, right: 20, top: 200, bottom: 220, width: 20 },
        btnWidth: 80,
        btnHeight: 32,
        viewportWidth: 1280,
        viewportHeight: 800,
    });
    assert.equal(pos.left, 8);
});

test("computeButtonPosition: clamps left so the button never goes past the right edge", () => {
    const pos = computeButtonPosition({
        rect: { left: 1250, right: 1270, top: 200, bottom: 220, width: 20 },
        btnWidth: 80,
        btnHeight: 32,
        viewportWidth: 1280,
        viewportHeight: 800,
    });
    assert.equal(pos.left, 1280 - 80 - 8);
});

// -------------------------------------------------------------- isSameContainer

test("isSameContainer: rejects two nulls", () => {
    assert.equal(isSameContainer(null, null), false);
});

test("isSameContainer: rejects null vs. an object", () => {
    assert.equal(isSameContainer(undefined, {}), false);
});

test("isSameContainer: accepts the same reference", () => {
    const node = { id: "answer-report-1" };
    assert.equal(isSameContainer(node, node), true);
});

test("isSameContainer: rejects two different references", () => {
    assert.equal(isSameContainer({ id: "a" }, { id: "b" }), false);
});
