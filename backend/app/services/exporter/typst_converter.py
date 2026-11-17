"""
Typst Content Converter (TASK-306).

Converts Markdown and LaTeX mathematical notation into clean, idiomatic
Typst markup syntax ($...$).
"""

import re
from typing import Callable, List, Tuple

_QUOTED_STR_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')

_TEXT_WRAPPER_RE = re.compile(
    r"\\(?:text|textrm|textbf|textsf|operatorname)(?![a-zA-Z])\s*\{"
)
_TWO_ARG_CMD_RE = re.compile(r"\\([dt]?frac|[dt]?binom)(?![a-zA-Z])\s*\{")
_SQRT_N_RE = re.compile(r"\\sqrt(?![a-zA-Z])\s*\[([^\[\]]+)\]\s*\{")
_SQRT_RE = re.compile(r"\\sqrt(?![a-zA-Z])\s*\{")

_SINGLE_ARG_WRAPPERS: dict[str, str] = {
    "mathbb": "bb",
    "mathbf": "bold",
    "boldsymbol": "bold",
    "mathrm": "upright",
    "mathcal": "cal",
    "mathit": "italic",
    "mathsf": "sans",
    "overline": "overline",
    "underline": "underline",
    "vec": "arrow",
    "hat": "hat",
    "widehat": "hat",
    "bar": "macron",
    "tilde": "tilde",
    "widetilde": "tilde",
    "dot": "dot",
    "ddot": "dot.double",
    "underbrace": "underbrace",
    "overbrace": "overbrace",
}
_SINGLE_ARG_WRAPPER_RE = re.compile(
    r"\\(" + "|".join(_SINGLE_ARG_WRAPPERS) + r")(?![a-zA-Z])\s*\{"
)
_UNBRACED_WRAPPER_RE = re.compile(
    r"\\("
    + "|".join(_SINGLE_ARG_WRAPPERS)
    + r")(?![a-zA-Z])\s*([A-Za-z0-9])(?![A-Za-z])"
)

_ENV_RE = re.compile(
    r"\\begin\s*\{(cases|pmatrix|bmatrix|vmatrix|Vmatrix|matrix|aligned|alignedat|gathered|split)\}"
    r"((?:(?!\\begin\s*\{).)*?)"
    r"\\end\s*\{\1\}",
    re.DOTALL,
)
_MATRIX_DELIMS: dict[str, str | None] = {
    "pmatrix": None,
    "bmatrix": "[",
    "vmatrix": "|",
    "Vmatrix": "||",
    "matrix": "none",
}
_ROW_SPLIT_RE = re.compile(r"\\\\(?:\s*\[[^\]]*\])?")
_COL_SPLIT_RE = re.compile(r"(?<!\\)&")

_BINARY_SYMBOLS: dict[str, str] = {
    "notin": "not in",
    "in": "in",
    "leq": "<=",
    "le": "<=",
    "geq": ">=",
    "ge": ">=",
    "neq": "!=",
    "ne": "!=",
    "approx": "approx",
    "equiv": "equiv",
    "cong": "tilde.equiv",
    "sim": "tilde.op",
    "propto": "prop",
    "cdot": "dot",
    "times": "times",
    "div": "div",
    "pm": "plus.minus",
    "mp": "minus.plus",
    "implies": "=>",
    "Rightarrow": "=>",
    "Leftarrow": "arrow.l.double",
    "iff": "<=>",
    "Leftrightarrow": "<=>",
    "rightarrow": "->",
    "to": "->",
    "leftarrow": "<-",
    "mapsto": "arrow.r.bar",
    "subseteq": "subset.eq",
    "supseteq": "supset.eq",
    "subset": "subset",
    "supset": "supset",
    "setminus": "without",
    "cup": "union",
    "cap": "sect",
    "land": "and",
    "lor": "or",
    "perp": "perp",
    "perpendicular": "perp",
    "parallel": "parallel",
    "bmod": "mod",
    "pmod": "mod",
    "mod": "mod",
}

_PREFIX_SYMBOLS: dict[str, str] = {
    "iiint": "integral.triple",
    "iint": "integral.double",
    "oint": "integral.cont",
    "int": "integral",
    "sum": "sum",
    "prod": "product",
    "infty": "infinity",
    "emptyset": "emptyset",
    "varnothing": "emptyset",
    "forall": "forall",
    "exists": "exists",
    "neg": "not",
    "lnot": "not",
    "partial": "partial",
    "nabla": "nabla",
    "degree": "degree",
    "circ": "circle.small",
    "angle": "angle",
    "triangle": "triangle",
    "ldots": "dots.h",
    "dots": "dots.h",
    "cdots": "dots.c",
    "vdots": "dots.v",
    "ddots": "dots.down",
    "langle": "angle.l",
    "rangle": "angle.r",
    "lvert": "|",
    "rvert": "|",
    "vert": "|",
    "lVert": "bar.v.double",
    "rVert": "bar.v.double",
    "Vert": "bar.v.double",
    "quad": "quad",
    "qquad": "wide",
    "colon": ":",
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "delta": "delta",
    "varepsilon": "epsilon.alt",
    "epsilon": "epsilon",
    "zeta": "zeta",
    "eta": "eta",
    "vartheta": "theta.alt",
    "theta": "theta",
    "iota": "iota",
    "kappa": "kappa",
    "lambda": "lambda",
    "mu": "mu",
    "nu": "nu",
    "xi": "xi",
    "pi": "pi",
    "rho": "rho",
    "sigma": "sigma",
    "tau": "tau",
    "upsilon": "upsilon",
    "varphi": "phi.alt",
    "phi": "phi",
    "chi": "chi",
    "psi": "psi",
    "omega": "omega",
    "Gamma": "Gamma",
    "Delta": "Delta",
    "Theta": "Theta",
    "Lambda": "Lambda",
    "Xi": "Xi",
    "Pi": "Pi",
    "Sigma": "Sigma",
    "Upsilon": "Upsilon",
    "Phi": "Phi",
    "Psi": "Psi",
    "Omega": "Omega",
    "arcsin": "arcsin",
    "arccos": "arccos",
    "arctan": "arctan",
    "sinh": "sinh",
    "cosh": "cosh",
    "tanh": "tanh",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "cot": "cot",
    "sec": "sec",
    "csc": "csc",
    "ln": "ln",
    "log": "log",
    "lim": "lim",
    "exp": "exp",
    "min": "min",
    "max": "max",
    "sup": "sup",
    "inf": "inf",
    "det": "det",
    "gcd": "gcd",
}

_MODIFIER_CMDS: frozenset[str] = frozenset(
    {
        "big",
        "Big",
        "bigg",
        "Bigg",
        "limits",
        "nolimits",
        "displaystyle",
        "textstyle",
        "scriptscriptstyle",
    }
)

_CONTROL_WORD_RE = re.compile(r"\\([A-Za-z]+)(?![a-zA-Z])")

_TYPST_DOT_SYMBOLS: frozenset[str] = frozenset(
    {
        "plus.minus",
        "minus.plus",
        "integral.double",
        "integral.triple",
        "integral.cont",
        "epsilon.alt",
        "theta.alt",
        "phi.alt",
        "subset.eq",
        "supset.eq",
        "tilde.op",
        "tilde.eq",
        "tilde.equiv",
        "circle.small",
        "dots.h",
        "dots.c",
        "dots.v",
        "dots.down",
        "angle.l",
        "angle.r",
        "chevron.l",
        "chevron.r",
        "arrow.l.double",
        "arrow.r.bar",
        "bar.v",
        "bar.v.double",
        "dot.double",
    }
)

_TYPST_MATH_IDENTIFIERS: frozenset[str] = frozenset(
    {
        # Logic, set, relation, and symbol keywords
        "in",
        "not",
        "and",
        "or",
        "approx",
        "equiv",
        "prop",
        "subset",
        "supset",
        "union",
        "sect",
        "without",
        "emptyset",
        "forall",
        "exists",
        "hash",
        "times",
        "div",
        "dot",
        "infinity",
        "oo",
        "partial",
        "nabla",
        "degree",
        "angle",
        "triangle",
        "perp",
        "parallel",
        # Big operators, constructs, and delimiters
        "sum",
        "product",
        "integral",
        "sqrt",
        "root",
        "binom",
        "mat",
        "cases",
        "lr",
        "abs",
        "norm",
        "floor",
        "ceil",
        "round",
        "frac",
        "dif",
        "op",
        "delim",
        "none",
        # Spacing and typography wrappers
        "quad",
        "wide",
        "thin",
        "med",
        "thick",
        "bold",
        "upright",
        "italic",
        "sans",
        "serif",
        "bb",
        "cal",
        "frak",
        "mono",
        "overline",
        "underline",
        "underbrace",
        "overbrace",
        "arrow",
        "hat",
        "macron",
        "tilde",
        # Greek letters
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "zeta",
        "eta",
        "theta",
        "iota",
        "kappa",
        "lambda",
        "mu",
        "nu",
        "xi",
        "omicron",
        "pi",
        "rho",
        "sigma",
        "tau",
        "upsilon",
        "phi",
        "chi",
        "psi",
        "omega",
        "Gamma",
        "Delta",
        "Theta",
        "Lambda",
        "Xi",
        "Pi",
        "Sigma",
        "Upsilon",
        "Phi",
        "Psi",
        "Omega",
        # Standard math functions
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "arcsin",
        "arccos",
        "arctan",
        "arccot",
        "sinh",
        "cosh",
        "tanh",
        "coth",
        "sech",
        "csch",
        "ln",
        "log",
        "lg",
        "exp",
        "lim",
        "limsup",
        "liminf",
        "min",
        "max",
        "sup",
        "inf",
        "arg",
        "det",
        "dim",
        "gcd",
        "lcm",
        "deg",
        "mod",
    }
)

_SPLIT_TOKEN_RE = re.compile(
    _QUOTED_STR_RE.pattern
    + r"|(?<![A-Za-z])(?:"
    + "|".join(re.escape(sym) for sym in sorted(_TYPST_DOT_SYMBOLS, key=len, reverse=True))
    + r")(?![A-Za-z])"
    r"|(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])"
)


def _transform_outside_quotes(text: str, transform: Callable[[str], str]) -> str:
    """Apply a string transformation only outside double-quoted literals."""
    parts: List[str] = []
    last = 0
    for match in _QUOTED_STR_RE.finditer(text):
        if match.start() > last:
            parts.append(transform(text[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()
    if last < len(text):
        parts.append(transform(text[last:]))
    return "".join(parts)


def _extract_balanced_braces(text: str, start_idx: int) -> Tuple[str, int]:
    """
    Extract content inside balanced curly braces starting at start_idx.
    Returns (inner_content, end_idx) where end_idx is the index after the closing '}'.
    """
    if start_idx >= len(text) or text[start_idx] != "{":
        return "", start_idx

    depth = 0
    inner_chars: List[str] = []
    i = start_idx

    while i < len(text):
        c = text[i]
        if c == "\\":
            if i + 1 < len(text) and text[i + 1] in "{}":
                inner_chars.append(text[i : i + 2])
                i += 2
                continue
            inner_chars.append(c)
            i += 1
            continue
        if c == "{":
            depth += 1
            if depth > 1:
                inner_chars.append(c)
        elif c == "}":
            depth -= 1
            if depth == 0:
                return "".join(inner_chars), i + 1
            inner_chars.append(c)
        else:
            inner_chars.append(c)
        i += 1

    return "".join(inner_chars), i


def _convert_aligned_row(row: str) -> str:
    """Convert one &-delimited row while preserving Typst column separators."""
    cols = [latex_math_to_typst(col.strip()) for col in _COL_SPLIT_RE.split(row)]
    return " & ".join(cols)


def _convert_env(name: str, body: str) -> str:
    """Convert a LaTeX math environment body to Typst syntax."""
    body_clean = body.strip()

    # Handle optional alignment / placement specifier [t|b|c] for alignment environments
    if name in {"aligned", "alignedat", "gathered", "split"}:
        if body_clean.startswith("["):
            bracket_end = body_clean.find("]")
            if bracket_end != -1:
                body_clean = body_clean[bracket_end + 1 :].strip()

        # F82-01: alignedat requires a mandatory column-count argument {n} (e.g. {2})
        # which is LaTeX layout metadata and must not be printed into Typst math output.
        if name == "alignedat":
            if body_clean.startswith("{"):
                _, end_idx = _extract_balanced_braces(body_clean, 0)
                body_clean = body_clean[end_idx:].strip()
            elif re.match(r"^\d+", body_clean):
                body_clean = re.sub(r"^\d+\s*", "", body_clean)

    rows = _ROW_SPLIT_RE.split(body_clean)
    if rows and not rows[-1].strip():
        rows = rows[:-1]

    if name == "cases":
        # F82-02: preserve '&' column separators inside Typst cases(...).
        converted_rows = [_convert_aligned_row(row) for row in rows if row.strip()]
        return f"cases({', '.join(converted_rows)})"

    if name in _MATRIX_DELIMS:
        converted_rows = []
        for row in rows:
            if not row.strip():
                continue
            cells = [latex_math_to_typst(cell.strip()) for cell in _COL_SPLIT_RE.split(row)]
            converted_rows.append(", ".join(cells))
        delim = _MATRIX_DELIMS[name]
        joined = "; ".join(converted_rows)
        if delim is None:
            return f"mat({joined})"
        delim_arg = "none" if delim == "none" else f'"{delim}"'
        return f"mat(delim: {delim_arg}, {joined})"

    # aligned / alignedat / gathered / split
    converted_lines: List[str] = []
    for row in rows:
        if not row.strip():
            continue
        if name in {"aligned", "alignedat", "split"}:
            converted_lines.append(_convert_aligned_row(row))
        else:
            converted_lines.append(latex_math_to_typst(row.strip()))
    return r" \ ".join(converted_lines)


def _split_multiletter_segment(segment: str) -> str:
    """Split adjacent single-letter variables such as dx or Oxyz into d x / O x y z."""

    def _replace_tok(match: re.Match[str]) -> str:
        tok = match.group(0)
        if tok.startswith('"') or tok in _TYPST_DOT_SYMBOLS or tok in _TYPST_MATH_IDENTIFIERS:
            return tok
        return " ".join(tok)

    return _SPLIT_TOKEN_RE.sub(_replace_tok, segment)


def _finalize_math_segment(segment: str) -> str:
    """Convert LaTeX control words, attach scripts, and separate adjacent variables."""

    def _replace_cmd(match: re.Match[str]) -> str:
        cmd = match.group(1)
        if cmd in _MODIFIER_CMDS:
            return " "
        if cmd in _BINARY_SYMBOLS:
            return f" {_BINARY_SYMBOLS[cmd]} "
        if cmd in _PREFIX_SYMBOLS:
            return f" {_PREFIX_SYMBOLS[cmd]} "
        # Fallback: quote unrecognized TeX control words so Typst never parses '\cmd' as '\c' + 'md'.
        return f'"{cmd}"'

    # Strip spacing punctuation commands, convert escaped math literals, and convert '\\' line breaks.
    segment = re.sub(r"\\[,;:!]", " ", segment)
    segment = segment.replace(r"\|", " bar.v.double ")
    segment = segment.replace(r"\&", '"&"')
    segment = segment.replace(r"\%", "%")
    segment = segment.replace(r"\_", '"_"')
    segment = _ROW_SPLIT_RE.sub(r" \\ ", segment)

    segment = _CONTROL_WORD_RE.sub(_replace_cmd, segment)
    segment = re.sub(r"[ \t]+", " ", segment)
    segment = re.sub(r"(?<=[A-Za-z0-9)\]|\"'])[ \t]+(?=[_^])", "", segment)
    segment = re.sub(r"([_^])[ \t]+", r"\1", segment)
    return _split_multiletter_segment(segment)


def latex_math_to_typst(math_str: str) -> str:
    """
    Convert LaTeX math syntax into Typst math syntax.

    Transformations:
    - \\frac{A}{B}, \\dfrac{A}{B}, \\tfrac{A}{B} -> ((A)/(B)); \\binom{n}{k} -> binom(n, k)
    - \\sqrt{A} -> sqrt(A); \\sqrt[n]{A} -> root(n, A)
    - \\text{A} and text-style wrappers -> "A"
    - \\mathbb, \\mathbf, \\overline, \\vec, \\hat, \\bar, etc. -> Typst style/accent calls
    - \\begin{cases}/matrices/aligned environments -> Typst cases(...)/mat(...)/linebreaks
    - \\left, \\right delimiters -> standard brackets
    - Standard LaTeX symbols, big operators, arrows, relations, Greek letters, functions -> Typst
    - Adjacent multi-letter LaTeX identifiers (e.g., dx, Oxyz) -> space-separated variables (d x, O x y z)
    - Grouped superscripts / subscripts: ^{...} -> ^(...), _{...} -> _(...)
    - Security: neutralizes '#' and control triggers in math mode to prevent Typst code injection
    """
    if not math_str or not math_str.strip():
        return ""

    s = math_str.strip()

    # 0. Security neutralization of '#' and code triggers in math mode (F03, F06)
    # In Typst math mode, the hash symbol is represented by the symbol identifier 'hash'.
    # We neutralize '\#' and '#' to ' hash ', ensuring no literal '#' ever enters math mode.
    # Strip method calls (\.[a-zA-Z_]\w*\s*\() without corrupting decimal numbers (e.g. 0.5(x+1)),
    # and strip code keywords (panic, eval, assert).
    s = re.sub(r"\\#", " hash ", s)
    s = re.sub(r"#", " hash ", s)
    s = re.sub(r"\.[a-zA-Z_]\w*\s*\(", " ", s)
    s = re.sub(r"\b(?:panic|eval|assert)\b", " ", s)

    # 1. Convert innermost LaTeX math environments (cases, matrices, aligned, etc.)
    while _ENV_RE.search(s):
        m = _ENV_RE.search(s)
        if not m:
            break
        s = s[: m.start()] + _convert_env(m.group(1), m.group(2)) + s[m.end() :]

    # 2. Convert \text{...} / \textrm{...} / \textbf{...} / \textsf{...} / \operatorname{...} -> "..."
    while _TEXT_WRAPPER_RE.search(s):
        m = _TEXT_WRAPPER_RE.search(s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        escaped_inner = re.sub(r'(?<!\\)"', r'\"', inner)
        s = s[: m.start()] + f'"{escaped_inner}"' + s[end_idx:]

    # 3. Convert two-argument fraction and binomial commands.
    while _TWO_ARG_CMD_RE.search(s):
        m = _TWO_ARG_CMD_RE.search(s)
        if not m:
            break
        num, idx2 = _extract_balanced_braces(s, m.end() - 1)
        while idx2 < len(s) and s[idx2].isspace():
            idx2 += 1
        if idx2 < len(s) and s[idx2] == "{":
            den, end_idx = _extract_balanced_braces(s, idx2)
            conv_num = latex_math_to_typst(num)
            conv_den = latex_math_to_typst(den)
            converted = (
                f"binom({conv_num}, {conv_den})"
                if m.group(1).endswith("binom")
                else f"(({conv_num})/({conv_den}))"
            )
            s = s[: m.start()] + converted + s[end_idx:]
        else:
            break

    # 4. Convert \sqrt[n]{A} -> root(n, A) and \sqrt{A} -> sqrt(A)
    while _SQRT_N_RE.search(s):
        m = _SQRT_N_RE.search(s)
        if not m:
            break
        deg = latex_math_to_typst(m.group(1).strip())
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = latex_math_to_typst(inner)
        s = s[: m.start()] + f"root({deg}, {conv_inner})" + s[end_idx:]

    while _SQRT_RE.search(s):
        m = _SQRT_RE.search(s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = latex_math_to_typst(inner)
        s = s[: m.start()] + f"sqrt({conv_inner})" + s[end_idx:]

    # 5. Convert braced and single-token style/accent commands (\mathbb, \overline, \vec, \hat, \bar, ...)
    while _SINGLE_ARG_WRAPPER_RE.search(s):
        m = _SINGLE_ARG_WRAPPER_RE.search(s)
        if not m:
            break
        typst_fn = _SINGLE_ARG_WRAPPERS[m.group(1)]
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = latex_math_to_typst(inner)
        s = s[: m.start()] + f"{typst_fn}({conv_inner})" + s[end_idx:]

    s = _transform_outside_quotes(
        s,
        lambda seg: _UNBRACED_WRAPPER_RE.sub(
            lambda m: f"{_SINGLE_ARG_WRAPPERS[m.group(1)]}({m.group(2)})",
            seg,
        ),
    )

    # 6. Remove \left and \right modifiers (including empty delimiters \left. / \right.)
    s = _transform_outside_quotes(
        s,
        lambda seg: re.sub(r"\\(?:left|right)(?![a-zA-Z])\s*(?:\.(?!\d))?", "", seg),
    )

    # 7. Grouped superscripts and subscripts: ^{abc} -> ^(abc), _{abc} -> _(abc)
    while re.search(r"\^\{", s):
        m = re.search(r"\^\{", s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = s[: m.start()] + f"^({latex_math_to_typst(inner)})" + s[end_idx:]

    while re.search(r"_\{", s):
        m = re.search(r"_\{", s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = s[: m.start()] + f"_({latex_math_to_typst(inner)})" + s[end_idx:]

    # 8. Symbols, Greek letters, functions, script attachment, and adjacent variable splitting
    s = _transform_outside_quotes(s, _finalize_math_segment)

    return s.strip()


def escape_typst_text(text: str) -> str:
    """
    Escape special Typst markup characters (#, @, $, \\) in plain text blocks (F03).
    Escapes backslash first so pre-existing backslashes cannot unescape subsequent escapes.
    """
    if not text:
        return ""
    # 1. Escape backslash first
    escaped = text.replace("\\", "\\\\")
    # 2. Escape # and @ so they are not parsed as function calls or citations
    escaped = escaped.replace("#", r"\#").replace("@", r"\@")
    # 3. Escape stray dollar signs that are not math delimiters
    escaped = escaped.replace("$", r"\$")
    return escaped


def convert_markdown_to_typst(content: str) -> str:
    """
    Convert a mixed Markdown/LaTeX string into valid Typst markup.
    Preserves math delimiters while converting math contents to Typst syntax,
    and converts Markdown bold/italic formatting.
    """
    if not content:
        return ""

    # Split content into math and non-math segments using regex
    # Matches:
    # 1. Display math: $$...$$ or \[...\]
    # 2. Inline math: $...$ or \(...\)
    math_pattern = re.compile(
        r"(\$\$.*?\$\$|\\\[.*?\\\]|\$.*?\$|\\\(.*?\\\))",
        re.DOTALL,
    )

    parts = math_pattern.split(content)
    result: List[str] = []

    for part in parts:
        if not part:
            continue

        # Check if part is math
        if part.startswith("$$") and part.endswith("$$") and len(part) >= 4:
            inner_math = part[2:-2]
            conv_math = latex_math_to_typst(inner_math)
            result.append(f" $ {conv_math.strip()} $ ")
        elif part.startswith(r"\[") and part.endswith(r"\]") and len(part) >= 4:
            inner_math = part[2:-2]
            conv_math = latex_math_to_typst(inner_math)
            result.append(f" $ {conv_math.strip()} $ ")
        elif part.startswith(r"\(") and part.endswith(r"\)") and len(part) >= 4:
            inner_math = part[2:-2]
            conv_math = latex_math_to_typst(inner_math)
            result.append(f"${conv_math.strip()}$")
        elif part.startswith("$") and part.endswith("$") and len(part) >= 2:
            inner_math = part[1:-1]
            conv_math = latex_math_to_typst(inner_math)
            result.append(f"${conv_math.strip()}$")
        else:
            # Plain text segment:
            text = escape_typst_text(part)
            # Preserve paired Markdown emphasis, but escape a lone multiplication
            # star so prose such as "3190 * (32 / 55)" cannot open Typst emphasis.
            text = re.sub(
                r"\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|\*",
                lambda match: (
                    f"*{match.group(1)}*" if match.group(1) is not None
                    else f"_{match.group(2)}_" if match.group(2) is not None
                    else r"\*"
                ),
                text,
            )
            result.append(text)

    return "".join(result)
