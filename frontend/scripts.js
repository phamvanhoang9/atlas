/**
 * ATLAS app shell + research view.
 *
 * Owns: view routing (Research / Automation / History), the research
 * WebSocket flow, report streaming, the sources panel, refusals, and
 * follow-up questions. History and automation views live in their own
 * files and register through window.AtlasViews.
 */

/* ------------------------------------------------- shared helpers */

const AtlasShared = (() => {
    const authToken = () => window.localStorage.getItem("atlas_auth_token");

    const authHeaders = () => {
        const token = authToken();
        return token ? { "Authorization": `Bearer ${token}` } : {};
    };

    const withAuthToken = (url) => {
        const token = authToken();
        if (!token) return url;
        const separator = url.includes("?") ? "&" : "?";
        return `${url}${separator}token=${encodeURIComponent(token)}`;
    };

    const escapeHtml = (value) => {
        const div = document.createElement("div");
        div.textContent = String(value ?? "");
        return div.innerHTML;
    };

    const timeAgo = (isoString) => {
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return "";
        const diffMs = Date.now() - date.getTime();
        const mins = Math.floor(diffMs / 60000);
        if (mins < 1) return "just now";
        if (mins < 60) return `${mins} min ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours} h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days} d ago`;
        return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    };

    const converter = () => new showdown.Converter({ tables: true, openLinksInNewWindow: true });

    return { authHeaders, withAuthToken, escapeHtml, timeAgo, converter };
})();
window.AtlasShared = AtlasShared;

/* --------------------------------------------------- view router */

const AtlasRouter = (() => {
    const initializers = {};   // view name -> { init, initialized }

    const register = (name, initFn) => {
        initializers[name] = { init: initFn, initialized: false };
    };

    const show = (name) => {
        document.querySelectorAll(".nav-tab").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.view === name);
        });
        document.querySelectorAll(".view").forEach((view) => {
            view.classList.toggle("active", view.id === `view-${name}`);
        });
        const entry = initializers[name];
        if (entry && !entry.initialized) {
            entry.initialized = true;
            entry.init();
        } else if (entry && entry.refresh) {
            entry.refresh();
        }
        window.scrollTo(0, 0);
    };

    const init = () => {
        document.querySelectorAll(".nav-tab").forEach((tab) => {
            tab.addEventListener("click", () => show(tab.dataset.view));
        });
    };

    return { register, show, init };
})();
window.AtlasViews = AtlasRouter;

/* -------------------------------------------------- research view */

const Atlas = (() => {
    const MODE_LABELS = {
        quick: "Quick Answer",
        research: "Research",
        deep: "Deep Research",
        // Legacy ids kept readable for stored history entries.
        "hỏi đáp": "Quick Answer",
        "đề xuất bài báo": "Research",
        "phân tích": "Deep Research",
    };
    const MODE_CLASSES = {
        quick: "quick", research: "research", deep: "deep",
        "hỏi đáp": "quick", "đề xuất bài báo": "research", "phân tích": "deep",
    };

    const converter = AtlasShared.converter();

    let reportMarkdown = "";
    let renderQueued = false;
    let running = false;
    let finished = false;
    let refused = false;
    let socket = null;

    const el = (id) => document.getElementById(id);

    /* ---------- progress */

    const STAGE_RULES = [
        [/^Researching/i, "Planning research…"],
        [/Selected agent/i, "Planning research…"],
        [/report/i, "Writing the report…"],
        [/context/i, "Building context…"],
        [/sources kept|quality score|low-quality/i, "Ranking sources by quality…"],
        [/Scraping/i, "Reading sources…"],
        [/^Searching|parallel search|^Found \d+ results|Added URL/i, "Searching the web…"],
        [/quer(y|ies)/i, "Generating search queries…"],
    ];

    const stageFor = (line) => {
        for (const [pattern, stage] of STAGE_RULES) {
            if (pattern.test(line)) return stage;
        }
        return null;
    };

    const appendLog = (text) => {
        const log = el("progressLog");
        const line = String(text ?? "").trim();
        if (!line) return;
        log.textContent += (log.textContent ? "\n" : "") + line;
        log.scrollTop = log.scrollHeight;
        const stage = stageFor(line);
        if (stage) el("progressStage").textContent = stage;
    };

    /* ---------- report rendering (chunk stream + replace) */

    const renderReport = () => {
        renderQueued = false;
        el("reportContainer").innerHTML = converter.makeHtml(reportMarkdown);
    };

    const queueRender = () => {
        if (!renderQueued) {
            renderQueued = true;
            requestAnimationFrame(renderReport);
        }
    };

    const handleReportMessage = (data) => {
        if (data.replace) {
            reportMarkdown = data.output ?? "";
        } else {
            reportMarkdown += data.output ?? "";
        }
        // A refused query renders only the refusal card, not a report card.
        if (refused) return;
        el("resultArea").classList.remove("is-hidden");
        queueRender();
    };

    /* ---------- sources panel */

    const renderSources = (sources) => {
        const list = el("sourcesList");
        list.innerHTML = "";
        if (!Array.isArray(sources) || sources.length === 0) {
            list.innerHTML = '<p class="empty-note">No ranked sources for this run.</p>';
            el("sourceCount").textContent = "";
            return;
        }
        el("sourceCount").textContent = String(sources.length);
        sources.forEach((source) => {
            const item = document.createElement("div");
            item.className = "source-item";

            const link = document.createElement("a");
            link.className = "source-title";
            link.href = source.url || "#";
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = source.title || source.url || "Untitled source";

            const meta = document.createElement("div");
            meta.className = "source-meta";

            const chip = document.createElement("span");
            chip.className = `cat-chip ${source.category || "uncategorized"}`;
            chip.textContent = source.category_label || "Web source";

            const score = document.createElement("span");
            score.className = "source-score";
            score.textContent = `${source.score ?? "?"}/100`;

            meta.appendChild(chip);
            meta.appendChild(score);
            item.appendChild(link);
            item.appendChild(meta);
            list.appendChild(item);
        });
    };

    /* ---------- suggested questions */

    const renderSuggestedQuestions = (questions) => {
        const container = el("suggestedQuestions");
        container.innerHTML = "";
        if (!Array.isArray(questions) || questions.length === 0) {
            container.innerHTML = '<p class="empty-note">No follow-up questions for this run.</p>';
            return;
        }
        questions.forEach((question) => {
            const div = document.createElement("div");
            div.className = "suggested-question";
            div.textContent = question;
            div.addEventListener("click", () => {
                el("task").value = question;
                AtlasRouter.show("research");
                el("task").focus();
                window.scrollTo({ top: 0, behavior: "smooth" });
            });
            container.appendChild(div);
        });
    };

    /* ---------- quality / evaluation notes */

    const renderQualityCheck = (payload) => {
        if (!payload || typeof payload !== "object") return;
        const note = el("qualityNote");
        const verdict = payload.passed ? "passed" : "needs review";
        note.textContent =
            `Grounding check ${verdict} — score ${payload.score}, ` +
            `${payload.grounded_url_count}/${payload.context_url_count} reference URLs verified against retrieved sources.`;
        note.classList.remove("is-hidden");
    };

    const renderEvaluation = (payload) => {
        if (!payload || typeof payload !== "object" || payload.error) return;
        const note = el("qualityNote");
        const existing = note.classList.contains("is-hidden") ? "" : note.textContent + " · ";
        note.textContent = `${existing}Evaluation: overall ${Number(payload.overall_score).toFixed(2)} (${payload.label}).`;
        note.classList.remove("is-hidden");
    };

    /* ---------- refusal */

    const showRefusal = (markdown) => {
        refused = true;
        const card = el("refusalCard");
        el("refusalBody").innerHTML = converter.makeHtml(markdown ?? "");
        card.classList.remove("is-hidden");
        el("progressCard").classList.add("is-hidden");
        el("resultArea").classList.add("is-hidden");
    };

    /* ---------- run state */

    const setFormBusy = (busy, completed = false) => {
        const submit = el("submitResearch");
        const label = el("taskLabel");
        submit.disabled = busy;
        if (busy) {
            submit.textContent = "Running…";
            label.textContent = "ATLAS is working on your question";
        } else if (completed) {
            submit.textContent = "Run again";
            label.textContent = "What do you want to explore next?";
        } else {
            submit.textContent = "Run";
            label.textContent = "Ask about AI research, models, tools, or papers";
        }
    };

    const showError = (message) => {
        const card = el("errorCard");
        card.textContent = message;
        card.classList.remove("is-hidden");
        el("progressSpinner").classList.add("done");
        setFormBusy(false);
        running = false;
    };

    const resetRunUI = () => {
        reportMarkdown = "";
        finished = false;
        refused = false;
        el("researchEmpty").classList.add("is-hidden");
        el("errorCard").classList.add("is-hidden");
        el("refusalCard").classList.add("is-hidden");
        el("resultArea").classList.add("is-hidden");
        el("reportContainer").innerHTML = "";
        el("qualityNote").classList.add("is-hidden");
        el("qualityNote").textContent = "";
        el("status").textContent = "";
        el("sourcesList").innerHTML = '<p class="empty-note">Sources appear here as they are found and ranked.</p>';
        el("sourceCount").textContent = "";
        el("suggestedQuestions").innerHTML = '<p class="empty-note">Generated after the report is ready.</p>';
        el("progressLog").textContent = "";
        el("progressStage").textContent = "Starting research…";
        el("progressSpinner").classList.remove("done");
        el("progressCard").classList.remove("is-hidden");
        el("copyToClipboard").disabled = true;
        const pdf = el("downloadLink");
        pdf.classList.add("disabled");
        pdf.href = "#";
    };

    const finishRun = () => {
        finished = true;
        running = false;
        el("progressSpinner").classList.add("done");
        el("progressStage").textContent = "Research complete";
        if (!refused) {
            el("status").textContent = "Report complete.";
            el("copyToClipboard").disabled = false;
        }
        setFormBusy(false, true);
        setTimeout(() => el("progressCard").classList.add("is-hidden"), 1200);
    };

    /* ---------- websocket */

    const startResearch = () => {
        if (running) return;
        const task = el("task").value.trim();
        if (!task) return;
        const mode = document.querySelector('input[name="report_type"]:checked').value;

        running = true;
        resetRunUI();
        setFormBusy(true);
        setModeBadge(mode);

        const { protocol, host } = window.location;
        const token = window.localStorage.getItem("atlas_auth_token");
        const authQuery = token ? `?token=${encodeURIComponent(token)}` : "";
        const wsUri = `${protocol === "https:" ? "wss:" : "ws:"}//${host}/ws${authQuery}`;

        socket = new WebSocket(wsUri);

        socket.onopen = () => {
            socket.send(`start ${JSON.stringify({ task, report_type: mode, agent: "Auto Agent" })}`);
        };

        socket.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch { return; }

            switch (data.type) {
                case "logs": appendLog(data.output); break;
                case "report": handleReportMessage(data); break;
                case "sources": renderSources(data.output); break;
                case "refusal": showRefusal(data.output); break;
                case "suggested_questions": renderSuggestedQuestions(data.output); break;
                case "quality_check": renderQualityCheck(data.output); break;
                case "evaluation": renderEvaluation(data.output); break;
                case "history_id":
                    if (window.AtlasHistory) AtlasHistory.setCurrentHistoryId(data.output);
                    break;
                case "path": {
                    const pdf = el("downloadLink");
                    if (data.output) {
                        pdf.href = data.output;
                        pdf.classList.remove("disabled");
                    }
                    finishRun();
                    break;
                }
                case "error": showError(data.output || "The server rejected the request."); break;
                default: break;
            }
        };

        socket.onclose = () => {
            if (running && !finished) {
                showError("Connection lost before the report finished. Check that the server is running, then try again.");
            }
        };

        socket.onerror = () => {
            if (running && !finished) {
                showError("Could not reach the ATLAS server. Is it running on this host?");
            }
        };
    };

    /* ---------- shared render for stored history entries */

    const setModeBadge = (mode, kind = "chat") => {
        const badge = el("modeBadge");
        if (kind === "daily_report") {
            badge.textContent = "Daily Intelligence";
            badge.className = "mode-badge daily";
            return;
        }
        badge.textContent = MODE_LABELS[mode] || mode || "Report";
        badge.className = `mode-badge ${MODE_CLASSES[mode] || "research"}`;
    };

    const displayStoredReport = (entry) => {
        running = false;
        resetRunUI();
        el("progressCard").classList.add("is-hidden");
        setFormBusy(false, true);

        el("task").value = entry.kind === "daily_report" ? "" : (entry.query || "");
        setModeBadge(entry.mode, entry.kind);

        reportMarkdown = entry.report || "*This entry has no stored report.*";
        renderReport();
        el("resultArea").classList.remove("is-hidden");
        el("status").textContent = `Loaded from history · ${AtlasShared.timeAgo(entry.timestamp)}`;
        el("copyToClipboard").disabled = false;

        const pdf = el("downloadLink");
        if (entry.pdf_path) {
            pdf.href = entry.pdf_path;
            pdf.classList.remove("disabled");
        }

        renderSuggestedQuestions(entry.suggested_questions || []);
        el("sourcesList").innerHTML =
            '<p class="empty-note">Live source ranking is shown during a run. For stored reports, see the Sources section inside the report.</p>';
        el("sourceCount").textContent = "";

        AtlasRouter.show("research");
    };

    /* ---------- clipboard */

    const copyToClipboard = () => {
        const text = el("reportContainer").innerText;
        const done = () => { el("status").textContent = "Report copied to clipboard."; };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
            return;
        }
        fallbackCopy(text, done);
    };

    const fallbackCopy = (text, done) => {
        const textarea = document.createElement("textarea");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        done();
    };

    /* ---------- init */

    const init = () => {
        AtlasRouter.init();
        document.getElementById("researchForm").addEventListener("submit", (event) => {
            event.preventDefault();
            startResearch();
        });
        document.getElementById("copyToClipboard").addEventListener("click", copyToClipboard);
    };

    document.addEventListener("DOMContentLoaded", init);

    return { startResearch, displayStoredReport, setModeBadge };
})();

window.Atlas = Atlas;
