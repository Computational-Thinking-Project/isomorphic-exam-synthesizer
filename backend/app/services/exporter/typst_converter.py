"""
Typst Content Converter (TASK-306).

Converts Markdown and LaTeX mathematical notation into clean, idiomatic
Typst markup syntax ($...$).
"""

import re
from typing import List, Tuple


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


def latex_math_to_typst(math_str: str) -> str:
    """
    Convert LaTeX math syntax into Typst math syntax.

    Transformations:
    - \\frac{A}{B}, \\dfrac{A}{B} -> ((A)/(B))
    - \\sqrt{A} -> sqrt(A)
    - \\sqrt[n]{A} -> root(n, A)
    - \\text{A} -> "A"
    - \\left, \\right delimiters -> standard brackets
    - Common LaTeX symbols, arrows, relations, and Greek letters -> Typst equivalents
    - Grouped superscripts / subscripts: ^{...} -> ^(...), _{...} -> _(...)
    - Security: neutralizes '#' in math mode to prevent Typst code injection
    """
    s = math_str.strip()

    # 0. Security neutralization of '#' in math mode (F03)
    # Typst enters code mode on '#'. LaTeX math does not execute code; verbatim string quotes prevent execution.
    s = s.replace(r"\#", '"#"').replace("#", '"#"')

    # 1. Convert \\text{...} -> "..."
    while re.search(r"\\text\s*\{", s):
        m = re.search(r"\\text\s*\{", s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        s = s[: m.start()] + f'"{inner}"' + s[end_idx:]

    # 2. Convert \\frac{A}{B} or \\dfrac{A}{B} -> ((A)/(B))
    while re.search(r"\\(?:d)?frac\s*\{", s):
        m = re.search(r"\\(?:d)?frac\s*\{", s)
        if not m:
            break
        num, idx2 = _extract_balanced_braces(s, m.end() - 1)
        while idx2 < len(s) and s[idx2].isspace():
            idx2 += 1
        if idx2 < len(s) and s[idx2] == "{":
            den, end_idx = _extract_balanced_braces(s, idx2)
            conv_num = latex_math_to_typst(num)
            conv_den = latex_math_to_typst(den)
            s = s[: m.start()] + f"(({conv_num})/({conv_den}))" + s[end_idx:]
        else:
            break

    # 3. Convert \\sqrt[n]{A} -> root(n, A) and \\sqrt{A} -> sqrt(A)
    while re.search(r"\\sqrt\s*\[", s):
        m = re.search(r"\\sqrt\s*\[([^\[\]]+)\]\s*\{", s)
        if not m:
            break
        deg = m.group(1).strip()
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = latex_math_to_typst(inner)
        s = s[: m.start()] + f"root({deg}, {conv_inner})" + s[end_idx:]

    while re.search(r"\\sqrt\s*\{", s):
        m = re.search(r"\\sqrt\s*\{", s)
        if not m:
            break
        inner, end_idx = _extract_balanced_braces(s, m.end() - 1)
        conv_inner = latex_math_to_typst(inner)
        s = s[: m.start()] + f"sqrt({conv_inner})" + s[end_idx:]

    # 4. Remove \\left and \\right modifiers
    s = re.sub(r"\\left\s*", "", s)
    s = re.sub(r"\\right\s*", "", s)

    # 5. Grouped superscripts and subscripts: ^{abc} -> ^(abc), _{abc} -> _(abc)
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

    # 6. Standard math symbols & relations (F02: match LaTeX control word boundary (?![a-zA-Z]) and enforce whitespace separation)
    replacements = [
        (r"\s*\\notin(?![a-zA-Z])\s*", " not in "),
        (r"\s*\\in(?![a-zA-Z])\s*", " in "),
        (r"\s*\\leq(?![a-zA-Z])\s*", " <= "),
        (r"\s*\\le(?![a-zA-Z])\s*", " <= "),
        (r"\s*\\geq(?![a-zA-Z])\s*", " >= "),
        (r"\s*\\ge(?![a-zA-Z])\s*", " >= "),
        (r"\s*\\neq(?![a-zA-Z])\s*", " != "),
        (r"\s*\\ne(?![a-zA-Z])\s*", " != "),
        (r"\s*\\approx(?![a-zA-Z])\s*", " approx "),
        (r"\s*\\cdot(?![a-zA-Z])\s*", " dot "),
        (r"\s*\\times(?![a-zA-Z])\s*", " times "),
        (r"\s*\\pm(?![a-zA-Z])\s*", " plus.minus "),
        (r"\s*\\mp(?![a-zA-Z])\s*", " minus.plus "),
        (r"\s*\\infty(?![a-zA-Z])\s*", " infinity "),
        (r"\s*\\implies(?![a-zA-Z])\s*", " => "),
        (r"\s*\\Rightarrow(?![a-zA-Z])\s*", " => "),
        (r"\s*\\iff(?![a-zA-Z])\s*", " <=> "),
        (r"\s*\\Leftrightarrow(?![a-zA-Z])\s*", " <=> "),
        (r"\s*\\rightarrow(?![a-zA-Z])\s*", " -> "),
        (r"\s*\\to(?![a-zA-Z])\s*", " -> "),
        (r"\s*\\subset(?![a-zA-Z])\s*", " subset "),
        (r"\s*\\cup(?![a-zA-Z])\s*", " union "),
        (r"\s*\\cap(?![a-zA-Z])\s*", " sect "),
        (r"\s*\\emptyset(?![a-zA-Z])\s*", " emptyset "),
    ]

    for pat, rep in replacements:
        s = re.sub(pat, rep, s)

    # 7. Common Greek letters (with LaTeX word boundary (?![a-zA-Z]))
    greek = [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "Delta",
        "epsilon",
        "theta",
        "lambda",
        "Lambda",
        "pi",
        "Pi",
        "sigma",
        "Sigma",
        "omega",
        "Omega",
    ]
    for g in greek:
        s = re.sub(rf"\s*\\{g}(?![a-zA-Z])\s*", f" {g} ", s)

    # 8. Functions (with LaTeX word boundary (?![a-zA-Z]))
    functions = ["sin", "cos", "tan", "cot", "ln", "log", "lim", "exp", "min", "max"]
    for fn in functions:
        s = re.sub(rf"\s*\\{fn}(?![a-zA-Z])\s*", f" {fn} ", s)

    return s


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
            # Convert Markdown **bold** -> Typst *bold*
            text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)
            result.append(text)

    return "".join(result)
