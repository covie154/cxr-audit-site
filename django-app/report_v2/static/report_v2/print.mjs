import './widgets/boot.mjs';
import { registry } from './widgets/registry.mjs';

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
        mount.hidden = true;
        fallback.hidden = false;
    }
}
