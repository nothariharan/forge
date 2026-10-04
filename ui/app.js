// FORGE lab UI. Read-only consumer of ledger events (schemas/event.schema.json).
// Sources:  ?src=<path to exported .jsonl>   (default fixtures/exo-demo.jsonl, replayed)
//           ?sse=<url>                         (live EventSource; each message is one event JSON)
// All state below is derived by folding events; nothing is stored outside the event list.

import { resolveAgent, mascotSVG, ARCHETYPES } from "./mascots.js";

// Room boxes in % of the floor, and slots inside a room (0..1 of the room box)
// chosen to stay clear of the room label in the top-left corner and of each other.
const ROOMS = { library: [0, 0], whiteboard: [1, 0], compute: [2, 0], safety: [0, 1], meeting: [1, 1], pi: [2, 1] };
const SLOT = [[0.66, 0.5], [0.42, 0.68], [0.86, 0.68], [0.2, 0.74], [0.64, 0.8], [0.66, 0.3], [0.86, 0.36], [0.42, 0.82], [0.12, 0.5]];
function slotPos(room, i) {
  const [col, row] = ROOMS[room]; const [rx, ry] = SLOT[i % SLOT.length];
  return [col * 33.333 + rx * 33.333, row * 59 + ry * 41];
}
const roomOfAgent = (name) => resolveAgent(name).home;

// Where an agent goes for each event type (defaults to its home room).
const MOVE = {
  NOVELTY_VERDICT: "library", EXPERIMENT_SELECTED: "whiteboard", PREDICTION_COMMITTED: "whiteboard",
  RUN_STARTED: "compute", RUN_FINISHED: "compute", FINDING: "meeting", SURPRISE: "meeting",
  REPLAN: "meeting", CONSENSUS: "meeting", POLICY_DENIED: "safety", GATE_OPENED: "pi",
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// arXiv / DOI / URL refs become links. Demo placeholders (0000 ids) stay plain text.
function refLink(ref) {
  const r = String(ref || "");
  const demo = /0000[.\/]/.test(r) || r.includes("demo");
  let url = null;
  if (/^arxiv:/i.test(r)) url = `https://arxiv.org/abs/${r.slice(6)}`;
  else if (/^10\.\d{4,}\//.test(r)) url = `https://doi.org/${r}`;
  else if (/^https?:\/\//.test(r)) url = r;
  if (!url || demo) return `<span class="ref">${esc(r)}${demo ? ' <span class="badge grey">demo ref</span>' : ""}</span>`;
  return `<a class="ref" href="${esc(url)}" target="_blank" rel="noopener">${esc(r)} ↗</a>`;
}
const hhmmss = (ts) => (ts || "").slice(11, 19);
const agentOf = (name) => (name === "system" ? { label: "System", color: "#8a8378" } : resolveAgent(name));

let events = [];
let pos = 0;           // number of events applied
let timer = null;
let live = false;

// ---------- one-line summaries ----------
function summary(e) {
  const p = e.payload || {};
  switch (e.type) {
    case "RUN_CREATED": return `Run created: ${p.question}`;
    case "EVIDENCE_ADDED": return `Evidence: ${(p.claims || []).map((c) => c.ref).join(", ")}`;
    case "HYPOTHESIS_PROPOSED": return `Created ${p.hid}: "${p.claim}"`;
    case "NOVELTY_VERDICT": return `${p.hid} novelty: ${p.label}`;
    case "PREDICTION_COMMITTED": return `Prediction committed for ${p.eid || p.hid}: ${p.metric} ~ ${p.mean} ± ${p.sd}`;
    case "EXPERIMENT_SELECTED": return `Selected ${p.chosen} (budget left ${p.budget_left ?? "?"})`;
    case "RUN_STARTED": return `Running ${p.eid}…`;
    case "RUN_FINISHED": return `${p.eid} ${p.status}: ${Object.entries(p.metrics || {}).map(([k, v]) => `${k}=${v}`).join(", ")}`;
    case "FINDING": return `${p.eid} effect ${p.effect} [${(p.ci || []).join(", ")}] ${p.verdict}`;
    case "CONSENSUS": return `${p.eid} consensus ${p.agreement} (${p.accepted ? "accepted" : "rejected"})`;
    case "SURPRISE": return `Surprise ${p.surprise_score} > ${p.threshold} on ${p.eid}`;
    case "REPLAN": return `Replan: ${p.reason}`;
    case "POLICY_DENIED": return `${p.policy_id} denied ${p.target_agent}: ${p.reason}`;
    case "GATE_OPENED": return `Approval requested: ${p.action}`;
    case "GATE_RESOLVED": return `${p.gate_id} ${p.status}: ${p.action}`;
    case "RUN_COMPLETED": return `Run ${p.status}. ${p.summary || ""}`;
    case "ERROR": return `Error: ${p.message}`;
    default: return e.type;
  }
}
function bubbleText(e) {
  const p = e.payload || {};
  switch (e.type) {
    case "EVIDENCE_ADDED": return ["Searching literature…", (p.claims || [])[0]?.ref];
    case "HYPOTHESIS_PROPOSED": return [p.hid, "New hypothesis"];
    case "NOVELTY_VERDICT": return [p.hid, `Novelty: ${p.label}`];
    case "PREDICTION_COMMITTED": return [p.eid || p.hid, "Prediction committed"];
    case "EXPERIMENT_SELECTED": return [p.chosen, "Selected experiment"];
    case "RUN_STARTED": return [p.eid, "Running experiment…"];
    case "RUN_FINISHED": return [p.eid, "Results ready"];
    case "FINDING": return [p.eid, p.verdict];
    case "REPLAN": return ["Replan", `Reopened ${(p.reopened || []).join(", ")}`];
    case "CONSENSUS": return [p.eid, `Agreement ${p.agreement}`];
    case "POLICY_DENIED": return [`${p.policy_id} denied`, p.target_agent];
    case "GATE_OPENED": return ["Agent knock", p.action];
    default: return null;
  }
}

// ---------- fold events into state ----------
function fold(list) {
  const s = {
    run: null, done: null, budget: null, budgetLeft: null, dataVer: null,
    hyps: {}, hypOrder: [], novelty: {}, preds: {}, selections: [], runs: {}, findings: {}, surprises: [],
    replans: [], claims: [], denials: [], gates: {}, errors: [],
    agents: {}, lastByAgent: {}, place: {}, seen: [],
  };
  for (const e of list) {
    const p = e.payload || {};
    s.lastByAgent[e.agent] = e;
    if (e.agent !== "system" && e.agent !== "human") {
      if (!s.seen.includes(e.agent)) s.seen.push(e.agent);
      s.place[e.agent] = MOVE[e.type] || roomOfAgent(e.agent);
    }
    if (e.type === "GATE_RESOLVED") { s.seen.filter((n) => resolveAgent(n).type === "safety").forEach((n) => { s.place[n] = "safety"; }); s.lastByAgent.human = e; }
    if (e.type === "RUN_COMPLETED") s.seen.forEach((n) => { s.place[n] = roomOfAgent(n); });
    switch (e.type) {
      case "RUN_CREATED": s.run = e; s.budget = p.budget ?? null; break;
      case "EVIDENCE_ADDED": (p.claims || []).forEach((c) => s.claims.push({ ...c, seq: e.seq })); break;
      case "HYPOTHESIS_PROPOSED": if (!s.hyps[p.hid]) s.hypOrder.push(p.hid); s.hyps[p.hid] = p; break;
      case "NOVELTY_VERDICT": s.novelty[p.hid] = p; break;
      case "PREDICTION_COMMITTED": s.preds[p.eid || p.hid] = { ...p, seq: e.seq }; break;
      case "EXPERIMENT_SELECTED": s.selections.push({ ...p, seq: e.seq }); s.budgetLeft = p.budget_left ?? s.budgetLeft; break;
      case "RUN_STARTED": s.runs[p.eid] = { ...p, state: "running", startSeq: e.seq }; s.dataVer = p.data_ver; break;
      case "RUN_FINISHED": s.runs[p.eid] = { ...(s.runs[p.eid] || {}), ...p, state: p.status === "ok" ? "done" : "failed" }; break;
      case "FINDING": s.findings[p.eid] = p; break;
      case "SURPRISE": s.surprises.push(p); break;
      case "REPLAN": s.replans.push(p); break;
      case "POLICY_DENIED": s.denials.push({ ...p, seq: e.seq }); break;
      case "GATE_OPENED": case "GATE_RESOLVED": s.gates[p.gate_id] = { ...p, seq: e.seq }; break;
      case "RUN_COMPLETED": s.done = e; break;
      case "ERROR": s.errors.push(e); break;
    }
  }
  return s;
}

function hypStatus(s, hid) {
  const eids = Object.values(s.runs).filter((r) => r.hid === hid).map((r) => r.eid);
  const f = eids.map((id) => s.findings[id]).filter(Boolean).pop();
  if (f) return f.verdict;
  if (eids.some((id) => s.runs[id].state === "running")) return "TESTING";
  if (s.replans.some((r) => (r.reopened || []).includes(hid))) return "REOPENED";
  return "PROPOSED";
}
const VERDICT_BADGE = { SUPPORTS: "ok", REFUTES: "bad", INCONCLUSIVE: "warn", TESTING: "info", REOPENED: "info", PROPOSED: "grey",
  NOVEL: "ok", KNOWN: "warn", CONTRADICTED: "bad", UNCERTAIN: "grey" };
const badge = (t) => `<span class="badge ${VERDICT_BADGE[t] || "grey"}">${esc(t)}</span>`;

// Harness each agent is configured with in omnigent/forge (config, not ledger data).
const HARNESS = { director: "claude-sdk", librarian: "claude-sdk", hypothesizer: "claude-sdk", referee: "claude-sdk",
  planner: "claude-sdk", safety: "claude-sdk", experimenter: "claude-sdk", analyst: "claude-sdk" };
let pinned = null;
const clip = (t, n) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
function showAgentCard(name, el) {
  const a = resolveAgent(name);
  const mine = events.slice(0, pos).filter((e) => e.agent === name || (name === "human" && e.type === "GATE_RESOLVED"));
  const last = mine[mine.length - 1];
  const card = $("#agent-card");
  card.innerHTML = `<div class="ac-head"><span class="ac-icon">${mascotSVG(name)}</span><div><b>${esc(a.label)}</b><small>${esc(a.role)}</small></div></div>
    <dl class="kv"><dt>Doing</dt><dd>${esc(clip(last ? summary(last) : name === "human" ? "Watching; approves P6 gates" : "Idle", 150))}</dd>
    ${HARNESS[name] ? `<dt>Harness</dt><dd>${HARNESS[name]} <span class="muted">(Omnigent)</span></dd>` : ""}
    <dt>Events</dt><dd>${mine.length}</dd></dl>
    ${mine.length ? `<div class="ac-recent">${mine.slice(-3).reverse().map((e) => `<div><span class="mono muted">#${e.seq}</span> ${esc(e.type)}</div>`).join("")}</div>` : ""}
    ${pinned ? '<div class="muted ac-hint">click anywhere to close</div>' : '<div class="muted ac-hint">click to pin</div>'}`;
  const fr = $("#floor").getBoundingClientRect(); const r = el.getBoundingClientRect();
  card.style.left = `${Math.min(r.left - fr.left + r.width / 2, fr.width - 270)}px`;
  card.style.top = `${r.top - fr.top + r.height + 6}px`;
  card.hidden = false;
}
document.addEventListener("mouseover", (ev) => {
  const m = ev.target.closest(".mascot"); if (!m || pinned) return;
  showAgentCard(m.dataset.agent, m);
});
document.addEventListener("mouseout", (ev) => {
  const m = ev.target.closest(".mascot"); if (!m || pinned || m.contains(ev.relatedTarget)) return;
  $("#agent-card").hidden = true;
});
document.addEventListener("click", (ev) => {
  const m = ev.target.closest(".mascot");
  if (m) { pinned = m.dataset.agent; showAgentCard(pinned, m); return; }
  if (!ev.target.closest("#agent-card")) { pinned = null; $("#agent-card").hidden = true; }
});

// ---------- mascots ----------
function ensureMascot(name) {
  const id = `m-${name.replace(/[^a-z0-9_-]/gi, "_")}`;
  let el = document.getElementById(id);
  if (!el) {
    const a = resolveAgent(name);
    el = document.createElement("div");
    el.className = `mascot type-${a.type}`; el.id = id; el.style.left = "50%"; el.style.top = "50%";
    el.dataset.agent = name; el.tabIndex = 0;
    el.title = `${a.label}: ${a.role}`;
    el.innerHTML = `${mascotSVG(name)}<span class="tag">${esc(a.label)}</span>`;
    $("#mascots").appendChild(el);
  }
  return el;
}
const mascotEl = (name) => document.getElementById(`m-${String(name).replace(/[^a-z0-9_-]/gi, "_")}`);
function placeMascots(s, current) {
  const names = [...new Set([...s.seen, "human"])];
  document.querySelectorAll(".mascot").forEach((el) => { if (!names.some((n) => mascotEl(n) === el)) el.remove(); });
  const used = {};
  for (const n of names) {
    const room = n === "human" ? "pi" : s.place[n] || roomOfAgent(n);
    const i = (used[room] = (used[room] ?? -1) + 1);
    const [x, y] = slotPos(room, i);
    const el = ensureMascot(n);
    if (el.style.left !== `${x}%` || el.style.top !== `${y}%`) {
      el.classList.add("walking"); clearTimeout(el._walk); el._walk = setTimeout(() => el.classList.remove("walking"), 1100);
    }
    el.style.left = `${x}%`; el.style.top = `${y}%`;
    const actor = current && (current.type === "GATE_RESOLVED" || current.agent === "human" ? "human" : current.agent);
    el.classList.toggle("active", actor === n);
  }
  for (const n of names) {
    const room = n === "human" ? "pi" : s.place[n] || roomOfAgent(n);
    ensureMascot(n).classList.toggle("small", used[room] >= 3);
  }
  document.querySelectorAll(".room").forEach((r) => r.classList.toggle("busy", !!current && current.agent !== "system" && (MOVE[current.type] || roomOfAgent(current.agent)) === r.dataset.room));
}
function renderAlerts(s, current) {
  const out = [];
  if (current) {
    const bt = current.type === "GATE_RESOLVED" ? [current.payload.status === "approved" ? "Approved ✓" : "Rejected", current.payload.action] : bubbleText(current);
    const el = mascotEl(current.type === "GATE_RESOLVED" ? "human" : current.agent);
    if (bt && el) out.push(`<div class="bubble" style="left:${el.style.left};top:${el.style.top}"><b>${esc(bt[0])}</b>${esc(bt[1] || "")}</div>`);
  }
  const pending = Object.values(s.gates).filter((g) => g.status === "pending").pop();
  if (pending) {
    out.push(`<div class="alert danger" style="left:3%;top:73%"><b>⚠ Requires human approval</b>Action: ${esc(pending.action)}<br>Policy: ${esc(pending.policy || "P6")} · risk ${esc(pending.risk)}</div>`);
    out.push(`<div class="alert" style="left:69%;top:63%"><b>Agent knock</b>${esc(pending.action)} needs your approval.
      <div class="btns"><button class="approve" data-gate="${esc(pending.gate_id)}" data-decision="approve" ${live ? "" : "disabled"}>Approve</button><button class="reject" data-gate="${esc(pending.gate_id)}" data-decision="deny" ${live ? "" : "disabled"}>Reject</button></div>
      <div class="note">${live ? "Your decision is written to the ledger; the experiment waits for it (P6)." : "Replay: the recorded decision follows."}</div></div>`);
  }
  const lastDenial = current && current.type === "POLICY_DENIED" ? current.payload : null;
  if (lastDenial) out.push(`<div class="alert danger" style="left:3%;top:73%"><b>${esc(lastDenial.policy_id)} denied</b>${esc(lastDenial.reason)}</div>`);
  if (current && current.type === "SURPRISE") out.push(`<div class="alert danger" style="left:36%;top:73%"><b>⚠ Surprising result!</b>score ${current.payload.surprise_score} &gt; ${current.payload.threshold}. Replanning…</div>`);
  $("#alerts").innerHTML = out.join("");
}

// ---------- panels ----------
function renderBanner(s) {
  const pending = Object.values(s.gates).filter((g) => g.status === "pending").pop();
  const el = $("#approval-banner");
  if (!pending) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<b>⚠ Approval needed (${esc(pending.policy || "P6")})</b><span>${esc(pending.action)}</span>
    <button class="approve" data-gate="${esc(pending.gate_id)}" data-decision="approve" ${live ? "" : "disabled"}>Approve</button>
    <button class="reject" data-gate="${esc(pending.gate_id)}" data-decision="deny" ${live ? "" : "disabled"}>Reject</button>`;
}
function renderTop(s) {
  const running = s.run && !s.done;
  $("#status-dot").className = "dot " + (running ? "running" : s.done ? "done" : "");
  $("#status-text").textContent = !s.run ? "Waiting" : running ? "Running" : `Run ${s.done.payload.status}`;
  const nExp = Object.keys(s.runs).length;
  $("#context").textContent = s.run ? `${s.run.run_id} · ${nExp} experiment${nExp === 1 ? "" : "s"}` : "";
  const last = events[pos - 1];
  $("#clock").textContent = last ? hhmmss(last.ts) : "--:--";
  const demo = s.run && (s.run.payload.mode === "demo" || s.run.payload.mode === "fake" || s.run.payload.demo);
  $("#demo-badge").hidden = !demo;
  // A recorded real run played back from its exported ledger is labelled as a replay.
  const replayOfLive = !live && s.run && s.run.payload.mode === "live";
  $("#replay-badge").hidden = !replayOfLive;
  if (replayOfLive) $("#replay-badge").textContent = `REPLAY of live Omnigent run ${s.run.run_id}`;
}
function renderRun(s) {
  if (!s.run) { $("#run").innerHTML = `<p class="muted">No run yet.</p>`; return; }
  const sel = s.selections[s.selections.length - 1];
  const chosen = sel && (sel.candidates || []).find((c) => c.eid === sel.chosen);
  const hid = (chosen && chosen.hid) || s.hypOrder[s.hypOrder.length - 1];
  const h = s.hyps[hid];
  const runList = Object.values(s.runs);
  const r = runList[runList.length - 1];
  const p = s.run.payload;
  $("#run").innerHTML = `
    <div class="run-head">⚗ ${esc(hid || "No hypothesis")} ${hid ? badge(hypStatus(s, hid)) : ""}</div>
    <div class="run-q">${esc(h ? h.claim : p.question)}</div>
    <dl class="kv">
      <dt>Experiment</dt><dd>${r ? `${esc(r.eid)} ${badge(r.state === "running" ? "TESTING" : r.state === "done" ? "done" : r.state)}` : "none"}</dd>
      <dt>Dataset</dt><dd>${esc(p.dataset || s.dataVer || "n/a")}</dd>
      <dt>Budget</dt><dd>${s.budgetLeft != null ? `${s.budgetLeft} left of ${s.budget}<div class="bar"><i style="width:${Math.max(0, Math.min(100, 100 * (1 - s.budgetLeft / s.budget)))}%"></i></div>` : s.budget ?? "n/a"}</dd>
      <dt>Approvals</dt><dd>${Object.values(s.gates).map((g) => `${esc(g.gate_id)} ${badge(g.status)}`).join(" ") || "none"}</dd>
      ${p.cohorts ? `<dt>Cohorts</dt><dd>resolved: ${esc(p.cohorts.resolved.join(" + "))}<br>unresolved: ${esc(p.cohorts.unresolved.join(", "))}<br>excluded: ${esc((p.cohorts.excluded || []).join(", "))}</dd>` : ""}
    </dl>
    <div class="note-box"><b>Question</b><br>${esc(p.question)}</div>`;
}
function renderAgents(s) {
  $("#agents").innerHTML = [...new Set([...s.seen, "human"])].map((n) => {
    const a = resolveAgent(n); const e = s.lastByAgent[n];
    return `<div class="agent-row"><span class="mini">${mascotSVG(n)}</span><span title="${esc(a.role)}">${esc(a.label)}</span><span title="${esc(e ? summary(e) : "")}">${esc(e ? summary(e) : n === "human" ? "Watching" : "Idle")}</span></div>`;
  }).join("") || `<p class="muted">No agents summoned yet.</p>`;
}
function renderRecent() {
  const last = events.slice(0, pos).slice(-6).reverse();
  $("#recent").innerHTML = last.map((e) => `<div class="ev"><i style="background:${agentOf(e.agent).color}"></i><span class="mono muted">${hhmmss(e.ts)}</span><span>${esc(e.type.replace(/_/g, " ").toLowerCase())}<small>${esc(summary(e)).slice(0, 90)}</small></span></div>`).join("") || `<p class="muted">Nothing yet.</p>`;
}
function renderLog() {
  const box = $("#log");
  box.innerHTML = events.slice(0, pos).map((e) => {
    const a = agentOf(e.agent);
    return `<div><span class="t">${hhmmss(e.ts)}</span><span style="color:${a.color}">[${esc(a.label)}]</span><span>${esc(summary(e))}</span></div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
}
function renderMinimap(s) {
  const order = ["library", "whiteboard", "compute", "safety", "meeting", "pi"];
  $("#minimap").innerHTML = order.map((room) =>
    `<div title="${room}">${[...new Set([...s.seen, "human"])].filter((n) => (n === "human" ? "pi" : s.place[n] || roomOfAgent(n)) === room).map((n) => `<i style="background:${resolveAgent(n).color}" title="${esc(resolveAgent(n).label)}"></i>`).join("")}</div>`).join("");
}

// ---------- pages ----------
function renderPages(s) {
  $("#hyp").innerHTML = s.hypOrder.length ? `<table><tr><th>ID</th><th>Claim</th><th>Prediction</th><th>Falsifier</th><th>Prior</th><th>Novelty</th><th>Status</th></tr>${
    s.hypOrder.map((id) => { const h = s.hyps[id]; const n = s.novelty[id];
      return `<tr><td class="mono">${esc(id)}</td><td>${esc(h.claim)} <span class="badge grey">AI-generated</span></td><td>${esc(h.prediction)}</td><td>${esc(h.falsifier)}</td><td>${esc(h.prior)}</td><td>${n ? badge(n.label) : "–"}</td><td>${badge(hypStatus(s, id))}</td></tr>`; }).join("")}</table>` : `<p class="muted">No hypotheses yet.</p>`;

  $("#exp").innerHTML = s.selections.map((sel) => `
    <h3>Decision at seq ${sel.seq} · budget left ${esc(sel.budget_left)}</h3>
    <table><tr><th>ID</th><th>Hypothesis</th><th>Design</th><th>EIG</th><th>Cost</th><th>EIG / cost</th><th>Status</th></tr>
    ${(sel.candidates || []).map((c) => { const r = s.runs[c.eid]; const pre = s.preds[c.eid];
      const status = c.eid === sel.chosen ? (r ? r.state : "selected") : "not chosen";
      return `<tr class="${c.eid === sel.chosen ? "chosen" : ""}"><td class="mono">${esc(c.eid)}</td><td class="mono">${esc(c.hid)}</td><td>${esc(c.design)}</td><td>${esc(c.eig)}</td><td>${esc(c.est_cost)}</td><td>${c.eig && c.est_cost ? (c.eig / c.est_cost).toFixed(3) : "–"}</td><td>${esc(status)}${pre && r && pre.seq < r.startSeq ? ' <span class="badge ok">preregistered</span>' : ""}</td></tr>`; }).join("")}
    </table>${sel.rationale ? `<div class="note-box">Planner: ${esc(sel.rationale)}</div>` : ""}`).join("")
    + (Object.keys(s.runs).length ? `<h3>Runs</h3><table><tr><th>ID</th><th>Data</th><th>Seed</th><th>Code</th><th>Status</th><th>Metrics</th><th>Finding</th></tr>${Object.values(s.runs).map((r) => { const f = s.findings[r.eid];
      return `<tr><td class="mono">${esc(r.eid)}</td><td>${esc(r.data_ver)}</td><td>${esc(r.seed)}</td><td class="mono">${esc(r.code_hash)}</td><td>${esc(r.status || r.state)}</td><td class="mono">${esc(Object.entries(r.metrics || {}).map(([k, v]) => `${k}=${v}`).join(" "))}</td><td>${f ? `${badge(f.verdict)} ${esc(f.effect)} [${esc((f.ci || []).join(", "))}]` : "–"}</td></tr>`; }).join("")}</table>` : "")
    + s.denials.map((d) => `<div class="note-box bad"><b>${esc(d.policy_id)} denied ${esc(d.target_agent)}</b> · ${esc(d.reason)}</div>`).join("")
    || `<p class="muted">No experiments selected yet.</p>`;

  $("#lit").innerHTML = s.claims.length ? s.claims.map((c, i) => `<div class="note-box"><b>${i + 1}. ${refLink(c.ref)}</b><br>${esc(c.text)}<br><span class="muted">“${esc(c.quote_span)}”</span></div>`).join("")
    + `<div class="note-box">Citation resolution and quote support are checked by <code>tools/citation_check.py</code>; agent-reported verification is never trusted on its own.</div>`
    + s.denials.filter((d) => d.policy_id === "P1").map((d) => `<div class="note-box bad"><b>P1 citation policy</b> · ${esc(d.reason)}</div>`).join("")
    : `<p class="muted">No evidence yet.</p>`;

  const shown = events.slice(0, pos);
  const brokenAt = shown.findIndex((e, i) => i > 0 && e.prev_hash !== shown[i - 1].hash);
  $("#led").innerHTML = `<div class="note-box ${brokenAt === -1 ? "ok" : "bad"}">${brokenAt === -1 ? `Hash links consistent for ${shown.length} events (prev_hash matches the previous hash).` : `Link broken at seq ${shown[brokenAt].seq}.`} Full recompute: <code>python -m cli.verify &lt;run_id&gt;</code></div>
    <table><tr><th>seq</th><th>time</th><th>agent</th><th>type</th><th>AI</th><th>hash</th><th>prev</th></tr>${shown.map((e) => `<tr><td>${e.seq}</td><td class="mono">${hhmmss(e.ts)}</td><td>${esc(e.agent)}</td><td class="mono">${esc(e.type)}</td><td>${e.ai_generated ? "yes" : ""}</td><td class="mono">${esc((e.hash || "").slice(0, 10))}</td><td class="mono">${esc((e.prev_hash || "").slice(0, 10))}</td></tr>`).join("")}</table>`;

  $("#bench").innerHTML = `<div class="note-box">No single-agent vs FORGE result yet. The benchmark protocol is unlocked until the science question is locked, so no speedup is claimed here.</div>
    <p class="muted">When the matched comparison runs, this page will read the report written by <code>bench/report.py</code> from raw artifacts.</p>`;

  $("#rt").innerHTML = `
    <p>Omnigent composes and governs the agents; FORGE adds the research workflow and this ledger. Config: <code>omnigent/forge/</code> (Omnigent 0.16.0). Every agent runs on the claude-sdk harness so the benchmark's arm B uses the same model as the single-agent arm A (pinned with <code>ANTHROPIC_MODEL</code>).</p>
    <table><tr><th>Agent</th><th>Harness</th><th>Live in Omnigent?</th></tr>
      <tr><td>Director</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
      <tr><td>Librarian</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
      <tr><td>Hypothesizer</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
      <tr><td>Experimenter</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
      <tr><td>Referee · Safety</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
      <tr><td>Planner · Analyst</td><td>claude-sdk</td><td><span class="badge ok">yes</span></td></tr>
    </table>
    <h3 style="margin-top:18px">Agent roster</h3>
    <p class="muted">Omnigent decides which sub-agents to summon. Any agent name that appears in the ledger gets a mascot: matched to one of these archetypes by name, or a generic dot if nothing matches.</p>
    <div class="roster">${Object.entries(ARCHETYPES).map(([k, a]) => `<div class="ros">${mascotSVG(k)}<b>${esc(a.label)}</b><span>${esc(a.role)}</span></div>`).join("")}</div>
    <h3 style="margin-top:18px">Policies</h3>
    <table><tr><th>Policy</th><th>Enforcement</th><th>Status</th></tr>
      <tr><td>P2 budget</td><td>Omnigent CEL policies: 60 dispatches, 10 experiments per run</td><td><span class="badge ok">enforced · tested live</span></td></tr>
      <tr><td>Handoff gate</td><td>tools/forge_emit.py + Omnigent tool_result/tool_call policies</td><td><span class="badge ok">enforced · tested live</span></td></tr>
      <tr><td>P5 shell allowlist</td><td>Omnigent CEL policy on sys_os_shell (applies to every sub-agent)</td><td><span class="badge ok">enforced · tested live</span></td></tr>
      <tr><td>P6 human approval</td><td>tools/forge_gate.py: the experiment waits for GATE_RESOLVED from this UI or cli.approve</td><td><span class="badge ok">enforced · verified live (live-exo-8)</span></td></tr>
      <tr><td>P1 citations</td><td>tools/citation_check.py</td><td><span class="badge grey">tool, not an Omnigent policy yet</span></td></tr>
    </table>`;
}


// ---------- room furniture (decorative) ----------
const plant = (x, y, k = 1) => `<g transform="translate(${x} ${y}) scale(${k})"><rect x="-9" y="6" width="18" height="16" rx="3" fill="#c98a5b"/><path d="M0 8C-14 0-16-14-4-18 0-10 0-4 0 8zM0 8C14 0 16-14 4-18 0-10 0-4 0 8zM0 8C-4-6 4-20 0-26 6-14 4-4 0 8z" fill="#5fae5a"/></g>`;
const desk = (x, y, w = 70) => `<g transform="translate(${x} ${y})"><rect width="${w}" height="26" rx="4" fill="#c7996b"/><rect y="22" width="${w}" height="6" rx="2" fill="#a97c52"/></g>`;
const monitor = (x, y) => `<g transform="translate(${x} ${y})"><rect width="30" height="20" rx="3" fill="#3d4654"/><rect x="3" y="3" width="24" height="14" rx="1" fill="#8fc3f0"/><rect x="12" y="20" width="6" height="5" fill="#3d4654"/></g>`;
const win = (x) => `<g transform="translate(${x} 6)"><rect width="46" height="26" rx="3" fill="#cfe7f7" stroke="#fff" stroke-width="3"/><path d="M23 0v26M0 13h46" stroke="#fff" stroke-width="2"/><path d="M4 22l10-10" stroke="rgba(255,255,255,.7)" stroke-width="3"/></g>`;
const rug = (x, y, w, h, c) => `<ellipse cx="${x}" cy="${y}" rx="${w}" ry="${h}" fill="${c}" opacity=".55"/>`;
const lamp = (x, y) => `<g transform="translate(${x} ${y})"><rect x="-1.5" y="0" width="3" height="26" fill="#8a8378"/><path d="M-10 0h20l-5-12h-10z" fill="#f6d27a"/><ellipse cx="0" cy="28" rx="7" ry="2" fill="#8a8378"/></g>`;
const codeScreen = (x, y) => `<g transform="translate(${x} ${y})"><rect width="30" height="20" rx="3" fill="#2b3240"/><g class="act-code"><rect x="4" y="4" width="14" height="2" fill="#7ee081"/><rect x="7" y="8" width="16" height="2" fill="#8fc3f0"/><rect x="7" y="12" width="10" height="2" fill="#f2c43a"/><rect x="4" y="16" width="18" height="2" fill="#7ee081"/></g><rect x="12" y="20" width="6" height="5" fill="#3d4654"/></g>`;
const FURNITURE = {
  library: () => { const books = ["#e07a5f", "#3d85c6", "#f2cc8f", "#81b29a", "#9b6cf0", "#e2468f"];
    let sh = `<rect x="200" y="46" width="88" height="96" rx="4" fill="#8b5e3c"/>`;
    for (let r = 0; r < 3; r++) for (let i = 0; i < 9; i++) sh += `<rect x="${205 + i * 9}" y="${52 + r * 30}" width="7" height="24" rx="1" fill="${books[(i + r) % 6]}"/>`;
    return win(120) + rug(105, 132, 70, 14, "#e9b48a") + sh + desk(60, 110, 90) + `<g class="act-float"><rect x="84" y="84" width="10" height="13" rx="1" fill="#fff" transform="rotate(-12 89 90)"/><rect x="104" y="78" width="10" height="13" rx="1" fill="#fff" transform="rotate(10 109 84)"/><rect x="124" y="86" width="9" height="12" rx="1" fill="#fff"/></g>` + lamp(160, 98) + `<rect x="70" y="102" width="22" height="10" rx="2" fill="#f2cc8f"/><rect x="120" y="100" width="18" height="12" rx="2" fill="#e07a5f"/>` + plant(26, 118, 1.1) + plant(270, 138, .8); },
  whiteboard: () => { let wb = `<rect x="150" y="40" width="130" height="78" rx="5" fill="#fbfbf8" stroke="#c9c2b6" stroke-width="3"/>`;
    const notes = ["#f9e27d", "#f7a8c4", "#a8d8f0", "#b9e3a3"];
    for (let i = 0; i < 8; i++) wb += `<rect x="${160 + (i % 4) * 29}" y="${50 + Math.floor(i / 4) * 30}" width="20" height="18" rx="2" fill="${notes[i % 4]}"/>`;
    return win(70) + rug(150, 138, 90, 14, "#c9b3e8") + wb + `<path class="act-draw" d="M170 105l20-8 18 6 22-12 22 4" stroke="#e2574c" stroke-width="2.5" fill="none"/>` + `<rect x="150" y="118" width="130" height="5" rx="2" fill="#c9c2b6"/>` + plant(30, 120) + plant(270, 140, .8); },
  compute: () => { let racks = "";
    for (let i = 0; i < 3; i++) { racks += `<rect x="${206 + i * 28}" y="40" width="24" height="70" rx="3" fill="#4a5262"/>`;
      for (let j = 0; j < 6; j++) racks += `<rect x="${210 + i * 28}" y="${46 + j * 10}" width="16" height="5" rx="1" fill="#2f3542"/><circle class="act-led" style="animation-delay:${(i * 6 + j) * 0.13}s" cx="${223 + i * 28}" cy="${48.5 + j * 10}" r="1.4" fill="${j % 2 ? "#7ee081" : "#f2c43a"}"/>`; }
    return win(120) + rug(110, 140, 85, 12, "#b9dba0") + racks + desk(40, 112, 80) + codeScreen(50, 92) + codeScreen(86, 92) + desk(140, 120, 60) + codeScreen(155, 100) + plant(22, 122, .9); },
  safety: () => win(120) + rug(190, 136, 70, 12, "#f3b1aa") + desk(150, 104, 90) + monitor(175, 84) + `<path class="act-pulse" d="M248 50l22 38h-44z" fill="#f2c43a"/><rect x="246" y="62" width="4" height="14" fill="#3a2f20"/><circle cx="248" cy="81" r="2" fill="#3a2f20"/>` + plant(30, 120) + plant(274, 138, .8),
  meeting: () => `<ellipse cx="150" cy="118" rx="80" ry="24" fill="#c7996b"/><ellipse cx="150" cy="114" rx="80" ry="24" fill="#d8ad80"/>`
    + [90, 130, 170, 210].map((x) => `<rect x="${x - 8}" y="100" width="16" height="10" rx="2" fill="#fff" opacity=".9"/>`).join("")
    + `<rect x="226" y="40" width="60" height="44" rx="4" fill="#fff" stroke="#c9c2b6" stroke-width="2"/><path class="act-draw" d="M234 76l10-10 10 4 10-14 14 6" stroke="#3b82c4" stroke-width="2" fill="none"/>` + win(120) + plant(28, 124),
  pi: () => win(60) + rug(200, 138, 80, 12, "#a9cdee") + lamp(132, 96) + desk(150, 104, 100) + monitor(185, 84) + `<rect x="250" y="34" width="34" height="74" rx="3" fill="#b07d52"/><circle cx="278" cy="72" r="2.5" fill="#f2cc8f"/>` + plant(30, 122) + plant(140, 132, .8),
};
function buildFurniture() {
  document.querySelectorAll(".room").forEach((room) => {
    const f = FURNITURE[room.dataset.room];
    if (f) room.querySelector(".props").innerHTML = `<svg viewBox="0 0 300 160" preserveAspectRatio="xMidYMid slice" style="inset:0;width:100%;height:100%">${f()}</svg>`;
  });
}


// ---------- handoffs: a document travels between rooms along the corridor ----------
const HANDOFF = {
  EVIDENCE_ADDED: ["library", "whiteboard", (p) => "evidence"],
  HYPOTHESIS_PROPOSED: ["whiteboard", "library", (p) => `${p.hid} for review`],
  NOVELTY_VERDICT: ["library", "whiteboard", (p) => `${p.hid} ${p.label}`],
  EXPERIMENT_SELECTED: ["whiteboard", "compute", (p) => `${p.chosen} spec`],
  GATE_OPENED: ["safety", "pi", (p) => `${p.gate_id} approval`],
  GATE_RESOLVED: ["pi", "compute", (p) => `${p.gate_id} ${p.status}`],
  RUN_FINISHED: ["compute", "meeting", (p) => `${p.eid} results`],
  FINDING: ["meeting", "whiteboard", (p) => `${p.eid} ${p.verdict}`],
  REPLAN: ["meeting", "whiteboard", (p) => "replan"],
  POLICY_DENIED: ["safety", "library", (p) => `${p.policy_id} denied`],
};
const roomCenter = (room) => { const [col, row] = ROOMS[room]; return [col * 33.333 + 16.7, row === 0 ? 30 : 80]; };
function sendPacket(e) {
  const h = HANDOFF[e.type];
  if (!h || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const [from, to, label] = h;
  const [x0, y0] = roomCenter(from); const [x1, y1] = roomCenter(to);
  const el = document.createElement("div");
  el.className = "packet";
  el.style.setProperty("--c", agentOf(e.agent).color);
  el.innerHTML = `<svg viewBox="0 0 16 18"><path d="M2 1h8l4 4v12H2z" fill="#fff" stroke="#8a8378"/><path d="M5 8h6M5 11h6M5 14h4" stroke="var(--c)" stroke-width="1.4"/></svg><span>${esc(label(e.payload || {}))}</span>`;
  $("#packets").appendChild(el);
  const dur = 2000 / Number($("#speed").value || 1);
  el.animate([
    { left: `${x0}%`, top: `${y0}%`, opacity: 0 },
    { left: `${x0}%`, top: "46.5%", opacity: 1, offset: .25 },
    { left: `${x1}%`, top: "46.5%", opacity: 1, offset: .75 },
    { left: `${x1}%`, top: `${y1}%`, opacity: 0 },
  ], { duration: dur, easing: "ease-in-out" }).onfinish = () => el.remove();
  setTimeout(() => el.remove(), dur + 500);  // hidden tabs pause animations; never let packets pile up
}
function renderHud(s, list) {
  const handoffs = list.filter((e) => e.agent !== "system" && e.agent !== "director" && e.type !== "ERROR").length;
  const rejected = s.errors.filter((e) => String(e.payload.message || "").startsWith("handoff rejected")).length;
  const pending = Object.values(s.gates).filter((g) => g.status === "pending").length;
  $("#hud").innerHTML = `<b>Omnigent</b>
    <span title="specialist results recorded in the ledger">handoffs <em>${handoffs}</em></span>
    <span class="${rejected ? "bad" : ""}" title="handoffs rejected by the schema gate">rejected <em>${rejected}</em></span>
    <span class="${s.denials.length ? "bad" : ""}" title="policy denials (P1-P6)">denials <em>${s.denials.length}</em></span>
    <span class="${pending ? "warn" : ""}" title="human approvals waiting (P6)">approvals pending <em>${pending}</em></span>
    <span class="agents-n">${s.seen.length} agents summoned</span>`;
}


// ---------- self-playing demo tour: ?tour=1 (switches views and shows captions) ----------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function showView(v) { document.querySelector(`#nav button[data-view="${v}"]`).click(); }
const CAPTIONS = new URLSearchParams(location.search).get("captions") !== "0";   // ?captions=0 hides them
function caption(t) { const c = $("#caption"); c.hidden = !t || !CAPTIONS; c.textContent = t || ""; }
async function stepTo(n, perEvent) {
  while (pos < n) { pos += 1; render(); sendPacket(events[pos - 1]); await sleep(perEvent); }
}
function highlightLedger(seqs) {
  document.querySelectorAll("#led tr").forEach((tr) => {
    const seq = Number(tr.firstElementChild && tr.firstElementChild.textContent);
    tr.classList.toggle("hl", seqs.includes(seq));
  });
}
async function runTour() {
  stop(); pos = 0; $("#speed").value = "1"; render(); showView("floor");   // tour always plays at 1x
  const ev = 2200;
  const idx = (type) => events.findIndex((e) => e.type === type) + 1;   // 1-based position
  caption("FORGE turns a research question into a reviewable experiment loop, built on Omnigent.");
  await sleep(4500);
  caption("The Librarian gathers cited evidence; the Hypothesizer proposes an AI-generated hypothesis.");
  await stepTo(idx("EXPERIMENT_SELECTED"), ev);
  caption("Every hypothesis has a prediction and a falsifier...");
  showView("hypotheses"); await sleep(4000);
  caption("...committed to the ledger before any compute runs.");
  showView("ledger"); highlightLedger([idx("PREDICTION_COMMITTED"), idx("RUN_STARTED")]); await sleep(4500);
  showView("floor");
  caption("A human approves the experiment (P6). Then it runs on the real NASA archive.");
  await stepTo(idx("RUN_FINISHED"), ev);
  caption("Result: AUC 0.76, 95% interval 0.75 to 0.77, prediction supported.");
  showView("experiments"); await sleep(4500);
  caption("Omnigent runs all eight agents and enforces the budget, tool and approval policies.");
  showView("runtime"); await sleep(4500);
  showView("floor");
  caption("The result changes the next decision: the analyst proposes the next experiment.");
  await stepTo(idx("REPLAN"), ev); await sleep(1500);
  caption("Every step lives in one hash-chained ledger, so the run stays inspectable.");
  showView("ledger"); highlightLedger([]); await sleep(4000);
  showView("floor"); await stepTo(events.length, ev);
  caption("This run measures catalog separability, not planet-vetting accuracy.");
  await sleep(5000); caption("");
}

// ---------- render + replay ----------
function render() {
  const s = fold(events.slice(0, pos));
  const current = events[pos - 1];
  if (pinned && mascotEl(pinned)) showAgentCard(pinned, mascotEl(pinned));
  renderTop(s); renderBanner(s); renderHud(s, events.slice(0, pos)); placeMascots(s, current); renderAlerts(s, current); renderRun(s);
  renderAgents(s); renderRecent(); renderLog(); renderMinimap(s); renderPages(s);
  $("#scrub").max = events.length; $("#scrub").value = pos; $("#pos").textContent = `${pos} / ${events.length}`;
}
function step() {
  if (pos >= events.length) { stop(); return; }
  pos += 1; render(); sendPacket(events[pos - 1]);
}
function play() {
  if (pos >= events.length) pos = 0;
  $("#play").textContent = "❚❚";
  timer = setInterval(step, 2200 / Number($("#speed").value));
}
function stop() { clearInterval(timer); timer = null; $("#play").textContent = "▶"; }

async function loadJsonl(src) {
  const text = await (await fetch(src)).text();
  return text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l)).sort((a, b) => a.seq - b.seq);
}
function connectSSE(url) {
  live = true;
  $("#source").textContent = `live: ${url}`;
  const es = new EventSource(url);
  es.onmessage = (m) => {
    const e = JSON.parse(m.data);
    if (events.some((x) => x.run_id === e.run_id && x.seq === e.seq)) return;
    events.push(e); events.sort((a, b) => a.seq - b.seq);
    if (pos === events.length - 1) { pos = events.length; render(); sendPacket(e); } else render();
  };
}

// The UI's only write: a human decision on a P6 gate, sent to the bridge.
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-gate]");
  if (!b || b.disabled) return;
  const run = events[0] && events[0].run_id;
  b.parentElement.querySelectorAll("button").forEach((x) => { x.disabled = true; });
  b.textContent = "Sending…";
  try {
    const r = await fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: run, gate_id: b.dataset.gate, decision: b.dataset.decision }) });
    const j = await r.json();
    b.textContent = j.ok ? (j.status === "approved" ? "Approved ✓" : "Rejected") : "Failed";
  } catch { b.textContent = "Failed"; }
});

function initNav() {
  document.querySelectorAll("#nav button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#nav button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${b.dataset.view}`));
  }));
}

(async function main() {
  buildFurniture(); initNav();
  $("#play").addEventListener("click", () => (timer ? stop() : play()));
  $("#speed").addEventListener("change", () => { if (timer) { stop(); play(); } });
  $("#scrub").addEventListener("input", (e) => { stop(); pos = Number(e.target.value); render(); });
  const q = new URLSearchParams(location.search);
  const sse = q.get("sse") || (q.get("run") ? `/events?run=${encodeURIComponent(q.get("run"))}` : null);
  if (sse) { connectSSE(sse); render(); return; }
  const src = q.get("src") || "fixtures/exo-demo.jsonl";
  $("#source").textContent = `replay: ${src}`;
  try { events = await loadJsonl(src); } catch (err) { $("#status-text").textContent = `Could not load ${src}`; return; }
  pos = q.has("at") ? Number(q.get("at")) : 0;
  render();
  if (q.has("tour")) { setTimeout(runTour, 2500); return; }
  if (!q.has("at")) play();
})();
