/**
 * ATLAS toast notifications — lightweight, dependency-free.
 *
 * Modeled on ChatGPT/Gemini: a top-right stack of dismissible cards for
 * transient errors, warnings, successes, and info. Errors are announced
 * assertively and persist longer; everything auto-dismisses.
 *
 * Usage: AtlasToast.error("Lost connection"); AtlasToast.show({type, message, timeout}).
 */
const AtlasToast = (() => {
    const ICONS = { error: "⚠", warning: "⚠", success: "✓", info: "ℹ" };
    const DEFAULT_TIMEOUT = { error: 8000, warning: 6000, success: 4000, info: 5000 };

    const host = () => document.getElementById("toastHost");

    const dismiss = (node) => {
        if (!node || node.dataset.leaving) return;
        node.dataset.leaving = "1";
        node.classList.add("toast--leaving");
        node.addEventListener("transitionend", () => node.remove(), { once: true });
        // Fallback removal in case the transition never fires.
        setTimeout(() => node.remove(), 400);
    };

    const show = ({ type = "info", message = "", timeout } = {}) => {
        const root = host();
        if (!root || !message) return null;

        const node = document.createElement("div");
        node.className = `toast toast--${type}`;
        node.setAttribute("role", type === "error" ? "alert" : "status");
        node.setAttribute("aria-live", type === "error" ? "assertive" : "polite");

        const icon = document.createElement("span");
        icon.className = "toast-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = ICONS[type] || ICONS.info;

        const text = document.createElement("span");
        text.className = "toast-msg";
        text.textContent = message;

        const close = document.createElement("button");
        close.type = "button";
        close.className = "toast-close";
        close.setAttribute("aria-label", "Dismiss");
        close.textContent = "×";
        close.addEventListener("click", () => dismiss(node));

        node.append(icon, text, close);
        root.appendChild(node);
        // Force reflow so the entrance transition runs.
        void node.offsetWidth;
        node.classList.add("toast--in");

        const ms = timeout != null ? timeout : (DEFAULT_TIMEOUT[type] || 5000);
        if (ms > 0) setTimeout(() => dismiss(node), ms);
        return node;
    };

    const make = (type) => (message, opts = {}) => show({ type, message, ...opts });

    return { show, dismiss, error: make("error"), warning: make("warning"), success: make("success"), info: make("info") };
})();
window.AtlasToast = AtlasToast;
