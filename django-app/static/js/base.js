(() => {
    const themeToggle = document.getElementById('themeToggle');
    const themeColor = document.getElementById('themeColor');
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');

    function savedTheme() {
        try { return localStorage.getItem('primer-theme'); } catch (error) { return null; }
    }

    function setTheme(theme, persist = false) {
        const isDark = theme === 'dark';
        document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
        document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';
        if (themeToggle) {
            themeToggle.setAttribute('aria-checked', String(isDark));
            themeToggle.setAttribute('aria-label', isDark ? 'Use light theme' : 'Use dark theme');
            const label = themeToggle.querySelector('.theme-label');
            if (label) label.textContent = isDark ? 'Light mode' : 'Dark mode';
        }
        if (themeColor) themeColor.content = isDark ? '#101821' : '#F4F6F9';
        if (persist) {
            try { localStorage.setItem('primer-theme', isDark ? 'dark' : 'light'); } catch (error) { /* Storage may be unavailable. */ }
        }
    }

    setTheme(document.documentElement.dataset.theme);
    themeToggle?.addEventListener('click', () => {
        setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
    });
    systemTheme.addEventListener('change', (event) => {
        if (!savedTheme()) setTheme(event.matches ? 'dark' : 'light');
    });

    const toggle = document.getElementById('menuToggle');
    const navigation = document.getElementById('primaryNavigation');
    const backdrop = document.getElementById('navBackdrop');
    const mobileQuery = window.matchMedia('(max-width: 900px)');

    if (!toggle || !navigation || !backdrop) return;

    const isOpen = () => navigation.classList.contains('is-open');

    function setOpen(open, returnFocus = false) {
        navigation.classList.toggle('is-open', open);
        backdrop.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', String(open));
        backdrop.tabIndex = open ? 0 : -1;
        document.body.classList.toggle('nav-open', open);

        if (open) {
            const activeLink = navigation.querySelector('[aria-current="page"]');
            const firstLink = navigation.querySelector('a, button');
            (activeLink || firstLink)?.focus();
        } else if (returnFocus) {
            toggle.focus();
        }
    }

    toggle.addEventListener('click', () => setOpen(!isOpen(), isOpen()));
    backdrop.addEventListener('click', () => setOpen(false, true));

    navigation.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', () => {
            if (mobileQuery.matches) setOpen(false);
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && isOpen()) {
            setOpen(false, true);
        }
    });

    mobileQuery.addEventListener('change', (event) => {
        if (!event.matches && isOpen()) setOpen(false);
    });
})();
