"""Source-independent syntax tree for the HARV v0.1 language."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


@dataclass(frozen=True)
class Expr:
    kind: str
    value: object = None
    children: tuple["Expr", ...] = ()
    unit: str | None = None
    line: int = 1
    column: int = 1


@dataclass(frozen=True)
class Field:
    name: str
    type_name: str
    unit: str | None
    line: int


@dataclass(frozen=True)
class Assignment:
    name: str
    expr: Expr
    line: int


@dataclass(frozen=True)
class StateDecl:
    name: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class InitDecl:
    name: str
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class OperatorDecl:
    name: str
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class EvolveDecl:
    state_name: str
    operator_name: str
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class ConstraintDecl:
    expression: Expr
    line: int | None


@dataclass(frozen=True)
class Program:
    state: StateDecl
    initial: InitDecl
    operator: OperatorDecl
    evolve: EvolveDecl
    observations: tuple[str, ...] = ()
    constraints: tuple[ConstraintDecl, ...] = ()
