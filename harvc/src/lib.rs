//! Language-neutral frontend model for the HARV compiler.
//!
//! The parser is not implemented in this crate yet. The normative syntax and
//! lowering contract live in `../docs/GRAMMAR_AND_AST.md`.

pub mod ast;

pub use ast::{Declaration, Expr, ExprKind, Program, Span};
