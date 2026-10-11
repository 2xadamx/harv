//! Source AST. Nodes retain spans and do not depend on solver/backend types.

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct Position {
    pub line: u32,
    pub column: u32,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct Span {
    pub start: Position,
    pub end: Position,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Ident {
    pub spelling: String,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Program {
    pub declarations: Vec<Declaration>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Declaration {
    State(StateDecl),
    Init(InitDecl),
    Operator(OperatorDecl),
    Evolve(EvolveDecl),
    Observe(ObserveDecl),
    Constraint(ConstraintDecl),
}

#[derive(Clone, Debug, PartialEq)]
pub struct StateDecl {
    pub name: Ident,
    pub fields: Vec<FieldDecl>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FieldDecl {
    pub name: Ident,
    pub ty: Type,
    pub unit: Option<UnitExpr>,
    pub span: Span,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Type {
    Scalar,
    Vector,
    Field,
    Vector2,
    Vector3,
    Field2D,
    Field3D,
    Tensor,
}

#[derive(Clone, Debug, PartialEq)]
pub struct InitDecl {
    pub state: Ident,
    pub assignments: Vec<Assignment>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct OperatorDecl {
    pub name: Ident,
    pub derivatives: Vec<Derivative>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Derivative {
    pub target: Ident,
    pub value: Expr,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EvolveDecl {
    pub state: Ident,
    pub operator: Ident,
    pub options: Vec<Assignment>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ObserveDecl {
    pub target: Ident,
    pub span: Span,
}

/// Reserved AST shape. The v0.1 grammar rejects `constraint` declarations.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstraintDecl {
    pub name: Ident,
    pub predicate: Expr,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Assignment {
    pub target: Ident,
    pub value: Expr,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct UnitExpr {
    /// Original normalized spelling, e.g. `kg/m^3`; semantic analysis
    /// converts it into a canonical dimension vector.
    pub spelling: String,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ExprKind {
    Number { value: f64, unit: Option<UnitExpr> },
    Name(Ident),
    Unary { op: UnaryOp, value: Box<Expr> },
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Call { function: Ident, args: Vec<Expr> },
    Index { target: Box<Expr>, indices: Vec<Expr> },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnaryOp {
    Positive,
    Negative,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BinaryOp {
    Add,
    Subtract,
    Multiply,
    Divide,
    Power,
    Less,
    Greater,
    LessEqual,
    GreaterEqual,
    Equal,
    NotEqual,
}
