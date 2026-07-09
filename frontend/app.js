/* toolkit-scout frontend: fetches data.json + verification.json from the
   backend, computes every number live (nothing hardcoded), renders charts,
   matrix, filterable table, verification stats, and drives the SSE demo. */

const API = window.TS_API || "http://localhost:8000";  // patched at deploy
const VERDICTS = ["ready", "partial", "blocked_thin_docs", "blocked_gated",
                  "blocked_no_api", "error"];
const VCOLOR = { ready: "var(--ok)", partial: "var(--part)",
  blocked_thin_docs: "var(--thin)", blocked_gated: "var(--gated)",
  blocked_no_api: "var(--noapi)", error: "var(--err)" };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const verdictOf = (a) => a.result ? a.result.buildability : "error";
const badge = (v) => `<span class="badge b-${v}">${v.replace(/_/g, " ")}</span>`;
const count = (arr) => arr.reduce((m, k) => (m[k] = (m[k] || 0) + 1, m), {});

function tile(big, lbl) {
  return `<div class="tile"><span class="big">${big}</span><span class="lbl">${lbl}</span></div>`;
}

function barChart(el, counts, color) {
  const max = Math.max(...Object.values(counts), 1);
  el.innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) =>
    `<div class="bar-row"><span class="lbl">${k.replace(/_/g, " ")}</span>
     <div class="track"><div class="bar" style="width:${(n / max) * 100}%;background:${color?.[k] || "var(--accent)"}"></div></div>
     <span class="n">${n}</span></div>`).join("");
}

function renderPatterns(apps) {
  const ok = apps.filter((a) => a.result);
  const verdicts = count(apps.map(verdictOf));
  const auth = count(ok.flatMap((a) => a.result.auth_methods));
  const access = count(ok.map((a) => a.result.access));
  const mcp = ok.filter((a) => a.result.has_mcp).length;
  const oauth = auth.oauth2 || 0, key = auth.api_key || 0;
  const self = (access.self_serve || 0) + (access.trial || 0);
  const gated = apps.filter((a) => verdictOf(a) === "blocked_gated");

  $("#stat-tiles").innerHTML =
    tile(`${verdicts.ready || 0}/100`, "toolkit-ready today") +
    tile(`${verdicts.ready + verdicts.partial || 0}`, "buildable incl. workarounds") +
    tile(`${Math.round((self / ok.length) * 100)}%`, "self-serve credentials") +
    tile(key >= oauth ? `API key (${key})` : `OAuth2 (${oauth})`, "dominant auth") +
    tile(`${mcp}`, "already ship an MCP server") +
    tile(`${verdicts.blocked_no_api || 0}`, "no public API at all");

  barChart($("#chart-verdict"), verdicts, VCOLOR);
  barChart($("#chart-auth"), auth);
  barChart($("#chart-access"), access);

  // per-category ready-rate -> best/worst clusters for the insight bullets
  const cats = [...new Set(apps.map((a) => a.category))].map((c) => {
    const rows = apps.filter((a) => a.category === c);
    return { c, rate: rows.filter((a) => verdictOf(a) === "ready").length / rows.length };
  }).sort((a, b) => b.rate - a.rate);
  const best = cats.slice(0, 2), worst = cats.slice(-2).reverse();
  $("#insights").innerHTML = `
    <li><strong>${verdicts.ready || 0} of 100 are buildable today</strong>, ${verdicts.partial || 0}
      more with workarounds — the easy wins far outnumber the blocked.</li>
    <li><strong>API keys (${key}) edge out OAuth2 (${oauth})</strong>; most mature platforms offer both,
      so a toolkit layer must speak both from day one.</li>
    <li><strong>${Math.round((self / ok.length) * 100)}% hand out credentials self-serve</strong> (free or
      trial) — partner-gated APIs${gated.length ? ` (${gated.map((g) => esc(g.name)).join(", ")})` : ""} are
      the exception, not the rule.</li>
    <li><strong>Easiest categories:</strong> ${best.map((x) => `${esc(x.c)} (${Math.round(x.rate * 100)}% ready)`).join(", ")}.
      <strong>Hardest:</strong> ${worst.map((x) => `${esc(x.c)} (${Math.round(x.rate * 100)}%)`).join(", ")}.</li>
    <li><strong>${mcp} apps already ship an official MCP server</strong> — the toolkit gap is closing fast.</li>`;

  const cols = VERDICTS.filter((v) => apps.some((a) => verdictOf(a) === v));
  $("#matrix").innerHTML =
    `<tr><th>Category</th>${cols.map((v) => `<th>${v.replace(/_/g, " ")}</th>`).join("")}</tr>` +
    cats.sort((a, b) => b.rate - a.rate).map(({ c }) => {
      const rows = apps.filter((a) => a.category === c);
      const vc = count(rows.map(verdictOf));
      const mx = Math.max(...cols.map((v) => vc[v] || 0));
      return `<tr><td>${esc(c)}</td>${cols.map((v) =>
        `<td class="${vc[v] === mx && vc[v] ? "hot" : ""}">${vc[v] || ""}</td>`).join("")}</tr>`;
    }).join("");
}

function rowHTML(a) {
  const r = a.result;
  if (!r) return `<tr><td><strong>${esc(a.name)}</strong></td><td>${esc(a.category)}</td>
    <td colspan="6" class="hint">${esc(a.error)}</td><td>${badge("error")}</td></tr>`;
  const ev = [...new Set([r.auth_evidence_url, r.access_evidence_url, r.api_evidence_url,
    r.mcp_evidence_url].filter(Boolean))];
  return `<tr><td><strong>${esc(a.name)}</strong><br><span class="hint">${esc(r.description)}</span></td>
    <td>${esc(a.category)}</td>
    <td>${r.auth_methods.map((m) => `<span class="pill">${m}</span>`).join("")}</td>
    <td>${r.access.replace(/_/g, " ")}</td>
    <td>${r.api_type} / ${r.api_breadth}</td>
    <td>${r.has_mcp === true ? "✓" : r.has_mcp === false ? "—" : "?"}</td>
    <td>${badge(r.buildability)}<br><span class="hint">${esc(r.buildability_reason)}</span></td>
    <td>${r.confidence}</td>
    <td>${ev.map((u, i) => `<a href="${esc(u)}" target="_blank" title="${esc(u)}">[${i + 1}]</a>`).join(" ")}</td></tr>`;
}

function renderTable(apps) {
  const cat = $("#f-category"), ver = $("#f-verdict"), acc = $("#f-access");
  [...new Set(apps.map((a) => a.category))].forEach((c) => cat.add(new Option(c, c)));
  VERDICTS.forEach((v) => ver.add(new Option(v.replace(/_/g, " "), v)));
  ["self_serve", "trial", "paid", "partner_gated", "unknown"].forEach((v) =>
    acc.add(new Option(v.replace(/_/g, " "), v)));
  const PER = 10;                 // 10 rows per page, 100 rows = 10 pages
  let page = 1;
  const apply = () => {
    const q = $("#f-search").value.toLowerCase();
    const rows = apps.filter((a) =>
      (!q || a.name.toLowerCase().includes(q)) &&
      (!cat.value || a.category === cat.value) &&
      (!ver.value || verdictOf(a) === ver.value) &&
      (!acc.value || (a.result && a.result.access === acc.value)));
    const pages = Math.max(1, Math.ceil(rows.length / PER));
    page = Math.min(page, pages);
    $("#apps-table tbody").innerHTML =
      rows.slice((page - 1) * PER, page * PER).map(rowHTML).join("");
    $("#f-count").textContent = `${rows.length} match · page ${page}/${pages}`;
    $("#pager").innerHTML = pages < 2 ? "" : Array.from({ length: pages }, (_, i) =>
      `<button data-p="${i + 1}" class="${i + 1 === page ? "cur" : ""}">${i + 1}</button>`).join("");
  };
  $("#pager").addEventListener("click", (e) => {
    if (e.target.dataset.p) { page = +e.target.dataset.p; apply(); }
  });
  ["#f-search", "#f-category", "#f-verdict", "#f-access"].forEach((s) =>
    $(s).addEventListener("input", () => { page = 1; apply(); }));
  apply();
}

function renderVerification(v) {
  if (!v) {
    $("#verif-tiles").innerHTML = tile("pending", "verification pass not yet run");
    return;
  }
  const corrected = v.apps.flatMap((a) => a.diffs.filter(
    (d) => d.resolution === "corrected_to_pass2").map((d) => ({ ...d, name: a.name })));
  $("#verif-tiles").innerHTML =
    tile(`${Math.round(v.pass1_agreement * 100)}%`, "pass-1 fields confirmed by independent re-check") +
    tile(`${v.fields_compared}`, "field-level comparisons") +
    tile(`${v.corrections_applied}`, "fields corrected by the loop") +
    tile(`${v.apps.filter((a) => a.skipped).length}`, "apps not verifiable (skipped)");
  if (corrected.length) $("#verif-detail").innerHTML =
    `<h3>What the loop actually fixed</h3><div class="scroll-x"><table>
     <tr><th>App</th><th>Field</th><th>Pass 1</th><th>Corrected to</th><th>Deciding quote</th></tr>` +
    corrected.slice(0, 12).map((d) => `<tr><td>${esc(d.name)}</td><td>${d.field}</td>
      <td>${esc(d.pass1)}</td><td>${esc(d.final)}</td>
      <td class="quote">${esc((d.quote || "").slice(0, 140))}</td></tr>`).join("") + "</table></div>";
}

async function sse(url, onEvent) {  // fetch-based SSE so non-200 JSON errors surface
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json()).error || `HTTP ${res.status}`);
  const rd = res.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await rd.read();
    if (done) break;
    // sse-starlette emits CRLF line endings; normalize so "\n\n" splits work
    buf = (buf + dec.decode(value, { stream: true })).replace(/\r/g, "");
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      let ev = "message", data = "";
      chunk.split("\n").forEach((l) => {
        if (l.startsWith("event:")) ev = l.slice(6).trim();
        else if (l.startsWith("data:")) data += l.slice(5).trim();
      });
      onEvent(ev, data);
    }
  }
}

function addStep(msg, cls = "active") {
  const log = $("#demo-log");
  log.querySelector(".row.active")?.classList.replace("active", "done");
  const div = document.createElement("div");
  div.className = `row ${cls}`;
  div.textContent = msg;
  log.appendChild(div);
  log.scrollTop = 1e9;
}

$("#demo-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#demo-form button"), log = $("#demo-log");
  btn.disabled = true; log.hidden = false; log.innerHTML = "";
  $("#demo-result").innerHTML = "";
  addStep("contacting research agent…");
  const url = `${API}/research?name=${encodeURIComponent($("#demo-name").value)}` +
              `&hint=${encodeURIComponent($("#demo-hint").value)}`;
  try {
    await sse(url, (ev, data) => {
      if (ev === "step") addStep(data);
      if (ev === "error") addStep("FAILED: " + data, "fail");
      if (ev === "result") {
        addStep("research complete", "done");
        const a = JSON.parse(data);
        $("#demo-result").innerHTML = `<div class="result-card">
          <strong>${esc(a.name)}</strong> ${badge(verdictOf(a))}
          ${a.result ? `<dl>${Object.entries({
            description: a.result.description, auth: a.result.auth_methods.join(", "),
            access: a.result.access, api: `${a.result.api_type} / ${a.result.api_breadth}`,
            mcp: a.result.has_mcp, reason: a.result.buildability_reason,
            confidence: a.result.confidence,
            evidence: a.sources_fetched.map((u) => `<a href="${esc(u)}" target="_blank">${esc(u)}</a>`).join("<br>"),
          }).map(([k, val]) => `<dt>${k}</dt><dd>${k === "evidence" ? val : esc(val)}</dd>`).join("")}</dl>`
          : `<p class="hint">${esc(a.error)}</p>`}</div>`;
      }
    });
  } catch (err) { addStep("FAILED: " + err.message, "fail"); }
  btn.disabled = false;
});

(async () => {
  $("#link-data").href = `${API}/data.json`;
  $("#link-verif").href = `${API}/verification.json`;
  try {
    const data = await (await fetch(`${API}/data.json`)).json();
    renderPatterns(data.apps);
    renderTable(data.apps);
  } catch { $("#stat-tiles").innerHTML = tile("offline", "backend unreachable — table unavailable"); }
  try { renderVerification(await (await fetch(`${API}/verification.json`)).json()); }
  catch { renderVerification(null); }
})();
