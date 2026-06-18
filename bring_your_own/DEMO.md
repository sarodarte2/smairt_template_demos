# Demo: Bring Your Own Problem

**You are given:** a question worksheet.  

**You build:** everything, on your own question, using SMAIRT.

### Key terms

- **SMAIRT loop:** hypothesis, ask AI for code, review, run, interpret, log, then
  repeat. One trip = one "iteration".
- **Hypothesis:** a specific, testable prediction (not just a topic).
- **Synthetic data:** data you generate with a known, built-in structure, so you
  can confirm a method works before trusting it on messy real data.
- **Breadcrumb trail:** the numbered scripts + logs + notes SMAIRT leaves behind,
  so anyone (including the AI later) can see what you tried and why.

---

## Steps

0. **Set up your environment first** (run from this folder, `demos/bring_your_own`):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   Installs `cookiecutter` (used in Step 2) plus common starter libs
   (numpy, pandas, matplotlib, scikit-learn). `command not found: cookiecutter`
   later means this step was skipped or your venv isn't active.

   Windows users: if PowerShell blocks activation, run
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal,
   then try `.venv\Scripts\Activate.ps1` again. In Command Prompt, use
   `.venv\Scripts\activate.bat`.

1. **Fill in [`QUESTION_WORKSHEET.md`](QUESTION_WORKSHEET.md)** first. It forces
   your idea into a shape one SMAIRT iteration can move (computable, evaluable,
   bounded, honest). If you have no data yet, plan a synthetic-first start.

2. **Generate a fresh SMAIRT project** (run from this folder, venv active):
   ```bash
   cookiecutter https://github.com/biodataganache/smairt-template.git
   ```
   Cookiecutter asks a series of questions. If you've run it before you may first
   see `Is it okay to delete and re-download it? [y/n] (y):`. Press
   **Enter**. Then answer the prompts. Press **Enter** to accept a default, or
   type the value/number shown. For the **Select** prompts, type the **number**
   (not the word). **Suggested answers (adapt to your problem):**

   | Prompt | Suggested answer |
   |--------|------------------|
   | project_name | your project name |
   | project_slug | press Enter (auto) |
   | author_name | your name |
   | author_email | your email (or Enter) |
   | description | one line about your project |
   | initial_research_question | your question |
   | domain | number closest to your field |
   | ai_tool | `2` (gpt5 / Zoo Code) |
   | include_example_project | `1` (no) |
   | data_progression | `2` (synthetic_real) or `4` (real_only) |
   | license | `1` (MIT) |
   | create_git_repo | `1` (yes) |

   This creates a folder named after your project_slug.

3. **Write your `background/01_initial_question.md`** in the new project using
   your worksheet answers (question + what's known + data notes). You can do
   this by hand, or ask Zoo Code: *"Turn my filled-in worksheet (pasted below)
   into a background/01_initial_question.md with clear Question and Hypothesis
   sections ad well as any additional relevant information - google search allowed,"* then paste your worksheet.

4. **Configure Zoo Code, then open the project in VS Code and prime it.** New to
   AI assistants? Read [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md) first
   (install, sign in, attaching files, approving edits).

   Basic Zoo Code configuration for this demo:
   - Install **Zoo Code** from the VS Code Extensions panel.
   - Set **API Provider** to **OpenAI Compatible**.
   - Create a PNNL Birthright API key at https://ai-incubator-depot.pnnl.gov/.
   - Use **API Base URL**: `https://ai-incubator-api.pnnl.gov`.
   - Select **Model**: try `gpt-5-birthright` first; if your key does not show it,
     use `gpt-5.5-project`.

   > **Important URL check:** the `depot` URL is only for creating the API key.
   > The API Base URL field must be `https://ai-incubator-api.pnnl.gov`, not the
   > `depot` website.
   >
   > **Markdown preview tip:** press `Cmd+Shift+V` on Mac or `Ctrl+Shift+V` on
   > Windows to render this file in VS Code.

   Open your new project folder (**File > Open Folder...**). In the Zoo Code chat,
   paste this direct prompt:

   ```text
   I'm starting a SMAIRT project to answer the question in
   background/01_initial_question.md. Please read these files before doing any
   work:
   1. prompts/AI_CONTEXT.md
   2. prompts/CODE_CONVENTIONS.md
   3. background/01_initial_question.md

   Follow the SMAIRT workflow described there. Don't write code yet. First
   summarize my question, propose a first hypothesis, and suggest an experiment
   that would produce evidence about it.
   ```

5. **Run one SMAIRT iteration.** Ask for an analysis that tests your hypothesis.
   A general-purpose first prompt:

   ```text
   Create script_01 in experiments/01_synthetic/ that tests my hypothesis. If I
   don't have data yet, generate synthetic data with a known, controllable
   structure so we can confirm the method works before using real data. Print
   results to console and results/logs/, and leave the output comment block at
   the end.
   ```
   Then review the proposed code, approve and run it, interpret the result
   yourself, log it in `analysis/iteration_log.md`, and decide the next step. See
   more starter prompts under "Suggested starter prompts" below.

---

## Safety rails

- Review AI output before trusting it (inputs, assumptions, metric, does it
  answer the hypothesis?).
- **Data sensitivity:** do not paste restricted/proprietary/personal data into
  an external AI service. Use synthetic stand-ins or local-only tools and note
  it.

## Suggested starter prompts

See [`QUESTION_WORKSHEET.md`](QUESTION_WORKSHEET.md) for the checklist; adapt a
domain quick-start (data science / ML / general Python / "no data yet") to your
problem.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `command not found: cookiecutter` | venv not active or Step 0 skipped. Run `source .venv/bin/activate` then `pip install -r requirements.txt`. |
| `No such file or directory: .../.venv/bin/...` | The venv was deleted/moved. Recreate it (the `python3 -m venv .venv` + install lines). |
| cookiecutter asks to re-download the template | Normal if you've run it before. Press **Enter** (y). |
| Your script needs a library that isn't installed | `pip install <package>` into the active venv, then re-run. |
| AI's result seems too good / circular | Check it isn't testing on the same data it learned from; ask for a held-out check. |
| Can't tell if the result answers the question | Your hypothesis or metric is probably fuzzy. Revisit the worksheet's "metric" and "what would change my mind" rows. |
| Working with sensitive data | Don't paste it into an external AI; use a synthetic stand-in or a local-only model, and note it in your log. |
| Zoo Code drifts off task | Re-attach `AI_CONTEXT.md` + your `background/01_initial_question.md` and restate the current step. |

### Zoo Code is stuck (an error a retry won't fix)

Don't keep retrying. **Start a fresh task/chat** (in Zoo Code, open a new task
with the `+` button) and re-prime it from your breadcrumb trail. Your project
files hold the context.

1. Keep your project folder open in the new task.
2. Attach `prompts/AI_CONTEXT.md`, `prompts/CODE_CONVENTIONS.md`, and your
   `background/01_initial_question.md`, then paste:

   ```text
   I'm resuming a SMAIRT project (question in background/01_initial_question.md)
   after my previous AI session got stuck. Please read AI_CONTEXT.md and
   CODE_CONVENTIONS.md and follow the SMAIRT workflow. To catch up, read my
   existing files:
   - experiments/ (numbered scripts, with output pasted at the bottom)
   - results/logs/ (run outputs)
   - analysis/iteration_log.md (conclusions so far)
   Summarize where the project stands and the next step. Don't rewrite working
   code. Continue from here.
   ```
   Tip: if it exists, run `python scripts/compile_for_ai.py` and paste its output
   to hand over the whole trail at once.
