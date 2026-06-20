/**
 * ATLAS automation view — daily AI intelligence settings + run history.
 * Talks to /api/automation/* (REST, D-007).
 */

const AtlasAutomation = (() => {
    const { authHeaders, escapeHtml, locale } = window.AtlasShared;
    const t = (k, v) => AtlasI18n.t(k, v);

    let pollTimer = null;
    let lastRuns = null;
    let lastEmailMode = null;

    const el = (id) => document.getElementById(id);

    /* ---------- config */

    const applyEmailChip = () => {
        const chip = el("emailModeChip");
        if (!chip || !lastEmailMode) return;
        if (lastEmailMode === "smtp") {
            chip.textContent = t("auto.email.smtp");
            chip.className = "chip smtp";
        } else {
            chip.textContent = t("auto.email.mock");
            chip.className = "chip mock";
        }
    };

    const fillForm = (config) => {
        el("autoEnabled").checked = Boolean(config.enabled);
        el("autoTime").value = config.time || "05:00";
        el("autoTimezone").value = config.timezone || "";
        el("autoEmail").value = config.recipient_email || "";
        el("autoTopics").value = (config.topics || []).join("\n");
        el("autoDepth").value = config.depth || "deep";
        lastEmailMode = config.email_mode || "mock";
        applyEmailChip();
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
            setStatus(t("auto.loadError"), false);
            if (window.AtlasToast) AtlasToast.error(t("auto.loadError"));
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
            topics: el("autoTopics").value.split("\n").map((line) => line.trim()).filter(Boolean),
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
                setStatus(t("auto.saved"));
            } else {
                const detail = Array.isArray(data.detail)
                    ? data.detail.map((d) => d.msg).join("; ")
                    : (data.detail || t("auto.saveError"));
                setStatus(String(detail), false);
            }
        } catch (error) {
            console.error("Automation config save failed:", error);
            setStatus(t("auto.saveError"), false);
            if (window.AtlasToast) AtlasToast.error(t("auto.saveError"));
        }
    };

    /* ---------- runs */

    const formatTime = (isoString) => {
        if (!isoString) return "—";
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return isoString;
        return date.toLocaleString(locale(), {
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
        lastRuns = runs;
        const list = el("runsList");
        if (!Array.isArray(runs) || runs.length === 0) {
            list.innerHTML = `<p class="empty-note">${escapeHtml(t("auto.runs.empty"))}</p>`;
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
                    ${run.history_id ? `<a class="run-link view-report">${escapeHtml(t("auto.viewReport"))}</a>` : ""}
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
            el("runsList").innerHTML = `<p class="empty-note">${escapeHtml(t("auto.runsLoadError"))}</p>`;
            return [];
        }
    };

    const toast = (type, key) => { if (window.AtlasToast) AtlasToast[type](t(key)); };

    // Failed runs are not persisted, so a watched run that vanishes from the list
    // (without ever appearing as "success") means it failed — surface that.
    const pollWhileRunning = (watchId) => {
        if (pollTimer) clearInterval(pollTimer);
        let ticks = 0;
        let sawRun = false;
        pollTimer = setInterval(async () => {
            ticks += 1;
            const runs = await loadRuns();
            const watched = watchId ? runs.find((run) => run.id === watchId) : null;
            if (watched) sawRun = true;
            const stillRunning = runs.some((run) => run.status === "running");

            const stop = () => { clearInterval(pollTimer); pollTimer = null; };
            if (watchId && watched && watched.status === "success") {
                toast("success", "auto.runDone");
                stop();
            } else if (watchId && sawRun && !watched && !stillRunning) {
                toast("warning", "auto.runFailed");   // our run was deleted => failed
                stop();
            } else if (!stillRunning || ticks > 120) {  // stop after ~10 minutes
                stop();
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
                setStatus(t("auto.runInProgress"), false);
                toast("warning", "auto.runInProgress");
            } else if (response.ok && data.success) {
                setStatus(t("auto.runStarted"));
                await loadRuns();
                const runId = data.data && data.data.run_id;
                if (runId) {
                    pollWhileRunning(runId);
                } else {
                    // Fast-fail (e.g. no recipient email): the run failed before we could track it.
                    toast("warning", "auto.runFailed");
                }
            } else {
                setStatus(String(data.detail || t("auto.runError")), false);
                toast("error", "auto.runError");
            }
        } catch (error) {
            console.error("Manual run failed:", error);
            setStatus(t("auto.runUnreachable"), false);
            toast("error", "auto.runUnreachable");
        } finally {
            setTimeout(() => { button.disabled = false; }, 2000);
        }
    };

    /* ---------- init */

    const init = () => {
        el("automationForm").addEventListener("submit", saveConfig);
        el("runNow").addEventListener("click", runNow);
        el("refreshRuns").addEventListener("click", loadRuns);
        document.addEventListener("atlas:langchange", () => {
            applyEmailChip();
            if (lastRuns) renderRuns(lastRuns);
        });
        loadConfig();
        loadRuns();
    };

    window.AtlasViews.register("automation", init, loadRuns);

    return {
        reload: () => { loadConfig(); loadRuns(); },
        reloadRuns: () => { loadRuns(); },
    };
})();

window.AtlasAutomation = AtlasAutomation;
