# Final Reports Index — SMAIRT Template Demonstration Repository

| Field | Details |
|---|---|
| Collection | SMAIRT Template Demonstration Repository |
| Generated | 2026-07-10 |
| Purpose | Track which research projects have completed final reports and which directories currently contain only starter materials or infrastructure. |

---

## 1. Completed Research Reports

The following projects contain completed analysis trails and now have project-level final reports.

| Project | Status | Completed Analysis Trail | Final Report | Final-Report Template |
|---|---|---:|---|---|
| Lunar Free Return | Completed report | 3 analyses | [FINAL_REPORT.md](lunar/lunar_free_return/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](lunar/lunar_free_return/analysis/FINAL_REPORT_TEMPLATE.md) |
| Peptide Digest | Completed report | 3 analyses | [FINAL_REPORT.md](peptide_digest/peptide_digest/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](peptide_digest/peptide_digest/analysis/FINAL_REPORT_TEMPLATE.md) |
| Protein Properties | Completed report | 3 analyses | [FINAL_REPORT.md](protein_properties/protein_properties/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](protein_properties/protein_properties/analysis/FINAL_REPORT_TEMPLATE.md) |
| Proteomics Differential Expression | Completed report | 3 analyses | [FINAL_REPORT.md](proteomics_de/proteomics_de/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](proteomics_de/proteomics_de/analysis/FINAL_REPORT_TEMPLATE.md) |
| PPI Network Analysis | Completed report | 3 analyses | [FINAL_REPORT.md](ppi_network/ppi_network/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](ppi_network/ppi_network/analysis/FINAL_REPORT_TEMPLATE.md) |
| Protein Language Model | Completed report | 9 analyses | [FINAL_REPORT.md](protein_lm/protein_language_model/FINAL_REPORT.md) | [FINAL_REPORT_TEMPLATE.md](protein_lm/protein_language_model/analysis/FINAL_REPORT_TEMPLATE.md) |

---

## 2. Starter or Infrastructure-Only Directories

The following directories now contain a reusable final-report template, but they do not yet have completed final reports because this repository does not currently contain completed analysis trails for them.

| Project Directory | Current Status | Final-Report Template |
|---|---|---|
| Bring Your Own | Starter worksheet and prompt-driven entry point | [FINAL_REPORT_TEMPLATE.md](bring_your_own/analysis/FINAL_REPORT_TEMPLATE.md) |
| Enzyme Kinetics | Starter demo materials and background | [FINAL_REPORT_TEMPLATE.md](enzyme_kinetics/analysis/FINAL_REPORT_TEMPLATE.md) |
| Epidemic SIRD | Starter demo materials and background | [FINAL_REPORT_TEMPLATE.md](epidemic_sird/analysis/FINAL_REPORT_TEMPLATE.md) |
| ODE Convergence | Starter demo materials and background | [FINAL_REPORT_TEMPLATE.md](ode_convergence/analysis/FINAL_REPORT_TEMPLATE.md) |
| HVP | Database-oriented infrastructure and transition materials | [FINAL_REPORT_TEMPLATE.md](hvp/analysis/FINAL_REPORT_TEMPLATE.md) |
| Reserved Demo B | Reserved starter materials | [FINAL_REPORT_TEMPLATE.md](reserved_demo_b/analysis/FINAL_REPORT_TEMPLATE.md) |

---

## 3. Report Format Standardization

The reusable final-report format has been added to the SMAIRT framework template at [FINAL_REPORT_TEMPLATE.md](../smairt-template/%7B%7B%20cookiecutter.project_slug%20%7D%7D/analysis/FINAL_REPORT_TEMPLATE.md). It is intended to be copied to `FINAL_REPORT.md` at any major research checkpoint and upgraded as the project evolves.

The standardized report format emphasizes:

1. Research framing rather than demonstration framing.
2. A project-level executive synthesis.
3. A research audit trail linking hypotheses, scripts, logs, and analyses.
4. A final results matrix.
5. Iteration-level findings.
6. Cross-iteration comparison.
7. Key scientific conclusions.
8. Human intellectual contributions.
9. Reproducibility assets.
10. Limitations and recommended next steps.
11. A final assessment written as a research conclusion.

---

## 4. Current Coverage Summary

| Category | Count |
|---|---:|
| Completed final reports | 6 |
| Starter or infrastructure directories with final-report templates | 6 |
| Total top-level project/report targets covered | 12 |

---

## 5. Notes for Future Updates

- When starter projects gain completed analysis trails, copy their template to `FINAL_REPORT.md` and fill it from evidence in `background/`, `hypotheses/`, `experiments/`, `results/`, and `analysis/`.
- Keep final reports framed as actual research reports, not as template summaries or AI-workflow demonstrations.
- Update this index whenever a new project final report is created or upgraded.
