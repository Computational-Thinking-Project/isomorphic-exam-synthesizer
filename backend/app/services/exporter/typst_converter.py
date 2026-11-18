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
_MATHRM_WRAPPER_RE = re.compile(r"\\mathrm(?![a-zA-Z])\s*\{")
_TWO_ARG_CMD_RE = re.compile(r"\\([dt]?frac|[dt]?binom)(?![a-zA-Z])\s*\{")
_SQRT_N_RE = re.compile(r"\\sqrt(?![a-zA-Z])\s*\[([^\[\]]+)\]\s*\{")
_SQRT_RE = re.compile(r"\\sqrt(?![a-zA-Z])\s*\{")
_SUPERSCRIPT_RE = re.compile(r"\^\{")
_SUBSCRIPT_RE = re.compile(r"_\{")

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

_PROTECTED_OPEN = "\ue000"
_PROTECTED_CLOSE = "\ue001"
_ESCAPE_SENTINEL = "\ue002"

_SPLIT_TOKEN_RE = re.compile(
    _QUOTED_STR_RE.pattern
    + rf"|{_PROTECTED_OPEN}[^{_PROTECTED_CLOSE}]*{_PROTECTED_CLOSE}"
    + r"|(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])"
)


def _protect(typst_token: str) -> str:
    """Wrap a converter-generated Typst token so raw identifier passes keep it intact."""
    return f"{_PROTECTED_OPEN}{typst_token}{_PROTECTED_CLOSE}"


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


def _search_outside_quotes(text: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    """Return the first match of pattern that starts outside double-quoted literals."""
    quoted_spans = [m.span() for m in _QUOTED_STR_RE.finditer(text)]
    for match in pattern.finditer(text):
        if not any(start <= match.start() < end for start, end in quoted_spans):
            return match
    return None


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


def _convert_aligned_row(row: str, *, quote_unknown: bool = False) -> str:
    """Convert one &-delimited row while preserving Typst column separators."""
    cols = [
        _latex_math_to_typst_impl(col.strip(), quote_unknown=quote_unknown)
        for col in _COL_SPLIT_RE.split(row)
    ]
    return " & ".join(cols)


def _convert_env(name: str, body: str, *, quote_unknown: bool = False) -> str:
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
        converted_rows = [
            _convert_aligned_row(row, quote_unknown=quote_unknown)
            for row in rows
            if row.strip()
        ]
        return f"{_protect('cases')}({', '.join(converted_rows)})"

    if name in _MATRIX_DELIMS:
        converted_rows = []
        for row in rows:
            if not row.strip():
                continue
            cells = [
                _latex_math_to_typst_impl(cell.strip(), quote_unknown=quote_unknown)
                for cell in _COL_SPLIT_RE.split(row)
            ]
            converted_rows.append(", ".join(cells))
        delim = _MATRIX_DELIMS[name]
        joined = "; ".join(converted_rows)
        if delim is None:
            return f"{_protect('mat')}({joined})"
        delim_arg = _protect("none") if delim == "none" else f'"{delim}"'
        return f"{_protect('mat')}({_protect('delim')}: {delim_arg}, {joined})"

    # aligned / alignedat / gathered / split
    converted_lines: List[str] = []
    for row in rows:
        if not row.strip():
            continue
        if name in {"aligned", "alignedat", "split"}:
            converted_lines.append(_convert_aligned_row(row, quote_unknown=quote_unknown))
        else:
            converted_lines.append(
                _latex_math_to_typst_impl(row.strip(), quote_unknown=quote_unknown)
            )
    return r" \ ".join(converted_lines)


def _split_multiletter_segment(segment: str, *, quote_unknown: bool = False) -> str:
    """Handle multi-letter tokens: split math variables or quote upright labels."""

    def _replace_tok(match: re.Match[str]) -> str:
        tok = match.group(0)
        if tok.startswith('"') or tok.startswith(_PROTECTED_OPEN):
            return tok
        return f'"{tok}"' if quote_unknown else " ".join(tok)

    return _SPLIT_TOKEN_RE.sub(_replace_tok, segment)


def _finalize_math_segment(segment: str, *, quote_unknown: bool = False) -> str:
    """Convert LaTeX control words, attach scripts, and process multi-letter tokens."""

    def _replace_cmd(match: re.Match[str]) -> str:
        cmd = match.group(1)
        if cmd in _MODIFIER_CMDS:
            return " "
        if cmd in _BINARY_SYMBOLS:
            return f" {_protect(_BINARY_SYMBOLS[cmd])} "
        if cmd in _PREFIX_SYMBOLS:
            return f" {_protect(_PREFIX_SYMBOLS[cmd])} "
        # Fallback: quote unrecognized TeX control words so Typst never parses '\cmd' as '\c' + 'md'.
        return f'"{cmd}"'

    # Strip spacing punctuation commands, convert escaped math literals, and convert '\\' line breaks.
    segment = re.sub(r"\\[,;:!]", " ", segment)
    segment = segment.replace(r"\|", f" {_protect('bar.v.double')} ")
    segment = segment.replace(r"\&", '"&"')
    segment = segment.replace(r"\%", "%")
    segment = segment.replace(r"\_", '"_"')
    segment = _ROW_SPLIT_RE.sub(r" \\ ", segment)

    segment = _CONTROL_WORD_RE.sub(_replace_cmd, segment)
    segment = re.sub(r"[ \t]+", " ", segment)
    segment = re.sub(rf"(?<=[A-Za-z0-9)\]|\"'{_PROTECTED_CLOSE}])[ \t]+(?=[_^])", "", segment)
    segment = re.sub(r"([_^])[ \t]+", r"\1", segment)
    return _split_multiletter_segment(segment, quote_unknown=quote_unknown)


def _convert_mathrm(inner: str) -> str:
    """Convert \\mathrm{...} while preserving unit labels and math operators (F82-03, F82-04)."""
    if not inner.strip():
        return f'{_protect("upright")}("")'
    converted_inner = _latex_math_to_typst_impl(inner, quote_unknown=True)
    return f"{_protect('upright')}({converted_inner})"


def latex_math_to_typst(math_str: str) -> str:
    """
    Convert LaTeX math syntax into Typst math syntax.

    Transformations:
    - \\frac{A}{B}, \\dfrac{A}{B}, \\tfrac{A}{B} -> ((A)/(B)); \\binom{n}{k} -> binom(n, k)
    - \\sqrt{A} -> sqrt(A); \\sqrt[n]{A} -> root(n, A)
    - \\text{A} and text-style wrappers -> "A"; \\mathrm{unit} -> upright("unit")
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
    has_pua = any(ch in math_str for ch in (_PROTECTED_OPEN, _PROTECTED_CLOSE, _ESCAPE_SENTINEL))
    escaped_input = (
        math_str.replace(_ESCAPE_SENTINEL, f"{_ESCAPE_SENTINEL}\ue003")
        .replace(_PROTECTED_OPEN, f"{_ESCAPE_SENTINEL}\ue004")
        .replace(_PROTECTED_CLOSE, f"{_ESCAPE_SENTINEL}\ue005")
        if has_pua
        else math_str
    )
    out = _latex_math_to_typst_impl(escaped_input, quote_unknown=False)
    out = out.replace(_PROTECTED_OPEN, "").replace(_PROTECTED_CLOSE, "")
    if has_pua:
        out = (
            out.replace(f"{_ESCAPE_SENTINEL}\ue005", _PROTECTED_CLOSE)
            .replace(f"{_ESCAPE_SENTINEL}\ue004", _PROTECTED_OPEN)
            .replace(f"{_ESCAPE_SENTINEL}\ue003", _ESCAPE_SENTINEL)
        )
    return out


def _latex_math_to_typst_impl(math_str: str, *, quote_unknown: bool = False) -> str:
    """Internal implementation parameterizing multi-letter identifier splitting vs quoting."""
    if not math_str or not math_str.strip():
        return ""

    s = math_str.strip()

    # 0. Security neutralization of '#' and code triggers in math mode (F03, F06)
    # In Typst math mode, the hash symbol is represented by the symbol identifier 'hash'.
    # We neutralize '\#' and '#' to ' hash ', ensuring no literal '#' ever enters math mode.
    # Strip method calls (\.[a-zA-Z_]\w*\s*\() without corrupting decimal numbers (e.g. 0.5(x+1)),
    # and strip code keywords (panic, eval, assert).
    hash_tok = f" {_protect('hash')} "
    s = re.sub(r"\\#", hash_tok, s)
    s = re.sub(r"#", hash_tok, s)
    s = re.sub(r"\.[a-zA-Z_]\w*\s*\(", " ", s)
    s = re.sub(r"\b(?:panic|eval|assert)\b", " ", s)

    # 1. Convert \text{...} / \textrm{...} / \textbf{...} / \textsf{...} / \operatorname{...} -> "..."
    while (m := _search_outside_quotes(s, _TEXT_WRAPPER_RE)) is not None:
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        escaped_inner = re.sub(r'(?<!\\)"', r'\"', inner)
        s = s[: m.start()] + f'"{escaped_inner}"' + s[end_idx:]

    # 2. Convert \mathrm{...} before structural passes so nested fractions/scripts keep label context (F82-04)
    while (m := _search_outside_quotes(s, _MATHRM_WRAPPER_RE)) is not None:
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = s[: m.start()] + _convert_mathrm(inner) + s[end_idx:]

    # 3. Convert innermost LaTeX math environments (cases, matrices, aligned, etc.)
    while (m := _search_outside_quotes(s, _ENV_RE)) is not None:
        s = (
            s[: m.start()]
            + _convert_env(m.group(1), m.group(2), quote_unknown=quote_unknown)
            + s[m.end() :]
        )

    # 4. Convert two-argument fraction and binomial commands.
    while (m := _search_outside_quotes(s, _TWO_ARG_CMD_RE)) is not None:
        num, idx2 = _extract_balanced_braces(s, m.end() - 1)
        while idx2 < len(s) and s[idx2].isspace():
            idx2 += 1
        if idx2 < len(s) and s[idx2] == "{":
            den, end_idx = _extract_balanced_braces(s, idx2)
            conv_num = _latex_math_to_typst_impl(num, quote_unknown=quote_unknown)
            conv_den = _latex_math_to_typst_impl(den, quote_unknown=quote_unknown)
            converted = (
                f"{_protect('binom')}({conv_num}, {conv_den})"
                if m.group(1).endswith("binom")
                else f"(({conv_num})/({conv_den}))"
            )
            s = s[: m.start()] + converted + s[end_idx:]
        else:
            break

    # 5. Convert \sqrt[n]{A} -> root(n, A) and \sqrt{A} -> sqrt(A)
    while (m := _search_outside_quotes(s, _SQRT_N_RE)) is not None:
        deg = _latex_math_to_typst_impl(m.group(1).strip(), quote_unknown=quote_unknown)
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = _latex_math_to_typst_impl(inner, quote_unknown=quote_unknown)
        s = s[: m.start()] + f"{_protect('root')}({deg}, {conv_inner})" + s[end_idx:]

    while (m := _search_outside_quotes(s, _SQRT_RE)) is not None:
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = _latex_math_to_typst_impl(inner, quote_unknown=quote_unknown)
        s = s[: m.start()] + f"{_protect('sqrt')}({conv_inner})" + s[end_idx:]

    # 6. Convert braced and single-token style/accent commands (\mathbb, \overline, \vec, \hat, \bar, ...)
    while (m := _search_outside_quotes(s, _SINGLE_ARG_WRAPPER_RE)) is not None:
        cmd = m.group(1)
        typst_fn = _protect(_SINGLE_ARG_WRAPPERS[cmd])
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = _latex_math_to_typst_impl(inner, quote_unknown=quote_unknown)
        s = s[: m.start()] + f"{typst_fn}({conv_inner})" + s[end_idx:]

    s = _transform_outside_quotes(
        s,
        lambda seg: _UNBRACED_WRAPPER_RE.sub(
            lambda m: f"{_protect(_SINGLE_ARG_WRAPPERS[m.group(1)])}({m.group(2)})",
            seg,
        ),
    )

    # 7. Remove \left and \right modifiers (including empty delimiters \left. / \right.)
    s = _transform_outside_quotes(
        s,
        lambda seg: re.sub(r"\\(?:left|right)(?![a-zA-Z])\s*(?:\.(?!\d))?", "", seg),
    )

    # 8. Grouped superscripts and subscripts: ^{abc} -> ^(abc), _{abc} -> _(abc)
    while (m := _search_outside_quotes(s, _SUPERSCRIPT_RE)) is not None:
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = (
            s[: m.start()]
            + f"^({_latex_math_to_typst_impl(inner, quote_unknown=quote_unknown)})"
            + s[end_idx:]
        )

    while (m := _search_outside_quotes(s, _SUBSCRIPT_RE)) is not None:
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = (
            s[: m.start()]
            + f"_({_latex_math_to_typst_impl(inner, quote_unknown=quote_unknown)})"
            + s[end_idx:]
        )

    # 9. Symbols, Greek letters, functions, script attachment, and adjacent variable splitting
    s = _transform_outside_quotes(
        s,
        lambda seg: _finalize_math_segment(seg, quote_unknown=quote_unknown),
    )

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
