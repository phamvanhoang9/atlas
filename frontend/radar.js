/**
 * ATLAS Radar — saved recurring watches, rendered inside the Automation tab
 * (Trụ cột 4 of modes_redesign_plan.md; deliberately not a separate nav tab
 * or view — see .claude/memory/anti-patterns.md "Hai bề mặt UI làm cùng 1
 * việc"). Talks to /api/radar/*.
 */

const AtlasRadar = (() => {
    const { authHeaders, escapeHtml, locale } = window.AtlasShared;
    const t = (k, v) => AtlasI18n.t(k, v);

    // Preferred-source categories offered in the form. Matches
    // src/quality/source_scorer.py's taxonomy, excluding "low_quality"
    // (never primary evidence) and "uncategorized" (the fallback bucket,
    // not a meaningful preference).
    const PREFERRED_CATEGORY_OPTIONS = [
        ["official", "Official source"],
        ["peer_reviewed", "Peer-reviewed paper"],
        ["arxiv_preprint", "arXiv/preprint"],
        ["ai_lab_blog", "AI lab blog"],
        ["github_repo", "GitHub repository"],
        ["engineering_blog", "Engineering blog"],
        ["tech_forum", "Technical forum"],
        ["news", "News article"],
    ];

    let presets = [];
    let watches = [];
    let editingWatchId = null;
    let expandedRunsFor = null;
    let runsPollTimer = null;

    const el = (id) => document.getElementById(id);

    /* ---------- form helpers */

    const buildCategoryChecks = () => {
        const container = el("radarCategoryChecks");
        container.innerHTML = PREFERRED_CATEGORY_OPTIONS.map(([id, label]) => `
            <label class="radar-check-item">
                <input type="checkbox" class="radar-category-check" value="${escapeHtml(id)}">
                <span class="cat-chip ${escapeHtml(id)}">${escapeHtml(label)}</span>
            </label>
        `).join("");
    };

    const buildPresetButtons = () => {
        const container = el("radarPresetButtons");
        container.innerHTML = presets.map((preset) => `
            <button type="button" class="btn btn-ghost radar-preset-btn" data-preset="${escapeHtml(preset.id)}" title="${escapeHtml(preset.description)}">${escapeHtml(preset.name)}</button>
        `).join("");
        container.querySelectorAll(".radar-preset-btn").forEach((button) => {
            button.addEventListener("click", () => {
                const preset = presets.find((p) => p.id === button.dataset.preset);
                if (preset) applyPreset(preset);
            });
        });
    };

    const setWeekdayFieldVisibility = () => {
        const isWeekly = el("radarCadenceUnit").value === "weekly";
        el("radarWeekdayField").classList.toggle("is-hidden", !isWeekly);
    };

    const getCheckedCategories = () =>
        Array.from(document.querySelectorAll(".radar-category-check:checked")).map((c) => c.value);

    const setCheckedCategories = (categories) => {
        document.querySelectorAll(".radar-category-check").forEach((checkbox) => {
            checkbox.checked = (categories || []).includes(checkbox.value);
        });
    };

    const resetForm = () => {
        editingWatchId = null;
        el("radarWatchId").value = "";
        el("radarName").value = "";
        el("radarTopics").value = "";
        el("radarMode").value = "ask";
        el("radarEmail").value = "";
        el("radarCadenceUnit").value = "daily";
        el("radarWeekday").value = "1";
        el("radarTime").value = "08:00";
        el("radarTimezone").value = "UTC";
        setCheckedCategories([]);
        el("radarEnabled").checked = false;
        setWeekdayFieldVisibility();
        el("radarSave").textContent = t("radar.save");
    };

    const fillForm = (watch) => {
        editingWatchId = watch.id;
        el("radarWatchId").value = watch.id;
        el("radarName").value = watch.name || "";
        el("radarTopics").value = (watch.topics || []).join("\n");
        el("radarMode").value = watch.mode || "ask";
        el("radarEmail").value = watch.recipient_email || "";
        el("radarCadenceUnit").value = watch.cadence_unit || "daily";
        el("radarWeekday").value = String(watch.cadence_weekday || 1);
        el("radarTime").value = watch.cadence_time || "08:00";
        el("radarTimezone").value = watch.cadence_timezone || "UTC";
        setCheckedCategories(watch.preferred_categories || []);
        el("radarEnabled").checked = Boolean(watch.enabled);
        setWeekdayFieldVisibility();
        el("radarSave").textContent = t("radar.update");
    };

    const applyPreset = (preset) => {
        editingWatchId = null;
        el("radarWatchId").value = "";
        el("radarName").value = preset.name;
        el("radarTopics").value = (preset.topics || []).join("\n");
        el("radarMode").value = preset.mode;
        el("radarCadenceUnit").value = preset.cadence_unit;
        el("radarWeekday").value = String(preset.cadence_weekday || 1);
        el("radarTime").value = preset.cadence_time;
        el("radarTimezone").value = preset.cadence_timezone;
        setCheckedCategories(preset.preferred_categories || []);
        setWeekdayFieldVisibility();
        openForm();
    };

    const openForm = () => { el("radarForm").classList.remove("is-hidden"); };
    const closeForm = () => { el("radarForm").classList.add("is-hidden"); resetForm(); };

    const setFormStatus = (message, ok = true) => {
        const status = el("radarFormStatus");
        status.textContent = message;
        status.className = `form-status ${ok ? "ok" : "err"}`;
        if (message) setTimeout(() => { status.textContent = ""; }, 6000);
    };

    /* ---------- data */

    const loadPresets = async () => {
        try {
            const response = await fetch("/api/radar/presets", { headers: authHeaders() });
            const data = await response.json();
            if (data.success) { presets = data.data; buildPresetButtons(); }
        } catch (error) {
            console.error("Radar presets load failed:", error);
        }
    };

    const loadStatus = async () => {
        try {
            const response = await fetch("/api/radar/status", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) return;
            const { enabled_watches, total_watches, quota_used, quota_limit } = data.data;
            el("radarQuotaChip").textContent = t("radar.status", {
                enabled: enabled_watches, total: total_watches, used: quota_used, limit: quota_limit,
            });
        } catch (error) {
            console.error("Radar status load failed:", error);
        }
    };

    const formatTime = (isoString) => {
        if (!isoString) return "—";
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return isoString;
        return date.toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    };

    const cadenceSummary = (watch) => {
        if (watch.cadence_unit === "weekly") {
            const dayKey = ["", "mon", "tue", "wed", "thu", "fri", "sat", "sun"][watch.cadence_weekday || 1];
            return `${t("radar.cadence.weekly")} · ${t(`radar.weekday.${dayKey}`)} ${watch.cadence_time} ${watch.cadence_timezone}`;
        }
        return `${t("radar.cadence.daily")} · ${watch.cadence_time} ${watch.cadence_timezone}`;
    };

    const renderRunsList = (watchId, runs) => {
        const container = document.querySelector(`.radar-runs[data-watch-id="${watchId}"]`);
        if (!container) return;
        if (!Array.isArray(runs) || runs.length === 0) {
            container.innerHTML = `<p class="empty-note">${escapeHtml(t("auto.runs.empty"))}</p>`;
            return;
        }
        container.innerHTML = runs.slice(0, 5).map((run) => `
            <div class="run-item">
                <div class="run-row1">
                    <span class="run-time">${escapeHtml(formatTime(run.started_at))}</span>
                    <span class="run-chips">
                        <span class="status-chip ${escapeHtml(run.status || "running")}">${escapeHtml(run.status || "running")}</span>
                        <span class="status-chip skipped">${escapeHtml(t("radar.newItems", { n: run.new_items_count || 0 }))}</span>
                    </span>
                </div>
                <div class="run-row2">
                    <span>trigger: ${escapeHtml(run.trigger || "scheduled")}</span>
                </div>
                ${run.error_log ? `<div class="run-error">${escapeHtml(run.error_log)}</div>` : ""}
            </div>
        `).join("");
    };

    const loadRunsForWatch = async (watchId) => {
        try {
            const response = await fetch(`/api/radar/watches/${watchId}/runs?limit=5`, { headers: authHeaders() });
            const data = await response.json();
            if (data.success) renderRunsList(watchId, data.data);
        } catch (error) {
            console.error("Radar watch runs load failed:", error);
        }
    };

    const toggleRunsPanel = (watchId) => {
        expandedRunsFor = expandedRunsFor === watchId ? null : watchId;
        renderWatches();
        if (expandedRunsFor) loadRunsForWatch(watchId);
    };

    const renderWatches = () => {
        const list = el("radarWatchList");
        if (!Array.isArray(watches) || watches.length === 0) {
            list.innerHTML = `<p class="empty-note">${escapeHtml(t("radar.empty"))}</p>`;
            return;
        }
        list.innerHTML = watches.map((watch) => {
            const isExpanded = expandedRunsFor === watch.id;
            const categoryChips = (watch.preferred_categories || [])
                .map((c) => `<span class="cat-chip ${escapeHtml(c)}">${escapeHtml(c)}</span>`).join("");
            return `
                <div class="card radar-watch-card" data-watch-id="${escapeHtml(watch.id)}">
                    <div class="radar-watch-head">
                        <div>
                            <span class="mode-badge ${escapeHtml(watch.mode)}">${escapeHtml(t(`mode.${watch.mode}`))}</span>
                            <span class="radar-watch-name">${escapeHtml(watch.name)}</span>
                            ${!watch.enabled ? `<span class="chip mock">${escapeHtml(t("radar.disabled"))}</span>` : ""}
                        </div>
                        <label class="toggle radar-watch-toggle">
                            <input type="checkbox" class="radar-toggle-enabled" ${watch.enabled ? "checked" : ""}>
                            <span class="toggle-track"><span class="toggle-thumb"></span></span>
                        </label>
                    </div>
                    <div class="radar-watch-meta">${escapeHtml(cadenceSummary(watch))} · ${escapeHtml(watch.recipient_email)}</div>
                    ${watch.topics && watch.topics.length ? `<div class="radar-watch-topics">${escapeHtml(watch.topics.join(" · "))}</div>` : ""}
                    ${categoryChips ? `<div class="radar-watch-categories">${categoryChips}</div>` : ""}
                    <div class="radar-watch-actions">
                        <button type="button" class="btn btn-secondary radar-run-now" data-i18n="auto.runNow">Run now</button>
                        <button type="button" class="btn btn-ghost radar-toggle-runs">${escapeHtml(isExpanded ? t("radar.hideRuns") : t("radar.showRuns"))}</button>
                        <button type="button" class="btn btn-ghost radar-edit" data-i18n="radar.edit">Edit</button>
                        <button type="button" class="btn btn-danger-ghost radar-delete" data-i18n="radar.delete">Delete</button>
                    </div>
                    ${isExpanded ? `<div class="radar-runs" data-watch-id="${escapeHtml(watch.id)}"><p class="empty-note loading-note">${escapeHtml(t("auto.loadError"))}</p></div>` : ""}
                </div>
            `;
        }).join("");

        list.querySelectorAll(".radar-watch-card").forEach((card) => {
            const watchId = card.dataset.watchId;
            const watch = watches.find((w) => w.id === watchId);

            card.querySelector(".radar-toggle-enabled").addEventListener("change", (event) => {
                updateWatch(watchId, { enabled: event.target.checked });
            });
            card.querySelector(".radar-run-now").addEventListener("click", () => runNow(watchId));
            card.querySelector(".radar-toggle-runs").addEventListener("click", () => toggleRunsPanel(watchId));
            card.querySelector(".radar-edit").addEventListener("click", () => { fillForm(watch); openForm(); });
            card.querySelector(".radar-delete").addEventListener("click", () => deleteWatch(watchId));
        });
    };

    const loadWatches = async () => {
        try {
            const response = await fetch("/api/radar/watches", { headers: authHeaders() });
            const data = await response.json();
            if (!data.success) throw new Error("API error");
            watches = data.data || [];
            renderWatches();
        } catch (error) {
            console.error("Radar watches load failed:", error);
            el("radarWatchList").innerHTML = `<p class="empty-note">${escapeHtml(t("auto.loadError"))}</p>`;
            if (window.AtlasToast) AtlasToast.error(t("auto.loadError"));
        }
    };

    /* ---------- mutations */

    const collectPayload = () => ({
        name: el("radarName").value.trim(),
        topics: el("radarTopics").value.split("\n").map((line) => line.trim()).filter(Boolean),
        mode: el("radarMode").value,
        cadence_unit: el("radarCadenceUnit").value,
        cadence_weekday: el("radarCadenceUnit").value === "weekly" ? Number(el("radarWeekday").value) : null,
        cadence_time: el("radarTime").value,
        cadence_timezone: el("radarTimezone").value.trim(),
        recipient_email: el("radarEmail").value.trim(),
        preferred_categories: getCheckedCategories(),
        enabled: el("radarEnabled").checked,
    });

    const saveWatch = async (event) => {
        event.preventDefault();
        const payload = collectPayload();
        const isUpdate = Boolean(editingWatchId);
        try {
            const response = await fetch(
                isUpdate ? `/api/radar/watches/${editingWatchId}` : "/api/radar/watches",
                {
                    method: isUpdate ? "PUT" : "POST",
                    headers: { "Content-Type": "application/json", ...authHeaders() },
                    body: JSON.stringify(payload),
                },
            );
            const data = await response.json();
            if (response.ok && data.success) {
                setFormStatus(t("radar.saved"));
                if (!isUpdate && data.data && data.data.duplicate_of) {
                    if (window.AtlasToast) AtlasToast.warning(t("radar.duplicateWarning"));
                }
                closeForm();
                await loadWatches();
                await loadStatus();
            } else {
                const detail = Array.isArray(data.detail)
                    ? data.detail.map((d) => d.msg).join("; ")
                    : (data.detail || t("radar.saveError"));
                setFormStatus(String(detail), false);
            }
        } catch (error) {
            console.error("Radar watch save failed:", error);
            setFormStatus(t("radar.saveError"), false);
        }
    };

    const updateWatch = async (watchId, updates) => {
        try {
            const response = await fetch(`/api/radar/watches/${watchId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify(updates),
            });
            const data = await response.json();
            if (data.success) {
                const index = watches.findIndex((w) => w.id === watchId);
                if (index >= 0) watches[index] = data.data;
                renderWatches();
                await loadStatus();
            } else if (window.AtlasToast) {
                AtlasToast.error(t("radar.saveError"));
                await loadWatches();
            }
        } catch (error) {
            console.error("Radar watch update failed:", error);
            if (window.AtlasToast) AtlasToast.error(t("radar.saveError"));
        }
    };

    const deleteWatch = async (watchId) => {
        if (!window.confirm(t("radar.deleteConfirm"))) return;
        try {
            const response = await fetch(`/api/radar/watches/${watchId}`, {
                method: "DELETE", headers: authHeaders(),
            });
            const data = await response.json();
            if (data.success) {
                watches = watches.filter((w) => w.id !== watchId);
                renderWatches();
                await loadStatus();
            } else if (window.AtlasToast) {
                AtlasToast.error(t("radar.deleteError"));
            }
        } catch (error) {
            console.error("Radar watch delete failed:", error);
            if (window.AtlasToast) AtlasToast.error(t("radar.deleteError"));
        }
    };

    const pollWhileRunning = (watchId) => {
        if (runsPollTimer) clearInterval(runsPollTimer);
        let ticks = 0;
        runsPollTimer = setInterval(async () => {
            ticks += 1;
            const response = await fetch(`/api/radar/watches/${watchId}/runs?limit=1`, { headers: authHeaders() });
            const data = await response.json();
            const latest = data.success && data.data && data.data[0];
            const stop = () => { clearInterval(runsPollTimer); runsPollTimer = null; };
            if (latest && latest.status === "success") {
                if (window.AtlasToast) AtlasToast.success(t("auto.runDone"));
                stop();
                if (expandedRunsFor === watchId) loadRunsForWatch(watchId);
                loadStatus();
            } else if (latest && latest.status === "failed") {
                if (window.AtlasToast) AtlasToast.warning(t("auto.runFailed"));
                stop();
                if (expandedRunsFor === watchId) loadRunsForWatch(watchId);
                loadStatus();
            } else if (ticks > 120) {
                stop();
            }
        }, 5000);
    };

    const runNow = async (watchId) => {
        try {
            const response = await fetch(`/api/radar/watches/${watchId}/run`, {
                method: "POST", headers: authHeaders(),
            });
            const data = await response.json();
            if (response.status === 409) {
                if (window.AtlasToast) AtlasToast.warning(t("auto.runInProgress"));
            } else if (response.ok && data.success) {
                if (window.AtlasToast) AtlasToast.success(t("auto.runStarted"));
                pollWhileRunning(watchId);
            } else if (window.AtlasToast) {
                AtlasToast.error(t("auto.runError"));
            }
        } catch (error) {
            console.error("Radar run-now failed:", error);
            if (window.AtlasToast) AtlasToast.error(t("auto.runUnreachable"));
        }
    };

    /* ---------- init */

    const init = () => {
        buildCategoryChecks();
        el("radarNewWatch").addEventListener("click", () => { resetForm(); openForm(); });
        el("radarCancel").addEventListener("click", closeForm);
        el("radarForm").addEventListener("submit", saveWatch);
        el("radarCadenceUnit").addEventListener("change", setWeekdayFieldVisibility);

        document.addEventListener("atlas:langchange", () => {
            buildPresetButtons();
            renderWatches();
        });

        loadPresets();
        loadWatches();
        loadStatus();
    };

    return { init, reload: () => { loadWatches(); loadStatus(); } };
})();

window.AtlasRadar = AtlasRadar;
