// Landing page: mascots from the lab, and "A day in the lab" rendered from the
// real run's exported ledger (fixtures/live-exo-9.jsonl). No numbers are typed in.
import { ARCHETYPES, mascotSVG } from "./mascots.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LIVE = ["director", "librarian", "hypothesizer", "referee", "planner", "safety", "experimenter", "analyst"];

// parades and inline mascots
const paradeSet = ["librarian", "hypothesizer", "referee", "planner", "experimenter", "analyst", "safety", "director", "human"];
for (const id of ["#parade", "#parade2"]) $(id).innerHTML = paradeSet.map((n) => `<span>${mascotSVG(n)}</span>`).join("");
document.querySelectorAll(".m[data-agent]").forEach((el) => { el.innerHTML = mascotSVG(el.dataset.agent); });

// roster
const card = (n) => { const a = ARCHETYPES[n]; return `<div class="ag"><div class="pic">${mascotSVG(n)}</div><b>${esc(a.label)}</b><span>${esc(a.role)}</span></div>`; };
$("#roster").innerHTML = [...LIVE, "human"].map(card).join("");
$("#roster-more").innerHTML = Object.keys(ARCHETYPES).filter((k) => !LIVE.includes(k) && k !== "human").map(card).join("");

// lab iframe loads only when scrolled near, so the tour starts when someone is watching
const frame = $("#labframe");
new IntersectionObserver((entries, obs) => {
  if (entries.some((e) => e.isIntersecting)) { frame.src = frame.dataset.src; obs.disconnect(); }
}, { rootMargin: "200px" }).observe(frame);

// a day in the lab, from the ledger
const LINES = {
  RUN_CREATED: (p) => ["The question arrives", p.question],
  EVIDENCE_ADDED: (p) => [`${p.claims.length} cited sources`, p.claims.map((c) => c.ref).join(" · ")],
  HYPOTHESIS_PROPOSED: (p) => [`Hypothesis ${p.hid}, labelled AI-generated`, p.claim],
  NOVELTY_VERDICT: (p) => [`Novelty: ${p.label}`, (p.prior_art || []).length ? `Closest prior work: ${p.prior_art.join(", ")}` : "No close prior work named"],
  PREDICTION_COMMITTED: (p) => [`Prediction committed for ${p.eid}, before any compute`, `${p.metric}: ${p.mean} ± ${p.sd}`],
  EXPERIMENT_SELECTED: (p) => [`Chose ${p.chosen} of ${p.candidates.length} candidate experiments`, p.candidates.find((c) => c.eid === p.chosen)?.design || ""],
  GATE_OPENED: (p) => ["Safety asks for approval", p.action],
  GATE_RESOLVED: (p) => [`You ${p.status} it`, `from the ${p.resolved_via === "lab-ui" ? "lab" : p.resolved_via}`],
  RUN_STARTED: (p) => [`Running ${p.eid}`, p.code_hash],
  RUN_FINISHED: (p) => [`${p.eid} finished: ${p.status}`, `primary AUC ${fmt(p.metrics.primary_oof_auc ?? p.metrics.primary_arm_auc)}`],
  FINDING: (p) => [`Finding: ${p.verdict}`, `effect ${fmt(p.effect)}, 95% CI [${p.ci.map(fmt).join(", ")}]`],
  REPLAN: (p) => ["The next decision", p.next || p.reason],
  RUN_COMPLETED: (p) => [`Run ${p.status}`, `candidate ${p.candidate ?? "n/a"}`],
};
const fmt = (x) => (typeof x === "number" ? x.toFixed(4).replace(/0+$/, "").replace(/\.$/, "") : x);
const clip = (t, n) => (String(t).length > n ? `${String(t).slice(0, n - 1)}…` : t);

async function day() {
  let events;
  try {
    const text = await (await fetch("fixtures/live-exo-9.jsonl")).text();
    events = text.split("\n").filter(Boolean).map((l) => JSON.parse(l)).sort((a, b) => a.seq - b.seq);
  } catch { $("#day").innerHTML = '<p class="muted">The run could not be loaded.</p>'; return; }
  $("#day").innerHTML = events.map((e) => {
    const f = LINES[e.type]; if (!f) return "";
    const [title, body] = f(e.payload);
    const who = e.type === "GATE_RESOLVED" ? "human" : e.agent;
    const cls = who === "human" ? "human" : e.type === "FINDING" ? "result" : "";
    return `<div class="ev ${cls}"><span class="t">${e.ts.slice(11, 16)}</span><span class="who" title="${esc(who)}">${mascotSVG(who)}</span>
      <div class="bubble"><b>${esc(title)}</b><span>${esc(clip(body, 220))}</span></div></div>`;
  }).join("");
  const obs = new IntersectionObserver((es) => es.forEach((x) => { if (x.isIntersecting) { x.target.classList.add("in"); obs.unobserve(x.target); } }), { threshold: 0.2 });
  document.querySelectorAll(".ev").forEach((el) => obs.observe(el));

  const fin = events.find((e) => e.type === "FINDING")?.payload;
  const agents = new Set(events.map((e) => e.agent).filter((a) => !["system", "human", "harness"].includes(a)));
  if (fin) {
    $("#result").innerHTML = `<div class="stat"><b>${fmt(fin.effect)}</b><span>primary AUC (${esc(fin.verdict.toLowerCase())})</span></div>
      <div class="stat"><b>[${fin.ci.map((x) => x.toFixed(3)).join(", ")}]</b><span>95% bootstrap interval</span></div>
      <div class="stat"><b>${events.length}</b><span>ledger events · ${agents.size} agents · 1 human approval</span></div>`;
  }
  const first = events[0], last = events[events.length - 1];
  $("#day-note").textContent = `Real Omnigent run ${first.run_id}, ${first.ts.slice(0, 10)}, ${first.ts.slice(11, 16)} to ${last.ts.slice(11, 16)} UTC, on a NASA Exoplanet Archive snapshot. The hash chain verifies. It measures how well catalog values separate resolved from unresolved TOIs, not planet-vetting accuracy.`;
}
day();
