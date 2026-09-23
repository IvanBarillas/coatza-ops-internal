(function () {
    "use strict";

    const NAV_SELECTOR = "[data-bottom-nav]";
    const TAB_SELECTOR = "[data-bottom-nav-path]";
    const TOGGLE_SELECTOR = "[data-modules-toggle]";
    const SHEET_SELECTOR = "#mobile-modules-sheet";

    function normalizePath(value) {
        let pathname;

        try {
            pathname = new URL(value || window.location.href, window.location.origin).pathname;
        } catch (_error) {
            pathname = window.location.pathname;
        }

        pathname = pathname.replace(/\/{2,}/g, "/");

        if (pathname.length > 1 && !pathname.endsWith("/")) {
            pathname += "/";
        }

        return pathname;
    }

    function tabMatches(tab, currentPath) {
        const tabPath = normalizePath(tab.dataset.bottomNavPath);

        if (tab.dataset.bottomNavMatch === "prefix") {
            return currentPath.startsWith(tabPath);
        }

        return currentPath === tabPath;
    }

    function markCurrent(path) {
        const currentPath = normalizePath(path);

        document.querySelectorAll(NAV_SELECTOR + " " + TAB_SELECTOR).forEach(function (tab) {
            if (tabMatches(tab, currentPath)) {
                tab.setAttribute("aria-current", "page");
            } else {
                tab.removeAttribute("aria-current");
            }
        });
    }

    function sheet() {
        return document.querySelector(SHEET_SELECTOR);
    }

    function isOpen() {
        const element = sheet();
        return Boolean(element) && !element.hidden;
    }

    function setOpen(open) {
        const element = sheet();

        if (!element) {
            return;
        }

        element.hidden = !open;
        document.documentElement.classList.toggle("overflow-hidden", open);
        document.querySelectorAll(TOGGLE_SELECTOR).forEach(function (toggle) {
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });

        // Con la hoja abierta solo "Módulos" queda resaltado; al cerrar se restaura la página actual.
        if (open) {
            document.querySelectorAll(NAV_SELECTOR + " " + TAB_SELECTOR).forEach(function (tab) {
                tab.removeAttribute("aria-current");
            });
        } else {
            markCurrent(window.location.href);
        }
    }

    function synchronize(path) {
        markCurrent(path || window.location.href);
        setOpen(false);
    }

    document.addEventListener("click", function (event) {
        const target = event.target;

        if (!target || !target.closest) {
            return;
        }

        if (target.closest(TOGGLE_SELECTOR)) {
            setOpen(!isOpen());
            return;
        }

        if (target.closest("[data-modules-close]")) {
            setOpen(false);
            return;
        }

        // Cualquier enlace del panel cierra la hoja: vive fuera de #workbench y
        // HTMX no la reemplaza, así que se quedaría abierta sobre la página nueva.
        if (target.closest(SHEET_SELECTOR + " a[href]")) {
            setOpen(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
        }
    });

    document.addEventListener("DOMContentLoaded", function () {
        markCurrent(window.location.href);
    });

    document.body.addEventListener("htmx:beforeRequest", function () {
        setOpen(false);
    });
    document.body.addEventListener("htmx:pushedIntoHistory", function (event) {
        const detail = event.detail || {};
        synchronize(detail.path || detail.url);
    });
    document.body.addEventListener("htmx:replacedInHistory", function (event) {
        const detail = event.detail || {};
        synchronize(detail.path || detail.url);
    });
    document.body.addEventListener("htmx:historyRestore", function (event) {
        const detail = event.detail || {};
        synchronize(detail.path || detail.url);
    });
    document.body.addEventListener("htmx:afterSwap", function () {
        markCurrent(window.location.href);
    });
    window.addEventListener("popstate", function () {
        synchronize(window.location.href);
    });

    window.AxentraBottomNav = {
        synchronize: synchronize,
        close: function () {
            setOpen(false);
        },
    };
})();
