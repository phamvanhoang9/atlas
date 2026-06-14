/**
 * ATLAS history view — chat reports and daily intelligence reports.
 * Talks to /api/history*; opens stored entries in the Research view.
 */

const AtlasHistory = (() => {
    const { authHeaders, withAuthToken, escapeHtml, timeAgo } = window.AtlasShared;

    let allEntries = [];
    let kindFilter = "";       // "" | "chat" | "daily"
    let searchTerm = "";
    let currentHistoryId = null;
    let loaded = false;

    const el = (id) => document.getElementById(id);

    const MODE_LABELS = {
        quick: "Quick Answer", research: "Research", deep: "Deep Research",
        "hỏi đáp": "Quick Answer", "đề xuất bài báo": "Research", "phân tích": "Deep Research",
    };
    const MODE_CLASSES = {
        quick: "quick", research: "research", deep: "deep",
        "hỏi đáp": "quick", "đề xuất bài báo": "research", "phân tích": "deep",
    };

    /* ---------- data */

    const loadHistory = async () => {
        const list = el("historyList");
        list.innerHTML = '<div class="empty-note loading-note">Loading history…</div>';
        try {
            const response = await fetch("/api/history?limit=200", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error(data.error || "API error");
            allEntries = data.data || [];
            loaded = true;
            render();
        } catch (error) {
            console.error("History load failed:", error);
            list.innerHTML =
                '<div class="history-empty">Could not load history. Check the server logs and refresh.</div>';
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
            const message = allEntries.length === 0
                ? "No reports yet. Run a research query or enable the daily automation."
                : "Nothing matches the current filter.";
            list.innerHTML = `<div class="history-empty">${escapeHtml(message)}</div>`;
            return;
        }

        list.innerHTML = "";
        entries.forEach((entry) => {
            const kind = entry.kind || "chat";
            const card = document.createElement("div");
            card.className = "history-item";
            card.dataset.id = entry.id;

            const badgeClass = kind === "daily_report" ? "daily" : (MODE_CLASSES[entry.mode] || "research");
            const badgeText = kind === "daily_report" ? "Daily Intelligence" : (MODE_LABELS[entry.mode] || entry.mode || "Report");

            card.innerHTML = `
                <div class="history-item-head">
                    <span class="mode-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
                </div>
                <div class="history-item-query">${escapeHtml(entry.query || "(untitled)")}</div>
                <div class="history-item-preview">${escapeHtml(entry.preview || "")}</div>
                <div class="history-item-foot">
                    <span class="history-item-time">${escapeHtml(timeAgo(entry.timestamp))}</span>
                    <button class="icon-btn history-delete" title="Delete entry" type="button">Delete</button>
                </div>
            `;

            card.addEventListener("click", (event) => {
                if (event.target.closest(".history-delete")) return;
                openEntry(entry.id);
            });
            card.querySelector(".history-delete").addEventListener("click", (event) => {
                event.stopPropagation();
                deleteEntry(entry.id);
            });

            list.appendChild(card);
        });
    };

    /* ---------- actions */

    const openEntry = async (entryId) => {
        try {
            const response = await fetch(`/api/history/${entryId}`, { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error(data.error || "API error");
            window.Atlas.displayStoredReport(data.data);
        } catch (error) {
            console.error("History entry load failed:", error);
            window.alert("Could not load this history entry.");
        }
    };

    const deleteEntry = async (entryId) => {
        if (!window.confirm("Delete this report from history?")) return;
        try {
            const response = await fetch(`/api/history/${entryId}`, {
                method: "DELETE",
                headers: authHeaders(),
            });
            const data = await response.json();
            if (data.success) {
                allEntries = allEntries.filter((entry) => entry.id !== entryId);
                render();
            } else {
                window.alert("Could not delete the entry.");
            }
        } catch (error) {
            console.error("History delete failed:", error);
            window.alert("Could not delete the entry.");
        }
    };

    const clearAll = async () => {
        if (!window.confirm("Delete ALL history? This cannot be undone.")) return;
        try {
            const response = await fetch("/api/history", { method: "DELETE", headers: authHeaders() });
            const data = await response.json();
            if (data.success) {
                allEntries = [];
                render();
            } else {
                window.alert("Could not clear history.");
            }
        } catch (error) {
            console.error("History clear failed:", error);
            window.alert("Could not clear history.");
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

        loadHistory();
    };

    // Register with the router: init on first open, refresh on later opens.
    window.AtlasViews.register("history", init);

    return {
        setCurrentHistoryId: (id) => { currentHistoryId = id; loaded = false; },
        getCurrentHistoryId: () => currentHistoryId,
        reload: loadHistory,
    };
})();

window.AtlasHistory = AtlasHistory;
