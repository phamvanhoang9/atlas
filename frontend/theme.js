/** ATLAS light/dark theme. Default dark; choice persisted. */
const AtlasTheme = (() => {
    const KEY = "atlas_theme";

    let current = (() => {
        const saved = window.localStorage.getItem(KEY);
        return saved === "light" || saved === "dark" ? saved : "dark";
    })();

    const apply = (theme) => {
        if (theme === "light" || theme === "dark") current = theme;
        window.localStorage.setItem(KEY, current);
        document.documentElement.setAttribute("data-theme", current);
        const btn = document.getElementById("themeToggle");
        if (btn) btn.textContent = current === "dark" ? "☀" : "☾"; // sun when dark, moon when light
    };

    const toggle = () => apply(current === "dark" ? "light" : "dark");

    return { apply, toggle, getTheme: () => current };
})();
window.AtlasTheme = AtlasTheme;
// Apply ASAP to avoid a flash of the wrong theme.
document.documentElement.setAttribute(
    "data-theme",
    window.localStorage.getItem("atlas_theme") === "light" ? "light" : "dark"
);
