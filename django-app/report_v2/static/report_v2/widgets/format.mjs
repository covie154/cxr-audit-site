const PALETTE = ["#3E7FA8", "#C86B4E", "#4E9B6F", "#8E6BAF", "#B5852F", "#5F8FA8", "#A85F6B", "#6F8F5F"];

function isRatio(unit) {
    const u = String(unit || "");
    return u.includes("rate[0,1]") || u.includes("ratio") || u.includes("probability");
}

function finiteOrNull(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function percent(value) {
    return (Math.round(value * 1000) / 10).toFixed(1) + "%";
}

function duration(value) {
    if (value === 0) { return "0 seconds"; }
    let total = Math.round(Math.abs(value));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    const parts = [];
    if (hours) { parts.push(hours + " h"); }
    if (minutes) { parts.push(minutes === 1 ? "1 min" : minutes + " minutes"); }
    if (seconds && !hours) { parts.push(seconds + " s"); }
    if (!parts.length) { return "0 seconds"; }
    if (hours && minutes && seconds) { parts.push(seconds + " s"); }
    return parts.join(" ");
}

export function formatValue(value, unit) {
    const num = finiteOrNull(value);
    if (num === null) { return "—"; }
    const u = unit === null || unit === undefined ? "" : String(unit);
    if (isRatio(u)) { return percent(num); }
    if (u === "seconds") { return duration(num); }
    if (u.includes("index[")) { return num.toFixed(3); }
    if (u === "count") { return Math.round(num).toLocaleString("en-US"); }
    if (u) { return String(value); }
    return String(value);
}

export function groupColor(label) {
    const text = label === null || label === undefined ? "" : String(label);
    let hash = 0x811c9dc5;
    for (let i = 0; i < text.length; i += 1) {
        hash ^= text.charCodeAt(i);
        hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return PALETTE[hash % PALETTE.length];
}
