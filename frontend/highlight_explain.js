"use strict";
/* -------------------------------------------------- Explain-by-highlight */
// Bôi đen 1 đoạn trong report -> nút Explain nổi gần vùng chọn -> mở side
// panel (AtlasPanel.openExplain). Thay thế nút Explain gắn theo từng
// citation trong Sources list (đã xoá). Chỉ kích hoạt bên trong
// `.answer-report` (live turn LẪN report mở lại từ History, vì cả hai dùng
// chung class này qua renderInto/displayStoredReport/displayStoredSession).
//
// File này tách khỏi scripts.js để phần logic thuần (không đụng DOM) có
// thể unit-test bằng `node --test`, không cần thêm dependency nào
// (tests/frontend/test_highlight_explain_logic.js).

(function (root, factory) {
    if (typeof module !== "undefined" && module.exports) {
        module.exports = factory();
    } else {
        root.AtlasHighlightExplainLogic = factory();
    }
})(typeof window !== "undefined" ? window : globalThis, function () {
    const MIN_HIGHLIGHT_CHARS = 3;
    const MAX_PASSAGE_CHARS = 4000; // khớp ExplainRequest.passage max_length backend
    const MAX_CONTEXT_CHARS = 1000;
    const BUTTON_MARGIN = 8;

    const isLongEnough = (text, minChars) => {
        const min = minChars == null ? MIN_HIGHLIGHT_CHARS : minChars;
        return (text || "").trim().length >= min;
    };

    const truncatePassage = (text, maxChars) => {
        const max = maxChars == null ? MAX_PASSAGE_CHARS : maxChars;
        return (text || "").slice(0, max);
    };

    const extractContext = (blockText, highlightedText, maxChars) => {
        const max = maxChars == null ? MAX_CONTEXT_CHARS : maxChars;
        const trimmedBlock = (blockText || "").trim();
        const trimmedHighlight = (highlightedText || "").trim();
        if (!trimmedBlock || trimmedBlock === trimmedHighlight) return "";
        return trimmedBlock.slice(0, max);
    };

    const computeButtonPosition = ({ rect, btnWidth, btnHeight, viewportWidth, viewportHeight, margin }) => {
        const m = margin == null ? BUTTON_MARGIN : margin;
        let top = rect.top - btnHeight - m;
        if (top < m) top = rect.bottom + m;
        if (top + btnHeight > viewportHeight - m) top = Math.max(m, rect.top - btnHeight - m);

        let left = rect.left + (rect.width - btnWidth) / 2;
        left = Math.min(left, viewportWidth - btnWidth - m);
        left = Math.max(left, m);

        return { left, top };
    };

    const isSameContainer = (a, b) => a != null && a === b;

    return { isLongEnough, truncatePassage, extractContext, computeButtonPosition, isSameContainer };
});

/* -------------------------------------------------- DOM wiring (browser only) */
// Thin glue around the pure functions above - no unit-test surface without a
// real DOM, verified live in the browser instead (per verification_workflow).
// Mobile/touch: cố ý bỏ qua (không bind touchend/long-press) - toàn bộ UI
// ATLAS hiện đã desktop-first (composer dropdown, hover badge), chưa có hạ
// tầng test touch trong repo. Giới hạn đã biết, không phải bỏ sót.

if (typeof document !== "undefined") {
    const AtlasHighlightExplain = (() => {
        const logic = window.AtlasHighlightExplainLogic;
        const BLOCK_SELECTOR = "p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th";

        let captured = null; // { text, context } captured at mouseup time - a
        // click on the button clears the live selection before its own click
        // handler runs, so getSelection() can't be re-read at click time.

        const btn = () => document.getElementById("highlightExplainBtn");

        const hide = () => {
            const b = btn();
            if (b) b.classList.add("is-hidden");
            captured = null;
        };

        // Walk up from the selection's start node looking for the nearest
        // block-level ancestor, but never past `container` (.answer-report) -
        // guarantees the extracted context can't leak content from outside
        // the report (e.g. a sibling turn, the composer).
        const findContextBlock = (node, container) => {
            let el = node.nodeType === 1 ? node : node.parentElement;
            while (el && el !== container) {
                if (el.matches && el.matches(BLOCK_SELECTOR)) return el;
                el = el.parentElement;
            }
            return container;
        };

        const showButtonFor = (range, text, context) => {
            captured = { text: logic.truncatePassage(text.trim()), context };

            const b = btn();
            b.classList.remove("is-hidden");
            // Đo sau khi unhide để getBoundingClientRect phản ánh kích thước
            // thật, giống pattern của AtlasTrustPopover.open().
            const rect = range.getBoundingClientRect();
            const btnRect = b.getBoundingClientRect();
            const pos = logic.computeButtonPosition({
                rect,
                btnWidth: btnRect.width,
                btnHeight: btnRect.height,
                viewportWidth: window.innerWidth,
                viewportHeight: window.innerHeight,
            });
            b.style.left = `${pos.left}px`;
            b.style.top = `${pos.top}px`;
        };

        const handleMouseUp = (event) => {
            if (event.target.closest && event.target.closest("#highlightExplainBtn")) return;

            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0 || selection.isCollapsed) { hide(); return; }

            const text = selection.toString();
            if (!logic.isLongEnough(text)) { hide(); return; }

            const anchorEl = selection.anchorNode.nodeType === 1 ? selection.anchorNode : selection.anchorNode.parentElement;
            const focusEl = selection.focusNode.nodeType === 1 ? selection.focusNode : selection.focusNode.parentElement;
            const anchorContainer = anchorEl ? anchorEl.closest(".answer-report") : null;
            const focusContainer = focusEl ? focusEl.closest(".answer-report") : null;
            if (!logic.isSameContainer(anchorContainer, focusContainer)) { hide(); return; }

            const range = selection.getRangeAt(0);
            const blockEl = findContextBlock(range.startContainer, anchorContainer);
            const context = logic.extractContext(blockEl.innerText, text);
            showButtonFor(range, text, context);
        };

        const handleClick = () => {
            if (!captured) return;
            const { text, context } = captured;
            hide();
            if (window.AtlasPanel) window.AtlasPanel.openExplain(text, context);
        };

        // mousedown-elsewhere (not selectionchange) is the hide trigger: a
        // mousedown on the button itself would collapse the live selection
        // and fire selectionchange before the button's own click handler
        // runs, which would hide (and risk losing) the button mid-click.
        const handleMouseDown = (event) => {
            if (event.target.closest && event.target.closest("#highlightExplainBtn")) return;
            hide();
        };

        const init = () => {
            const b = btn();
            if (!b) return;
            b.addEventListener("click", handleClick);
            document.addEventListener("mouseup", handleMouseUp);
            document.addEventListener("mousedown", handleMouseDown);
            document.addEventListener("scroll", hide, true);
            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape") hide();
            });
        };

        document.addEventListener("DOMContentLoaded", init);
        return { hide };
    })();
    window.AtlasHighlightExplain = AtlasHighlightExplain;
}
