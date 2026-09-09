(() => {
    'use strict';

    const containers = document.querySelectorAll('[data-report-chart]');
    if (!window.echarts) {
        document.getElementById('chartStatus').textContent = 'Charts could not load. Reload the page to try again.';
        return;
    }
    // Each section owns an ECharts instance; add section-specific options as reports evolve.
    const charts = Array.from(containers, (container) => window.echarts.init(container));
    function render() {
        const styles = getComputedStyle(document.documentElement);
        charts.forEach((chart) => chart.setOption({
            animation: false,
            graphic: [{
                type: 'text', left: 'center', top: 'middle',
                style: {
                    text: 'Your report charts will appear here',
                    fill: styles.getPropertyValue('--c-text-muted').trim(),
                    font: '14px sans-serif'
                }
            }]
        }));
    }
    render();
    const resizeObserver = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
    containers.forEach((container) => resizeObserver.observe(container));
    const themeObserver = new MutationObserver(render);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
