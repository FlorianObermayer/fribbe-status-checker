// Shared dark mode / theme management.
// Loaded by all pages. The FOUC-prevention inline script in each HTML <head>
// already applies the class before first paint; this module wires up the
// toggle button and the system-preference change listener.

function applyTheme(isDark) {
    if (isDark) {
        document.documentElement.classList.add('dark-mode');
    } else {
        document.documentElement.classList.remove('dark-mode');
    }
}

function setupThemeToggle() {
    // Sync with whatever the inline FOUC script already applied.
    const stored = localStorage.getItem('theme');
    const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(stored === 'dark' || (!stored && systemDark));

    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.addEventListener('click', () => {
            const newDark = !document.documentElement.classList.contains('dark-mode');
            localStorage.setItem('theme', newDark ? 'dark' : 'light');
            applyTheme(newDark);
        });
    }

    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            if (!localStorage.getItem('theme')) {
                applyTheme(e.matches);
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', setupThemeToggle);
