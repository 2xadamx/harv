# HARV+ language design: proposed semantics and scope

This document captures the broader HARV+ direction. It is a design target, not a claim about the current v0.1 implementation. The executable prototype currently supports first-order scalar ODEs, explicit initial values, dimensional checks, a typed scalar IR, and Euler/RK4; it does not yet parse algebraic laws or constraints.

## Product definition

HARV+ is a domain-specific language for declaring continuous or discrete mathematical models and compiling them to numerical execution. Its promise is narrower and more testable than “simulate the universe”: preserve a model's declared mathematical structure across supported backends, check dimensions and model conditions, and report numerical assumptions/results reproducibly.

The long-term scope may include ODEs, PDEs, and discrete agents, but these are different execution models. They should share an outer model/IR framework only where their semantics genuinely agree; they should not be presented as one solver problem.

## Four distinct model concepts

The language should keep these separate in syntax, AST, and IR:

1. **State**: independent quantities advanced by an integrator.
2. **Law**: an algebraic definition derived from state and parameters, such as ideal-gas pressure. A law is evaluated, not integrated.
3. **Operator**: a pure function from state/time to derivatives, written with derivative targets such as `dvolume_dt`. It does not update state and does not receive `dt`.
4. **Constraint**: a predicate or invariant with a specified enforcement policy. A check can abort; projection requires a separately defined projection method. The compiler must not invent one.

An `evolve` declaration owns the time interval, step policy, solver, tolerances, and output selection. This prevents discrete updates containing `dt` from being confused with continuous differential equations.

### Second-order equations in the ODE MVP

The v0.1 solver accepts first-order systems only. A second-order equation must be lowered explicitly by the model author to first-order state variables. For a pendulum,

```text
d²θ/dt² = -(g/L) sin(θ)
ω = dθ/dt
```

becomes the state `(theta, omega)` and operator equations `dtheta_dt = omega` and `domega_dt = -(g/length)*sin(theta)`. Initial conditions must specify both `theta` and `omega`; for release from rest, `omega = 0<rad/s>`. HARV v0.1 does not infer missing initial conditions or parse second-derivative syntax.

Angles use SI's dimensionless plane-angle convention, while `rad` and `deg` unit aliases make intent explicit and convert degrees to radians at evaluation. Thus `scalar<rad>` and `scalar` have equal dimensions, but explicit `rad` is preferred for angular state.

## Consistent illustrative model

The following is target syntax only. It illustrates a derived pressure law and an explicit expansion rate; it is not accepted by today's parser because `law`, `mol`, and named constraint policies are not implemented.

```harv
state Gas {
    amount: scalar<mol>
    temperature: scalar<K>
    volume: scalar<m^3>
}

init Gas {
    amount = 1<mol>
    temperature = 300<K>
    volume = 0.01<m^3>
}

parameters GasParams {
    R: scalar<Pa*m^3/mol/K> = 8.314<Pa*m^3/mol/K>
    expansion_rate: scalar<m^3/s> = 0.001<m^3/s>
}

law IdealGas {
    pressure = amount * R * temperature / volume
}

operator Expansion {
    damount_dt = 0<mol/s>
    dtemperature_dt = 0<K/s>
    dvolume_dt = expansion_rate
}

constraint PositiveVolume {
    volume > 0<m^3>
} on_violation = abort

evolve Gas using Expansion {
    dt = 0.01<s>
    duration = 10<s>
    method = RK4
}

observe pressure
```

`R` and `expansion_rate` are explicit parameters with units `Pa*m^3/mol/K` and `m^3/s`. Pressure is a derived observable, not a second integrated state. This example makes no claim of energy conservation: such a claim needs a defined energy expression and thermodynamic assumptions.

## Physical type system

The unit checker should normalize aliases to dimensions. For example, `Pa = kg/(m*s^2)` and `J = kg*m^2/s^2`; aliases do not add new independent dimensions. `mol` adds amount-of-substance as an SI base dimension. Currency (such as USD) is not an SI unit and needs a declared custom dimension or a separate economic type domain. Division by time is explicit in derivative dimensions: `dtemperature_dt` must have units `K/s`.

The checker validates algebraic laws and derivatives separately:

- a law's right-hand side has the unit declared for its derived output;
- every operator target names an evolvable state field;
- a derivative's unit equals its target unit per second;
- constraints compare compatible dimensions and produce a boolean predicate.

## Constraints and reproducibility

A constraint declaration needs a named expression and a policy such as `abort` or an explicit projection function. “Conserve energy” alone is not executable. The runtime should record the invariant value, residual/tolerance, and any projection applied. Determinism also requires explicit random seeds for stochastic models, defined solver tolerances, and recorded backend/version settings.

## Solver selection

Automatic solver selection should begin as a recommendation with a reported reason. Selecting a method requires more than a broad label:

- ODE stiffness classification needs defined diagnostics and tolerances.
- RK4 is an explicit ODE method, not a universally optimal solver for every linear system.
- BDF is a candidate for some stiff ODEs; it is not implied by “stiff” without stability/error goals.
- PDE execution requires a spatial domain, boundary conditions, discretization, and a time integrator. FEM is a spatial discretization family, not a complete solver choice by itself.
- Euler–Maruyama applies to a specified stochastic differential equation and noise interpretation.

An `auto(...)` policy may choose among supported numerical strategies, but must not silently change the equations, boundary conditions, or constitutive physics. It should expose the choice and allow a fixed solver for reproducibility.

## H-7: no implied economic model

HARV+ has no built-in opinion about markets, inflation, policy, or causal mechanisms. The compiler checks the model the author wrote; it does not infer a monetarist, Keynesian, or other economic law from a name such as `Market`, `GDP`, or `inflation`. Model libraries may offer explicitly named alternatives, with their assumptions and provenance visible, but selecting and connecting them is the model author's decision.

For an economic model, the type checker can reject invalid dimensions such as adding a GDP stock in `USD` to a flow in `USD/year`. It cannot determine whether a dimensionally valid equation is economically true, empirically identified, or suitable for policy. Simulation results must not be described as forecasts or recommendations without separate validation and uncertainty analysis.

`USD` is treated only as a dimensional label. It does not encode exchange rates, inflation adjustment, or a claim about a currency's value. `year` is normalized to a Julian year in SI seconds. Constraints such as `GDP > 0<USD>` are executable predicates; “economy is stable” is not, unless the author defines a measurable predicate and a violation policy. The first supported response should be to abort and report the violated condition; projection requires an explicit algorithm.

## HARV+, EIDOLON, and HARVEID boundary

- **HARV+**: explicit equations, units, constraints, and requested evolution.
- **EIDOLON**: a high-level intent/modeling layer that may propose equations and assumptions. It must disclose the proposed model; intent alone does not uniquely determine physics.
- **HARVEID**: composition of an explicit model with controlled automation for solver, discretization, resolution, or agent execution. Automation should operate within declared bounds and return an auditable execution plan.

This can be one family of tools sharing typed model and execution-plan interfaces, rather than three unrelated languages. Agent behavior remains a separate subsystem until its event, state, and time semantics are defined.

## Staged implementation boundary

1. **Current scalar ODE MVP**: source → lexer → AST → dimension/name checks → typed scalar IR → Euler/RK4 → observations; units include `USD`, `year`, `Pa`, `J`, `rad`, and `deg`.
2. **Frontend semantics**: declaration-list AST, formal source spans in implementation, native parameter/law declarations, derived outputs, and stronger dimensional tests.
3. **Constraint model**: check/abort first; projection only with explicit projection semantics.
4. **Fields/PDE**: domain and boundary-condition model, then a specified 1D/2D discretization and tested operators.
5. **Solver advice**: classification and explainable recommendations, before any automatic selection.
6. **Additional backends and agent composition**: after the typed IR has stable semantics and conformance tests.

## Product scope decision

HARV v0.1 is an executable DSL for explicitly specified scalar ODE simulation. That is the first vertical slice and the only current runtime promise. The broader ambition—AI-proposed mathematical models, richer dynamical systems, and eventually other execution domains—is a long-term direction, not part of the v0.1 language contract. Proposals from an AI must be surfaced as explicit equations and assumptions, then pass the same validation as human-written models; the runtime does not derive physics from intent alone.

The grammar and source AST contract for the current subset are in [`GRAMMAR_AND_AST.md`](GRAMMAR_AND_AST.md). Future productions for `law`, `constraint`, parameters, domains, and behavior should be added there only after their semantics are specified and an implementation milestone accepts them.
