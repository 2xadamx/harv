"""Single source-AST to typed-IR to solver pipeline for HARV models."""
from .ast import Program
from .ir import TypedProgram, lower
from .parser import parse
from .solver import run_ir


def compile_program(program: Program) -> TypedProgram:
    """Semantically validate a parsed program and lower it to executable IR."""
    return lower(program)


def compile_source(source: str) -> tuple[Program, TypedProgram]:
    """Parse HARV source, perform semantic/unit checks, and build typed IR."""
    program = parse(source)
    return program, compile_program(program)


def execute_program(program: Program):
    """Execute a parsed model through semantic checks, typed IR, and solver."""
    typed_program = compile_program(program)
    return typed_program, run_ir(typed_program)


def execute_source(source: str):
    """Run source text end to end; return AST, typed IR, and time-series rows."""
    program, typed_program = compile_source(source)
    return program, typed_program, run_ir(typed_program)
