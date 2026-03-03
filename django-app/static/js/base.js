// Hamburger toggle
const toggle = document.getElementById('menuToggle');
const collapse = document.getElementById('navCollapse');
if (toggle && collapse) {
    toggle.addEventListener('click', () => {
        toggle.classList.toggle('open');
        collapse.classList.toggle('open');
    });
    // Close menu when a nav link is tapped on mobile
    collapse.querySelectorAll('nav a').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                toggle.classList.remove('open');
                collapse.classList.remove('open');
            }
        });
    });
}
