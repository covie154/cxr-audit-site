import './widgets/boot.mjs';
import { registry } from './widgets/registry.mjs';

let failed = false;

// Frozen payloads only: printing never fetches data or restores page preferences.
for (const card of document.querySelectorAll('[data-print-widget]')) {
    const mount = card.querySelector('[data-export-mount]');
    if (!mount) { continue; }
    const fallback = card.querySelector('[data-export-fallback]');
    try {
        const payload = JSON.parse(card.querySelector('script[type="application/json"]').textContent);
        const instance = registry.render(card.dataset.type, mount, payload, {
            primaryOnly: card.dataset.type === 'value', measurement: card.dataset.measurement, hideCaption: true
        });
        if (instance.chart) { instance.chart.setOption({ animation: false }); }
        fallback.hidden = true;
    } catch (error) {
        failed = true;
        mount.hidden = true;
        fallback.hidden = false;
    }
}


const button = document.querySelector('[data-print-button]');
const status = document.querySelector('[data-print-status]');
if (button) {
    button.disabled = failed;
    button.addEventListener('click', () => window.print());
}
if (status) {
    status.textContent = failed ? 'A card could not be displayed. Reload the report before printing.' : '';
}
document.documentElement.dataset.printReady = failed ? 'error' : 'true';
