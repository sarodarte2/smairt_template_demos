# Demo: Numerical ODE Solving & Convergence (Logistic Growth)

**You are given:** the background and the research question.

**You build:** the logistic-growth solver (Euler and RK4) and the error-vs-step-size
convergence analysis using SMAIRT.

There are **no solution scripts here**. The goal is to experience using SMAIRT
to go from a question to an answer with an AI assistant, on a small, exactly-checkable
numerical-methods problem you can iterate on.

> New to AI assistants? Read [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md) first
> (install, sign in, attach files, approve edits).

---

## Background / Why this matters

**The field:** Most physical laws are written as **differential equations** -
rules for how fast something changes right now. Population growth, cooling,
chemical reactions, orbits, and epidemics are all modeled this way. But most of
these equations have **no tidy pen-and-paper solution**, so scientists solve them
**numerically**: march forward in small time steps, approximating the true curve
as you go. This branch of math, **numerical analysis**, quietly powers weather
models, engineering simulations, and much of scientific computing.

**The core idea:** a numerical method is only as trustworthy as its **error**. If
you take smaller steps, the answer should get closer to the truth - but *how
fast*? A method's **order of convergence** answers this: a first-order method
(like **Euler**) roughly halves its error when you halve the step; a fourth-order
method (like **RK4**) cuts the error ~16x for the same halving. You can *measure*
this order empirically as the slope of an error-vs-step-size plot.

**Why it's a good SMAIRT demo:** we use the **logistic growth** equation, which
models a population leveling off at a carrying capacity - and which has an
**exact closed-form solution**. Because you know the true answer, you can compute
the error exactly, confirm Euler converges at order ~1 and RK4 at order ~4, and
even watch the round-off floor appear. No lab, no special data, and only basic
calculus and Python needed to follow along.

---

## The question

When we solve the logistic-growth differential equation numerically, how does the
**global error** depend on the **step size**, and do the **Euler** and
**fourth-order Runge-Kutta (RK4)** methods converge at the theoretically
predicted rates?

Full context, hypothesis, and metrics are in
[`background/01_initial_question.md`](background/01_initial_question.md).

### Key terms

- **Differential equation (ODE):** a rule for a rate of change, e.g.
  `dP/dt = r*P*(1 - P/K)`. Solving it means finding `P(t)`.
- **Logistic growth:** population grows fast, then saturates at carrying capacity
  `K`. It has an **exact** solution, so "truth" is known.
- **Step size (`h`):** how far forward in time each numerical step advances.
  Smaller `h` = more steps = (usually) less error.
- **Euler's method:** the simplest solver, one slope estimate per step;
  **first-order** accurate.
- **RK4 (Runge-Kutta 4):** combines four slope estimates per step;
  **fourth-order** accurate, far more precise for the same `h`.
- **Global error:** the gap between the numerical solution and the exact solution
  over the whole interval.
- **Order of convergence:** the exponent `p` in `error ~ h^p`; it shows up as the
  **slope** on a log-log error-vs-`h` plot (Euler ~1, RK4 ~4).
- **Round-off floor:** the point where shrinking `h` stops helping because
  finite floating-point precision dominates.

---

## Steps

0. **Set up your environment first** (run from this folder, `reserved_demo/`):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   This installs `cookiecutter` (used in the next step) plus numpy/scipy/
   matplotlib. If you see `command not found: cookiecutter`, this step was
   skipped or your venv isn't active.

   Windows users: if PowerShell blocks activation, run
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal,
   then try `.venv\Scripts\Activate.ps1` again. In Command Prompt, use
   `.venv\Scripts\activate.bat`.

1. **Generate a fresh SMAIRT project** (run from this folder, venv active):
   ```bash
   cookiecutter https://github.com/biodataganache/smairt-template.git
   ```
   Cookiecutter then asks you a series of questions. If you've run it before you
   may first see `Is it okay to delete and re-download it? [y/n] (y):`. Press
   **Enter**. Then answer the prompts. Press **Enter** to accept a default,
   or type the value/number shown. For the **Select** prompts, type the
   **number** (not the word). **Suggested answers for this demo:**

   | Prompt | Suggested answer |
   |--------|------------------|
   | project_name | `ODE Convergence` |
   | project_slug | press Enter (auto) |
   | author_name | your name |
   | author_email | your email (or Enter) |
   | description | `Numerical ODE solving and convergence-order analysis` |
   | project_mode | `1` (standard) |
   | workflow_mode | `1` (ide_native) |
   | initial_research_question | `Do Euler and RK4 converge at their predicted orders on logistic growth?` |
   | domain | number closest to `mathematics` (or `physics` if math isn't listed) |
   | ai_tool | `1` (roo_zoo / Zoo Code) |
   | include_example_project | `1` (no) |
   | starting_phase | `1` (synthetic) |
   | license | `1` (MIT) |
   | create_git_repo | `1` (yes) |

   This creates a folder named after your project_slug (e.g. `ode_convergence/`).

2. **Seed your project with the background:**
   ```bash
   cp background/01_initial_question.md ode_convergence/background/
   ```

3. **Configure Zoo Code, then open the project in VS Code and prime it.** New to
   AI assistants? Read [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md) first. It
   covers installing Zoo Code, signing in, and how to attach files and approve
   edits.

   Basic Zoo Code configuration for this demo:
   - Install **Zoo Code** from the VS Code Extensions panel.
   - Set **API Provider** to **OpenAI Compatible**. Any OpenAI-compatible
     endpoint works (OpenAI, Anthropic, OpenRouter, Azure OpenAI, a local server
     such as Ollama / LM Studio, or an institutional gateway).
   - Use **API Base URL**: your provider's documented base URL (for example,
     `https://api.openai.com/v1` for OpenAI).
   - Paste an **API Key** from your chosen provider.
   - Select a **Model** by difficulty. This is an **intermediate** track, so a
     mid-tier reasoning model is a good default for the solver implementation and
     the convergence-slope analysis. Step up to a larger model if the assistant
     struggles.
   >
   > **Markdown preview tip:** press `Cmd+Shift+V` on Mac or `Ctrl+Shift+V` on
   > Windows to render this file in VS Code.

   Open your new project folder in VS Code (**File > Open Folder...**). In the
   Zoo Code chat, paste this direct prompt:

   ```text
   I'm starting a SMAIRT project to answer the question in
   background/01_initial_question.md. Please read these files before doing any
   work:
   1. prompts/AI_CONTEXT.md
   2. prompts/CODE_CONVENTIONS.md
   3. background/01_initial_question.md

   Follow the SMAIRT workflow described there: numbered scripts, output to console
   + results/logs/, and a pasted-output comment block at the end of each script.
   Don't write any code yet. First summarize the question and propose a first
   hypothesis and an experiment to test it.
   ```

   Read its reply. You decide whether the proposed hypothesis/experiment is
   reasonable before moving on.

4. **Start the SMAIRT loop with one focused request.** After the assistant has
   summarized the question and proposed a first hypothesis, paste a prompt like
   this. Treat the reply as a proposal: you may accept, narrow, or redirect it.

   ```text
   Based on background/01_initial_question.md and the SMAIRT conventions, start
   with a small, exactly-checkable example. Create the first numbered script in
   experiments/01_synthetic/ that (a) implements Euler's method for the logistic
   ODE dP/dt = r*P*(1 - P/K), (b) compares the numerical solution against the EXACT
   closed-form logistic solution at a few step sizes, and (c) reports the global
   error and shows it shrinking as the step size shrinks, with a plot.

   Before writing code, briefly state the parameters you'll use (r, K, P0, time
   interval), what error trend would make the method credible, and how later
   scripts will add RK4 and fit the convergence-order slopes. Follow the project
   code conventions for logging, figures, and the output comment block.
   ```

   How to handle the AI response:
   - If the plan compares against the exact solution and checks that error falls
     with step size, say: `Proceed with building the script.`
   - Before trusting results, check it uses the **correct closed-form solution**
     `P(t) = K / (1 + A*exp(-r*t))` with `A = (K - P0)/P0`, keeps the time
     interval fixed, and measures a well-defined **global** error (e.g. max error
     over the interval).
   - If the assistant only plots the trajectory without an error-vs-step-size
     comparison, redirect it: `The experiment is the error vs. step size against
     the exact solution; report that, not just the curve.`
   - **Second iteration:** add **RK4**, sweep a range of step sizes, and fit the
     slope of `log(error)` vs. `log(h)`; verify Euler ~ 1 and RK4 ~ 4.
   - **Third iteration:** push `h` very small and show RK4 hitting the
     **round-off floor**; discuss the accuracy-vs-cost trade-off between the methods.

5. **Interpret and log.** In `analysis/ANALYSIS_01.md`, note: did the error fall
   with step size? what convergence slopes did you measure for Euler and RK4, and
   did they match the expected 1 and 4? where did round-off take over? Record your
   key judgment call (e.g. which method you'd use for a given accuracy budget, and
   why) in `prompts/intellectual_contribution.md`. That reasoning is the science.

---

## What "done" looks like

A logistic-growth solver whose numerical output matches the exact solution, a
log-log error-vs-step-size plot showing Euler converging at order ~1 and RK4 at
order ~4 (with RK4's round-off floor visible), and measured convergence slopes
that match theory, all reproducible from your breadcrumb trail. (Requirements:
cookiecutter + numpy/scipy/matplotlib, installed in Step 0; CPU-only, no network
needed.)

> **Going further (optional, later):** apply the same convergence analysis to an
> ODE with no simple closed form (e.g. a nonlinear pendulum), using a
> very-fine-step RK4 run as the reference "truth," and report how the measured
> orders compare.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `command not found: cookiecutter` | venv not active or Step 0 skipped. Run `source .venv/bin/activate` then `pip install -r requirements.txt`. |
| `No such file or directory: .../.venv/bin/...` | The venv was deleted/moved. Recreate it: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`. |
| cookiecutter asks to re-download the template | Normal if you've run it before. Press **Enter** (y). |
| Error doesn't shrink with step size | Likely a bug in the update rule or the exact-solution formula. Check `A = (K - P0)/P0` and the sign in `exp(-r*t)`. |
| Euler slope isn't ~1 / RK4 slope isn't ~4 | Steps may be too large (not yet in the asymptotic regime). Use a wider range of smaller step sizes and fit only the clean part. |
| RK4 error stops improving (or rises) at tiny `h` | Expected: that's the round-off floor. Stop shrinking `h` there; it's a feature to report, not a bug. |
| Solution blows up / goes negative | Step size too large for stability, or the ODE was coded wrong. Reduce `h` and re-check `dP/dt = r*P*(1 - P/K)`. |
| Log-log fit is noisy | Compute error consistently (same norm, same interval) and ensure step sizes span several orders of magnitude. |
| Zoo Code edits the wrong file / drifts | Re-attach `AI_CONTEXT.md` + your `background/01_initial_question.md` and restate the current step. |

### Zoo Code is stuck (an error a retry won't fix)

If the assistant gets into a broken state, don't keep retrying. **Start a fresh
task/chat** (in Zoo Code, open a new task with the `+` button) and re-prime it
from your breadcrumb trail. SMAIRT is designed for exactly this: your project
files hold the context.

1. Save your work (your scripts/logs are already on disk).
2. Open the new task with your project folder still open.
3. Attach `prompts/AI_CONTEXT.md`, `prompts/CODE_CONVENTIONS.md`, and
   `background/01_initial_question.md`, then paste:

   ```text
   I'm resuming a SMAIRT project (the question is in
   background/01_initial_question.md) after my previous AI session got stuck.
   Please read AI_CONTEXT.md and CODE_CONVENTIONS.md and follow the SMAIRT
   workflow. To get back up to speed, read my existing files:
   - experiments/ (my numbered scripts so far, with output pasted at the bottom)
   - results/logs/ (run outputs)
   - analysis/ANALYSIS_01.md (what I concluded so far)
   Summarize where the project stands and what the next step is. Don't rewrite
   working code. Continue from here.
   ```
   Tip: if it exists, run `python scripts/compile_for_ai.py` and paste its output
   to hand over the whole trail at once.
