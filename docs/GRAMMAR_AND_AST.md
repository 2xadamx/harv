# HARV v0.1: formal grammar, AST, and lowering contract

This document is the parser/compiler contract for the scalar ODE MVP. It describes the syntax already accepted by the Python frontend and a language-neutral typed AST suitable for the planned Rust compiler. It does not claim vectors, fields, or a Rust executable are implemented.

## 1. Lexical conventions

The lexer emits `IDENT`, `NUMBER`, `KEYWORD`, `SYMBOL`, and `EOF` tokens. Every non-EOF token carries a half-open source span `(start_line, start_column, end_line, end_column)`; diagnostics refer to one-based line and column. Whitespace is insignificant. `#` and `//` begin comments through end of line. Identifiers are ASCII letters/underscore followed by ASCII letters, digits, or underscores. Numeric literals support integer, decimal, and scientific forms.

```ebnf
letter       = "A" … "Z" | "a" … "z" | "_" ;
digit        = "0" … "9" ;
identifier   = (letter), { letter | digit } ;
number       = digits, [ ".", { digit } ], [ exponent ]
             | ".", digits, [ exponent ] ;
exponent     = ("e" | "E"), [ "+" | "-" ], digits ;
digits       = digit, { digit } ;
```

The sign is a separate unary operator, not part of the numeric token. Multi-character operators are recognized before their one-character prefixes: `**`, `<=`, `>=`, `==`, `!=`.

## 2. Grammar (EBNF)

The grammar below is for the currently implemented scalar subset. Braces and punctuation are literal tokens. Newlines and semicolons do not delimit statements; a statement ends when its expression ends before the next non-operator identifier or the enclosing `}`.

```ebnf
program          = { top_level }, EOF ;
top_level        = state_decl | init_decl | operator_decl | evolve_decl | observe_decl | constraint_decl ;

state_decl       = "state", identifier, "{", { field_decl }, "}" ;
field_decl       = identifier, ":", type_name, [ "<", unit, ">" ] ;
type_name        = "scalar" | "vector" | "field"
                 | "vector2" | "vector3" | "field2d" | "field3d" | "tensor" ;

init_decl        = "init", identifier, "{", { assignment }, "}" ;
operator_decl    = "operator", identifier, "{", { derivative_assignment }, "}" ;
derivative_assignment = derivative_name, "=", expression ;
derivative_name  = "d", identifier, "_dt" ;
assignment       = identifier, "=", expression ;

evolve_decl      = "evolve", identifier, "using", identifier,
                   "{", { assignment }, "}" ;
observe_decl     = "observe", identifier ;
constraint_decl  = "constraint", comparison ;

unit             = unit_factor, { ("*" | "/"), unit_factor } ;
unit_factor      = [ "1" | identifier ], [ "^", [ "+" | "-" ], digits ] ;

expression       = comparison ;
comparison       = sum, { ("<" | ">" | "<=" | ">=" | "==" | "!="), sum } ;
sum              = product, { ("+" | "-"), product } ;
product          = unary, { ("*" | "/"), unary } ;
unary            = ("+" | "-"), unary | power ;
power            = postfix, [ ("^" | "**"), unary ] ;
postfix          = primary, { index_suffix }
                 | identifier, call_suffix, { index_suffix } ;
call_suffix      = "(", [ expression, { ",", expression } ], ")" ;
index_suffix     = "[", expression, { ",", expression }, "]" ;
primary          = number, [ "<", unit, ">" ]
                 | identifier
                 | "(", expression, ")" ;
```

Exponentiation is right-associative and binds more tightly than unary signs; multiplication/division bind more tightly than addition/subtraction; comparisons bind least tightly. Function calls use an identifier as the call target. `t`, `pi`, and `e` are predefined names. The lexer knows the future type names, but semantic analysis currently accepts only `scalar` fields. Constraints must be comparisons with compatible dimensions, for example `constraint x > 0<m>`.

## 3. Semantic constraints

The grammar alone is insufficient for a valid program. v0.1 semantic validation requires exactly one each of `state`, `init`, `operator`, and `evolve`; names in `init` and `evolve` must match the declared state; the selected operator name must match; each scalar field is initialized exactly once and has exactly one derivative; and `evolve` has exactly `dt`, `duration`, and `method` assignments. `method` is `RK4` or `Euler`. `dt` and `duration` are positive, finite seconds and the duration must be an integer number of steps. Typed lowering rejects non-finite initial values and simulations above one million steps.

Units are dimension vectors over `m`, `s`, `kg`, `K`, `A`, and `USD`. Addition, subtraction, and comparisons require equal dimensions. Multiplication and division combine exponents. Derivative `dname_dt` must have the dimension of `name / s`. Initial expressions may use constants and pure math calls, but may not depend on another state variable. `sin`, `cos`, `tan`, `exp`, and `log` require dimensionless inputs. Angles are dimensionless radians; `rad` has scale 1 and `deg` converts by π/180. Unit aliases and scaled literals are normalized to SI magnitudes internally. Each constraint must be a comparison at its root; the solver checks it at the initial state, every solver stage, and after each step, aborting on the first false result.

## 4. Typed AST (Rust-oriented, language-neutral contract)

Source spans are retained through parsing and semantic analysis so errors can point to the original source. AST nodes own syntax and source locations; they do not depend on any numerical backend.

```rust
struct Span { start: Position, end: Position }
struct Position { line: u32, column: u32 }

struct Program { declarations: Vec<Declaration>, span: Span }
enum Declaration {
    State(StateDecl), Init(InitDecl), Operator(OperatorDecl),
    Evolve(EvolveDecl), Observe(ObserveDecl), Constraint(ConstraintDecl),
}

struct StateDecl { name: Ident, fields: Vec<FieldDecl>, span: Span }
struct FieldDecl { name: Ident, ty: Type, unit: Option<UnitExpr>, span: Span }
enum Type { Scalar, Vector, Field, Vector2, Vector3, Field2D, Field3D, Tensor }
struct InitDecl { state: Ident, assignments: Vec<Assignment>, span: Span }
struct OperatorDecl { name: Ident, derivatives: Vec<Derivative>, span: Span }
struct Derivative { target: Ident, value: Expr, span: Span }
struct EvolveDecl { state: Ident, operator: Ident, options: Vec<Assignment>, span: Span }
struct ObserveDecl { target: Ident, span: Span }
struct ConstraintDecl { predicate: Expr, span: Span } // scalar comparison; abort-on-violation
struct Assignment { target: Ident, value: Expr, span: Span }

enum ExprKind {
    Number { value: f64, unit: Option<UnitExpr> },
    Name(Ident), Unary { op: UnaryOp, value: Box<Expr> },
    Binary { op: BinaryOp, left: Box<Expr>, right: Box<Expr> },
    Call { function: Ident, args: Vec<Expr> },
    Index { target: Box<Expr>, indices: Vec<Expr> },
}
struct Expr { kind: ExprKind, span: Span }
enum UnaryOp { Positive, Negative }
enum BinaryOp { Add, Subtract, Multiply, Divide, Power, Less, Greater,
                LessEqual, GreaterEqual, Equal, NotEqual }
```

`Ident` stores its spelling and span. `UnitExpr` is parsed from source spelling and then normalized by semantic analysis into a canonical dimension vector. `Expr` is syntax-only; resolved names, inferred dimensions, and backend values belong to later compiler stages rather than being written back into source nodes.

The current Python AST uses a compact fixed-shape `Program` for the implemented subset. The Rust compiler should use the declaration list above so adding constraints and additional declarations does not require changing the top-level representation.

## 5. Typed IR boundary

Successful semantic analysis lowers source AST into the implemented immutable Python IR (`harv/ir.py`):

```text
TypedProgram
  fields: ordered (name, rational dimension vector, SI initial value)
  derivatives: ordered (target, typed expression tree)
  time: (start_seconds, step_seconds, duration_seconds, integer steps)
  solver: Euler | RK4
  observations: ordered state-field names
  constraints: ordered typed boolean expressions with source lines
```

Expression nodes carry inferred dimensions; numeric literals and initial values are normalized to SI magnitudes during lowering. The numerical engine consumes `TypedProgram` through `run_ir`; `run(Program)` is a convenience wrapper that checks and lowers before delegating. The runtime evaluates `F(X, t) -> dX/dt`; it never mutates the AST or typed program. RK stages operate on temporary state values, then the solver commits the next state. Scalar predicates are stored in the IR and abort execution when false; no projection or repair policy is inferred. Vector/field values and backend selection remain out of scope.

`harvc ir file.harv` and `harvc ir-json file.json` emit the versioned JSON form in `schemas/harv-typed-ir-0.1.schema.json`; `examples/decay.typed-ir.json` is a generated reference. Canonical JSON bytes sort object keys and remove insignificant whitespace; the SHA-256 fingerprint covers model semantics, including constraints, but excludes diagnostic source-line metadata. It does not claim mathematical equivalence between different IR documents. A future independent compiler must adopt the same canonical number encoding before its fingerprints can be compared byte-for-byte.

## 6. Current implementation gap

The source `Program` remains fixed-shape rather than a declaration list, and the Python AST does not retain spans on every node. Unit checking and the current IR support scalar ODEs and scalar comparison constraints only. The Rust AST scaffold is still separate and does not yet lower to or execute this IR.
