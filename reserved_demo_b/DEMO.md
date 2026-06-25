# Demo: Reserved (To Be Defined)

> **Status: reserved placeholder.** This is one of two future domain-specific
> demos whose question and data are not finalized yet. The folder is scaffolded
> so it can be filled in quickly later.

## What to do when defining this demo

1. Write the science in
   [`background/01_initial_question.md`](background/01_initial_question.md)
   (question, hypothesis, metrics, fidelity ladder).
2. Add a `requirements.txt` (always include `cookiecutter`; keep it synthetic-
   first and CPU-only where possible).
3. Copy the `DEMO.md` structure from a completed demo and adapt it:
   - [`../enzyme_kinetics/DEMO.md`](../enzyme_kinetics/DEMO.md) (synthetic only)
   - [`../proteomics_de/DEMO.md`](../proteomics_de/DEMO.md) (synthetic + optional
     small real data)

The shared DEMO.md skeleton is: title -> "You are given / You build" -> The
question -> Key terms -> Steps 0-5 (env setup, cookiecutter prompts table,
seed background, Zoo Code config + prime prompt, SMAIRT loop focused request,
interpret & log) -> What "done" looks like -> Troubleshooting table -> "Zoo Code
is stuck" recovery section.
