"""Recursive block parser plus Pratt expression parser for HARV."""
from .ast import (Assignment, ConstraintDecl, EvolveDecl, Expr, Field, InitDecl,
                  OperatorDecl, Program, StateDecl)
from .lexer import lex, LexError


class ParseError(ValueError):
    pass


class Parser:
    def __init__(self, source: str):
        try:
            self.tokens = lex(source)
        except LexError as exc:
            raise ParseError(str(exc)) from exc
        self.i = 0

    @property
    def token(self): return self.tokens[self.i]
    def at(self, value): return self.token.value == value
    def take(self):
        t = self.token; self.i += 1; return t
    def expect(self, value):
        if not self.at(value): self.fail(f"se esperaba {value!r}, se encontró {self.token.value!r}")
        return self.take()
    def identifier(self):
        if self.token.kind not in ("IDENT", "KEYWORD") or self.token.value in {"state", "init", "operator", "evolve", "using"}:
            self.fail("se esperaba un identificador")
        return self.take()
    def fail(self, message):
        t = self.token
        raise ParseError(f"línea {t.line}, columna {t.column}: {message}")

    def unit_text(self):
        self.expect("<")
        pieces = []
        while not self.at(">"):
            if self.token.kind == "EOF": self.fail("unidad sin '>' de cierre")
            pieces.append(self.take().value)
        self.take()
        if not pieces: self.fail("unidad vacía")
        return "".join(pieces)

    def state_block(self):
        self.expect("state"); name = self.identifier().value; self.expect("{")
        fields = []
        while not self.at("}"):
            field = self.identifier(); self.expect(":")
            typ = self.take()
            if typ.value not in {"scalar", "vector", "field", "field2d", "field3d", "vector2", "vector3", "tensor"}:
                self.fail("tipo no reconocido")
            unit = self.unit_text() if self.at("<") else None
            fields.append(Field(field.value, typ.value, unit, field.line))
        self.take()
        return StateDecl(name, tuple(fields))

    def assignment_block(self, kind):
        self.expect(kind); name = self.identifier().value; self.expect("{")
        assignments = []
        while not self.at("}"):
            left = self.identifier(); self.expect("=")
            expr = self.expression()
            assignments.append(Assignment(left.value, expr, left.line))
        self.take()
        return name, tuple(assignments)

    def evolve_block(self):
        self.expect("evolve"); state = self.identifier().value
        self.expect("using"); operator = self.identifier().value; self.expect("{")
        assignments = []
        while not self.at("}"):
            left = self.identifier(); self.expect("=")
            expr = self.expression()
            assignments.append(Assignment(left.value, expr, left.line))
        self.take()
        return EvolveDecl(state, operator, tuple(assignments))

    def constraint_decl(self):
        token = self.expect("constraint")
        expression = self.expression()
        return ConstraintDecl(expression, token.line)

    def expression(self, min_bp=0):
        t = self.take()
        if t.kind == "NUMBER":
            left = Expr("number", float(t.value), unit=self.unit_text() if self.at("<") else None,
                        line=t.line, column=t.column)
        elif t.value in ("+", "-"):
            left = Expr("unary", t.value, (self.expression(25),), line=t.line, column=t.column)
        elif t.value == "(":
            left = self.expression(); self.expect(")")
        elif t.kind in ("IDENT", "KEYWORD") and t.value not in {"state", "init", "operator", "evolve", "using"}:
            if self.at("("):
                self.take(); args = []
                if not self.at(")"):
                    while True:
                        args.append(self.expression())
                        if not self.at(","): break
                        self.take()
                self.expect(")")
                left = Expr("call", t.value, tuple(args), line=t.line, column=t.column)
            else:
                left = Expr("name", t.value, line=t.line, column=t.column)
        else:
            self.fail(f"se esperaba una expresión, se encontró {t.value!r}")

        while True:
            if self.at("["):
                self.take(); indices = [self.expression()]
                while self.at(","):
                    self.take(); indices.append(self.expression())
                self.expect("]")
                left = Expr("index", children=(left, *indices), line=left.line, column=left.column)
                continue
            op = self.token.value
            binding = {"^": (30, 30), "**": (30, 30), "*": (20, 21), "/": (20, 21),
                       "+": (10, 11), "-": (10, 11), "<": (5, 6), ">": (5, 6),
                       "<=": (5, 6), ">=": (5, 6), "==": (5, 6), "!=": (5, 6)}
            if op not in binding or binding[op][0] < min_bp: break
            self.take(); right = self.expression(binding[op][1])
            left = Expr("binary", op, (left, right), line=left.line, column=left.column)
        return left

    def parse(self):
        state = initial = operator = evolve = None
        observations = []
        constraints = []
        while self.token.kind != "EOF":
            if self.at("state"):
                if state is not None: self.fail("solo se permite un bloque state en v0.1")
                state = self.state_block()
            elif self.at("init"):
                if initial is not None: self.fail("solo se permite un bloque init en v0.1")
                name, values = self.assignment_block("init"); initial = InitDecl(name, values)
            elif self.at("operator"):
                if operator is not None: self.fail("solo se permite un bloque operator en v0.1")
                name, values = self.assignment_block("operator"); operator = OperatorDecl(name, values)
            elif self.at("evolve"):
                if evolve is not None: self.fail("solo se permite un bloque evolve en v0.1")
                evolve = self.evolve_block()
            elif self.at("observe"):
                self.take(); observations.append(self.identifier().value)
            elif self.at("constraint"):
                constraints.append(self.constraint_decl())
            else:
                self.fail(f"declaración inesperada {self.token.value!r}")
        if None in (state, initial, operator, evolve):
            raise ParseError("el programa requiere state, init, operator y evolve")
        return Program(state, initial, operator, evolve, tuple(observations), tuple(constraints))


def parse(source: str) -> Program:
    return Parser(source).parse()
