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
