# Deliverable Cleanup Plan — SMAIRT Template Demos

This plan documents the documentation and repository-structure changes needed to
prepare the `smairt_template_demos` collection as a clean, publishable set of
examples. Scope is limited to **documentation and structural cleanup**. Building
out the missing SMAIRT projects (enzyme kinetics, epidemic SIRD) is a separate,
follow-on effort performed by the PI/scientist.

---

## 1. Decisions (from PI)

| Item | Decision |
|---|---|
| `reserved_demo_b/` | Already removed. Scrub any lingering references. |
| `hvp/` | **Do NOT modify or remove** the folder (owned by another party). Avoid mentioning it in shared/top-level docs; where a mention is needed, substitute `epidemic_sird` or the protein LM project. |
| `FINAL_REPORTS_INDEX.md` | **Remove entirely.** It was a temporary hot-plug for the new analysis-report format now covered by the 12-steps material. |
| `enzyme_kinetics/` | **Keep.** Track to be built out later by the PI. |
| `epidemic_sird/` | **Keep.** Track to be built out later by the PI. |
| `ode_convergence/` | **Deprecate / remove.** |
| `bring_your_own/` | **Keep** as a scaffold (intentionally not a completed trail). |

---

## 2. Current-state findings (from codebase analysis)

- **Completed demos (6):** `lunar`, `peptide_digest`, `protein_properties`,
  `proteomics_de`, `ppi_network`, `protein_lm` — each has a generated SMAIRT
  project, analysis trail, and `FINAL_REPORT.md`.
- **Starter-only demos:** `enzyme_kinetics`, `epidemic_sird`, `ode_convergence`,
  `bring_your_own` — each has only `DEMO.md`, `background/01_initial_question.md`,
  `analysis/FINAL_REPORT_TEMPLATE.md`, `requirements.txt` (BYO also has a worksheet).
- **`README.md` is already aligned:** it lists `enzyme_kinetics` (core) and
  `epidemic_sird` (extended), and already omits `ode_convergence`, `hvp`, and
  `reserved_demo_b`. No substitution edits are required in `README.md`.
- **`demo_tracks.svg` is already aligned:** it contains Enzyme Kinetics and
  Epidemic Modeling cards and no `hvp`/`ode_convergence` cards.
- **`FINAL_REPORTS_INDEX.md` is the only shared doc** that references `hvp`,
  `ode_convergence`, and the non-existent `reserved_demo_b`. It is not linked
  from any other file, so deleting it breaks no links.
- **All other `hvp` mentions are self-contained** inside the `hvp/` folder
  (left untouched) except one **legitimate** scientific dataset-identifier note
  in `plans/GIT_HISTORY_REMEDIATION.md` (`PNNL_SM*` in the HVP dataset), which
  should remain.
- **`ode_convergence/DEMO.md` contains a stale `reserved_demo/` path** at its
  environment-setup step, confirming its placeholder origin.

---

## 3. Change set

### 3.1 Delete `FINAL_REPORTS_INDEX.md`
- Remove the file at repo root.
- No inbound links exist, so no follow-up link edits are required.

### 3.2 Deprecate / remove `ode_convergence/`
- Remove the `ode_convergence/` directory (DEMO.md, requirements.txt,
  background/, analysis/).
- Confirm no inbound references remain after removal (only `FINAL_REPORTS_INDEX.md`
  referenced it, and that file is being deleted).

### 3.3 Scrub `reserved_demo_b` references
- Only reference is in `FINAL_REPORTS_INDEX.md` (being deleted). No further
  action once that file is removed. Verify with a final search.

### 3.4 Verify `README.md` integrity (no substitution needed)
- Confirm the repository map and track galleries only reference demos that
  remain (`lunar`, `enzyme_kinetics`, `peptide_digest`, `protein_properties`,
  `proteomics_de`, `ppi_network`, `protein_lm`, `epidemic_sird`,
  `bring_your_own`).
- Confirm no `hvp` / `ode_convergence` / `reserved_demo_b` mentions were
  introduced. (Current state: already clean.)

### 3.5 Leave `hvp/` untouched
- Make no edits inside `hvp/`. Do not add it to any shared doc.
- Keep the legitimate `HVP` dataset identifier note in
  `plans/GIT_HISTORY_REMEDIATION.md`.

### 3.6 Final consistency sweep
- Re-run searches for `ode_convergence`, `reserved_demo_b`, `Reserved Demo`,
  `ODE Convergence`, and `FINAL_REPORTS_INDEX` across `*.md` to confirm zero
  residual references outside `hvp/`.
- Confirm the two retained starter tracks (`enzyme_kinetics`, `epidemic_sird`)
  still have intact `DEMO.md`, `background/01_initial_question.md`, and
  `analysis/FINAL_REPORT_TEMPLATE.md` so the PI can build them out.

---

## 4. Post-cleanup deliverable shape

```
smairt_template_demos/
├── README.md                       (landing page — already aligned)
├── USING_ZOO_CODE.md
├── FIRST_SCRIPT_GUIDE.md
├── demo_tracks.svg                 (already aligned)
├── requirements.txt
├── lunar/                          ✅ completed
├── peptide_digest/                 ✅ completed
├── protein_properties/             ✅ completed
├── proteomics_de/                  ✅ completed
├── ppi_network/                    ✅ completed
├── protein_lm/                     ✅ completed
├── enzyme_kinetics/                🟡 starter — PI to build out
├── epidemic_sird/                  🟡 starter — PI to build out
├── bring_your_own/                 🟡 scaffold (intentional)
├── hvp/                            🔵 untouched (third-party owned)
└── plans/
    ├── GIT_HISTORY_REMEDIATION.md
    └── DELIVERABLE_CLEANUP_PLAN.md (this file)
```

Removed: `FINAL_REPORTS_INDEX.md`, `ode_convergence/`.

---

## 5. Follow-on work (out of scope for this cleanup, PI-led)

- Build the `enzyme_kinetics` SMAIRT project (synthetic Michaelis-Menten curve →
  parameter recovery → noisy-fit interpretation) to a 3-iteration trail.
- Build the `epidemic_sird` SMAIRT project (SIRD ODE integration → conservation
  check → R0 sweep → final-size analysis) to a 3-iteration trail.
- After those trails exist, copy each `analysis/FINAL_REPORT_TEMPLATE.md` to a
  filled-in `FINAL_REPORT.md`.
