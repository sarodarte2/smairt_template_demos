# SMAIRT Demos

This is the participant workspace for the SMAIRT TechFest demo. Each subfolder is
a **starting point**, not a solution. You get the background and the research
question (and for HVP, the method to build the database). Your job is to use
**SMAIRT** to answer the question by writing the scripts.

> Solutions are intentionally NOT here. Worked-out reference versions live in the
> repo's `reference_solutions/` (used by the presenter).

> **First time using an AI coding assistant?** Read
> [`USING_ZOO_CODE.md`](USING_ZOO_CODE.md). It walks through installing Zoo
> Code, signing in, priming the assistant, and approving its edits. Every demo
> assumes you've skimmed it.

## How a demo works (all three follow the same shape)

**Step 0: set up your environment (do this first).** From the demo folder you
chose, create a virtual environment and install its requirements. This installs
`cookiecutter` (needed in Step 2) plus that demo's libraries:

```bash
cd demos/<your-demo>          # e.g. demos/lunar
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Hitting `command not found: cookiecutter`? You skipped Step 0 or your venv is
> not activated. Re-run the lines above (and confirm your prompt shows `.venv`).

Then, with the venv active:

1. **Read the demo's `DEMO.md`** and its `background/01_initial_question.md`.
2. **Generate a fresh SMAIRT project** with cookiecutter (the demo gives you the
   exact values):
   ```bash
   cookiecutter https://github.com/biodataganache/smairt-template.git
   ```
   Cookiecutter then asks 12 questions interactively. If you've run it before, it
   first asks `Is it okay to delete and re-download it? [y/n] (y):`. Press
   **Enter**. Press **Enter** to accept a default, or type the value/number. For
   the numbered "Select" prompts (domain, ai_tool, etc.) type the **number**
   (e.g. `4`), not the word. Each demo's `DEMO.md` lists the exact answers to
   use; for `ai_tool` choose `2` (gpt5, Zoo Code with `gpt-5.5-project`).
3. **Copy the background/question into your new project:**
   ```bash
   cp background/01_initial_question.md <your_project>/background/
   ```
4. **Configure and prime your AI assistant (Zoo Code).** Use **OpenAI Compatible**,
   create a PNNL Birthright API key at https://ai-incubator-depot.pnnl.gov/, set
   **API Base URL** to `https://ai-incubator-api.pnnl.gov`, and select model
   `gpt-5.5-project`. Then paste the demo's priming prompt directly into Zoo Code;
   that prompt tells the AI to read `prompts/AI_CONTEXT.md`,
   `prompts/CODE_CONVENTIONS.md`, and your `background/01_initial_question.md`.
5. **Run SMAIRT iterations on your own**: hypothesis, ask AI for code, review,
   run, interpret, log, then choose the next step. Nothing is pre-written for you.

## The three demos

| Demo | You are given | You build |
|------|---------------|-----------|
| [`hvp/`](hvp/DEMO.md) | Background + question + the database-build pipeline & data | The queries/analysis that answer the phage-host question |
| [`lunar/`](lunar/DEMO.md) | Background + question (Artemis II free-return) | The CR3BP model + free-return search |
| [`bring_your_own/`](bring_your_own/DEMO.md) | A question worksheet | Everything, on your own problem |

## Prerequisites

- Python 3.10+, VS Code, Git, Zoo Code (AI assistant)
- Everything else (cookiecutter + per-demo libraries) is installed by **Step 0**
  above via each demo's `requirements.txt`.
# techfest2026_demos
