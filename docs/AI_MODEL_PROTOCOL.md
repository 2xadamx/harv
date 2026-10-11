# HARV machine model protocol 0.1

## Purpose

This protocol defines how a model-generating agent can propose a runnable scalar ODE model to HARV without using natural-language interpretation at execution time. It is an interchange format, not a second source language. The loader and `check-json`, `ast-json`, and `run-json` CLI commands implement the supported 0.1 subset.

The first encoding is JSON because it is easy to inspect, validate, diff, and generate. A later binary encoding may reduce size, but must preserve the same versioned meaning. The model's equations and numerical choices remain explicit in either encoding.

## Trust boundary

An agent may propose a model; HARV remains responsible for checking and executing it. A proposal is never trusted just because it is well-formed JSON.

1. Parse against `schemas/harv-model-0.1.schema.json`.
2. Resolve every state, parameter, and time reference; reject unknown or duplicate names.
3. Type-check expression dimensions and require each right-hand side to have the target state's unit divided by seconds.
4. Check finite numeric values, positive time step, and exact step divisibility within a documented numeric tolerance.
5. If `constraints` are provided, require each expression to be a scalar comparison with dimensionally compatible operands; abort at the first false predicate, including intermediate numerical stages.
6. Execute only the explicitly named supported solver. Never infer or rewrite equations during execution.
7. When requested, emit a run record with exact input SHA-256, solver, time settings, runtime version, and optional CSV SHA-256. The record fingerprints exact input bytes; it is not a claim that mathematically equivalent source files have the same identity.

Schema validation checks shape, not truth. Dimensional consistency does not establish that a model describes nature correctly. Free-text intent, if supplied by a future proposal layer, is metadata only and must never alter execution.

## Minimal example: exponential decay

This describes `dx/dt = -k*x`, with `x(0)=1 m`, `k=2 s^-1`, and RK4 over five seconds. The expression tree contains only named operations; no source string is evaluated as code. The runnable copy is `examples/decay.harv.json`.

```json
{
  "format": "harv.model/0.1",
  "name": "exponential_decay",
  "states": [
    {"name": "x", "unit": "m", "initial": {"value": 1, "unit": "m"}}
  ],
  "parameters": [
    {"name": "k", "value": 2, "unit": "1/s"}
  ],
  "derivatives": [
    {
      "target": "x",
      "expr": {
        "op": "mul",
        "left": {"op": "neg", "arg": {"op": "parameter", "name": "k"}},
        "right": {"op": "state", "name": "x"}
      }
    }
  ],
  "time": {
    "start": {"value": 0, "unit": "s"},
    "duration": {"value": 5, "unit": "s"},
    "step": {"value": 0.01, "unit": "s"}
  },
  "solver": "rk4",
  "observe": ["x"]
}
```

The expected final value is approximately `4.539993e-5 m`; a conformance test should compare the solver result to the analytic solution `exp(-k*t)` using a stated tolerance.

Models may add comparison predicates. For example, this optional declaration requires positive length and uses the same dimensional validation and abort-on-violation behavior as source HARV:

```json
"constraints": [
  {"expr": {"op": "gt", "left": {"op": "state", "name": "x"}, "right": {"op": "constant", "value": 0, "unit": "m"}}}
]
```

## Deliberate limits of 0.1

- One deterministic scalar ODE system; constraints are limited to scalar comparisons with abort-on-violation. No fields, PDEs, agents, stochastic terms, or implicit solver.
- Supported expression operations must match the interpreter's allowlist. Inputs cannot name modules, functions, files, or executable code.
- Units use HARV's declared unit table and canonical internal dimensions. This schema does not make arbitrary unit strings valid.
- A model producer must identify its source or assumptions outside the executable equations when provenance is available; HARV must not invent them.
- Solver selection is explicit. Agent recommendations may be presented separately, but cannot silently replace the requested method.

## Loader behavior

The loader validates document shape and expression limits, rejects non-finite numbers and unknown operations, checks declarations, dimensions, and time-step configuration, and lowers the model into the source AST; the shared lowering pass then creates typed IR for execution. It currently caps a document at 1 MB, expression trees at 20,000 nodes/depth 128, variables at 10,000, and a run at one million steps. To reuse the v0.1 scalar-state IR, parameters are stored internally as frozen state slots with zero derivatives; only declared state variables may be observed. This is an implementation detail, not mutable parameter semantics.

Run the unconstrained example with `harvc check-json examples/decay.harv.json` or `harvc run-json examples/decay.harv.json`. The constraint example is executable with `harvc run-json examples/positive_decay.harv.json`. JSON paths appear in loader diagnostics. The model's equations are never inferred or rewritten during execution.

Run records are written only when `--manifest path.json` is supplied to either `run` or `run-json`. The record schema is `schemas/harv-run-record-0.1.schema.json`. It records the source file's basename and raw-byte hash, typed-IR SHA-256, model name, solver and SI time grid, HARV/Python versions, and the optional CSV basename/hash. It omits the local absolute path so the record can be shared without disclosing the producer's directory layout. `harvc ir file.harv` or `harvc ir-json file.json` emits the IR document directly for inspection or backend handoff.

The published IR and run-record schemas are now exercised by tests using the `test` extra. The next implementation slice is an independent consumer—most naturally the Rust crate—that reads this IR contract and can be checked against the Python reference on the same models.
