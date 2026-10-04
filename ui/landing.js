// Landing page: mascots from the lab, and "A day in the lab" rendered from the
// real run's exported ledger (fixtures/live-exo-9.jsonl). No numbers are typed in;
// they are read from the ledger and explained in plain language.
import { ARCHETYPES, mascotSVG } from "./mascots.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LIVE = ["director", "librarian", "hypothesizer", "referee", "planner", "safety", "experimenter", "analyst"];

// "FORGE" in the pixel serif wordmark wherever it appears in visible text
function wordmark(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (/FORGE/.test(n.nodeValue) && !n.parentElement.closest("code, script, style, .wm, title")
      ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  });
  const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const span = document.createElement("span");
    span.innerHTML = esc(n.nodeValue).replace(/FORGE/g, '<span class="wm">FORGE</span>');
    n.replaceWith(...span.childNodes);
  }
}

// parades and inline mascots
const paradeSet = ["librarian", "hypothesizer", "referee", "planner", "experimenter", "analyst", "safety", "director", "human"];
for (const id of ["#parade", "#parade2"]) $(id).innerHTML = paradeSet.map((n) => `<span>${mascotSVG(n)}</span>`).join("");
document.querySelectorAll(".m[data-agent]").forEach((el) => { el.innerHTML = mascotSVG(el.dataset.agent); });

// roster: one grid, equal boxes, tagged by what they did in the live run
const card = (n, tag, cls) => { const a = ARCHETYPES[n];
  return `<div class="ag"><div class="pic">${mascotSVG(n)}</div><b>${esc(a.label)}</b><span>${esc(a.role)}</span><span class="tag ${cls}">${tag}</span></div>`; };
$("#roster").innerHTML = [
  ...LIVE.map((n) => card(n, "ran live", "live")),
  card("human", "approves experiments", "you"),
  ...Object.keys(ARCHETYPES).filter((k) => !LIVE.includes(k) && k !== "human").map((n) => card(n, "on call", "")),
].join("");

// lab iframe loads only when scrolled near, so the tour starts when someone is watching
const frame = $("#labframe");
new IntersectionObserver((entries, obs) => {
  if (entries.some((e) => e.isIntersecting)) { frame.src = frame.dataset.src; obs.disconnect(); }
}, { rootMargin: "200px" }).observe(frame);

// ---------- a day in the lab, from the ledger, in plain language ----------
const pct = (x) => `${Math.round(x * 100)}%`;
const aucOf = (m) => m.primary_oof_auc ?? m.primary_arm_auc;
// first sentence of agent text, without the AI-generated preamble agents add
function sentence(t, max = 170) {
  let s = String(t || "").replace(/^\[?AI[- ]generated[^.\]]*[.\]]\s*/i, "").trim();
  const cut = s.search(/[.?!](\s|$)/);
  if (cut > 20 && cut < max) return s.slice(0, cut + 1);
  if (s.length <= max) return s;
  // too long: end cleanly at the last clause break before the limit, never mid-word
  const head = s.slice(0, max);
  const brk = Math.max(head.lastIndexOf(", "), head.lastIndexOf(" ("), head.lastIndexOf("; "));
  return `${head.slice(0, brk > 40 ? brk : head.lastIndexOf(" ")).trim()}.`;
}
const LINES = {
  RUN_CREATED: (p) => ["The question arrives", sentence(p.question.replace(/\s*\(?Provisional.*$/i, ""), 200)],
  EVIDENCE_ADDED: (p) => [`The Librarian finds ${p.claims.length} cited sources`, p.claims.map((c) => c.ref).join(" · ")],
  HYPOTHESIS_PROPOSED: (p) => [`A hypothesis (${p.hid}), labelled AI-generated`, sentence(p.claim)],
  NOVELTY_VERDICT: (p) => ["The Referee checks prior work", { NOVEL: "Looks new.", KNOWN: "Already known.", CONTRADICTED: "Contradicted by prior work.", UNCERTAIN: "Not clearly answered before: needs a closer search." }[p.label] || p.label],
  PREDICTION_COMMITTED: () => ["The prediction is locked in first", "What the result should look like, and what would prove it wrong, is recorded before anything runs."],
  EXPERIMENT_SELECTED: (p) => [`The Planner picks ${p.chosen} out of ${p.candidates.length} possible experiments`, "The one that teaches the most for the compute it costs."],
  GATE_OPENED: () => ["Safety asks for a human go-ahead", "Running the experiment spends compute, so it waits for approval."],
  GATE_RESOLVED: (p) => [p.status === "approved" ? "You approve it" : "You reject it", p.resolved_via === "lab-ui" ? "One click on the lab's approval banner." : `Via ${p.resolved_via}.`],
  RUN_STARTED: (p) => [`The experiment (${p.eid}) is queued`, "It waits at the gate until a human approves it."],
  RUN_FINISHED: (p) => { const a = aucOf(p.metrics || {});
    return [`${p.eid} runs on the NASA Exoplanet Archive`, a ? `The catalog values tell followed-up objects from open candidates ${pct(a)} of the time.` : `Status: ${p.status}.`]; },
  FINDING: (p) => [{ SUPPORTS: "The prediction holds", REFUTES: "The prediction fails", INCONCLUSIVE: "Inconclusive" }[p.verdict] || p.verdict,
    `${pct(p.effect)}, with 95% confidence it is between ${pct(p.ci[0])} and ${pct(p.ci[1])}.`],
  REPLAN: (p) => ["The result shapes the next step", sentence(p.next || p.reason)],
  RUN_COMPLETED: (p) => ["The run is complete", p.candidate ? `Recommended: ${p.candidate}.` : "Closed."],
};

async function day() {
  let events;
  try {
    const text = await (await fetch("fixtures/live-exo-9.jsonl")).text();
    events = text.split("\n").filter(Boolean).map((l) => JSON.parse(l)).sort((a, b) => a.seq - b.seq);
  } catch { $("#day").innerHTML = '<p class="muted">The run could not be loaded.</p>'; return; }
  $("#day").innerHTML = '<div class="rail" aria-hidden="true"><i id="rail-fill"></i></div>' + events.map((e) => {
    const f = LINES[e.type]; if (!f) return "";
    const [title, body] = f(e.payload);
    const who = e.type === "GATE_RESOLVED" ? "human" : e.agent;
    const cls = who === "human" ? "human" : e.type === "FINDING" ? "result" : "";
    return `<div class="ev ${cls}"><span class="t">${e.ts.slice(11, 16)}</span><span class="who" title="${esc(who)}">${mascotSVG(who)}</span>
      <div class="bubble"><b>${esc(title)}</b><span>${esc(body)}</span></div></div>`;
  }).join("");
  scrollTimeline();

  const fin = events.find((e) => e.type === "FINDING")?.payload;
  const agents = new Set(events.map((e) => e.agent).filter((a) => !["system", "human", "harness"].includes(a)));
  if (fin) {
    const hits = Math.round(fin.effect * 100);
    $("#result").innerHTML = `<div class="stat"><b>${hits} in 100</b><span>Pick one followed-up object and one open candidate at random: this often, the catalog values alone tell which is which</span></div>
      <div class="stat"><b>${pct(fin.ci[0])} to ${pct(fin.ci[1])}</b><span>The range we are 95% confident the true figure is in</span></div>
      <div class="stat"><b>${events.length} steps</b><span>${agents.size} agents, 1 human approval, every step on the record</span></div>`;
    countUp($("#result"));
  }
  const first = events[0], last = events[events.length - 1];
  $("#day-note").textContent = `Real Omnigent run ${first.run_id}, ${first.ts.slice(0, 10)}, ${first.ts.slice(11, 16)} to ${last.ts.slice(11, 16)} UTC, on a NASA Exoplanet Archive snapshot; the record's hash chain verifies. For researchers: the figure is the experiment's AUC (${fmt(fin?.effect)}). It shows the catalog's own values separate resolved from unresolved objects; it is not a measure of how accurately planets are vetted.`;
}
// ---------- scroll-triggered timeline ----------
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
function scrollTimeline() {
  const day = $("#day"), fill = $("#rail-fill"), evs = [...day.querySelectorAll(".ev")];
  if (REDUCED) { evs.forEach((e) => e.classList.add("in", "lit")); fill.style.height = "100%"; return; }
  const update = () => {
    const vh = innerHeight, r = day.getBoundingClientRect();
    // the rail fills as the reader's eye line (60% down the screen) moves through the timeline
    const eye = vh * 0.6;
    const progress = Math.min(1, Math.max(0, (eye - r.top) / r.height));
    fill.style.height = `${progress * 100}%`;
    for (const el of evs) {
      const top = el.getBoundingClientRect().top;
      if (top < vh * 0.88) el.classList.add("in");          // appears as it scrolls into view
      el.classList.toggle("lit", top + 22 < eye);            // lights up once the rail reaches it
    }
  };
  // scroll events already arrive at most once per frame; the work is 13 rect reads
  addEventListener("scroll", update, { passive: true });
  addEventListener("resize", update);
  update();
}
// numbers in the result cards count up the first time they are seen
function countUp(root) {
  const targets = [...root.querySelectorAll(".stat b")];
  const parts = targets.map((b) => b.textContent);
  if (REDUCED) return;
  const counted = (s, f) => s.replace(/\d+/g, (n, at) => (s.slice(at).startsWith("100") && /in 100/.test(s) && at === s.indexOf("100") ? n : f(Number(n))));
  targets.forEach((b, i) => { b.textContent = counted(parts[i], () => 0); });
  new IntersectionObserver((es, obs) => {
    if (!es.some((e) => e.isIntersecting)) return;
    obs.disconnect();
    const t0 = performance.now(), dur = 1300;
    const tick = (now) => {
      const k = Math.min(1, (now - t0) / dur), ease = 1 - Math.pow(1 - k, 3);
      targets.forEach((b, i) => { b.textContent = counted(parts[i], (n) => String(Math.round(n * ease))); });
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, { threshold: 0.5 }).observe(root);
}
const fmt = (x) => (typeof x === "number" ? x.toFixed(3) : "n/a");

wordmark(document.body);
day();

// copy buttons for the run-it-yourself commands
document.querySelectorAll(".copy-btn").forEach((b) => b.addEventListener("click", async () => {
  const text = b.previousElementSibling.textContent;
  try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; }
  catch { b.textContent = "Select + copy"; }
  setTimeout(() => { b.textContent = "Copy"; }, 1600);
}));
