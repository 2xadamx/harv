# HARV language specification — v0.1

This is the implemented subset of HARV. Features from the wider design are listed as future work rather than implied to work.

## Source file structure

A program contains one `state`, a matching `init`, one pure `operator`, and one matching `evolve`, in any order. It may contain `observe name` and scalar comparison `constraint` declarations after or between blocks. `#` and `//` start comments through end of line.

```harv
state Decay {
    x: scalar<m>
    k: scalar<1/s>
}
init Decay {
    x = 1.0<m>
    k = 2.0<1/s>
}
operator Physics {
    dx_dt = -k*x
    dk_dt = 0<1/s^2>
}
evolve Decay using Physics {
    dt = 0.01<s>
    duration = 5<s>
    method = RK4
}
observe x
constraint x > 0<m>
```

## Grammar sketch

```text
program      := declaration+
declaration  := state | init | operator | evolve | observe | constraint
state        := "state" IDENT "{" (IDENT ":" "scalar" ["<" unit ">"])* "}"
init         := "init" IDENT "{" (IDENT "=" expression)* "}"
operator     := "operator" IDENT "{" ("d" IDENT "_dt" "=" expression)* "}"
evolve       := "evolve" IDENT "using" IDENT "{" (IDENT "=" expression)* "}"
observe      := "observe" IDENT
constraint   := "constraint" comparison
```

Expressions include numeric literals (including scientific notation), identifiers, parentheses, unary `+`/`-`, arithmetic `+ - * / ^ **`, comparisons, and calls to `sin`, `cos`, `tan`, `exp`, `log`, `sqrt`, `abs`, `min`, and `max`. Precedence from tightest to loosest is parentheses/calls, exponentiation (right associative), unary sign, multiplication/division, addition/subtraction, comparisons. `pi`, `e`, and time variable `t` are available. Angles are represented as dimensionless values in radians.

## Types and units

The runnable v0.1 state type is `scalar`. The lexer/parser recognize future type names (`vector`, `field`, `vector2`, `vector3`, `field2d`, `field3d`, `tensor`), but semantic analysis rejects non-scalar state until a backend implements them.

Supported dimensions: SI bases `m`, `s`, `kg`, `K`, `A`, plus `USD` as a separate bookkeeping dimension for economic models. Derived aliases include `Pa = kg/(m*s^2)` and `J = kg*m^2/s^2`; `year` is a Julian year (`31557600 s`), `percent` has scale `0.01`, and `deg` converts to radians (`rad`). Plane angle is dimensionless in SI. Products, quotients, and integer powers are supported, e.g. `m/s^2`, `kg/m^3`, `USD/year`, `1/year`, `rad/s`. A unit on a numeric literal uses `number<unit>`. Values are normalized to SI base magnitudes internally. Other custom units and conversion scales (such as centimeters) are not currently provided.

Addition/subtraction and comparisons require equal dimensions. Multiplication/division combine dimensions. Powers require a dimensionless constant exponent for dimensional values. `sin`, `cos`, `tan`, `exp`, and `log` take dimensionless arguments. `sqrt` halves unit exponents. Each initial value must match its state field's unit. The derivative of each variable must have the variable's unit divided by seconds. `dt` and `duration` must have time dimensions; `year` literals are converted to seconds before integration.

## Solver and output

`method` accepts `Euler` or `RK4`. The operator is evaluated as `F(state, t) -> derivatives`; only the solver updates state. Both solvers are deterministic. `dt` and `duration` must be finite, positive, and `duration / dt` must be integral within a small floating point tolerance. Each `constraint` must be a comparison whose operands have compatible dimensions. The solver checks predicates at the initial state, every solver stage, and after each accepted step; a false predicate aborts the simulation and reports its source line and time. No state projection is implied. The run emits `t` plus observed fields; with no `observe` declaration it emits every state field. `harvc run --csv path.csv` saves the series.

## Explicitly not in v0.1

Vectorized populations, vector arithmetic, field allocation/index writes, field differential operators, named constraint policies/projection, implicit integration, autodifferentiation, GPU execution, and visualization. Scalar comparison constraints and the typed IR are implemented. In particular, the proposed water PDE is deferred until `field2d` and a tested stencil implementation exist.
