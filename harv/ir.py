"""Immutable, backend-neutral typed IR for the scalar ODE runtime."""
from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction

from .ast import Expr, Program
from .semantic import check, evaluate, infer
from .units import clean, parse_unit, unit_scale


Dimension = tuple[tuple[str, int, int], ...]
MAX_STEPS = 1_000_000


def _dimension(value) -> Dimension:
    """Encode rational SI exponents in a stable immutable representation."""
    return tuple(
        (name, Fraction(power).numerator, Fraction(power).denominator)
        for name, power in sorted(clean(value).items())
    )


@dataclass(frozen=True)
class IRExpression:
    op: str
    value: object
    args: tuple["IRExpression", ...]
    dimension: Dimension


@dataclass(frozen=True)
class IRField:
    name: str
    dimension: Dimension
    initial_si: float


@dataclass(frozen=True)
class IRDerivative:
    target: str
    expression: IRExpression


@dataclass(frozen=True)
class IRConstraint:
    expression: IRExpression
    line: int


@dataclass(frozen=True)
class TimeGrid:
    start_seconds: float
    step_seconds: float
    duration_seconds: float
    steps: int


@dataclass(frozen=True)
class TypedProgram:
    """Validated model independent of source syntax and numerical backend."""
    name: str
    fields: tuple[IRField, ...]
    derivatives: tuple[IRDerivative, ...]
    time: TimeGrid
    solver: str
    observations: tuple[str, ...]
    constraints: tuple[IRConstraint, ...] = ()


IR_FORMAT = "harv.typed-ir/0.1"


def to_document(program: TypedProgram) -> dict:
    """Return the versioned, JSON-compatible language-neutral IR document."""
    if not isinstance(program, TypedProgram):
        raise TypeError("to_document requiere un TypedProgram")

    def expression_document(expression):
        return {
            "op": expression.op,
            "value": expression.value,
            "args": [expression_document(arg) for arg in expression.args],
            "dimension": [list(power) for power in expression.dimension],
        }

    return {
        "ir_format": IR_FORMAT,
        "name": program.name,
        "fields": [
            {"name": field.name, "dimension": [list(power) for power in field.dimension],
             "initial_si": field.initial_si}
            for field in program.fields
        ],
        "derivatives": [
            {"target": derivative.target, "expression": expression_document(derivative.expression)}
            for derivative in program.derivatives
        ],
        "time": {
            "start_seconds": program.time.start_seconds,
            "step_seconds": program.time.step_seconds,
            "duration_seconds": program.time.duration_seconds,
            "steps": program.time.steps,
        },
        "solver": program.solver,
        "observations": list(program.observations),
        "constraints": [
            {"expression": expression_document(constraint.expression), "line": constraint.line}
            for constraint in program.constraints
        ],
    }


def canonical_bytes(program: TypedProgram) -> bytes:
    """Stable UTF-8 encoding used for IR fingerprints and cross-tool handoff."""
    return json.dumps(to_document(program), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def fingerprint(program: TypedProgram) -> str:
    """SHA-256 of semantic IR, excluding diagnostic source-line metadata."""
    document = to_document(program)
    for constraint in document["constraints"]:
        constraint.pop("line", None)
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def dumps(program: TypedProgram, *, indent: int = 2) -> str:
    """Pretty JSON encoding for inspection and backend handoff."""
    return json.dumps(to_document(program), indent=indent, ensure_ascii=False,
                      allow_nan=False) + "\n"


def _lower_expression(expr: Expr, names: dict[str, dict]) -> IRExpression:
    dims = _dimension(infer(expr, names))
    if expr.kind == "number":
        value = float(expr.value) * unit_scale(expr.unit)
        if not math.isfinite(value):
            raise ValueError(f"línea {expr.line}: literal fuera de rango")
        return IRExpression("constant", value, (), dims)
    if expr.kind == "name":
        return IRExpression("reference", expr.value, (), dims)
    if expr.kind == "unary":
        return IRExpression("unary:" + expr.value, None,
                            (_lower_expression(expr.children[0], names),), dims)
    if expr.kind == "binary":
        return IRExpression("binary:" + expr.value, None,
                            tuple(_lower_expression(child, names) for child in expr.children), dims)
    if expr.kind == "call":
        return IRExpression("call:" + expr.value, None,
                            tuple(_lower_expression(child, names) for child in expr.children), dims)
    raise ValueError(f"línea {expr.line}: no se puede bajar la expresión {expr.kind!r} al IR escalar")


def lower(program: Program) -> TypedProgram:
    """Validate a source AST and lower it into normalized, typed scalar IR."""
    check(program)
    fields_by_name = {field.name: field for field in program.state.fields}
    dimensions = {name: parse_unit(field.unit) for name, field in fields_by_name.items()}
    expression_names = {**dimensions, "t": parse_unit("s")}
    initial_by_name = {assignment.name: assignment.expr for assignment in program.initial.assignments}
    fields_list = []
    for name in fields_by_name:
        initial_si = float(evaluate(initial_by_name[name], {}))
        if not math.isfinite(initial_si):
            raise ValueError(f"valor inicial de {name} no finito")
        fields_list.append(IRField(name, _dimension(dimensions[name]), initial_si))
    fields = tuple(fields_list)
    derivatives = tuple(
        IRDerivative(
            target=assignment.name[1:-3],
            expression=_lower_expression(assignment.expr, expression_names),
        )
        for assignment in program.operator.assignments
    )
    constraints = tuple(
        IRConstraint(_lower_expression(item.expression, expression_names), item.line)
        for item in program.constraints
    )
    options = {assignment.name: assignment.expr for assignment in program.evolve.assignments}
    step_seconds = float(evaluate(options["dt"], {}))
    duration_seconds = float(evaluate(options["duration"], {}))
    if not math.isfinite(step_seconds) or step_seconds <= 0:
        raise ValueError("dt debe ser un número finito positivo")
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration debe ser un número finito positivo")
    raw_steps = duration_seconds / step_seconds
    if not math.isfinite(raw_steps):
        raise ValueError("el número de pasos calculado no es finito")
    steps = round(raw_steps)
    if abs(raw_steps - steps) > 1e-9:
        raise ValueError("duration debe ser un múltiplo exacto de dt")
    if steps > MAX_STEPS:
        raise ValueError(f"la simulación supera el límite de {MAX_STEPS} pasos")
    solver = options["method"].value
    observations = program.observations or tuple(fields_by_name)
    return TypedProgram(
        name=program.state.name,
        fields=fields,
        derivatives=derivatives,
        time=TimeGrid(0.0, step_seconds, duration_seconds, steps),
        solver=solver,
        observations=tuple(observations),
        constraints=constraints,
    )
