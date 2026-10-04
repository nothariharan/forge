// FORGE agent mascots. Omnigent can summon any sub-agent, so the UI never
// hard-codes the roster: resolveAgent(name) maps an agent name from the ledger
// to one of 15 archetypes by keyword, and unknown names get a generic dot
// with a stable color. Each archetype has its own silhouette.

const EYES = (y = 28, dx = 7, cx = 30) =>
  `<g class="eyes"><ellipse cx="${cx - dx}" cy="${y}" rx="2.6" ry="3.4" fill="#231a12"/><ellipse cx="${cx + dx}" cy="${y}" rx="2.6" ry="3.4" fill="#231a12"/>
   <circle cx="${cx - dx + 1}" cy="${y - 1.4}" r=".9" fill="#fff"/><circle cx="${cx + dx + 1}" cy="${y - 1.4}" r=".9" fill="#fff"/></g>`;
const SMILE = (y = 35, cx = 30) => `<path d="M${cx - 4} ${y}q4 3.5 8 0" stroke="#231a12" stroke-width="2" fill="none" stroke-linecap="round"/>`;
const CHEEKS = (y = 33, cx = 30, dx = 12) => `<circle cx="${cx - dx}" cy="${y}" r="2.6" fill="rgba(255,110,110,.4)"/><circle cx="${cx + dx}" cy="${y}" r="2.6" fill="rgba(255,110,110,.4)"/>`;
const SHINE = `<path d="M17 17c3-5 8-7 13-7" stroke="rgba(255,255,255,.55)" stroke-width="3" stroke-linecap="round" fill="none"/>`;
const face = (y = 28) => EYES(y) + SMILE(y + 7) + CHEEKS(y + 5);

export const ARCHETYPES = {
  director: { label: "Director", role: "Omnigent orchestrator", color: "#f5b82e", home: "pi",
    keys: ["director", "forge", "orchestr", "lead", "polly"],
    draw: (c) => `<path d="M30 6l6.5 13.5 14.5 1.7-10.8 10 3 14.6L30 38.6 16.8 45.8l3-14.6L9 21.2l14.5-1.7z" fill="${c}" stroke="#d99a12" stroke-width="1.5" stroke-linejoin="round"/>
      ${EYES(26)}${SMILE(32)}<path d="M14 24a16 16 0 0 1 32 0" stroke="#3a2f20" stroke-width="2.4" fill="none"/><rect x="11" y="22" width="5" height="8" rx="2" fill="#3a2f20"/><path d="M46 28l3 4h-5" stroke="#3a2f20" stroke-width="2" fill="none"/>` },
  librarian: { label: "Librarian", role: "Finds and cites literature", color: "#f28c38", home: "library",
    keys: ["librar", "literature", "citation"],
    draw: (c) => `<rect x="11" y="9" width="38" height="40" rx="9" fill="${c}"/><rect x="11" y="9" width="7" height="40" rx="3" fill="rgba(0,0,0,.12)"/>
      <path d="M38 9v12l-3-2.5-3 2.5V9z" fill="#e2468f"/>${SHINE}
      <circle cx="24" cy="28" r="5.5" fill="none" stroke="#3a2f20" stroke-width="1.8"/><circle cx="38" cy="28" r="5.5" fill="none" stroke="#3a2f20" stroke-width="1.8"/><path d="M29.5 28h3" stroke="#3a2f20" stroke-width="1.8"/>
      ${EYES(28, 7, 31)}${SMILE(38, 31)}` },
  scout: { label: "Scout", role: "Searches the web and databases", color: "#2bb5a8", home: "library",
    keys: ["scout", "search", "crawl", "fetch", "web"],
    draw: (c) => `<rect x="14" y="14" width="32" height="36" rx="16" fill="${c}"/>${SHINE}<path d="M30 14V5" stroke="#1f7f76" stroke-width="2.5"/>
      <circle class="blink-dot" cx="30" cy="5" r="3.2" fill="#ff5d5d"/><path d="M36 4a7 7 0 0 1 4 6M24 4a7 7 0 0 0-4 6" stroke="#1f7f76" stroke-width="1.6" fill="none"/>${face(30)}` },
  referee: { label: "Referee", role: "Checks novelty and prior art", color: "#4a90e2", home: "library",
    keys: ["referee", "novelty", "prior"],
    draw: (c) => `<path d="M30 6l19 6v14c0 13-8 21-19 25-11-4-19-12-19-25V12z" fill="${c}"/>
      <path d="M22 9v40M30 6v45M38 9v40" stroke="rgba(255,255,255,.35)" stroke-width="3"/>${face(26)}
      <circle cx="44" cy="38" r="3.5" fill="#d8d8d8" stroke="#888"/><path d="M41 37l-6-4" stroke="#888" stroke-width="1.5"/>` },
  hypothesizer: { label: "Hypothesizer", role: "Proposes falsifiable hypotheses", color: "#9b6cf0", home: "whiteboard",
    keys: ["hypoth", "idea", "ideat"],
    draw: (c) => `<g class="glow"><path d="M30 1v4M12 8l3 3M48 8l-3 3M5 24h4M51 24h4" stroke="#f6c343" stroke-width="2.5" stroke-linecap="round"/></g>
      <path d="M30 8c11 0 18 8 18 17 0 7-4 11-7 14v5H19v-5c-3-3-7-7-7-14 0-9 7-17 18-17z" fill="${c}"/>${SHINE}
      <rect x="20" y="44" width="20" height="4" rx="2" fill="#8a8378"/><rect x="22" y="49" width="16" height="4" rx="2" fill="#8a8378"/>${face(26)}` },
  planner: { label: "Planner", role: "Picks the next experiment within budget", color: "#f27bb4", home: "whiteboard",
    keys: ["plann", "schedul", "budget", "select"],
    draw: (c) => `<path d="M30 7l18 10.5v21L30 49 12 38.5v-21z" fill="${c}"/>${SHINE}${face(26)}
      <rect x="39" y="30" width="13" height="17" rx="2" fill="#fff" stroke="#c9c2b6"/><path d="M42 35h7M42 39h7M42 43h5" stroke="#e2468f" stroke-width="1.4"/><rect x="43" y="28" width="5" height="3" rx="1" fill="#8a8378"/>` },
  experimenter: { label: "Experimenter", role: "Runs computational experiments", color: "#8ccf3f", home: "compute",
    keys: ["experiment", "runner", "execut", "simulat"],
    draw: (c) => `<path d="M23 6h14v13l12 22c2 5-1 9-6 9H17c-5 0-8-4-6-9l12-22z" fill="${c}"/><rect x="21" y="4" width="18" height="5" rx="2" fill="#5d8f24"/>
      <circle class="bubble1" cx="24" cy="40" r="2.5" fill="rgba(255,255,255,.7)"/><circle class="bubble2" cx="34" cy="44" r="1.8" fill="rgba(255,255,255,.7)"/>${EYES(30)}${SMILE(36)}` },
  coder: { label: "Builder", role: "Writes and runs code", color: "#3d4654", home: "compute",
    keys: ["code", "coder", "build", "engineer", "dev", "program", "codex"],
    draw: (c) => `<rect x="10" y="14" width="40" height="36" rx="8" fill="${c}"/><rect x="14" y="19" width="32" height="20" rx="5" fill="#0f1a12"/>
      <text x="30" y="33" text-anchor="middle" font-family="monospace" font-size="10" font-weight="700" fill="#7ee081">&lt;/&gt;</text>
      <path d="M8 14c0-9 10-12 22-12s22 3 22 12z" fill="#f2c43a"/><rect x="6" y="12" width="48" height="4" rx="2" fill="#d9a520"/>
      <circle cx="22" cy="45" r="1.6" fill="#7ee081"/><circle cx="27" cy="45" r="1.6" fill="#f2c43a"/>` },
  data: { label: "Data Engineer", role: "Fetches and cleans datasets", color: "#22a6c9", home: "compute",
    keys: ["data", "etl", "dataset", "loader", "archive"],
    draw: (c) => `<path d="M12 14v30c0 4 8 7 18 7s18-3 18-7V14z" fill="${c}"/><ellipse cx="30" cy="14" rx="18" ry="6" fill="#5ec9e6"/>
      <path d="M12 24c0 4 8 7 18 7s18-3 18-7M12 34c0 4 8 7 18 7s18-3 18-7" stroke="rgba(255,255,255,.35)" stroke-width="2" fill="none"/>${EYES(29)}${SMILE(35)}` },
  analyst: { label: "Analyst", role: "Interprets results", color: "#f2c43a", home: "meeting",
    keys: ["analy", "interpret", "evaluat"],
    draw: (c) => `<circle cx="28" cy="29" r="20" fill="${c}"/>${SHINE}${face(27)}
      <circle cx="44" cy="40" r="7" fill="rgba(255,255,255,.6)" stroke="#3a2f20" stroke-width="2.4"/><path d="M49 45l5 5" stroke="#3a2f20" stroke-width="3" stroke-linecap="round"/>` },
  statistician: { label: "Statistician", role: "Uncertainty and significance", color: "#5b5fd6", home: "meeting",
    keys: ["stat", "bayes", "uncertain"],
    draw: (c) => `<path d="M30 6c3 0 5 2 7 5l14 28c2 5-1 10-6 10H15c-5 0-8-5-6-10l14-28c2-3 4-5 7-5z" fill="${c}"/>${EYES(30)}${SMILE(36)}
      <text x="30" y="47" text-anchor="middle" font-family="serif" font-size="11" font-style="italic" fill="#fff">σ</text>` },
  critic: { label: "Critic", role: "Reviews and challenges claims", color: "#c74b6b", home: "meeting",
    keys: ["critic", "review", "skeptic", "red"],
    draw: (c) => `<rect x="11" y="11" width="38" height="38" rx="6" fill="${c}"/>${SHINE}${EYES(28)}
      <circle cx="37" cy="28" r="6" fill="none" stroke="#f2c43a" stroke-width="2"/><path d="M43 31q3 8 1 12" stroke="#f2c43a" stroke-width="1.2" fill="none"/>
      <path d="M24 37h12" stroke="#231a12" stroke-width="2" stroke-linecap="round"/><path d="M8 44l12-12" stroke="#e23b3b" stroke-width="3.5" stroke-linecap="round"/>` },
  safety: { label: "Safety", role: "Flags risk, routes approvals", color: "#ef5b4f", home: "safety",
    keys: ["safety", "policy", "guard", "risk", "compliance"],
    draw: (c) => `<path d="M21 7h18l12 12v18L39 49H21L9 37V19z" fill="${c}" stroke="#fff" stroke-width="2.5"/>${EYES(26)}${SMILE(32)}
      <rect x="20" y="38" width="20" height="5" rx="2.5" fill="#fff"/>` },
  writer: { label: "Writer", role: "Drafts the report", color: "#f08a5d", home: "meeting",
    keys: ["writ", "report", "summar", "author", "draft"],
    draw: (c) => `<path d="M18 12h24v30l-12 12-12-12z" fill="${c}"/><rect x="18" y="5" width="24" height="9" rx="3" fill="#f2a7b5"/><rect x="18" y="12" width="24" height="3" fill="#c9c2b6"/>
      <path d="M27 51l3 3 3-3z" fill="#3a2f20"/>${EYES(25)}${SMILE(31)}` },
  astronomer: { label: "Astronomer", role: "Domain specialist (astronomy)", color: "#2f3e8f", home: "library",
    keys: ["astro", "domain", "special", "exo", "planet", "tess", "kepler"],
    draw: (c) => `<ellipse cx="30" cy="30" rx="27" ry="7" fill="none" stroke="#f2c43a" stroke-width="3" transform="rotate(-15 30 30)"/>
      <circle cx="30" cy="29" r="17" fill="${c}"/><circle cx="23" cy="20" r="2" fill="rgba(255,255,255,.4)"/>${EYES(28)}${SMILE(34)}
      <path d="M50 8l1.2 2.8 3 .4-2.2 2 .6 3-2.6-1.5-2.6 1.5.6-3-2.2-2 3-.4z" fill="#f2c43a"/>` },
  human: { label: "You (PI)", role: "Human in the loop", color: "#f3c9a0", home: "pi",
    keys: ["human", "pi", "user", "you", "scientist"],
    draw: () => `<rect x="14" y="30" width="32" height="22" rx="11" fill="#3b82c4"/><path d="M26 30l4 6 4-6" fill="#fff"/>
      <circle cx="30" cy="20" r="12" fill="#f3c9a0"/><path d="M18 18c0-9 6-12 12-12s13 3 12 13c-3-4-8-6-12-6s-9 2-12 5z" fill="#3a2f20"/>
      ${EYES(21, 5)}<path d="M27 26q3 2.5 6 0" stroke="#231a12" stroke-width="1.8" fill="none" stroke-linecap="round"/>
      <rect x="44" y="38" width="9" height="10" rx="2" fill="#fff" stroke="#c9c2b6"/><path d="M53 41h2v4h-2" stroke="#c9c2b6" fill="none"/>` },
};

const GENERIC_COLORS = ["#7c9cf0", "#e98fd0", "#56c2a6", "#f0a35e", "#a3a3f5", "#e57373", "#64b5f6"];
const hash = (s) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);

export function resolveAgent(name) {
  const n = String(name || "agent").toLowerCase();
  for (const [type, a] of Object.entries(ARCHETYPES)) {
    if (n === type || a.keys.some((k) => n.includes(k))) return { ...a, type, name };
  }
  const color = GENERIC_COLORS[hash(n) % GENERIC_COLORS.length];
  return { type: "generic", name, label: n[0].toUpperCase() + n.slice(1), role: "Summoned sub-agent", color, home: "meeting",
    draw: (c) => `<circle cx="30" cy="29" r="19" fill="${c}"/>${SHINE}${face(27)}` };
}

export function mascotSVG(name) {
  const a = resolveAgent(name);
  return `<svg viewBox="0 0 60 60" aria-hidden="true"><ellipse cx="30" cy="56" rx="15" ry="3" fill="rgba(60,40,20,.16)"/>${a.draw(a.color)}</svg>`;
}
