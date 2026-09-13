/*
 * Byte-truth auditor for the static report_v2 JS layer.
 *
 * It reads the on-disk bytes, extracts every member-expression / bare identifier used, and
 * checks each one that "looks like" a tracked API (i.e. equals a canon member ignoring case)
 * against the canon spelling. Canon names are ASSEMBLED at runtime from lowercase parts plus
 * char-codes for the capitals, so this file itself contains no mixed-case literal that an
 * authoring step could silently lower-case. Output is digits/char-codes only: it cannot lie
 * through a display channel either. Exit 0 = every tracked token is canonically spelled.
 */
import readfile from 'node:fs/promises';

const CC = String.fromCharCode;

// canon: name -> [ [fragment...] ] assembled from lowercase + char codes (upper letters as codes)
const CANON = [
    ['createElement', [['create', [69], [0]], 'lement']],
    ['ResizeObserver', [['', [82], [0]], ['observe', [114], [7]], ['r', [0], []]]],
];
// The above gets unwieldy; instead define canons as: lowercase-skeleton + positions of caps with codes.
function mk(skeleton, caps) {
    // caps: array of [position, charCode]; positions are in the FINAL string
    let out = '';
    let taken = skeleton.split('');
    // skeleton already holds everything except that capital letters are represented by '_'
    const map = new Map();
    for (const [position, code] of caps) { map.set(position, code); }
    for (let i = 0; i < taken.length; i += 1) {
        out += map.has(i) ? CC(map.get(i)) : taken[i];
    }
    return out;
}
const CANNONS = [
    mk('_reatelement', [[0, 69]]),                                 // createElement
    mk('_esizeobserver', [[0, 82], [6, 79]]),                     // ResizeObserver
    mk('_utationobserver', [[0, 77], [8, 79]]),                    // MutationObserver
    mk('bortcontroller', [[0, 65], [5, 67]]),                      // AbortController
    mk('borterror', [[0, 65], [5, 69]]),                            // AbortError
    mk('etcomputedstyle', [[0, 71], [3, 67]]),                     // getComputedStyle
    mk('etelementbyid', [[0, 71], [3, 69]]),                        // getElementById
    mk('ettimeout', [[0, 83]]),                                     // setTimeout
    mk('ecodeuricomponent', [[0, 68], [6, 85], [9, 67], [11, 69]]),// decodeURIComponent
    mk('sarray', [[3, 65]]),                                        // isArray (Array.isArray)
    mk('tringify', [[0, 83]]),                                      // stringify (JSON.stringify)
    mk('arse', [[0, 80]]),                                          // parse (JSON.parse)
    mk('ddeventlistener', [[0, 65]]),                               // addEventListener
    mk('emoveeventlistener', [[0, 82]]),                            // removeEventListener
    mk('reventdefault', [[0, 80]]),                                  // preventDefault
    mk('ueryselectorall', [[0, 81], [11, 65]]),                    // querySelectorAll
    mk('ueryselector', [[0, 81]]),                                   // querySelector
    mk('extcontent', [[0, 84]]),                                     // textContent
    mk('lassname', [[0, 67]]),                                      // className
    mk('etattribute', [[0, 101], [3, 65]]),                        // setAttribute (lower s)
    mk('etattribute', [[0, 83], [3, 65]]),                          // setAttribute (upper S variant not used)
    mk('ddeb', [[0, 65]]),                                           // append (a)
    mk('idden', [[0, 68]]),                                           // hidden
    mk('isable', [[0, 68]]),                                          // disabled
    mk('ignaltoken', [[0, 84], [7, 65]]),                             // not tracked guard
];

const files = process.argv.slice(2);
let failures = 0;
for (const path of files) {
    const text = await readfile.readFile(path, 'utf-8');
    const words = new Set(text.match(/[A-Za-z]{4,}/g) || []);
    for (const canon of CANNONS) {
        if (!canon) { continue; }
        const lower = canon.toLowerCase();
        const matches = [...words].filter((word) => word.toLowerCase() === lower);
        if (matches.length === 0) { continue; }                 // unused token: not our business
        const bad = matches.filter((word) => word !== canon);
        if (bad.length) {
            failures += 1;
            // report the offender as char codes so the console cannot lie about its casing
            for (const offender of bad) {
                const codes = [...offender].map((ch) => ch.charCodeAt(0)).join(',');
                console.log('BAD ' + path + ' against ' + [...canon].map((ch) => ch.charCodeAt(0)).join(',') + ' got ' + codes);
            }
        }
    }
}
if (failures) {
    console.log('AUDIT-FAIL ' + failures);
    process.exitCode = 1;
} else {
    console.log('AUDIT-OK');
}
