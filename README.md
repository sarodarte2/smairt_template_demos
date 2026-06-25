# SMAIRT TechFest Demos

Welcome to the participant workspace for the SMAIRT TechFest demos.

SMAIRT stands for **Scientific Method with AI Research Template**. These demos show how to use an AI coding assistant while keeping the scientist in control of the question, assumptions, code review, interpretation, and next steps.

You will choose one demo track, generate a fresh SMAIRT project, prime Zoo Code with the project context, and run one documented research iteration.

![SMAIRT demo tracks](demo_tracks.svg)

---

## Choose a demo track

Tracks are listed roughly easiest first. The biology tracks are all
synthetic-data-first (you generate data with a known answer, then check that
your analysis recovers it), pure Python, CPU-only, and need no downloads to
start. Two of them (`proteomics_de`, `protein_properties`) can optionally take a
small real dataset later.

| Track | Domain | Best for | Start here |
|-------|--------|----------|------------|
| Lunar free-return trajectory | Physics | A compact example with no external data. Good if you are newer to coding or want the fastest setup. | [`lunar/DEMO.md`](lunar/DEMO.md) |
| Enzyme kinetics (Michaelis-Menten) | Biochemistry | Recovering Km/Vmax from noisy velocity data; compares nonlinear fit vs. Lineweaver-Burk. Small, very approachable. | [`enzyme_kinetics/DEMO.md`](enzyme_kinetics/DEMO.md) |
| Peptide digestion | Proteomics | In-silico tryptic digestion validated on known proteins; pure standard-library Python. | [`peptide_digest/DEMO.md`](peptide_digest/DEMO.md) |
| Protein sequence properties | Proteomics | Compute MW/pI/GRAVY and test whether hydrophobicity separates membrane from soluble proteins. | [`protein_properties/DEMO.md`](protein_properties/DEMO.md) |
| Differential abundance | Proteomics | Find proteins that change between conditions with t-tests + BH-FDR; planted up/down truth. | [`proteomics_de/DEMO.md`](proteomics_de/DEMO.md) |
| Protein interaction networks | Network biology | Recover planted hubs and modules with centrality and community detection. | [`ppi_network/DEMO.md`](ppi_network/DEMO.md) |
| Human Virome Project | Database / metagenomics | A more advanced database example about phage-host links, CRISPR/Hi-C evidence, geography, and gene function. Requires PostgreSQL setup unless a presenter provides a database or fallback. | [`hvp/DEMO.md`](hvp/DEMO.md) |
| Bring your own problem | Any | Your own research question. Good if you already have an idea and want to turn it into a first SMAIRT iteration. | [`bring_your_own/DEMO.md`](bring_your_own/DEMO.md) |

---

## What you will do

Each demo follows the same basic flow:

1. Pick a track.
2. Read that track's `DEMO.md` file and background question.
3. Create a Python virtual environment.
4. Install the track requirements.
5. Generate a fresh SMAIRT project with Cookiecutter.
6. Configure Zoo Code.
7. Paste the priming prompt so Zoo Code reads the project context files.
8. Ask for one analysis script.
9. Review the script before running it.
10. Run it, interpret the result, and log what you learned.

The point is not to let AI run the project by itself. The point is to use AI speed while preserving a reproducible record of the scientific process.

---

## First-time Zoo Code setup

If you are new to Zoo Code, read this first:

[`USING_ZOO_CODE.md`](USING_ZOO_CODE.md)

For this workshop, configure Zoo Code with:

| Setting | Value |
|---------|-------|
| API Provider | OpenAI Compatible |
| API key | Create a PNNL Birthright key at https://ai-incubator-depot.pnnl.gov/ |
| API Base URL | `https://ai-incubator-api.pnnl.gov` |
| Model | Try `gpt-5-birthright` first; if your key does not show it, use `gpt-5.5-project`. |

> **Important URL check:** use the `depot` URL only to create the key. The API
> Base URL field must be `https://ai-incubator-api.pnnl.gov`, not the `depot`
> website.
>
> **Markdown preview tip:** press `Cmd+Shift+V` on Mac or `Ctrl+Shift+V` on
> Windows to render these `.md` instructions in VS Code.

---

## Common setup pattern

Run these commands from the demo folder you choose. For example, use `demos/lunar` for the Lunar track.

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows users: if PowerShell blocks activation, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal,
then try `.venv\Scripts\Activate.ps1` again. In Command Prompt, use
`.venv\Scripts\activate.bat`.

Then generate a new SMAIRT project:

```bash
cookiecutter https://github.com/biodataganache/smairt-template.git
```

Each track's `DEMO.md` gives the exact Cookiecutter answers to use.

---

## What the folders contain

| Path | Contents |
|------|----------|
| [`lunar/`](lunar/DEMO.md) | Lunar free-return demo instructions, requirements, and background question. |
| [`enzyme_kinetics/`](enzyme_kinetics/DEMO.md) | Michaelis-Menten Km/Vmax recovery demo (synthetic, numpy/scipy). |
| [`peptide_digest/`](peptide_digest/DEMO.md) | In-silico tryptic digestion demo (pure Python). |
| [`protein_properties/`](protein_properties/DEMO.md) | MW/pI/GRAVY and membrane-vs-soluble demo (synthetic, optional real later). |
| [`proteomics_de/`](proteomics_de/DEMO.md) | Differential-abundance demo with t-tests + BH-FDR (synthetic, optional real later). |
| [`ppi_network/`](ppi_network/DEMO.md) | Protein-interaction network demo: hubs and communities (synthetic, networkx). |
| [`hvp/`](hvp/DEMO.md) | HVP demo instructions, database build files, requirements, and background question. |
| [`bring_your_own/`](bring_your_own/DEMO.md) | Bring-your-own-problem instructions, worksheet, and starter requirements. |
| `reserved_demo_a/`, `reserved_demo_b/` | Scaffolded placeholders for two future domain-specific demos (not yet defined). |
| [`USING_ZOO_CODE.md`](USING_ZOO_CODE.md) | First-time Zoo Code setup and workflow guidance. |
| [`demo_tracks.svg`](demo_tracks.svg) | Visual summary of the demo tracks. |

---

## Important notes

- These folders are starting points, not solutions.
- Worked reference solutions are not in this participant folder.
- Review AI-generated code before running it.
- Record your interpretation in the generated SMAIRT project.
- If Zoo Code gets stuck, start a new task and re-prime it from your project files.

Your final product is not just a script. It is a documented reasoning trail that shows what you asked, what was run, what happened, and what you concluded.
