"""Loader for the versioned HARV machine-model JSON interchange format."""
from __future__ import annotations

import json
import math

from .ast import (Assignment, ConstraintDecl, EvolveDecl, Expr, Field, InitDecl,
                  OperatorDecl, Program, StateDecl)
from .semantic import SemanticError, check, evaluate
from .solver import run
from .units import UnitError, parse_unit, parse_unit_info, same, unit_scale


class MachineModelError(ValueError):
    """A malformed or semantically invalid machine-model document."""


MAX_DOCUMENT_BYTES = 1_000_000
MAX_EXPRESSION_DEPTH = 128
MAX_EXPRESSION_NODES = 20_000
MAX_STEPS = 1_000_000
MAX_DECLARATIONS = 10_000
RESERVED_NAMES = {"t", "pi", "e", "state", "init", "operator", "evolve", "using",
                  "scalar", "vector", "field", "field2d", "field3d", "vector2", "vector3",
                  "tensor", "dt", "duration", "method", "constraint", "observe", "RK4", "Euler"}


def _object(value, path, required, optional=()):
    if not isinstance(value, dict):
        raise MachineModelError(f"{path}: se esperaba un objeto")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing:
        raise MachineModelError(f"{path}: faltan campos {sorted(missing)}")
    if extra:
        raise MachineModelError(f"{path}: campos no permitidos {sorted(extra)}")
    return value


def _array(value, path, *, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        raise MachineModelError(f"{path}: se esperaba una lista con al menos {minimum} elementos")
    return value


def _identifier(value, path):
    if not isinstance(value, str) or not value.isascii() or not value:
        raise MachineModelError(f"{path}: identificador inválido")
    first = value[0]
    if not (first.isalpha() or first == "_") or not all(c.isalnum() or c == "_" for c in value):
        raise MachineModelError(f"{path}: identificador inválido {value!r}")
    if value in RESERVED_NAMES:
        raise MachineModelError(f"{path}: {value!r} es una palabra reservada")
    return value


def _number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MachineModelError(f"{path}: se esperaba un número finito")
    return float(value)


def _unit(value, path):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise MachineModelError(f"{path}: se esperaba una unidad no vacía")
    try:
        _, scale = parse_unit_info(value)
        if not math.isfinite(scale) or scale <= 0:
            raise MachineModelError(f"{path}: escala de unidad fuera de rango")
    except (UnitError, OverflowError, ZeroDivisionError) as exc:
        raise MachineModelError(f"{path}: {exc}") from exc
    return value


def _quantity(value, path):
    obj = _object(value, path, ("value", "unit"))
    return _number(obj["value"], f"{path}.value"), _unit(obj["unit"], f"{path}.unit")


def _expr(value, path, depth, counter, state_names, parameter_names):
    if depth > MAX_EXPRESSION_DEPTH:
        raise MachineModelError(f"{path}: se superó la profundidad máxima de expresión")
    counter[0] += 1
    if counter[0] > MAX_EXPRESSION_NODES:
        raise MachineModelError(f"{path}: se superó el máximo de nodos de expresión")
    if not isinstance(value, dict) or not isinstance(value.get("op"), str):
        raise MachineModelError(f"{path}: expresión sin operación válida")
    op = value["op"]
    if op == "constant":
        obj = _object(value, path, ("op", "value"), ("unit",))
        unit = _unit(obj["unit"], f"{path}.unit") if "unit" in obj else None
        return Expr("number", _number(obj["value"], f"{path}.value"), unit=unit)
    if op in {"state", "parameter"}:
        obj = _object(value, path, ("op", "name"))
        reference = _identifier(obj["name"], f"{path}.name")
        allowed = state_names if op == "state" else parameter_names
        if reference not in allowed:
            raise MachineModelError(f"{path}.name: {op} no declarado {reference!r}")
        return Expr("name", reference)
    if op == "time":
        _object(value, path, ("op",))
        return Expr("name", "t")
    if op == "neg":
        obj = _object(value, path, ("op", "arg"))
        return Expr("unary", "-", (_expr(obj["arg"], f"{path}.arg", depth + 1, counter, state_names, parameter_names),))
    if op in {"add", "sub", "mul", "div", "pow", "lt", "gt", "le", "ge", "eq", "ne"}:
        obj = _object(value, path, ("op", "left", "right"))
        symbol = {"add": "+", "sub": "-", "mul": "*", "div": "/", "pow": "^",
                  "lt": "<", "gt": ">", "le": "<=", "ge": ">=", "eq": "==", "ne": "!="}[op]
        left = _expr(obj["left"], f"{path}.left", depth + 1, counter, state_names, parameter_names)
        right = _expr(obj["right"], f"{path}.right", depth + 1, counter, state_names, parameter_names)
        return Expr("binary", symbol, (left, right))
    if op == "call":
        obj = _object(value, path, ("op", "function", "args"))
        function = obj["function"]
        if not isinstance(function, str) or function not in {"sin", "cos", "tan", "exp", "log"}:
            raise MachineModelError(f"{path}.function: función no permitida {function!r}")
        args = _array(obj["args"], f"{path}.args", minimum=1)
        if len(args) != 1:
            raise MachineModelError(f"{path}.args: {function} requiere exactamente un argumento")
        return Expr("call", function, (_expr(args[0], f"{path}.args[0]", depth + 1, counter, state_names, parameter_names),))
    raise MachineModelError(f"{path}.op: operación desconocida {op!r}")


def load_document(document: dict) -> Program:
    """Validate and lower a decoded JSON document to the existing scalar ODE AST.

    Parameters are represented internally as frozen state slots with zero
    derivatives. They are initialized once, never exposed for observation, and
    preserve the existing solver's pure derivative interface.
    """
    model = _object(document, "$", ("format", "name", "states", "parameters", "derivatives", "time", "solver", "observe"), ("provenance", "constraints"))
    if model["format"] != "harv.model/0.1":
        raise MachineModelError("$.format: versión no soportada; se esperaba 'harv.model/0.1'")
    name = _identifier(model["name"], "$.name")
    if "provenance" in model:
        provenance = _object(model["provenance"], "$.provenance", (), ("producer", "source", "assumptions"))
        for key in ("producer", "source"):
            if key in provenance and (not isinstance(provenance[key], str) or not provenance[key]):
                raise MachineModelError(f"$.provenance.{key}: se esperaba texto no vacío")
        if "assumptions" in provenance and (not isinstance(provenance["assumptions"], list)
                or any(not isinstance(item, str) for item in provenance["assumptions"])):
            raise MachineModelError("$.provenance.assumptions: se esperaba una lista de textos")
    state_items = _array(model["states"], "$.states", minimum=1)
    parameter_items = _array(model["parameters"], "$.parameters")
    derivative_items = _array(model["derivatives"], "$.derivatives", minimum=1)
    observe_items = _array(model["observe"], "$.observe", minimum=1)
    if len(state_items) + len(parameter_items) > MAX_DECLARATIONS:
        raise MachineModelError(f"$.states/parameters: se superó el límite de {MAX_DECLARATIONS} variables")
    if not isinstance(model["solver"], str) or model["solver"] not in {"rk4", "euler"}:
        raise MachineModelError("$.solver: método no soportado; use 'rk4' o 'euler'")

    names, state_specs, initial, derivatives = set(), [], [], []
    for i, item in enumerate(state_items):
        path = f"$.states[{i}]"
        state = _object(item, path, ("name", "unit", "initial"))
        state_name = _identifier(state["name"], f"{path}.name")
        if state_name in names:
            raise MachineModelError(f"{path}.name: nombre duplicado {state_name!r}")
        names.add(state_name)
        unit = _unit(state["unit"], f"{path}.unit")
        value, initial_unit = _quantity(state["initial"], f"{path}.initial")
        state_specs.append((state_name, unit, False))
        initial.append(Assignment(state_name, Expr("number", value, unit=initial_unit), 1))

    parameter_specs = []
    for i, item in enumerate(parameter_items):
        path = f"$.parameters[{i}]"
        parameter = _object(item, path, ("name", "value", "unit"))
        parameter_name = _identifier(parameter["name"], f"{path}.name")
        if parameter_name in names:
            raise MachineModelError(f"{path}.name: nombre duplicado {parameter_name!r}")
        names.add(parameter_name)
        unit = _unit(parameter["unit"], f"{path}.unit")
        value = _number(parameter["value"], f"{path}.value")
        parameter_specs.append((parameter_name, unit))
        state_specs.append((parameter_name, unit, True))
        initial.append(Assignment(parameter_name, Expr("number", value, unit=unit), 1))

    seen_derivatives = set()
    counter = [0]
    declared_states = {entry[0] for entry in state_specs if not entry[2]}
    declared_parameters = {entry[0] for entry in state_specs if entry[2]}
    for i, item in enumerate(derivative_items):
        path = f"$.derivatives[{i}]"
        derivative = _object(item, path, ("target", "expr"))
        target = _identifier(derivative["target"], f"{path}.target")
        if target not in declared_states:
            raise MachineModelError(f"{path}.target: debe nombrar un estado declarado")
        if target in seen_derivatives:
            raise MachineModelError(f"{path}.target: derivada duplicada para {target!r}")
        seen_derivatives.add(target)
        derivatives.append(Assignment(f"d{target}_dt", _expr(derivative["expr"], f"{path}.expr", 0, counter, declared_states, declared_parameters), 1))
    expected = declared_states
    if seen_derivatives != expected:
        raise MachineModelError(f"$.derivatives: faltan derivadas para {sorted(expected - seen_derivatives)}")

    for parameter_name, unit in parameter_specs:
        derivatives.append(Assignment(f"d{parameter_name}_dt", Expr("number", 0.0, unit=f"{unit}/s"), 1))

    constraint_items = _array(model.get("constraints", []), "$.constraints")
    if len(constraint_items) > MAX_DECLARATIONS:
        raise MachineModelError(f"$.constraints: se superó el límite de {MAX_DECLARATIONS} constraints")
    constraints = []
    for i, item in enumerate(constraint_items):
        path = f"$.constraints[{i}]"
        constraint = _object(item, path, ("expr",))
        expression = _expr(constraint["expr"], f"{path}.expr", 0, counter,
                           declared_states, declared_parameters)
        constraints.append(ConstraintDecl(expression, None))

    time = _object(model["time"], "$.time", ("start", "duration", "step"))
    start_value, start_unit = _quantity(time["start"], "$.time.start")
    duration_value, duration_unit = _quantity(time["duration"], "$.time.duration")
    step_value, step_unit = _quantity(time["step"], "$.time.step")
    if not same(parse_unit(start_unit), parse_unit("s")):
        raise MachineModelError("$.time.start.unit: start debe tener unidades de tiempo")
    start_expr = Expr("number", start_value, unit=start_unit)
    duration_expr = Expr("number", duration_value, unit=duration_unit)
    step_expr = Expr("number", step_value, unit=step_unit)

    # Shift explicit time references because the current solver's clock begins at
    # zero; shift returned timestamps back to the requested absolute start below.
    if start_value != 0:
        start_seconds = start_value * unit_scale(start_unit)
        def shift_time(expr):
            if expr.kind == "name" and expr.value == "t":
                return Expr("binary", "+", (expr, Expr("number", start_seconds, unit="s")), line=expr.line, column=expr.column)
            return Expr(expr.kind, expr.value, tuple(shift_time(child) for child in expr.children), expr.unit, expr.line, expr.column)
        derivatives = [Assignment(a.name, shift_time(a.expr), a.line) for a in derivatives]

    fields = tuple(Field(field_name, "scalar", unit, 1) for field_name, unit, _ in state_specs)
    init = InitDecl(name, tuple(initial))
    operator = OperatorDecl("MachineModel", tuple(derivatives))
    options = (
        Assignment("dt", step_expr, 1),
        Assignment("duration", duration_expr, 1),
        Assignment("method", Expr("name", "RK4" if model["solver"] == "rk4" else "Euler"), 1),
    )
    observations = tuple(_identifier(value, f"$.observe[{i}]") for i, value in enumerate(observe_items))
    if len(set(observations)) != len(observations):
        raise MachineModelError("$.observe: no se permiten nombres repetidos")
    declared_states = {entry[0] for entry in state_specs if not entry[2]}
    unknown = set(observations) - declared_states
    if unknown:
        raise MachineModelError(f"$.observe: solo se pueden observar estados; desconocidos {sorted(unknown)}")

    program = Program(StateDecl(name, fields), init, operator,
                      EvolveDecl(name, "MachineModel", options), observations, tuple(constraints))
    try:
        check(program)
    except (SemanticError, UnitError) as exc:
        raise MachineModelError(str(exc)) from exc
    controls = {assignment.name: assignment.expr for assignment in options}
    start_seconds = evaluate(start_expr, {}) * unit_scale(start_unit)
    step_seconds = evaluate(controls["dt"], {})
    duration_seconds = evaluate(controls["duration"], {})
    if not math.isfinite(start_seconds):
        raise MachineModelError("$.time.start: debe ser finito")
    if not math.isfinite(step_seconds) or step_seconds <= 0:
        raise MachineModelError("$.time.step: debe ser finito y positivo")
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise MachineModelError("$.time.duration: debe ser finita y positiva")
    steps = duration_seconds / step_seconds
    if not math.isfinite(steps) or abs(steps - round(steps)) > 1e-9:
        raise MachineModelError("$.time.duration: debe ser múltiplo entero de $.time.step")
    if steps > MAX_STEPS:
        raise MachineModelError(f"$.time: el modelo supera el límite de {MAX_STEPS} pasos")
    return program


def loads(text: str) -> Program:
    """Decode untrusted JSON with size and non-finite-number guards."""
    if not isinstance(text, str):
        raise MachineModelError("el documento debe ser texto JSON")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise MachineModelError(f"el documento supera el límite de {MAX_DOCUMENT_BYTES} bytes")

    def reject_constant(value):
        raise MachineModelError(f"constante JSON no válida: {value}")

    return load_document(_decode(text, reject_constant))


def _decode(text, reject_constant=None):
    if not isinstance(text, str):
        raise MachineModelError("el documento debe ser texto JSON")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise MachineModelError(f"el documento supera el límite de {MAX_DOCUMENT_BYTES} bytes")
    if reject_constant is None:
        def reject_constant(value):
            raise MachineModelError(f"constante JSON no válida: {value}")
    try:
        return json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MachineModelError(f"JSON no válido: {exc}") from exc


def run_document(document: dict):
    program = load_document(document)
    rows = run(program)
    start = document["time"]["start"]["value"]
    offset = float(start) * unit_scale(document["time"]["start"]["unit"])
    if offset:
        for row in rows:
            row["t"] += offset
    return rows


def run_json(text: str):
    """Load and execute one machine model, returning its observed time series."""
    return run_document(_decode(text))
