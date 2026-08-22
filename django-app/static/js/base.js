(() => {
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