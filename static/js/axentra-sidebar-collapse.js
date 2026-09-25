(function () {
    "use strict";

    const STORAGE_KEY = "axentra.moduleSidebar";
    const ATTRIBUTE = "moduleSidebar";
    const TOGGLE_SELECTOR = "[data-axentra-sidebar-toggle]";
    const LINK_SELECTOR = "#module-sidebar a[href]";
    const AUTO_TITLE = "data-axentra-auto-title";

    function isCollapsed() {
        return document.documentElement.dataset[ATTRIBUTE] === "collapsed";
    }

    function persist(collapsed) {
        try {
            if (collapsed) {
                window.localStorage.setItem(STORAGE_KEY, "collapsed");
            } else {
                window.localStorage.removeItem(STORAGE_KEY);
            }
        } catch (_error) {
            // Sin almacenamiento: el estado dura solo mientras no se recargue.
        }
    }

    // Contraído, el texto de los enlaces no se ve: el título nativo lo sustituye.
    function syncLinkTitles(collapsed) {
        document.querySelectorAll(LINK_SELECTOR).forEach(function (link) {
            if (collapsed) {
                if (!link.hasAttribute("title")) {
                    const label = link.textContent.replace(/\s+/g, " ").trim();
                    if (label) {
                        link.setAttribute("title", label);
                        link.setAttribute(AUTO_TITLE, "");
                    }
                }
            } else if (link.hasAttribute(AUTO_TITLE)) {
                link.removeAttribute("title");
                link.removeAttribute(AUTO_TITLE);
            }
        });
    }

    function syncToggle(collapsed) {
        const label = collapsed ? "Expandir menú lateral" : "Contraer menú lateral";

        document.querySelectorAll(TOGGLE_SELECTOR).forEach(function (button) {
            button.setAttribute("aria-expanded", collapsed ? "false" : "true");
            button.setAttribute("aria-label", label);
            button.setAttribute("title", label);
        });
    }

    function apply() {
        const collapsed = isCollapsed();

        syncToggle(collapsed);
        syncLinkTitles(collapsed);
    }

    // Charts y tablas necesitan recalcular su ancho cuando termina la transición.
    function notifyResize() {
        window.setTimeout(function () {
            window.dispatchEvent(new Event("resize"));
        }, 220);
    }

    function toggle() {
        const collapsed = !isCollapsed();

        if (collapsed) {
            document.documentElement.dataset[ATTRIBUTE] = "collapsed";
        } else {
            delete document.documentElement.dataset[ATTRIBUTE];
        }

        persist(collapsed);
        apply();
        notifyResize();
    }

    document.addEventListener("click", function (event) {
        const button = event.target.closest && event.target.closest(TOGGLE_SELECTOR);

        if (button) {
            toggle();
        }
    });

    document.addEventListener("DOMContentLoaded", apply);
    document.body.addEventListener("htmx:afterSwap", apply);
    document.body.addEventListener("htmx:historyRestore", apply);

    window.AxentraSidebarCollapse = { toggle: toggle, isCollapsed: isCollapsed };
})();
