// The three-mode comparison (SPEC-03 §9) -- the instructor's / management's view.
//
// ITS OWN MODULE because app.js hit 494 of CLAUDE.md's 500 lines. Splitting is
// also the honest boundary: everything here is STATIC teaching content driven by
// content.js, with no live data, no SSE and no relay state. app.js is the
// instrument; this is the explanation.
//
// SYNCHRONISED ROWS, not per-card accordions (Jeffry's choice, 2026-07-16).
// A topic opens across ALL THREE modes at once, so the columns stay aligned and
// one click answers "how do the three differ on X?" -- which is the only question
// this section exists to answer. Per-card accordions would have made the three
// cards different heights and cost three clicks to compare one topic.

import { UI, MODE_INFO, MODE_IDS } from "/content.js";

// Order matters: it is the argument. Senses first (the multi-modal point, and the
// one row where Mode 3 visibly differs), then what/why, then the thing a student
// actually needs, then the trade-offs.
const TOPICS = [
  { key: "senses", label: "colSenses", kind: "text" },
  { key: "what",   label: "colWhat",   kind: "text" },
  { key: "why",    label: "colWhy",    kind: "text" },
  { key: "how",    label: "colHow",    kind: "list" },
  { key: "pros",   label: "colPros",   kind: "list", cls: "pros" },
  { key: "cons",   label: "colCons",   kind: "list", cls: "cons" },
];

// Open by default: the two most actionable rows. `senses` carries the multi-modal
// point and `how` is what a student came for -- so the page says something useful
// at a glance while still being tidy. Module-level, so the open/closed state
// SURVIVES a language switch (renderCompare re-renders the whole section).
const open = new Set(["senses", "how"]);

const esc = (s) => String(s).replace(/[&<>]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function cell(topic, mode, lang) {
  const c = MODE_INFO[mode][lang];
  const v = c[topic.key];
  if (topic.kind === "list") {
    return `<ul class="${topic.cls || ""}">` +
      v.map((x) => `<li>${esc(x)}</li>`).join("") + "</ul>";
  }
  return `<p class="${topic.key === "senses" ? "senses" : ""}">${esc(v)}</p>`;
}

export function renderCompare(lang) {
  const t = (k) => UI[lang][k];
  const modeWord = lang === "zh" ? "模式" : "Mode";

  const head = MODE_IDS.map((m) => {
    const c = MODE_INFO[m][lang];
    // The name already reads "Mode 1 — send everything"; strip the leading label
    // so the column header is the DISTINCTION, not the number we already show.
    const short = c.name.replace(/^.*?[—-]\s*/, "");
    return `<div class="chead">
      <span class="chead-n">${modeWord} ${m}</span>
      <span class="chead-t">${esc(short)}</span>
      <span class="chead-tag">${esc(c.tagline)}</span>
    </div>`;
  }).join("");

  const rows = TOPICS.map((topic) => {
    const isOpen = open.has(topic.key);
    return `<section class="crow" data-topic="${topic.key}"${isOpen ? " data-open" : ""}>
      <button class="crow-toggle" type="button" aria-expanded="${isOpen}"
              aria-controls="crow-${topic.key}">
        <span class="crow-caret" aria-hidden="true">▸</span>
        <span>${esc(t(topic.label))}</span>
      </button>
      <div class="crow-body" id="crow-${topic.key}">
        ${MODE_IDS.map((m) => `<div class="ccell">${cell(topic, m, lang)}</div>`).join("")}
      </div>
    </section>`;
  }).join("");

  $("compare-head").innerHTML = head;
  $("compare-rows").innerHTML = rows;
}

const $ = (id) => document.getElementById(id);

// Delegated: renderCompare replaces this subtree on every language switch, so a
// listener bound to each button would be re-bound (or leak) each time.
export function wireCompare() {
  $("compare-rows").addEventListener("click", (e) => {
    const btn = e.target.closest(".crow-toggle");
    if (!btn) return;
    const row = btn.closest(".crow");
    const key = row.dataset.topic;
    const nowOpen = !open.has(key);
    if (nowOpen) open.add(key); else open.delete(key);
    row.toggleAttribute("data-open", nowOpen);
    btn.setAttribute("aria-expanded", String(nowOpen));
  });
}
