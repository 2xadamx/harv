"""Dimension vectors and parser for a small SI unit algebra."""
import math
import re
from fractions import Fraction


class UnitError(ValueError):
    pass


BASE = {name: {name: Fraction(1)} for name in ("m", "s", "kg", "K", "A", "USD")}
# Unit aliases map to canonical dimensions and a multiplier into base units.
# year is the Julian year (365.25 days); monetary units are model labels, not
# claims that currency has a universal physical exchange scale.
ALIASES = {
    "Pa": ({"kg": Fraction(1), "m": Fraction(-1), "s": Fraction(-2)}, 1.0),
    "J": ({"kg": Fraction(1), "m": Fraction(2), "s": Fraction(-2)}, 1.0),
    "year": ({"s": Fraction(1)}, 31557600.0),
    "percent": ({}, 0.01),
    # Plane angle is dimensionless in SI; degrees convert to radians.
    "rad": ({}, 1.0),
    "deg": ({}, math.pi / 180.0),
}


def clean(dims):
    return {key: Fraction(value) for key, value in dims.items() if value}


def parse_unit_info(text: str | None):
    if not text or text == "1": return {}, 1.0
    tokens = re.findall(r"1|[A-Za-z]+|\d+|[*/^+-]", text)
    if "".join(tokens) != text:
        raise UnitError(f"unidad no válida: {text}")
    out, scale, sign, i = {}, 1.0, 1, 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("*", "/"):
            sign = 1 if token == "*" else -1; i += 1; continue
        if token == "1": dims, factor = {}, 1.0
        elif token in BASE: dims, factor = BASE[token], 1.0
        elif token in ALIASES: dims, factor = ALIASES[token]
        else: raise UnitError(f"unidad base no reconocida: {token}")
        i += 1; power = Fraction(1)
        if i < len(tokens) and tokens[i] == "^":
            i += 1
            if i >= len(tokens): raise UnitError("falta exponente de unidad")
            raw = tokens[i]; i += 1
            if raw in ("+", "-"):
                if i >= len(tokens): raise UnitError("falta exponente de unidad")
                power = Fraction(int(tokens[i]) * (-1 if raw == "-" else 1)); i += 1
            else: power = Fraction(int(raw))
        for key, value in dims.items(): out[key] = out.get(key, Fraction()) + sign * value * power
        scale *= factor ** float(sign * power)
        sign = 1
    return clean(out), scale


def parse_unit(text: str | None):
    return parse_unit_info(text)[0]


def unit_scale(text: str | None):
    return parse_unit_info(text)[1]


def format_unit(dims):
    dims = clean(dims)
    return "1" if not dims else " ".join(f"{k}^{v}" if v != 1 else k for k, v in sorted(dims.items()))


def same(a, b): return clean(a) == clean(b)

def mul(a, b):
    out = dict(a)
    for k, v in b.items(): out[k] = out.get(k, Fraction()) + v
    return clean(out)

def div(a, b):
    return mul(a, {k: -v for k, v in b.items()})

def power(a, p):
    return clean({k: v * Fraction(p) for k, v in a.items()})
