# 01_initial_question.md

## Brief Background

Most laws in science are written as **differential equations**: rules that say
how fast something changes right now, given its current state. Population growth,
radioactive decay, cooling coffee, planetary motion, and epidemic spread are all
described this way. The trouble is that only a handful of these equations can be
solved with a neat pen-and-paper formula. For everything else, scientists reach
for a **numerical solver**: a method that marches forward in small time steps,
approximating the true solution as it goes.

This SMAIRT project studies *how good those approximations are*. We use the
**logistic growth** equation, which models a population that grows quickly at
first and then levels off as it approaches a carrying capacity. It is a perfect
teaching case because it **has an exact closed-form solution** we can compare
against. That means we always know the true answer, so we can measure exactly how
much error a numerical method makes and how that error shrinks as we take smaller
steps.

It is CPU-only, pure Python (numpy/scipy/matplotlib), and needs no external data.

## Question

When we solve the logistic-growth differential equation numerically, how does the
**global error** of the solution depend on the **step size**, and do the
**Euler** and **fourth-order Runge-Kutta (RK4)** methods converge at the
theoretically predicted rates?

## Hypothesis

As the step size `h` is reduced, the global error of the **Euler** method will
fall in proportion to `h` (first-order: halving `h` roughly halves the error),
while the **RK4** method's error will fall in proportion to `h^4` (fourth-order:
halving `h` cuts the error by roughly 16x). On a log-log plot of error versus step
size, Euler will show a slope near **1** and RK4 a slope near **4**, until RK4
reaches the floor set by finite-precision (round-off) arithmetic.

## Evidence / metrics

- **Global error:** the maximum (or final-time) absolute difference between the
  numerical solution and the exact logistic solution, over a fixed time interval.
- **Observed order of convergence:** the slope of a straight-line fit to
  `log(error)` vs. `log(h)`. Compare against the expected 1 (Euler) and 4 (RK4).
- **Method comparison:** error of Euler vs. RK4 at the *same* step size and at the
  *same computational cost* (RK4 does more work per step but can take far bigger
  steps for the same accuracy).
- **Visual check:** the numerical trajectories overlaid on the exact curve, plus
  the log-log error-vs-step-size plot with reference slope lines.

## Domain Context

### The logistic equation and its exact solution
- ODE: `dP/dt = r * P * (1 - P / K)`
- Parameters: `r` = intrinsic growth rate, `K` = carrying capacity.
- Exact solution: `P(t) = K / (1 + A * exp(-r * t))`, where
  `A = (K - P0) / P0` and `P0 = P(0)`.
- Because the true `P(t)` is known, every numerical error can be computed exactly.

### The two solvers
- **Euler's method** (first order): `P_{n+1} = P_n + h * f(t_n, P_n)`. The
  simplest possible scheme; takes a single slope estimate per step.
- **RK4** (fourth order): combines four slope estimates per step in a weighted
  average. Much more accurate for the same `h`, at the cost of more evaluations.

### Order of convergence (the central idea)
- A method is **order p** if its global error behaves like `error ~ C * h^p` for
  small `h`. On a log-log plot, `log(error) = log(C) + p * log(h)`, a straight
  line whose **slope is p**. Measuring that slope is how you *empirically confirm*
  a method's order.

### Round-off floor
- Errors cannot shrink forever. Once `h` is very small, finite floating-point
  precision dominates and the error curve flattens (or even rises). Seeing this
  floor is part of understanding real numerical computation.

### Fidelity ladder (SMAIRT data progression)
1. **Synthetic, exact-truth (start here):** solve logistic growth with Euler,
   compare against the closed-form solution at a few step sizes, and confirm the
   error goes down as `h` goes down.
2. **Synthetic, method comparison:** add RK4, sweep a range of step sizes, and fit
   the convergence slopes; verify Euler ~ 1 and RK4 ~ 4, and locate RK4's round-off
   floor.
3. **Harder ODE (optional):** apply the same convergence analysis to an ODE with
   no simple closed form (e.g. a nonlinear pendulum), using a very-fine-step RK4
   run as the reference "truth."

### Caveats
- The observed order only matches theory in the **asymptotic** regime (small
  enough `h`) and before the round-off floor. Steps that are too large, or an
  unstable step size for a stiff problem, will not show the clean slope.
- Stating the time interval, parameters, and step-size range next to the fitted
  slopes is part of the SMAIRT method.

## Known values (for validation)

| Quantity | Value |
|----------|-------|
| growth rate `r` | 1.0 |
| carrying capacity `K` | 100 |
| initial population `P0` | 10 |
| time interval | `t` = 0 to 10 |
| expected Euler convergence slope | ~1 (first order) |
| expected RK4 convergence slope | ~4 (fourth order) |
| step sizes to sweep | e.g. 1.0, 0.5, 0.25, ... down to ~1e-3 |
| random seed | fixed (reproducibility, if any noise is added) |
