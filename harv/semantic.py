"""Name, shape, and dimensional checks for scalar HARV programs."""
import math
from .ast import Expr, Program
from .units import UnitError, clean, div, mul, parse_unit, power, same, unit_scale


class SemanticError(ValueError):
    pass


FUNCTIONS = {"sin", "cos", "tan", "exp", "log", "sqrt", "abs", "min", "max",
             "dot", "cross", "norm", "normalize", "laplacian", "gradient", "divergence"}


def infer(expr: Expr, names: dict[str, dict], *, allow_time=True):
    if expr.kind == "number": return parse_unit(expr.unit)
    if expr.kind == "name":
        if expr.value == "pi" or expr.value == "e": return {}
        if expr.value == "t" and allow_time: return parse_unit("s")
        if expr.value not in names: raise SemanticError(f"línea {expr.line}: nombre no declarado {expr.value!r}")
        return names[expr.value]
    if expr.kind == "unary": return infer(expr.children[0], names, allow_time=allow_time)
    if expr.kind == "binary":
        a, b = (infer(child, names, allow_time=allow_time) for child in expr.children)
        if expr.value in ("+", "-"):
            if not same(a, b): raise SemanticError(f"línea {expr.line}: no se pueden sumar/restar unidades {a} y {b}")
            return a
        if expr.value in ("*", "/"): return mul(a, b) if expr.value == "*" else div(a, b)
        if expr.value in ("^", "**"):
            if b: raise SemanticError(f"línea {expr.line}: el exponente debe ser adimensional")
            if expr.children[1].kind != "number" or expr.children[1].unit:
                if a: raise SemanticError(f"línea {expr.line}: potencia de una cantidad dimensional requiere exponente numérico constante")
                return {}
            return power(a, expr.children[1].value)
        if not same(a, b): raise SemanticError(f"línea {expr.line}: comparación entre unidades incompatibles")
        return {}
    if expr.kind == "call":
        if expr.value not in FUNCTIONS: raise SemanticError(f"línea {expr.line}: función desconocida {expr.value!r}")
        args = [infer(arg, names, allow_time=allow_time) for arg in expr.children]
        if expr.value in {"sin", "cos", "tan", "exp", "log"}:
            if len(args) != 1 or args[0]: raise SemanticError(f"línea {expr.line}: {expr.value} requiere un argumento adimensional")
            return {}
        if expr.value == "sqrt":
            if len(args) != 1: raise SemanticError(f"línea {expr.line}: sqrt requiere un argumento")
            return power(args[0], 0.5)
        if expr.value in {"abs", "norm", "normalize"}:
            if len(args) != 1: raise SemanticError(f"línea {expr.line}: {expr.value} requiere un argumento")
            return {} if expr.value == "normalize" else args[0]
        if expr.value in {"min", "max"}:
            if not args or any(not same(args[0], item) for item in args[1:]):
                raise SemanticError(f"línea {expr.line}: {expr.value} requiere argumentos con unidades iguales")
            return args[0]
        raise SemanticError(f"línea {expr.line}: {expr.value} requiere tipos vectoriales aún no disponibles")
    if expr.kind == "index":
        raise SemanticError(f"línea {expr.line}: indexación disponible cuando se implementen vectores/campos")
    raise SemanticError(f"línea {expr.line}: expresión no soportada")


def evaluate(expr: Expr, env: dict[str, float]):
    if expr.kind == "number": return expr.value * unit_scale(expr.unit)
    if expr.kind == "name":
        constants = {"pi": math.pi, "e": math.e}
        if expr.value in constants: return constants[expr.value]
        if expr.value not in env: raise SemanticError(f"valor no inicializado: {expr.value}")
        return env[expr.value]
    if expr.kind == "unary":
        value = evaluate(expr.children[0], env)
        return value if expr.value == "+" else -value
    if expr.kind == "binary":
        a, b = (evaluate(child, env) for child in expr.children)
        return {"+": lambda: a+b, "-": lambda: a-b, "*": lambda: a*b, "/": lambda: a/b,
                "^": lambda: a**b, "**": lambda: a**b, "<": lambda: float(a < b),
                ">": lambda: float(a > b), "<=": lambda: float(a <= b), ">=": lambda: float(a >= b),
                "==": lambda: float(a == b), "!=": lambda: float(a != b)}[expr.value]()
    if expr.kind == "call":
        fns = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
               "log": math.log, "sqrt": math.sqrt, "abs": abs, "min": min, "max": max}
        if expr.value not in fns: raise SemanticError(f"función no ejecutable en v0.1: {expr.value}")
        return fns[expr.value](*(evaluate(arg, env) for arg in expr.children))
    raise SemanticError(f"expresión no ejecutable: {expr.kind}")


def check(program: Program):
    fields = {f.name: f for f in program.state.fields}
    if not fields: raise SemanticError("state debe declarar al menos una variable")
    if len(fields) != len(program.state.fields): raise SemanticError("variable duplicada en state")
    unsupported = [(f.name, f.type_name) for f in fields.values() if f.type_name != "scalar"]
    if unsupported: raise SemanticError(f"v0.1 solo ejecuta scalar; no implementado: {unsupported[0][0]}: {unsupported[0][1]}")
    declared = {name: parse_unit(f.unit) for name, f in fields.items()}
    if program.initial.name != program.state.name: raise SemanticError("init debe referirse al mismo estado que state")
    if program.evolve.state_name != program.state.name: raise SemanticError("evolve debe referirse al mismo estado que state")
    if program.evolve.operator_name != program.operator.name: raise SemanticError("evolve debe referirse al operador declarado")

    initial = {a.name: a for a in program.initial.assignments}
    if len(initial) != len(program.initial.assignments): raise SemanticError("asignación inicial duplicada")
    if set(initial) != set(fields): raise SemanticError("init debe asignar exactamente las variables de state")
    # Initializers may use numeric constants and functions, but not another
    # field's runtime value: that keeps initialization independent of order.
    init_names = {}
    for name, assignment in initial.items():
        actual = infer(assignment.expr, init_names, allow_time=False)
        if not same(actual, declared[name]):
            raise SemanticError(f"línea {assignment.line}: init de {name} tiene unidad {actual}, se esperaba {declared[name]}")

    derivatives = {a.name: a for a in program.operator.assignments}
    if len(derivatives) != len(program.operator.assignments): raise SemanticError("derivada duplicada")
    expected = {f"d{name}_dt" for name in fields}
    if set(derivatives) != expected:
        missing = sorted(expected - set(derivatives))
        extra = sorted(set(derivatives) - expected)
        raise SemanticError(f"operator debe definir una derivada por variable; faltan={missing}, sobran={extra}")
    derivative_names = {**declared, "t": parse_unit("s")}
    for target, assignment in derivatives.items():
        variable = target[1:-3]
        expected_unit = div(declared[variable], parse_unit("s"))
        actual = infer(assignment.expr, derivative_names)
        if not same(actual, expected_unit):
            raise SemanticError(f"línea {assignment.line}: {target} tiene unidad {actual}, se esperaba {expected_unit}")

    controls = {a.name: a for a in program.evolve.assignments}
    if len(controls) != len(program.evolve.assignments): raise SemanticError("parámetro evolve duplicado")
    if set(controls) != {"dt", "duration", "method"}:
        raise SemanticError("evolve requiere exactamente dt, duration y method")
    for key in ("dt", "duration"):
        a = controls[key]
        if not same(infer(a.expr, {}, allow_time=False), parse_unit("s")):
            raise SemanticError(f"línea {a.line}: {key} debe tener unidades de tiempo, por ejemplo {key} = 0.01<s>")
    method_expr = controls["method"].expr
    if method_expr.kind != "name" or method_expr.value not in {"RK4", "Euler"}:
        raise SemanticError("method debe ser RK4 o Euler")
    for name in program.observations:
        if name not in fields: raise SemanticError(f"observe referencia variable desconocida {name!r}")
    comparison_ops = {"<", ">", "<=", ">=", "==", "!="}
    for constraint in program.constraints:
        expression = constraint.expression
        if expression.kind != "binary" or expression.value not in comparison_ops:
            where = f"línea {constraint.line}: " if constraint.line is not None else ""
            raise SemanticError(f"{where}constraint debe ser una comparación, por ejemplo x > 0<m>")
        infer(expression, derivative_names)
    return program
