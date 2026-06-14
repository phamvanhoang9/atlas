/**
 * ATLAS automation view — daily AI intelligence settings + run history.
 * Talks to /api/automation/* (REST, D-007).
 */

const AtlasAutomation = (() => {
    const { authHeaders, escapeHtml } = window.AtlasShared;

    let pollTimer = null;

    const el = (id) => document.getElementById(id);

    /* ---------- config */

    const fillForm = (config) => {
        el("autoEnabled").checked = Boolean(config.enabled);
        el("autoTime").value = config.time || "05:00";
        el("autoTimezone").value = config.timezone || "";
        el("autoEmail").value = config.recipient_email || "";
        el("autoTopics").value = (config.topics || []).join("\n");
        el("autoDepth").value = config.depth || "deep";

        const chip = el("emailModeChip");
        if (config.email_mode === "smtp") {
            chip.textContent = "Email delivery: SMTP (real)";
            chip.className = "chip smtp";
        } else {
            chip.textContent = "Email delivery: mock — emails are logged, not sent. Set SMTP_* env vars to enable real delivery.";
            chip.className = "chip mock";
        }
    };

    const setStatus = (message, ok = true) => {
        const status = el("automationStatus");
        status.textContent = message;
        status.className = `form-status ${ok ? "ok" : "err"}`;
        if (message) {
            setTimeout(() => { status.textContent = ""; }, 6000);
        }
    };

    const loadConfig = async () => {
        try {
            const response = await fetch("/api/automation/config", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error("API error");
            fillForm(data.data);
        } catch (error) {
            console.error("Automation config load failed:", error);
            setStatus("Could not load settings from the server.", false);
        }
    };

    const saveConfig = async (event) => {
        event.preventDefault();
        const payload = {
            enabled: el("autoEnabled").checked,
            time: el("autoTime").value,
            timezone: el("autoTimezone").value.trim(),
            recipient_email: el("autoEmail").value.trim(),
            depth: el("autoDepth").value,
            topics: el("autoTopics").value.split("\n").map((t) => t.trim()).filter(Boolean),
        };
        try {
            const response = await fetch("/api/automation/config", {
                method: "PUT",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (response.ok && data.success) {
                fillForm(data.data);
                setStatus("Settings saved.");
            } else {
                const detail = Array.isArray(data.detail)
                    ? data.detail.map((d) => d.msg).join("; ")
                    : (data.detail || "Validation failed");
                setStatus(String(detail), false);
            }
        } catch (error) {
            console.error("Automation config save failed:", error);
            setStatus("Could not save settings — server unreachable.", false);
        }
    };

    /* ---------- runs */

    const formatTime = (isoString) => {
        if (!isoString) return "—";
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return isoString;
        return date.toLocaleString("en-GB", {
            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        });
    };

    const durationOf = (run) => {
        if (!run.started_at || !run.finished_at) return "";
        const ms = new Date(run.finished_at) - new Date(run.started_at);
        if (!Number.isFinite(ms) || ms < 0) return "";
        return `${Math.round(ms / 1000)}s`;
    };

    const renderRuns = (runs) => {
        const list = el("runsList");
        if (!Array.isArray(runs) || runs.length === 0) {
            list.innerHTML = '<p class="empty-note">No runs yet. Enable the schedule or click “Run now”.</p>';
            return;
        }
        list.innerHTML = "";
        runs.slice(0, 12).forEach((run) => {
            const item = document.createElement("div");
            item.className = "run-item";

            const emailChip = run.email_status
                ? `<span class="status-chip ${run.email_status === "sent" ? "success" : "skipped"}">email: ${escapeHtml(run.email_status)}</span>`
                : "";

            item.innerHTML = `
                <div class="run-row1">
                    <span class="run-time">${escapeHtml(formatTime(run.started_at))}</span>
                    <span class="run-chips">
                        <span class="status-chip ${escapeHtml(run.status || "running")}">${escapeHtml(run.status || "running")}</span>
                        ${emailChip}
                    </span>
                </div>
                <div class="run-row2">
                    <span>trigger: ${escapeHtml(run.trigger || "scheduled")}${durationOf(run) ? ` · ${durationOf(run)}` : ""}</span>
                    ${run.history_id ? '<a class="run-link view-report">View report</a>' : ""}
                </div>
                ${run.error ? `<div class="run-error">${escapeHtml(run.error)}</div>` : ""}
            `;

            const link = item.querySelector(".view-report");
            if (link) {
                link.addEventListener("click", async () => {
                    try {
                        const response = await fetch(`/api/history/${run.history_id}`, { headers: authHeaders() });
                        const data = await response.json();
                        if (data.success) window.Atlas.displayStoredReport(data.data);
                    } catch (error) {
                        console.error("Run report load failed:", error);
                    }
                });
            }
            list.appendChild(item);
        });
    };

    const loadRuns = async () => {
        try {
            const response = await fetch("/api/automation/runs?limit=12", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error("API error");
            renderRuns(data.data);
            return data.data;
        } catch (error) {
            console.error("Automation runs load failed:", error);
            el("runsList").innerHTML = '<p class="empty-note">Could not load runs from the server.</p>';
            return [];
        }
    };

    const pollWhileRunning = () => {
        if (pollTimer) clearInterval(pollTimer);
        let ticks = 0;
        pollTimer = setInterval(async () => {
            ticks += 1;
            const runs = await loadRuns();
            const stillRunning = runs.some((run) => run.status === "running");
            if (!stillRunning || ticks > 120) {     // stop after ~10 minutes
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }, 5000);
    };

    const runNow = async () => {
        const button = el("runNow");
        button.disabled = true;
        try {
            const response = await fetch("/api/automation/run", {
                method: "POST",
                headers: authHeaders(),
            });
            const data = await response.json();
            if (response.status === 409) {
                setStatus("A run is already in progress.", false);
            } else if (response.ok && data.success) {
                setStatus("Run started — refreshing status below.");
                await loadRuns();
                pollWhileRunning();
            } else {
                setStatus(String(data.detail || "Could not start the run."), false);
            }
        } catch (error) {
            console.error("Manual run failed:", error);
            setStatus("Could not start the run — server unreachable.", false);
        } finally {
            setTimeout(() => { button.disabled = false; }, 2000);
        }
    };

    /* ---------- init */

    const init = () => {
        el("automationForm").addEventListener("submit", saveConfig);
        el("runNow").addEventListener("click", runNow);
        el("refreshRuns").addEventListener("click", loadRuns);
        loadConfig();
        loadRuns();
    };

    window.AtlasViews.register("automation", init);

    return { reload: () => { loadConfig(); loadRuns(); } };
})();

window.AtlasAutomation = AtlasAutomation;
