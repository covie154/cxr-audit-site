import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../../static/report_v2/report.js', import.meta.url), 'utf8');
const exportCode = source.slice(source.indexOf('    const printButton ='), source.indexOf('    // -- email modal'));
function setup(blocked = false) {
    let click, resolveFetch;
    const calls = [];
    const button = { addEventListener(event, callback) { click = callback; } };
    const status = { textContent: '', firstChild: null, append(node) { this.link = node; } };
    const tab = { closed:false, document:{body:{}}, location:{replace(url) {calls.push(['navigate',url]);}}, close() {this.closed=true;} };
    const document = { querySelector(selector) { return selector.includes('print-status') ? status : button; } };
    const window = {
        open() {calls.push(['open']); return blocked ? null : tab;},
        fetch() {calls.push(['fetch']);return new Promise(resolve => {resolveFetch=resolve;});},
        setTimeout
    };
    new Function('document','window','root','inflightByWidget','frames','state','baseDefaults','CSRFToken','el',exportCode)(document,window,{dataset:{slug:'new'}},new Map(),[],{widgets:{}},()=>({}),()=>'',()=>({}));
    return {click, calls, status, tab, button, respond(status, payload) {resolveFetch({status,ok:status===201,json:()=>Promise.resolve(payload)});} };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
test('print opens a tab during the click before awaiting the snapshot', async () => {
    const h=setup();h.click();
    assert.deepEqual(h.calls.map(c=>c[0]),['open','fetch']);
    assert.match(h.status.textContent,/Preparing/);
    h.respond(201,{token:'frozen',print_url:'/report/new/print/frozen/'});await flush();
    assert.deepEqual(h.calls.at(-1),['navigate','/report/new/print/frozen/']);
    assert.equal(h.button.disabled,false);
});
test('blocked tabs produce an actionable export link', async () => {
    const h=setup(true);h.click();h.respond(201,{token:'frozen',print_url:'/print/frozen/'});await flush();
    assert.equal(h.status.link.href,'/print/frozen/');
    assert.equal(h.calls.filter(c=>c[0]==='open').length,1);
});
test('failed exports close the placeholder and show the server error', async () => {
    const h=setup();h.click();h.respond(400,{error:'Export rejected'});await flush();
    assert.equal(h.tab.closed,true);
    assert.equal(h.status.textContent,'Export rejected');
    assert.equal(h.button.disabled,false);
});
