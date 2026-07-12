/**
 * ATLAS history view — chat reports and daily intelligence reports.
 * Talks to /api/history*; opens stored entries in the Research view.
 */

const AtlasHistory = (() => {
    const { authHeaders, withAuthToken, escapeHtml, timeAgo } = window.AtlasShared;
    const t = (k, v) => AtlasI18n.t(k, v);

    let allEntries = [];
    let kindFilter = "";       // "" | "chat" | "daily_report"
    let searchTerm = "";
    let currentHistoryId = null;
    let loaded = false;

    const el = (id) => document.getElementById(id);

    const MODE_LABEL_KEYS = {
        ask: "mode.ask", compare: "mode.compare", deep_dive: "mode.deep_dive",
    };
    const MODE_CLASSES = {
        ask: "ask", compare: "compare", deep_dive: "deep_dive",
    };

    /* ---------- data */

    const loadHistory = async () => {
        const list = el("historyList");
        list.innerHTML = `<div class="empty-note loading-note">${escapeHtml(t("hist.loading"))}</div>`;
        try {
            const response = await fetch("/api/history?limit=200", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error(data.error || "API error");
            allEntries = data.data || [];
            loaded = true;
            render();
        } catch (error) {
            console.error("History load failed:", error);
            list.innerHTML = `<div class="history-empty">${escapeHtml(t("hist.loadError"))}</div>`;
            if (window.AtlasToast) AtlasToast.error(t("hist.loadError"));
        }
    };

    const visibleEntries = () => allEntries.filter((entry) => {
        const kind = entry.kind || "chat";
        if (kindFilter && kind !== kindFilter) return false;
        if (searchTerm) {
            const haystack = `${entry.query || ""} ${entry.preview || ""}`.toLowerCase();
            if (!haystack.includes(searchTerm)) return false;
        }
        return true;
    });

    /* ---------- rendering */

    const render = () => {
        const list = el("historyList");
        const entries = visibleEntries();

        if (entries.length === 0) {
            const message = allEntries.length === 0 ? t("hist.empty") : t("hist.noMatch");
            list.innerHTML = `<div class="history-empty">${escapeHtml(message)}</div>`;
            return;
        }

        // Group entries by session_id; empty session_id = standalone (its own group).
        const groups = [];
        const bySession = {};
        entries.forEach((entry) => {
            const sid = entry.session_id;
            if (sid) {
                if (!bySession[sid]) { bySession[sid] = { sessionId: sid, entries: [] }; groups.push(bySession[sid]); }
                bySession[sid].entries.push(entry);
            } else {
                groups.push({ sessionId: null, entries: [entry] });
            }
        });

        list.innerHTML = "";
        groups.forEach((group) => {
            // entries arrive newest-first; oldest is the first question of the conversation.
            const ordered = group.entries.slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            const latest = group.entries[0];
            const oldest = ordered[0];
            const kind = latest.kind || "chat";
            const count = group.entries.length;

            const card = document.createElement("div");
            card.className = "history-item";

            const badgeClass = kind === "daily_report" ? "daily" : (MODE_CLASSES[latest.mode] || "compare");
            const badgeText = kind === "daily_report"
                ? t("badge.daily")
                : t(MODE_LABEL_KEYS[latest.mode] || "mode.compare");
            const countChip = (group.sessionId && count > 1)
                ? `<span class="count-chip">${escapeHtml(t("session.turns", { n: count }))}</span>`
                : "";

            card.innerHTML = `
                <div class="history-item-head">
                    <span class="mode-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
                    ${countChip}
                </div>
                <div class="history-item-query">${escapeHtml(oldest.query || "(untitled)")}</div>
                <div class="history-item-preview">${escapeHtml(latest.preview || "")}</div>
                <div class="history-item-foot">
                    <span class="history-item-time">${escapeHtml(timeAgo(latest.timestamp))}</span>
                    <button class="icon-btn history-delete" title="${escapeHtml(t("hist.delete"))}" type="button">${escapeHtml(t("hist.delete"))}</button>
                </div>
            `;

            card.addEventListener("click", (event) => {
                if (event.target.closest(".history-delete")) return;
                if (group.sessionId) window.Atlas.displayStoredSession(ordered);
                else window.Atlas.displayStoredReport(latest);
            });
            card.querySelector(".history-delete").addEventListener("click", (event) => {
                event.stopPropagation();
                deleteGroup(group);
            });

            list.appendChild(card);
        });
    };

    /* ---------- actions */

    const deleteGroup = async (group) => {
        if (!window.confirm(t("hist.deleteConfirm"))) return;
        try {
            for (const entry of group.entries) {
                await fetch(`/api/history/${entry.id}`, { method: "DELETE", headers: authHeaders() });
            }
            const ids = new Set(group.entries.map((entry) => entry.id));
            allEntries = allEntries.filter((entry) => !ids.has(entry.id));
            render();
        } catch (error) {
            console.error("History delete failed:", error);
            if (window.AtlasToast) AtlasToast.error(t("hist.deleteError"));
        }
    };

    const clearAll = async () => {
        if (!window.confirm(t("hist.clearConfirm"))) return;
        try {
            const response = await fetch("/api/history", { method: "DELETE", headers: authHeaders() });
            const data = await response.json();
            if (data.success) {
                allEntries = [];
                render();
                // Clearing history also clears automation runs server-side; refresh that view too.
                if (window.AtlasAutomation && typeof window.AtlasAutomation.reloadRuns === "function") {
                    window.AtlasAutomation.reloadRuns();
                }
            } else if (window.AtlasToast) {
                AtlasToast.error(t("hist.clearError"));
            }
        } catch (error) {
            console.error("History clear failed:", error);
            if (window.AtlasToast) AtlasToast.error(t("hist.clearError"));
        }
    };

    const exportHistory = () => {
        window.open(withAuthToken("/api/history/export"), "_blank");
    };

    /* ---------- init */

    const init = () => {
        el("historySearch").addEventListener("input", (event) => {
            searchTerm = event.target.value.trim().toLowerCase();
            if (loaded) render();
        });

        document.querySelectorAll(".filter-tab").forEach((tab) => {
            tab.addEventListener("click", () => {
                document.querySelectorAll(".filter-tab").forEach((other) =>
                    other.classList.toggle("active", other === tab));
                kindFilter = tab.dataset.kind || "";
                if (loaded) render();
            });
        });

        el("exportHistory").addEventListener("click", exportHistory);
        el("clearHistory").addEventListener("click", clearAll);

        document.addEventListener("atlas:langchange", () => { if (loaded) render(); });

        loadHistory();
    };

    // init on first open; reload on every later open so the current session shows immediately.
    window.AtlasViews.register("history", init, loadHistory);

    return {
        setCurrentHistoryId: (id) => { currentHistoryId = id; loaded = false; },
        getCurrentHistoryId: () => currentHistoryId,
        reload: loadHistory,
    };
})();

window.AtlasHistory = AtlasHistory;
