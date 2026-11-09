import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../static/report_v2/report.js', import.meta.url), 'utf8');
const captureSource = source.slice(source.indexOf('    const captureChartImages ='), source.indexOf('    if (emailButton && emailModal && emailForm)'));

test('email combines every period chart and label in one widget image', () => {
    const drawn = [], labels = [];
    const context = { fillRect() {}, fillText(text) { labels.push(text); }, drawImage(image) { drawn.push(image); } };
    const canvas = { getContext() { return context; }, toDataURL() { return 'data:image/png;base64,test'; } };
    const plots = ['January', 'February'].map(label => ({clientWidth:400, clientHeight:300,
        closest() { return {querySelector() { return {textContent:label}; }}; }}));
    const frames = [{id:'trend', type:'bar', el:{querySelectorAll() { return plots; }}}];
    const document = {createElement() { return canvas; }};
    const window = {echarts:{getInstanceByDom(plot) {return {getRenderedCanvas() {return plot;}};}}};
    const capture = new Function('frames', 'document', 'window', 'CHART_TYPES', captureSource + ';return captureChartImages;')(frames, document, window, {bar:1});
    assert.deepEqual(capture(), {trend:'data:image/png;base64,test'});
    assert.deepEqual(drawn, plots);
    assert.deepEqual(labels, ['January', 'February']);
    assert.equal(canvas.height, 1312);
});
