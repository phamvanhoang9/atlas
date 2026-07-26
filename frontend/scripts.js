/**
 * ATLAS app shell + research view.
 *
 * Owns: view routing (Research / Automation / History), the new-session hero,
 * the pinned auto-resizing composer, and a conversation thread where each
 * question becomes a turn (user bubble + streamed answer block with collapsible
 * Sources and Follow-up sections). History/Automation open stored reports as a
 * single read-only turn. Interface strings come from AtlasI18n; theme from
 * AtlasTheme. The WebSocket message contract is unchanged.
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

    const locale = () => (window.AtlasI18n && AtlasI18n.getLang() === "vi" ? "vi-VN" : "en-GB");

    const timeAgo = (isoString) => {
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return "";
        const diffMs = Date.now() - date.getTime();
        const mins = Math.floor(diffMs / 60000);
        const T = (k) => (window.AtlasI18n ? AtlasI18n.t(k) : k);
        if (mins < 1) return T("time.now");
        if (mins < 60) return `${mins} ${T("time.min")}`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours} ${T("time.hour")}`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days} ${T("time.day")}`;
        return date.toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" });
    };

    const converter = () => new showdown.Converter({ tables: true, openLinksInNewWindow: true });

    const TRUST_CATEGORY_SHORT = {
        official: "official", peer_reviewed: "peer-reviewed", arxiv_preprint: "arxiv",
        ai_lab_blog: "AI lab", github_repo: "GitHub", engineering_blog: "eng blog",
        tech_forum: "forum", uncategorized: "web", news: "news", low_quality: "low-quality",
    };

    // Deterministic trust badge summary from source_scorer categories — never
    // LLM-generated (D-008). Returns null when there is nothing to score
    // (Mục 8.2: "0 nguồn tìm được" must hide the badge, not show "0/100").
    // Shared between the live turn (scripts.js) and stored History entries
    // (history.js) so both surfaces compute the identical badge.
    const computeTrustSummary = (sources) => {
        if (!Array.isArray(sources) || sources.length === 0) return null;

        const counts = new Map();
        let scoreSum = 0;
        let scoreCount = 0;
        sources.forEach((source) => {
            const category = source.category || "uncategorized";
            counts.set(category, (counts.get(category) || 0) + 1);
            const score = Number(source.score);
            if (Number.isFinite(score)) { scoreSum += score; scoreCount += 1; }
        });

        // Tie-break: highest count first, then alphabetical by category key,
        // so equal-count categories render in a stable, deterministic order
        // (Mục 8.2: "2 nguồn điểm bằng nhau — tie-break hiển thị thứ tự nào").
        const sortedCategories = [...counts.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
        const breakdown = sortedCategories
            .map(([category, count]) => `${count} ${TRUST_CATEGORY_SHORT[category] || category}`)
            .join(" · ");
        const categories = sortedCategories.map(([category, count]) => ({
            category, label: TRUST_CATEGORY_SHORT[category] || category, count,
        }));

        const avgScore = scoreCount ? Math.round(scoreSum / scoreCount) : null;
        const tier = avgScore === null ? "low" : avgScore >= 80 ? "high" : avgScore >= 50 ? "mid" : "low";
        return { avgScore, tier, breakdown, count: sources.length, categories };
    };

    return {
        authHeaders, withAuthToken, escapeHtml, timeAgo, converter, locale,
        computeTrustSummary, TRUST_CATEGORY_SHORT,
    };
})();
window.AtlasShared = AtlasShared;

/* --------------------------------------------------- view router */

const AtlasRouter = (() => {
    const initializers = {};

    const register = (name, initFn, refreshFn) => {
        initializers[name] = { init: initFn, refresh: refreshFn, initialized: false };
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
    };

    const init = () => {
        document.querySelectorAll(".nav-tab").forEach((tab) => {
            tab.addEventListener("click", () => show(tab.dataset.view));
        });
    };

    return { register, show, init };
})();
window.AtlasViews = AtlasRouter;

/* -------------------------------------------------- Explain this / Vet this side panel */
// Trụ cột 5 (modes_redesign_plan.md): context actions, NOT a mode — a single
// side panel reused by both "Explain this" (per source) and "Vet this"
// (free-form claim). Deliberately outside the composer/mode-select flow.

const AtlasPanel = (() => {
    const { authHeaders, escapeHtml } = window.AtlasShared;
    const t = (k, v) => AtlasI18n.t(k, v);
    const el = (id) => document.getElementById(id);

    let activeController = null;   // in-flight fetch for the currently open panel

    const isOpen = () => el("sidePanel").classList.contains("show");

    const close = () => {
        // Cancel any in-flight request so a slow response from a panel the
        // user already closed can never land in a stale/reused panel state
        // (Mục 8.2: "đang gọi mà user bấm nút khác/rời trang").
        if (activeController) { activeController.abort(); activeController = null; }
        el("sidePanel").classList.remove("show");
        el("sidePanel").setAttribute("aria-hidden", "true");
        el("sideOverlay").classList.remove("show");
    };

    const open = (kind, tagText) => {
        if (activeController) { activeController.abort(); activeController = null; }
        el("sidePanelTag").textContent = tagText;
        el("sidePanelTag").className = `side-panel-tag ${kind}`;
        el("sidePanel").classList.add("show");
        el("sidePanel").setAttribute("aria-hidden", "false");
        el("sideOverlay").classList.add("show");
    };

    const setBody = (html) => { el("sidePanelBody").innerHTML = html; };

    const openExplain = async (passage, context) => {
        open("explain", t("explain.title"));
        setBody(`
            <h4>${escapeHtml(t("explain.original"))}</h4>
            <div class="orig-text">${escapeHtml(passage)}</div>
            <p class="side-panel-spinner">${escapeHtml(t("explain.loading"))}</p>
        `);

        const controller = new AbortController();
        activeController = controller;
        try {
            const response = await fetch("/api/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify({ passage, context: context || "" }),
                signal: controller.signal,
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.detail || "explain failed");
            activeController = null;

            const result = data.data;
            if (result.skipped) {
                setBody(`
                    <h4>${escapeHtml(t("explain.original"))}</h4>
                    <div class="orig-text">${escapeHtml(passage)}</div>
                    <p class="empty-note">${escapeHtml(t("explain.tooShort"))}</p>
                `);
                return;
            }
            setBody(`
                <h4>${escapeHtml(t("explain.original"))}</h4>
                <div class="orig-text">${escapeHtml(passage)}</div>
                <h4>${escapeHtml(t("explain.result"))}</h4>
                <p>${escapeHtml(result.explanation)}</p>
            `);
        } catch (error) {
            if (error.name === "AbortError") return;   // panel closed mid-request; nothing to render
            console.error("Explain failed:", error);
            setBody(`
                <h4>${escapeHtml(t("explain.original"))}</h4>
                <div class="orig-text">${escapeHtml(passage)}</div>
                <p class="empty-note">${escapeHtml(t("explain.error"))}</p>
            `);
        }
    };

    const VERDICT_CLASS = {
        confirmed: "confirmed", contradicted: "contradicted",
        insufficient_evidence: "insufficient_evidence", not_verifiable: "not_verifiable",
    };

    const renderVetForm = (prefill) => `
        <h4>${escapeHtml(t("vet.claim"))}</h4>
        <form class="vet-form" id="vetForm">
            <textarea id="vetClaimInput" placeholder="${escapeHtml(t("vet.placeholder"))}" required>${escapeHtml(prefill || "")}</textarea>
            <button type="submit" class="btn btn-primary">${escapeHtml(t("vet.submit"))}</button>
        </form>
    `;

    const wireVetForm = () => {
        const form = el("vetForm");
        if (!form) return;
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const claim = el("vetClaimInput").value.trim();
            if (claim) runVet(claim);
        });
    };

    const openVet = (prefillClaim) => {
        open("vet", t("vet.title"));
        setBody(renderVetForm(prefillClaim));
        wireVetForm();
        if (prefillClaim) runVet(prefillClaim);
    };

    const runVet = async (claim) => {
        setBody(`
            <h4>${escapeHtml(t("vet.claim"))}</h4>
            <div class="orig-text">${escapeHtml(claim)}</div>
            <p class="side-panel-spinner">${escapeHtml(t("vet.loading"))}</p>
        `);

        const controller = new AbortController();
        activeController = controller;
        try {
            const response = await fetch("/api/vet", {
                method: "POST",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify({ claim }),
                signal: controller.signal,
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.detail || "vet failed");
            activeController = null;

            const result = data.data;
            const verdictClass = VERDICT_CLASS[result.verdict] || "insufficient_evidence";
            const evidenceHtml = (result.evidence || []).length
                ? result.evidence.map((e) => `
                    <div class="evidence-item">
                        <div class="source-meta">
                            <span class="cat-chip ${e.category || "uncategorized"}">${escapeHtml(e.category_label || "Web source")}</span>
                            <span class="source-score">${e.quality_score ?? "?"}/100</span>
                        </div>
                        <a class="source-title" href="${escapeHtml(e.url)}" target="_blank" rel="noopener">${escapeHtml(e.title || e.url)}</a>
                    </div>
                `).join("")
                : `<p class="empty-note">${escapeHtml(t("vet.evidence.empty"))}</p>`;

            setBody(`
                <h4>${escapeHtml(t("vet.claim"))}</h4>
                <div class="orig-text">${escapeHtml(claim)}</div>
                <span class="verdict-pill ${verdictClass}">${escapeHtml(t(`vet.verdict.${result.verdict}`))}</span>
                <p>${escapeHtml(result.explanation || "")}</p>
                <h4>${escapeHtml(t("vet.evidence"))}</h4>
                ${evidenceHtml}
            `);
        } catch (error) {
            if (error.name === "AbortError") return;
            console.error("Vet failed:", error);
            setBody(`
                <h4>${escapeHtml(t("vet.claim"))}</h4>
                <div class="orig-text">${escapeHtml(claim)}</div>
                <p class="empty-note">${escapeHtml(t("vet.error"))}</p>
            `);
        }
    };

    // -------- Deep Dive plan-gate approval (Giai đoạn 4) --------
    // Reuses this same side panel rather than a second UI surface (see
    // .claude/memory/anti-patterns.md #2 "Hai bề mặt UI làm cùng 1 việc").
    // *onRespond(payload)* sends the client's decision back over the
    // already-open research WebSocket; this module never touches the
    // socket directly.

    const renderPlanForm = (proposal, onRespond) => {
        const headingsText = (proposal.headings || []).join("\n");
        setBody(`
            <p class="empty-note">${escapeHtml(t("plan.intro"))}</p>
            <h4>${escapeHtml(t("plan.approach"))}</h4>
            <div class="vet-form">
                <textarea id="planApproachInput">${escapeHtml(proposal.approach || "")}</textarea>
            </div>
            <h4>${escapeHtml(t("plan.headings"))}</h4>
            <div class="vet-form">
                <textarea id="planHeadingsInput" rows="8">${escapeHtml(headingsText)}</textarea>
            </div>
            <div class="plan-actions">
                <button type="button" class="btn btn-primary" id="planApproveBtn">${escapeHtml(t("plan.approve"))}</button>
                <button type="button" class="btn" id="planRegenerateBtn">${escapeHtml(t("plan.regenerate"))}</button>
                <button type="button" class="btn btn-danger-ghost" id="planRejectBtn">${escapeHtml(t("plan.reject"))}</button>
            </div>
            <h4>${escapeHtml(t("plan.feedback"))}</h4>
            <div class="vet-form">
                <textarea id="planFeedbackInput" placeholder="${escapeHtml(t("plan.feedback.placeholder"))}"></textarea>
            </div>
        `);

        const readEditedPlan = () => ({
            headings: el("planHeadingsInput").value.split("\n").map((h) => h.trim()).filter(Boolean),
            approach: el("planApproachInput").value.trim(),
        });

        el("planApproveBtn").addEventListener("click", () => {
            onRespond({ action: "approve", plan: readEditedPlan() });
            close();
        });
        el("planRegenerateBtn").addEventListener("click", () => {
            const feedback = el("planFeedbackInput").value.trim();
            onRespond({ action: "regenerate", feedback });
            setBody(`<p class="side-panel-spinner">${escapeHtml(t("plan.regenerating"))}</p>`);
        });
        el("planRejectBtn").addEventListener("click", () => {
            onRespond({ action: "reject" });
            close();
        });
    };

    // Called once per plan_proposal WS message — including regenerated
    // ones, so the panel just re-renders with the new proposal each time.
    const openPlanApproval = (proposal, onRespond) => {
        open("plan", t("plan.title"));
        renderPlanForm(proposal, onRespond);
    };

    const init = () => {
        el("sideOverlay").addEventListener("click", close);
        el("sidePanelClose").addEventListener("click", close);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && isOpen()) close();
        });
        const vetEntry = el("vetEntryBtn");
        if (vetEntry) vetEntry.addEventListener("click", () => openVet());
    };

    document.addEventListener("DOMContentLoaded", init);

    return { openExplain, openVet, openPlanApproval, close };
})();
window.AtlasPanel = AtlasPanel;

/* -------------------------------------------------- trust badge popover */
// Click-to-open replacement for the old `title` tooltip (Phần 1 #3). A
// single shared popover element positioned near whichever badge was
// clicked; content is read back off badge.dataset.trust (set by
// renderTrustBadge / history.js) so this works for badges created anywhere
// - live turn, reopened stored report, or a History list card - without a
// shared in-memory lookup keyed by DOM node.

const AtlasTrustPopover = (() => {
    const t = (k, v) => AtlasI18n.t(k, v);
    const el = (id) => document.getElementById(id);

    const TIER_COLOR_VAR = { high: "var(--green)", mid: "var(--amber)", low: "var(--red)" };

    const close = () => { el("trustPopover").classList.add("is-hidden"); };

    const buildRows = (categories, total) => (categories || []).map(({ label, count }) => {
        const pct = total ? Math.round((count / total) * 100) : 0;
        return `
            <div class="taxo-row">
                <span class="taxo-label">${AtlasShared.escapeHtml(label)}</span>
                <div class="taxo-bar-bg"><div class="taxo-bar-fill" style="width:${pct}%"></div></div>
                <span class="taxo-val">${count}</span>
            </div>
        `;
    }).join("");

    const open = (badge) => {
        let summary = null;
        try { summary = JSON.parse(badge.dataset.trust || "null"); } catch { /* malformed - just skip */ }
        if (!summary) return;

        const pop = el("trustPopover");
        const color = TIER_COLOR_VAR[summary.tier] || TIER_COLOR_VAR.low;
        const scoreLine = summary.avgScore === null ? summary.breakdown : `${summary.avgScore}/100`;
        pop.innerHTML = `
            <div class="tp-score" style="color:${color}">${AtlasShared.escapeHtml(String(scoreLine))}</div>
            <div class="tp-cat">${AtlasShared.escapeHtml(t("trust.popover.sources", { n: summary.count }))} · ${AtlasShared.escapeHtml(t(`trust.tier.${summary.tier}`))}</div>
            ${buildRows(summary.categories, summary.count)}
            <p class="tp-note">${AtlasShared.escapeHtml(t("trust.badge.tip", { n: summary.count }))}</p>
        `;
        pop.classList.remove("is-hidden");

        // Position after unhiding so getBoundingClientRect reflects real size;
        // flip above the badge if it would overflow the bottom of the viewport.
        const rect = badge.getBoundingClientRect();
        const popRect = pop.getBoundingClientRect();
        let left = rect.left;
        let top = rect.bottom + 8;
        if (left + popRect.width > window.innerWidth - 12) left = window.innerWidth - popRect.width - 12;
        if (top + popRect.height > window.innerHeight - 12) top = rect.top - popRect.height - 8;
        pop.style.left = `${Math.max(8, left)}px`;
        pop.style.top = `${Math.max(8, top)}px`;
    };

    const init = () => {
        // Capture phase: a trust badge can sit inside a clickable ancestor
        // (a History card that opens the stored report on click), so this
        // must intercept and stopPropagation() before that ancestor's own
        // bubble-phase listener ever runs, not after.
        document.addEventListener("click", (event) => {
            const badge = event.target.closest(".trust-badge");
            if (badge && !badge.classList.contains("is-hidden")) {
                event.stopPropagation();
                open(badge);
                return;
            }
            if (!event.target.closest("#trustPopover")) close();
        }, true);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") close();
        });
    };

    document.addEventListener("DOMContentLoaded", init);
    return { close };
})();
window.AtlasTrustPopover = AtlasTrustPopover;

/* -------------------------------------------------- research view */

const Atlas = (() => {
    const t = (k, v) => AtlasI18n.t(k, v);

    const MODE_LABEL_KEYS = {
        ask: "mode.ask", compare: "mode.compare", deep_dive: "mode.deep_dive",
    };
    const MODE_CLASSES = {
        ask: "ask", compare: "compare", deep_dive: "deep_dive",
    };

    const converter = AtlasShared.converter();
    const el = (id) => document.getElementById(id);

    let running = false;
    let currentTurn = null;
    let socket = null;
    let currentSessionId = null;   // one id per conversation; reset on New chat

    const genId = () => (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID()
        : "s-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);

    /* ---------- hero / new-session */

    const HERO_LINES = ["hero.1", "hero.2", "hero.3", "hero.4"];
    const CHIP_KEYS = ["chip.specdec", "chip.agenticrag", "chip.gpt5llama", "chip.moe", "chip.codingagents", "chip.longcontext"];

    const greetingKey = () => {
        const h = new Date().getHours();
        return h < 12 ? "greeting.morning" : h < 17 ? "greeting.afternoon" : "greeting.evening";
    };
    const pick = (arr, n) => arr.slice().sort(() => Math.random() - 0.5).slice(0, n);

    let heroLineKey = HERO_LINES[Math.floor(Math.random() * HERO_LINES.length)];
    let heroChipKeys = pick(CHIP_KEYS, 3);

    const renderHero = () => {
        el("heroGreeting").textContent = t(greetingKey());
        el("heroLine").textContent = t(heroLineKey);
        const wrap = el("starterChips");
        wrap.innerHTML = "";
        heroChipKeys.forEach((k) => {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "starter-chip";
            b.textContent = t(k);
            b.addEventListener("click", () => {
                el("task").value = t(k).replace(/^\S+\s/, "");
                submit();
            });
            wrap.appendChild(b);
        });
    };

    const showHero = (rotate) => {
        if (rotate) {
            heroLineKey = HERO_LINES[Math.floor(Math.random() * HERO_LINES.length)];
            heroChipKeys = pick(CHIP_KEYS, 3);
        }
        renderHero();
        el("heroState").classList.remove("is-hidden");
    };
    const hideHero = () => el("heroState").classList.add("is-hidden");

    const newChat = () => {
        if (socket && running) {
            try { socket.close(); } catch { /* ignore */ }
        }
        running = false;
        currentTurn = null;
        currentSessionId = null;
        el("thread").innerHTML = "";
        setComposerBusy(false);
        showHero(true);
        showTopbar();
        AtlasRouter.show("research");
        el("task").focus();
    };

    // Abort a streaming run: close the socket and mark the turn stopped.
    const abort = () => {
        if (socket) { try { socket.close(); } catch { /* ignore */ } }
        running = false;
        if (currentTurn && !currentTurn.finished) {
            currentTurn.finished = true;
            stopTimer(currentTurn);
            currentTurn.spinner.classList.add("done");
            currentTurn.stage.textContent = t("progress.stopped");
            currentTurn.stepsDis.removeAttribute("open");
            renderStatus(currentTurn, t("answer.stopped"));
            renderInto(currentTurn);   // paint whatever streamed before the stop
            if (currentTurn.markdown) currentTurn.copyBtn.disabled = false;
        }
        setComposerBusy(false);
    };

    /* ---------- progress stage mapping */

    const STAGE_RULES = [
        [/report/i, "stage.writing"],
        [/context/i, "stage.context"],
        [/sources kept|quality score|low-quality/i, "stage.ranking"],
        [/Scraping|Reading/i, "stage.reading"],
        [/^Searching|parallel search|^Found \d+ results|Added URL/i, "stage.searching"],
        [/quer(y|ies)/i, "stage.queries"],
        [/^Researching|Selected agent|Planning/i, "stage.planning"],
    ];
    const stageKeyFor = (line) => {
        for (const [pattern, key] of STAGE_RULES) {
            if (pattern.test(line)) return key;
        }
        return null;
    };

    // Per-stage icon + ordinal (for the activity-feed header + progress bar).
    const STAGE_META = {
        "stage.planning": { icon: "🧭", order: 1 },
        "stage.queries": { icon: "✏️", order: 2 },
        "stage.searching": { icon: "🔎", order: 3 },
        "stage.reading": { icon: "📖", order: 4 },
        "stage.ranking": { icon: "⚖️", order: 5 },
        "stage.context": { icon: "🧩", order: 6 },
        "stage.writing": { icon: "📝", order: 7 },
    };
    const STAGE_TOTAL = 7;
    const MODE_ICONS = { ask: "⚡", compare: "⚖", deep_dive: "🔬" };

    const fmtElapsed = (ms) => {
        const s = Math.max(0, Math.floor(ms / 1000));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };

    /* ---------- turn construction */

    const setBadge = (turn, mode, kind = "chat") => {
        if (kind === "daily_report") {
            turn.badge.textContent = t("badge.daily");
            turn.badge.className = "mode-badge daily";
            return;
        }
        turn.badge.textContent = t(MODE_LABEL_KEYS[mode] || "mode.compare");
        turn.badge.className = `mode-badge ${MODE_CLASSES[mode] || "compare"}`;
    };

    const createTurn = (task, mode) => {
        hideHero();
        const root = document.createElement("div");
        root.className = "turn";
        root.innerHTML = `
            <div class="bubble-user"></div>
            <article class="answer-block">
                <div class="answer-head">
                    <span class="mode-badge"></span>
                    <span class="trust-badge is-hidden"></span>
                    <div class="answer-actions">
                        <button type="button" class="btn btn-ghost answer-copy" disabled>${AtlasShared.escapeHtml(t("answer.copy"))}</button>
                        <a class="btn btn-ghost answer-pdf disabled" target="_blank" rel="noopener" href="#">${AtlasShared.escapeHtml(t("answer.pdf"))}</a>
                    </div>
                </div>
                <details class="disclosure steps-dis" open>
                    <summary>
                        <span class="spinner"></span>
                        <span class="step-icon" aria-hidden="true">🧭</span>
                        <span class="stage"></span>
                        <span class="steps-meta">
                            <span class="steps-count"></span>
                            <span class="steps-timer">0:00</span>
                        </span>
                    </summary>
                    <div class="steps-progress"><span class="steps-progress-fill"></span></div>
                    <div class="steps-body"></div>
                </details>
                <div class="answer-report report-content"></div>
                <div class="answer-error is-hidden"></div>
                <div class="refusal-card is-hidden"></div>
                <details class="disclosure sources-dis is-hidden"><summary></summary><div class="sources-body"></div></details>
                <details class="disclosure follow-dis is-hidden"><summary></summary><div class="follow-body"></div></details>
                <div class="answer-status"></div>
            </article>`;

        const turn = {
            root,
            bubble: root.querySelector(".bubble-user"),
            badge: root.querySelector(".mode-badge"),
            trustBadge: root.querySelector(".trust-badge"),
            copyBtn: root.querySelector(".answer-copy"),
            pdfLink: root.querySelector(".answer-pdf"),
            stepsDis: root.querySelector(".steps-dis"),
            stepsBody: root.querySelector(".steps-body"),
            spinner: root.querySelector(".spinner"),
            stepIcon: root.querySelector(".step-icon"),
            stage: root.querySelector(".stage"),
            stepsCount: root.querySelector(".steps-count"),
            stepsTimer: root.querySelector(".steps-timer"),
            progressFill: root.querySelector(".steps-progress-fill"),
            reportEl: root.querySelector(".answer-report"),
            errorEl: root.querySelector(".answer-error"),
            refusalEl: root.querySelector(".refusal-card"),
            sourcesDis: root.querySelector(".sources-dis"),
            sourcesSummary: root.querySelector(".sources-dis summary"),
            sourcesBody: root.querySelector(".sources-body"),
            followDis: root.querySelector(".follow-dis"),
            followSummary: root.querySelector(".follow-dis summary"),
            followBody: root.querySelector(".follow-body"),
            statusEl: root.querySelector(".answer-status"),
            markdown: "",
            sourceCount: 0,
            scrapeCount: 0,
            followCount: 0,
            refused: false,
            finished: false,
            mode,
            kind: "chat",
            qualityData: null,
            evalData: null,
            statusBase: "",
            startTime: Date.now(),
            timer: null,
        };

        turn.bubble.textContent = task;
        turn.stage.textContent = t("progress.start");
        setBadge(turn, mode);
        turn.copyBtn.addEventListener("click", () => copyTurn(turn));

        // Live elapsed timer in the process-feed header.
        turn.timer = setInterval(() => {
            if (turn.stepsTimer) turn.stepsTimer.textContent = fmtElapsed(Date.now() - turn.startTime);
        }, 1000);

        el("thread").appendChild(root);
        root.scrollIntoView({ behavior: "smooth", block: "start" });
        return turn;
    };

    const stopTimer = (turn) => {
        if (turn && turn.timer) { clearInterval(turn.timer); turn.timer = null; }
    };

    /* ---------- per-turn renderers */

    let renderTimer = null;
    const renderInto = (turn) => {
        if (turn) turn.reportEl.innerHTML = converter.makeHtml(turn.markdown);
    };
    const renderReport = () => { renderTimer = null; renderInto(currentTurn); };
    const queueRender = () => {
        // setTimeout (not requestAnimationFrame) so streaming still renders when the
        // tab is offscreen/throttled; finishRun() also flushes a final render.
        if (renderTimer) return;
        renderTimer = setTimeout(renderReport, 60);
    };

    const handleReportMessage = (data) => {
        if (!currentTurn) return;
        if (data.replace) currentTurn.markdown = data.output ?? "";
        else currentTurn.markdown += data.output ?? "";
        if (currentTurn.refused) return;
        queueRender();
    };

    // Compact display names for the trust badge's category breakdown text
    // (e.g. "2 official · 1 arxiv"). Falls back to the raw category key for
    // any taxonomy value not listed here, so a future source_scorer category
    // never breaks the badge (Mục 8.2: "nguồn không khớp category nào").
    const renderTrustBadge = (turn, sources) => {
        const summary = AtlasShared.computeTrustSummary(sources);
        if (!summary) { turn.trustBadge.classList.add("is-hidden"); return; }
        turn.trustBadge.className = `trust-badge trust-${summary.tier}`;
        turn.trustBadge.textContent = summary.avgScore === null ? summary.breakdown : `${summary.avgScore} · ${summary.breakdown}`;
        // Popover reads the summary back off the element itself (Task 4) -
        // works for badges created anywhere (live turn, History cards)
        // without needing a shared in-memory lookup keyed by DOM node.
        turn.trustBadge.dataset.trust = JSON.stringify(summary);
    };

    const renderSources = (turn, sources) => {
        renderTrustBadge(turn, sources);
        turn.sourcesBody.innerHTML = "";
        if (!Array.isArray(sources) || sources.length === 0) {
            turn.sourcesBody.innerHTML = `<p class="empty-note">${AtlasShared.escapeHtml(t("sources.empty"))}</p>`;
            turn.sourceCount = 0;
        } else {
            turn.sourceCount = sources.length;
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
                // Sources saved before the snippet field existed (older
                // history entries) have nothing to explain — disable rather
                // than send a blank passage to /api/explain (Mục 8.2:
                // "claim/passage rỗng → disable nút thay vì lỗi 400").
                if (source.snippet) {
                    const explainBtn = document.createElement("button");
                    explainBtn.type = "button";
                    explainBtn.className = "source-explain-btn";
                    explainBtn.textContent = t("explain.btn");
                    explainBtn.title = t("explain.btn.tip");
                    explainBtn.addEventListener("click", () => {
                        if (window.AtlasPanel) window.AtlasPanel.openExplain(source.snippet, source.title || "");
                    });
                    meta.appendChild(explainBtn);
                }
                item.appendChild(link);
                item.appendChild(meta);
                turn.sourcesBody.appendChild(item);
            });
        }
        turn.sourcesSummary.dataset.count = String(turn.sourceCount);
        turn.sourcesSummary.textContent = `${t("answer.sources")} · ${turn.sourceCount}`;
        turn.sourcesDis.classList.remove("is-hidden");
    };

    const renderFollowups = (turn, questions) => {
        turn.followBody.innerHTML = "";
        if (!Array.isArray(questions) || questions.length === 0) {
            turn.followBody.innerHTML = `<p class="empty-note">${AtlasShared.escapeHtml(t("followups.empty"))}</p>`;
            turn.followCount = 0;
        } else {
            turn.followCount = questions.length;
            questions.forEach((question) => {
                const div = document.createElement("div");
                div.className = "suggested-question";
                div.textContent = question;
                div.addEventListener("click", () => {
                    el("task").value = question;
                    AtlasRouter.show("research");
                    autoResize();
                    el("task").focus();
                });
                turn.followBody.appendChild(div);
            });
        }
        turn.followSummary.dataset.count = String(turn.followCount);
        turn.followSummary.textContent = `${t("answer.followups")} · ${turn.followCount}`;
        turn.followDis.classList.remove("is-hidden");
    };

    // Re-localize labels inside already-rendered turns when the language changes.
    const relocalizeTurns = () => {
        document.querySelectorAll("#thread .answer-copy").forEach((b) => { b.textContent = t("answer.copy"); });
        document.querySelectorAll("#thread .answer-pdf").forEach((a) => { a.textContent = t("answer.pdf"); });
        document.querySelectorAll("#thread .sources-dis summary").forEach((s) => {
            const c = s.dataset.count;
            s.textContent = c ? `${t("answer.sources")} · ${c}` : t("answer.sources");
        });
        document.querySelectorAll("#thread .follow-dis summary").forEach((s) => {
            const c = s.dataset.count;
            s.textContent = c ? `${t("answer.followups")} · ${c}` : t("answer.followups");
        });
        document.querySelectorAll("#thread .quality-chip.grounding").forEach((chip) => {
            const { qv, qg, qc, qs } = chip.dataset;
            chip.textContent = t("quality.grounding", { verdict: qv, g: qg, c: qc });
            chip.title = t("quality.grounding.tip", { g: qg, c: qc, score: qs });
        });
        document.querySelectorAll("#thread .quality-chip.evalc").forEach((chip) => {
            chip.textContent = t("quality.eval", { score: chip.dataset.es, label: chip.dataset.el });
            chip.title = t("quality.eval.tip");
        });
        // Trust badges no longer carry a title tooltip - the popover (built
        // fresh from dataset.trust on each click) replaces it, so there is
        // nothing here to re-localize.
    };

    // Build the quality chips (grounding + optional evaluation) from a turn's
    // stored data. Numbers live in data-* so labels can be re-localized later.
    const buildQualityChips = (turn) => {
        const chips = [];
        if (turn.qualityData) {
            const { passed, g, c, score } = turn.qualityData;
            const verdict = passed ? "✓" : "⚠";
            const chip = document.createElement("span");
            chip.className = `quality-chip grounding ${passed ? "ok" : "warn"}`;
            chip.dataset.qv = verdict; chip.dataset.qg = g; chip.dataset.qc = c; chip.dataset.qs = score;
            chip.textContent = t("quality.grounding", { verdict, g, c });
            chip.title = t("quality.grounding.tip", { g, c, score });
            chips.push(chip);
        }
        if (turn.evalData) {
            const { score, label } = turn.evalData;
            const chip = document.createElement("span");
            chip.className = "quality-chip evalc";
            chip.dataset.es = score; chip.dataset.el = label;
            chip.textContent = t("quality.eval", { score, label });
            chip.title = t("quality.eval.tip");
            chips.push(chip);
        }
        return chips;
    };

    const renderStatus = (turn, baseText) => {
        if (baseText != null) turn.statusBase = baseText;
        turn.statusEl.textContent = turn.statusBase || "";
        buildQualityChips(turn).forEach((chip) => {
            turn.statusEl.appendChild(document.createTextNode(" "));
            turn.statusEl.appendChild(chip);
        });
    };

    const renderQualityCheck = (turn, payload) => {
        if (!payload || typeof payload !== "object") return;
        turn.qualityData = {
            passed: Boolean(payload.passed),
            g: payload.grounded_url_count,
            c: payload.context_url_count,
            score: payload.score,
        };
        renderStatus(turn);
    };

    const renderEvaluation = (turn, payload) => {
        if (!payload || typeof payload !== "object" || payload.error) return;
        turn.evalData = { score: Number(payload.overall_score).toFixed(2), label: payload.label };
        renderStatus(turn);
    };

    const showRefusal = (turn, markdown) => {
        turn.refused = true;
        turn.refusalEl.innerHTML = `<div class="mode-badge daily" style="margin-bottom:8px">${AtlasShared.escapeHtml(t("refusal.title"))}</div>` + converter.makeHtml(markdown ?? "");
        turn.refusalEl.classList.remove("is-hidden");
        turn.reportEl.classList.add("is-hidden");
    };

    const showError = (turn, message) => {
        if (!turn) return;
        stopTimer(turn);
        turn.errorEl.textContent = message;
        turn.errorEl.classList.remove("is-hidden");
        turn.spinner.classList.add("done");
        turn.stepsDis.removeAttribute("open");
        setComposerBusy(false);
        running = false;
        if (window.AtlasToast) AtlasToast.error(message);
    };

    const finishRun = (turn) => {
        turn.finished = true;
        running = false;
        stopTimer(turn);
        renderInto(turn);   // guarantee the final report is painted (rAF-independent)
        turn.spinner.classList.add("done");
        turn.stage.textContent = t("progress.done");
        if (turn.progressFill) turn.progressFill.style.width = "100%";
        if (!turn.refused) {
            renderStatus(turn, t("answer.complete"));
            turn.copyBtn.disabled = false;
        }
        setComposerBusy(false);
        turn.stepsDis.removeAttribute("open");   // collapse the process steps when done
    };

    /* ---------- composer */

    const autoResize = () => {
        const ta = el("task");
        ta.style.height = "auto";
        ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    };

    const setComposerBusy = (busy) => {
        const send = el("sendBtn");
        if (busy) {
            // running → show a clickable Stop control
            send.disabled = false;
            send.classList.add("stop");
            send.innerHTML = '<span class="stop-sq"></span>';
            send.setAttribute("title", t("composer.stop.tip"));
        } else {
            send.classList.remove("stop");
            send.innerHTML = "↑";
            send.disabled = el("task").value.trim() === "";
            send.setAttribute("title", t("composer.send.tip"));
        }
    };

    /* ---------- websocket run */

    const submit = () => {
        if (running) return;
        const task = el("task").value.trim();
        if (!task) return;
        const mode = el("reportType").value || "ask";

        if (!currentSessionId) currentSessionId = genId();   // start/continue a conversation

        running = true;
        currentTurn = createTurn(task, mode);
        setComposerBusy(true);

        el("task").value = "";
        autoResize();

        const { protocol, host } = window.location;
        const token = window.localStorage.getItem("atlas_auth_token");
        const authQuery = token ? `?token=${encodeURIComponent(token)}` : "";
        const wsUri = `${protocol === "https:" ? "wss:" : "ws:"}//${host}/ws${authQuery}`;

        const turn = currentTurn;
        socket = new WebSocket(wsUri);

        socket.onopen = () => {
            socket.send(`start ${JSON.stringify({ task, report_type: mode, agent: "Auto Agent", session_id: currentSessionId })}`);
        };

        socket.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch { return; }
            switch (data.type) {
                case "logs": {
                    const line = String(data.output ?? "").trim();
                    if (line) {
                        const div = document.createElement("div");
                        div.className = "step-line";
                        div.textContent = line;
                        turn.stepsBody.appendChild(div);
                        turn.stepsBody.scrollTop = turn.stepsBody.scrollHeight;
                        if (/Added URL/i.test(line)) {
                            turn.scrapeCount += 1;
                            turn.stepsCount.textContent = `${turn.scrapeCount} ${t("stage.sources")}`;
                        }
                    }
                    const key = stageKeyFor(line);
                    if (key) {
                        turn.stage.textContent = t(key);
                        const meta = STAGE_META[key];
                        if (meta) {
                            turn.stepIcon.textContent = meta.icon;
                            turn.progressFill.style.width = Math.round((meta.order / STAGE_TOTAL) * 100) + "%";
                        }
                    }
                    break;
                }
                case "report": handleReportMessage(data); break;
                case "plan_proposal": {
                    const proposal = data.output || {};
                    AtlasPanel.openPlanApproval(proposal, (response) => {
                        if (socket && socket.readyState === WebSocket.OPEN) {
                            socket.send("plan_response " + JSON.stringify({ ...response, run_id: proposal.run_id }));
                        }
                    });
                    break;
                }
                case "sources": renderSources(turn, data.output); break;
                case "refusal": showRefusal(turn, data.output); break;
                case "suggested_questions": renderFollowups(turn, data.output); break;
                case "quality_check": renderQualityCheck(turn, data.output); break;
                case "evaluation": renderEvaluation(turn, data.output); break;
                case "history_id":
                    if (window.AtlasHistory) AtlasHistory.setCurrentHistoryId(data.output);
                    break;
                case "path": {
                    if (data.output) {
                        turn.pdfLink.href = data.output;
                        turn.pdfLink.classList.remove("disabled");
                    }
                    finishRun(turn);
                    break;
                }
                case "error": showError(turn, data.output || t("error.rejected")); break;
                default: break;
            }
        };

        socket.onclose = () => {
            if (running && !turn.finished) showError(turn, t("error.connlost"));
        };
        socket.onerror = () => {
            if (running && !turn.finished) showError(turn, t("error.unreachable"));
        };
    };

    /* ---------- stored entries (history / automation) */

    // Render one stored history entry as a read-only thread turn (appends; does not clear).
    const buildStoredTurn = (entry) => {
        const isDaily = entry.kind === "daily_report";
        const title = isDaily ? (entry.query || t("badge.daily")) : (entry.query || "(untitled)");
        const turn = createTurn(title, entry.mode);
        stopTimer(turn);                            // stored entries have no live run
        turn.kind = entry.kind || "chat";
        turn.finished = true;
        setBadge(turn, entry.mode, turn.kind);
        turn.stepsDis.classList.add("is-hidden");   // no live process for stored entries

        turn.markdown = entry.report || "*This entry has no stored report.*";
        renderInto(turn);

        turn.statusEl.textContent = `${t("stored.loaded")} · ${AtlasShared.timeAgo(entry.timestamp)}`;
        turn.copyBtn.disabled = false;
        if (entry.pdf_path) {
            turn.pdfLink.href = entry.pdf_path;
            turn.pdfLink.classList.remove("disabled");
        }
        renderFollowups(turn, entry.suggested_questions || []);
        // Entries saved before sources_json existed (or with no ranked sources
        // for that run) render the same "no sources" state as a live 0-source
        // run — Mục 8.2 treats both as "hide badge", not a distinct error.
        renderSources(turn, entry.sources || []);
        return turn;
    };

    const resetForStored = () => {
        if (socket && running) { try { socket.close(); } catch { /* ignore */ } }
        running = false;
        currentTurn = null;
        el("thread").innerHTML = "";
        hideHero();
        showTopbar();
        setComposerBusy(false);
    };

    // Single stored entry (e.g. a daily report, or a standalone chat).
    const displayStoredReport = (entry) => {
        resetForStored();
        buildStoredTurn(entry);
        currentSessionId = entry.session_id || null;   // continue the session if it has one
        AtlasRouter.show("research");
    };

    // A whole conversation: render every turn oldest→newest, then continue it.
    const displayStoredSession = (entries) => {
        resetForStored();
        entries.forEach(buildStoredTurn);
        currentSessionId = (entries[0] && entries[0].session_id) || null;
        AtlasRouter.show("research");
        const sc = document.querySelector(".thread-scroll");
        if (sc) sc.scrollTop = sc.scrollHeight;
    };

    /* ---------- clipboard */

    const copyTurn = (turn) => {
        const text = turn.reportEl.innerText;
        const done = () => { turn.statusEl.textContent = t("answer.copied"); };
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

    /* ---------- mode selector (in-composer popover, Gemini-style) */

    const setMode = (mode) => {
        const safe = MODE_ICONS[mode] ? mode : "ask";
        el("reportType").value = safe;
        el("modeBtnIcon").textContent = MODE_ICONS[safe];
        el("modeBtnLabel").textContent = t(`mode.${safe}`);
        document.querySelectorAll("#modePopover .mode-option").forEach((opt) => {
            opt.setAttribute("aria-selected", opt.dataset.mode === safe ? "true" : "false");
        });
    };

    const initModeSelect = () => {
        const btn = el("modeBtn");
        const pop = el("modePopover");
        if (!btn || !pop) return;
        const isOpen = () => btn.getAttribute("aria-expanded") === "true";
        const setOpen = (open) => {
            pop.classList.toggle("is-hidden", !open);
            btn.setAttribute("aria-expanded", open ? "true" : "false");
        };
        btn.addEventListener("click", (event) => { event.stopPropagation(); setOpen(!isOpen()); });
        pop.querySelectorAll(".mode-option").forEach((opt) => {
            opt.addEventListener("click", () => { setMode(opt.dataset.mode); setOpen(false); btn.focus(); });
        });
        document.addEventListener("click", (event) => {
            if (isOpen() && !pop.contains(event.target) && !btn.contains(event.target)) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && isOpen()) { setOpen(false); btn.focus(); }
        });
        setMode(el("reportType").value || "ask");
    };

    /* ---------- auto-hiding top bar (reveal on scroll up, hide on scroll down) */

    const showTopbar = () => {
        const tb = document.querySelector(".topbar");
        if (tb) tb.classList.remove("topbar--hidden");
    };

    const initTopbarAutoHide = () => {
        const tb = document.querySelector(".topbar");
        if (!tb) return;
        const containers = [document.querySelector(".thread-scroll"), ...document.querySelectorAll(".page")];
        const last = new WeakMap();
        containers.forEach((container) => {
            if (!container) return;
            container.addEventListener("scroll", () => {
                const y = container.scrollTop;
                const prev = last.get(container) || 0;
                if (y > prev && y > 80) tb.classList.add("topbar--hidden");
                else if (y < prev) tb.classList.remove("topbar--hidden");
                last.set(container, y);
            }, { passive: true });
        });
        document.querySelectorAll(".nav-tab").forEach((tab) => tab.addEventListener("click", showTopbar));
    };

    /* ---------- init */

    const init = () => {
        AtlasRouter.init();
        if (window.AtlasI18n) AtlasI18n.applyLang(AtlasI18n.getLang());
        if (window.AtlasTheme) AtlasTheme.apply(AtlasTheme.getTheme());
        initModeSelect();
        initTopbarAutoHide();
        renderHero();

        el("langToggle").addEventListener("click", () => AtlasI18n.toggle());
        el("themeToggle").addEventListener("click", () => AtlasTheme.toggle());
        el("newChat").addEventListener("click", newChat);

        window.addEventListener("offline", () => {
            if (window.AtlasToast) AtlasToast.warning(t("toast.offline"));
        });

        el("composerForm").addEventListener("submit", (event) => {
            event.preventDefault();
            if (running) abort();   // the send button acts as Stop while a run streams
            else submit();
        });

        const ta = el("task");
        ta.addEventListener("input", () => { autoResize(); setComposerBusy(running); });
        ta.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                submit();
            }
        });

        document.addEventListener("atlas:langchange", () => {
            setMode(el("reportType").value || "ask");
            relocalizeTurns();
            if (!el("heroState").classList.contains("is-hidden")) renderHero();
        });

        setComposerBusy(false);
    };

    document.addEventListener("DOMContentLoaded", init);

    return { submit, displayStoredReport, displayStoredSession, newChat };
})();

window.Atlas = Atlas;
