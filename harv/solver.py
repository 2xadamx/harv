"""Numerical execution over HARV's immutable typed scalar ODE IR."""
import math

from .ast import Program
from .ir import IRExpression, TypedProgram, lower


class SolverError(ValueError):
    pass


def _finite_real(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _evaluate(expression: IRExpression, environment: dict[str, float]) -> float:
    op = expression.op
    if op == "constant":
        return expression.value
    if op == "reference":
        if expression.value == "pi":
            return math.pi
        if expression.value == "e":
            return math.e
        try:
            return environment[expression.value]
        except KeyError as exc:
            raise SolverError(f"referencia IR sin valor: {expression.value}") from exc
    if op.startswith("unary:"):
        value = _evaluate(expression.args[0], environment)
        return value if op == "unary:+" else -value
    if op.startswith("binary:"):
        left, right = (_evaluate(arg, environment) for arg in expression.args)
        symbol = op.removeprefix("binary:")
        operations = {
            "+": lambda: left + right,
            "-": lambda: left - right,
            "*": lambda: left * right,
            "/": lambda: left / right,
            "^": lambda: left ** right,
            "**": lambda: left ** right,
            "<": lambda: float(left < right),
            ">": lambda: float(left > right),
            "<=": lambda: float(left <= right),
            ">=": lambda: float(left >= right),
            "==": lambda: float(left == right),
            "!=": lambda: float(left != right),
        }
        try:
            return operations[symbol]()
        except (KeyError, ArithmeticError) as exc:
            raise SolverError(f"operación IR no ejecutable: {symbol}") from exc
    if op.startswith("call:"):
        function = op.removeprefix("call:")
        functions = {
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "exp": math.exp, "log": math.log, "sqrt": math.sqrt,
            "abs": abs, "min": min, "max": max,
        }
        if function not in functions:
            raise SolverError(f"función IR no ejecutable: {function}")
        try:
            return functions[function](*(_evaluate(arg, environment) for arg in expression.args))
        except (ValueError, ArithmeticError) as exc:
            raise SolverError(f"falló la función {function} durante la simulación") from exc
    raise SolverError(f"operación IR desconocida: {op}")


def run_ir(program: TypedProgram):
    """Execute a validated typed IR program with its explicitly selected solver."""
    if not isinstance(program, TypedProgram):
        raise TypeError("run_ir requiere un TypedProgram producido por harv.ir.lower")
    grid = program.time
    if (not math.isfinite(grid.step_seconds) or grid.step_seconds <= 0
            or not math.isfinite(grid.duration_seconds) or grid.duration_seconds <= 0
            or grid.steps <= 0):
        raise SolverError("IR contiene una malla temporal no válida")
    if program.solver not in {"Euler", "RK4"}:
        raise SolverError(f"solver IR no soportado: {program.solver}")

    values = {field.name: field.initial_si for field in program.fields}
    derivative_map = {derivative.target: derivative.expression for derivative in program.derivatives}
    if set(derivative_map) != set(values):
        raise SolverError("IR debe contener exactamente una derivada por variable")
    observed = set(program.observations)
    if not observed <= set(values):
        raise SolverError("IR observa una variable no declarada")

    def validate_constraints(current, time):
        environment = {"t": time, **current}
        for index, constraint in enumerate(program.constraints, start=1):
            location = f" (linea {constraint.line})" if constraint.line is not None else ""
            try:
                satisfied = _evaluate(constraint.expression, environment)
            except SolverError as exc:
                raise SolverError(
                    f"no se pudo evaluar constraint {index}{location} en t={time:g} s: {exc}"
                ) from exc
            if satisfied != 1.0:
                raise SolverError(
                    f"constraint {index}{location} incumplida en t={time:g} s"
                )

    def field(current, time):
        validate_constraints(current, time)
        environment = {"t": time, **current}
        result = {name: _evaluate(expression, environment) for name, expression in derivative_map.items()}
        if not all(_finite_real(value) for value in result.values()):
            raise SolverError(f"dinámica produjo una derivada no finita en t={time:g}")
        return result

    def offset(base, slope, scale):
        return {name: base[name] + scale * slope[name] for name in base}

    rows = []
    def append_row(time):
        rows.append({"t": time, **{name: value for name, value in values.items() if name in observed}})

    time = grid.start_seconds
    validate_constraints(values, time)
    append_row(time)
    for index in range(grid.steps):
        k1 = field(values, time)
        if program.solver == "Euler":
            values = offset(values, k1, grid.step_seconds)
        else:
            half = grid.step_seconds / 2.0
            k2 = field(offset(values, k1, half), time + half)
            k3 = field(offset(values, k2, half), time + half)
            k4 = field(offset(values, k3, grid.step_seconds), time + grid.step_seconds)
            values = {
                name: values[name] + grid.step_seconds / 6.0
                * (k1[name] + 2.0 * k2[name] + 2.0 * k3[name] + k4[name])
                for name in values
            }
        time = (time + grid.step_seconds) if index < grid.steps - 1 else grid.start_seconds + grid.duration_seconds
        if not all(_finite_real(value) for value in values.values()):
            raise SolverError(f"simulación produjo un valor no finito en t={time:g}")
        validate_constraints(values, time)
        append_row(time)
    return rows


def run(program: Program):
    """Compatibility entry point: validate/lower source AST, then execute IR."""
    return run_ir(lower(program))
