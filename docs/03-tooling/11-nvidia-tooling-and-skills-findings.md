# 11 — NVIDIA tooling & Agent Skills: what helps, what breaks, what bricks

Findings from auditing the upstream NVIDIA material in `references/nvidia-jetson/`
(git-ignored, ~140MB) against **this** workshop. **This file is the *why*.**
Everything here was verified by running it or by reading the shipped source, and
the evidence is cited inline. Anything unproven is marked **UNVERIFIED**.

Read it before installing any NVIDIA Agent Skill on a Jetson, before touching
`.mcp.json`, or when someone proposes "there's an NVIDIA skill for that."

> **The one-line version**: of four upstream repos, exactly **one** MCP server is
> real and useful (Elements, for the dashboard UI), **three** Jetson skills are
> safe to run, and **one skill can brick a workshop Nano**. Nothing upstream helps
> with `trt_pose` / mode 3.

---

## The hardware constraint everything is measured against

| | This workshop's Jetson | What NVIDIA's skills assume |
|---|---|---|
| SoC | **t210**, Maxwell, `sm_53` | t234 (Orin) / t264 (Thor) |
| JetPack / L4T | **4.6.x / L4T 32.7.x** | JetPack 6 / L4T 36+ |
| OS / Python | **Ubuntu 18.04 / Python 3.6** | Ubuntu 22.04+ / Python 3.10+ |

Every incompatibility below traces to this single gap.

---

## 1. MCP: only Elements has one

Four repos live under `references/nvidia-jetson/`. Their MCP status:

| Repo | MCP server? | Evidence |
|---|---|---|
| `NVIDIA/elements` | **Yes** — real, stdio, `@modelcontextprotocol/sdk` | `projects/cli/src/mcp/index.ts` |
| `NVIDIA-AI-IOT/jetson-device-skills` | **No** — zero `mcp` matches repo-wide | Agent Skills only; `install.sh` symlinks `SKILL.md` dirs |
| `NVIDIA/skills` | **No** | Catalog installed via `npx skills add`. Its one `mcp.md` is *documentation inside* the `rag-blueprint` skill teaching an agent to run **NVIDIA RAG's** FastMCP server — not an endpoint of its own |
| `trt_pose` | (excluded from this audit) | — |

**NVIDIA is deliberately using Agent Skills, not MCP, for Jetson developer
tooling.** That suits a 4GB Nano: skills are markdown + scripts, with no resident
server, no port, and no daemon.

### `NVIDIA/skills` is a superset — clone one, not both

The skills shared between `NVIDIA/skills` and `jetson-device-skills` are
**byte-identical** (`diff -rq` clean across all five). The catalog adds ~10 more
(including the BSP-side skills). **Install from `NVIDIA/skills`:**

```bash
npx skills add nvidia/skills --skill jetson-headless-mode --yes
```

### ⚠ `nve` on npm is NOT NVIDIA's

`npm view nve` → **"Run any command on specific Node.js versions"** — a Node
version executor at v18.0.3, unrelated to NVIDIA. The Elements CLI is
**`@nvidia-elements/cli`**; its *bin* is named `nve`, which is the trap. A config
using `npx nve mcp` silently runs the wrong package.

### The MCP config (already applied)

`.mcp.json` is git-ignored by design ("kept on disk, kept out of the repo"), so
this is recorded here rather than versioned:

```json
"elements": {
  "description": "NVIDIA Elements UI Design System (nve-*), custom element schemas, APIs and examples",
  "command": "cmd",
  "args": ["/c", "npx", "-y", "@nvidia-elements/cli@2.1.4", "mcp"],
  "env": { "npm_config_update_notifier": "false" }
}
```

Pinned to `2.1.4`, which matches the vendored source exactly — so **no `pnpm`
build of `references/nvidia-jetson/elements` is needed**. Requires a Claude Code
restart to load.

**Verified** by JSON-RPC handshake, not assumption: serves
`io.github.NVIDIA/elements` v2.1.4 and **18 tools** — `api_list`, `api_get`,
`api_template_validate`, `api_imports_get`, `api_tokens_list`, `api_icons_list`,
`cli_upgrade`, `examples_*` (3), `project_*` (3), `packages_*` (3), `skills_*` (2).

The same tools are reachable from a shell without the MCP, which is how the
component APIs below were checked:

```bash
npx -y @nvidia-elements/cli@2.1.4 api.get --names nve-badge
npx -y @nvidia-elements/cli@2.1.4 api.template.validate '<nve-badge status="danger">FALL</nve-badge>'
```

---

## 2. Elements for the dashboard — vendored and proven offline

Per [`06`](../01-design/06-jetson-allinone-web-dashboard.md), the dashboard is served by
**`relay_server.py` on the student laptop** (FastAPI), *not* the Jetson. So the
Nano's 4GB never touches these assets, and the LAN cable isn't in the asset path.

### Why vendor now

The workshop LAN has **no internet**. There is no recovery path on the morning.
Assets are committed at **`static/vendor/elements/`**:

| File | Source package (npm) | Raw | Gzipped |
|---|---|---|---|
| `core.js` | `@nvidia-elements/core@2.0.4` → `dist/bundles/index.js` | 560,657 | 132,690 |
| `themes.css` | `@nvidia-elements/themes@2.0.0` → `dist/bundles/index.css` | 58,250 | 6,793 |
| `styles.css` | `@nvidia-elements/styles@2.0.2` → `dist/bundles/index.css` | 15,228 | 2,571 |
| `fonts/inter.css` | `@nvidia-elements/themes@2.0.0` → `dist/fonts/inter.css` | 561 | — |
| `fonts/inter.woff2` | `@nvidia-elements/themes@2.0.0` → `dist/fonts/inter.woff2` | 227,180 | 226,493 |
| `LICENSE` | Apache-2.0, from the core package | — | — |
| **Total** | | **~841 KB** | **~360 KB** |

> **Correction to an earlier estimate**: the over-the-wire figure is **~360 KB**,
> not ~225 KB. `inter.woff2` is *already* compressed — gzip buys 687 bytes on it
> (227,180 → 226,493). Only the JS/CSS compress meaningfully.

To re-vendor or upgrade:

```bash
npm pack @nvidia-elements/core@latest @nvidia-elements/themes@latest @nvidia-elements/styles@latest
# extract; copy dist/bundles/index.{js,css} + dist/fonts/* per the table above
```

**`fonts/inter.css` and `fonts/inter.woff2` must stay siblings** — the `@font-face`
uses a relative `src: url('./inter.woff2')`. Nothing else cross-references
anything, so the flat renaming above is safe.

### Offline safety — verified, not assumed

Checked against the actual published bundles:

- **Zero bare imports** in `core.js` — Lit is inlined; nothing resolves at runtime.
- **Zero `@import`** and **zero `url()`** in either bundle CSS.
- The only `http` string in the whole bundle is `http://www.w3.org/2000/svg` — an
  XML namespace identifier, inert, never fetched.
- **No telemetry / analytics** (grepped `gtag|segment|mixpanel|posthog|sentry`).
- **No CDN**: only `projects/starters/go` uses jsDelivr, and its own README
  documents the local-asset swap. The `bundles` starter — which this follows —
  is relative-path only, and explicitly targets *"non-JS build pipelines
  (**Python**, SSR)"*.
- Apache-2.0, public npm registry, **no key or auth**.

**The one network path that exists**: `nve-icon` fetches only if you pass a
`.svg` **URL** as `name` (`projects/core/src/icon/icon.ts:162`). Named icons come
from an inlined registry.
> **Rule: `<nve-icon name="check">`, never `name="....svg">`.**

### Proof it works

`static/vendor/elements/smoke-test.html` renders the dashboard-relevant
components. It must be served over HTTP — **ES modules are blocked on
`file://`**. Per project convention, drive Python with **`uv`**:

```bash
cd static/vendor/elements
uv run python -m http.server 8080
# open http://localhost:8080/smoke-test.html  → expect a green PASS banner
```

Driven in real headless Chrome (2026-07-16), asserting the DOM and every network
request:

```
PASS  nve-badge      defined=true shadow=true h=24px
PASS  nve-dot        defined=true shadow=true h=12px
PASS  nve-pulse      defined=true shadow=true h=40px
PASS  nve-alert      defined=true shadow=true h=16px
PASS  nve-sparkline  defined=true shadow=true h=20px
PASS  nve-button     defined=true shadow=true h=32px
PASS  nve-icon       defined=true shadow=true h=16px

sparkline rendered svg/canvas: true
body font-family: Inter, Roboto, "Open Sans", "Helvetica Neue", sans-serif

total requests: 7    EXTERNAL (non-localhost): 0
OVERALL: PASS — offline-safe
```

### Component API gotchas (validated via `api.template.validate`)

The obvious guesses are wrong. These were caught by the validator, not by reading:

| Guess | Reality |
|---|---|
| `<nve-badge variant="danger">` | **`status`**, not `variant`. Same for `nve-dot`, `nve-alert`, `nve-sparkline` |
| `<nve-pulse><nve-dot/></nve-pulse>` | `nve-pulse` has **no default slot** — self-closing, `aria-label` + `size` only |
| `nve-text` is an element | It's an **attribute** from the styles package: `<h2 nve-text="heading sm muted">` |

`nve-sparkline` takes `data` as a **property**, not an attribute:
`document.querySelector('nve-sparkline').data = [18, 22, 20, …]`.

Validated markup for the docs/06 dashboard (`status="danger" open`, etc.) returns
`[]` — zero errors. **119 `nve-*` components** ship in the bundle.

### Is Elements worth it? — honest note

`docs/01-design/06` asks the dashboard to show *"motion / loud / fall flag + caregiver
note"*. That is a handful of numbers and a badge.
`references/edge_voice_assistant` does a comparable job with **one `index.html` +
`app.js` + `style.css` and zero dependencies**, proven on this hardware.

Elements buys `sparkline`, `badge`, `dot`/`pulse`, `alert`, `card`, `page` and a
coherent NVIDIA look, for ~360 KB and a vendoring step. **Both are defensible.**
The assets are vendored so the choice stays open — vendoring is not a commitment
to using it.

---

## 3. Jetson Agent Skills on a Nano 4GB

### Root cause: one SoC table, no t210 row

`skills/skills/jetson-diagnostic/scripts/detect_jetson.sh:53-63` is the canonical
detector every other skill sources:

```bash
__detect_sku() {
    case "$1" in
        *thor*)                    echo "thor" ;;
        *orin*nano*)               echo "orin-nano" ;;
        *"orin nx"*|*orin-nx*)     echo "orin-nx" ;;
        *"agx orin"*|*"orin agx"*) echo "orin-agx" ;;
        *orin*)                    echo "orin-agx" ;;
        *)                         echo "unknown" ;;     # ← a Nano lands here
    esac
}
```

A Nano's `/proc/device-tree/model` is `nvidia jetson nano developer kit` — no
`orin`, no `thor`. The presence gate still **passes**, so the Nano is admitted as
"a Jetson" and then labelled `unknown`. Whether that's fatal depends on the
consumer.

Two things *do* work: `__detect_l4t` parses `R32 … REVISION: 7.1` → `32.7.1`
correctly, and `__detect_mem_gb` reads `/proc/meminfo` (SoC-agnostic).

### Verdicts

| Skill | Nano 4GB | Mutates? | Why |
|---|---|---|---|
| `jetson-print-device-info` | **WORKS** | no | Prints `nvpmodel` **verbatim rather than parsing** (SKILL.md:116) — that's precisely why no format assumption breaks |
| `jetson-headless-mode` | **WORKS** | yes, safely | SKILL.md:104: *"it does not branch on product line."* Keys only on systemd; `lightdm` (the JetPack 4 default) is covered. Dry-run default (`apply.sh:134`), allowlisted to 3 systemctl forms, every action has a `reversible_command`, `nvargus-daemon`/`nvgetty` on the do-not-disable list |
| `jetson-diagnostic` | **PARTIAL** | no | Valid JSON, correct `l4t_version` / `mem_total_gb` / `product_model`, but `sku`/`variant`/`generation` = `unknown`. Degrades by *capability probe*, not SoC table: `tegrastats` captured opaquely (never field-parsed), `nvidia-smi` absent on JP4 → falls through to nvmap debugfs, which exists on t210 |
| `jetson-memory-audit` | **PARTIAL** | yes, benign | Thin `jq` filter over the diagnostic → inherits the same `unknown`s. `drop_caches.sh` is generic Linux `sysctl vm.drop_caches`, self-restoring |
| `jetson-package` | **WON'T RUN** | no | `artifact_hints.sh:41-58` → `exit 1`: *"refusing to guess a container image tag."* SM table has only 8.7/11.0; Nano needs `sm_53`. Correct behaviour, unusable skill |
| `jetson-optimize-memory` | **🛑 DO NOT USE** | **yes — re-flash** | See below |
| DeepStream skills | **OUT** | — | Target DS 7/8/9; Nano/JP4.6 maxes at **DS 6.0**. Also *"object detection models only"* — not pose |

### 🛑 `jetson-optimize-memory` can brick a workshop Nano

It is **t234/t264-only** and has **no scripts at all** — pure LLM prose, so
nothing executable can hard-fail:

- Its chip table (SKILL.md:60-61) has exactly two columns: **T234 (Orin)** and
  **T264 (Thor)**. No t210 row.
- Every carveout it names — `CARVEOUT_DCE`, `CARVEOUT_RCE`,
  `CARVEOUT_CAMERA_TASKLIST` — refers to the **DCE** (display) and **RCE**
  (camera) co-processors, **which do not exist on t210**.
- The MB1/MB2 BCT + `auxp_ast_config` machinery is a T234+ construct. t210 uses
  `.cfg`-style BCT, not `tegra234-mb1-bct-misc-*.dts`.
- SKILL.md:42-44 seals it: *"T234 -> nvgpu, T264 and later -> OpenRM"* — no t210.
- Its own guardrail is a **prose instruction** (*"Refuse any request to disable a
  carveout not in that table"*), not code. A model may not honour it.
- SKILL.md:225-227 states the stakes: *"Boot fails after MB1 BCT carveout
  disable — restore the pristine misc DTS and re-flash."*

**Never point a student or an agent at this skill on a Nano.** The mitigating
factor is that it edits a BSP tree and defers flashing — it never touches a
running device directly.

### The encouraging half

The **executable** surface degrades honestly nearly everywhere: capability probes
(`command -v nvidia-smi`, `[ -r "$NVMAP_PATH" ]`) instead of SoC tables, opaque
`tegrastats` capture, and an explicit refuse-to-guess where a wrong answer would
cost real money. **The exposure is concentrated in the prose-only layers** — the
diagnostic's reporting guidance, and `optimize-memory`'s entire design.

### Recommended, if installing anything

1. **`jetson-headless-mode`** — the only high-value *and* safe one. Reclaiming GUI
   RAM gives mode 3 / `trt_pose` headroom on a 4GB board.
2. **`jetson-diagnostic` + `jetson-memory-audit`** — decent before/after evidence
   when tuning, *if* you accept the `unknown` fields.

Under [`06`](../01-design/06-jetson-allinone-web-dashboard.md)'s locked topology the Jetson
serves no dashboard, so none of this is on the critical path. **UNVERIFIED**: no
skill here has been run on the actual dev Nano (`jetson-2gNANO`) — the verdicts
above are from reading the shipped source, not from execution.

---

## 4. Nothing upstream helps mode 3

**No pose skill targets Maxwell.** `tao-train-pose-classification` needs Docker +
`nvidia-container-toolkit` and trains ST-GCN on a host GPU; the DeepStream skills
are DS 7+ and detection-only. `trt_pose` on a Nano 4GB is **unassisted** by
anything in these repos.

**UNVERIFIED and load-bearing**: whether a Nano 4GB can run `trt_pose` at a useful
frame rate at all, alongside mode 1/2. That is the real mode-3 risk and no
upstream tooling reduces it.

---

## What changed in the repo

| Path | Status |
|---|---|
| `.mcp.json` | `elements` server added. **Git-ignored** — on-disk only, by design |
| `static/vendor/elements/` | **New.** 6 vendored files + `smoke-test.html`. Committed on purpose: the workshop LAN has no internet |
| `docs/03-tooling/11-…` (this file) | New |

Nothing under `references/` was modified. `references/nvidia-jetson/` stays
git-ignored (~140MB, not ours to version).
