"""Small handwritten lexer. Tokens retain source line and column."""
from .ast import Token


class LexError(ValueError):
    pass


KEYWORDS = {"state", "init", "operator", "evolve", "using", "scalar", "vector", "field",
            "field2d", "field3d", "vector2", "vector3", "tensor", "dt", "duration",
            "method", "constraint", "observe", "RK4", "Euler"}
_TWO = {"**", "<=", ">=", "==", "!="}
_ONE = set("{}()[]:,=+-*/^.<>")


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, col, n = 0, 1, 1, len(source)
    while i < n:
        ch = source[i]
        if ch in " \t\r":
            i += 1; col += 1; continue
        if ch == "\n":
            i += 1; line += 1; col = 1; continue
        if ch == "#" or source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1; col += 1
            continue
        start_line, start_col = line, col
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] == "_"): j += 1
            value = source[i:j]
            tokens.append(Token("KEYWORD" if value in KEYWORDS else "IDENT", value, line, col))
            col += j-i; i = j; continue
        if ch.isdigit() or (ch == "." and i+1 < n and source[i+1].isdigit()):
            j = i
            if source[j] == ".": j += 1
            while j < n and source[j].isdigit(): j += 1
            if j < n and source[j] == ".":
                j += 1
                while j < n and source[j].isdigit(): j += 1
            if j < n and source[j] in "eE":
                exp = j + 1
                if exp < n and source[exp] in "+-": exp += 1
                digits = exp
                while exp < n and source[exp].isdigit(): exp += 1
                if exp == digits:
                    raise LexError(f"línea {line}, columna {col}: exponente numérico incompleto")
                j = exp
            tokens.append(Token("NUMBER", source[i:j], line, col))
            col += j-i; i = j; continue
        pair = source[i:i+2]
        if pair in _TWO:
            tokens.append(Token("SYMBOL", pair, line, col)); i += 2; col += 2; continue
        if ch in _ONE:
            tokens.append(Token("SYMBOL", ch, line, col)); i += 1; col += 1; continue
        raise LexError(f"línea {line}, columna {col}: carácter inesperado {ch!r}")
    tokens.append(Token("EOF", "", line, col))
    return tokens
