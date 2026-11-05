"""Escape prose separately from supported math; never evaluate input as a template."""

import html
import re
from importlib.resources import files

from jinja2 import Environment, StrictUndefined

from .bundle_models import ApprovedExportSnapshot, BundleBuildError, DisplayVersion

_ESCAPE = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
# Explicit supported math commands. Unknown TeX/macros fail before export.
_MATH_COMMANDS = set("""
frac dfrac tfrac sqrt pm mp times cdot div le leq ge geq ne neq approx equiv
in notin subset subseteq supset supseteq cup cap emptyset varnothing forall exists
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda
mu nu xi pi rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta
Lambda Xi Pi Sigma Upsilon Phi Psi Omega sin cos tan cot sec csc arcsin arccos
arctan sinh cosh tanh log ln exp lim min max sup inf det gcd mod bmod pmod
sum prod int iint iiint oint to infty partial nabla degree circ angle triangle
left right big Big bigg Bigg langle rangle lvert rvert lVert rVert vert Vert
overline underline vec hat widehat bar dot ddot tilde widetilde
mathbb mathbf mathrm mathit mathcal mathsf boldsymbol text textrm textbf
operatorname binom dbinom tbinom begin end quad qquad ldots cdots vdots ddots
underbrace overbrace limits nolimits displaystyle textstyle scriptscriptstyle
colon setminus perpendicular perp parallel cong sim propto implies iff Rightarrow
Leftarrow Leftrightarrow rightarrow leftarrow mapsto neg land lor lnot
""".split())
_ENVIRONMENTS = {"aligned", "alignedat", "gathered", "split", "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "cases"}
_ENV = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True,
                   block_start_string="((*", block_end_string="*))",
                   variable_start_string="(((", variable_end_string=")))")


def _math_segments(value: str) -> list[tuple[bool, str]]:
    segments: list[tuple[bool, str]] = []
    text_start = i = 0
    while i < len(value):
        if value.startswith(r"\$", i):
            i += 2
            continue
        opener = next((token for token in ("$$", r"\(", r"\[", "$") if value.startswith(token, i)), None)
        if opener is None:
            i += 1
            continue
        closer = {"$$": "$$", "$": "$", r"\(": r"\)", r"\[": r"\]"}[opener]
        end = i + len(opener)
        while True:
            end = value.find(closer, end)
            if end < 0:
                raise BundleBuildError("EXPORT_UNBALANCED_MATH")
            slashes = 0
            cursor = end - 1
            while cursor >= 0 and value[cursor] == "\\":
                slashes += 1
                cursor -= 1
            if slashes % 2 == 0:
                break
            end += len(closer)
        if i > text_start:
            segments.append((False, value[text_start:i]))
        segments.append((True, value[i:end + len(closer)]))
        i = text_start = end + len(closer)
    if text_start < len(value):
        segments.append((False, value[text_start:]))
    return segments


def _check_math(value: str) -> None:
    for command in re.findall(r"\\([A-Za-z]+)", value):
        if command not in _MATH_COMMANDS:
            raise BundleBuildError("EXPORT_UNSUPPORTED_MATH_COMMAND")
    if "^^" in value or re.search(r"(?<!\\)[%#]", value):
        raise BundleBuildError("EXPORT_UNSUPPORTED_MATH_COMMAND")
    for environment in re.findall(r"\\(?:begin|end)\s*\{([^}]+)\}", value):
        if environment not in _ENVIRONMENTS:
            raise BundleBuildError("EXPORT_UNSUPPORTED_MATH_ENVIRONMENT")


def latex_text(value: str) -> str:
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise BundleBuildError("EXPORT_CONTROL_CHARACTER")
    output = []
    for is_math, segment in _math_segments(value):
        if is_math:
            _check_math(segment)
            output.append(segment)
        else:
            segment = segment.replace(r"\$", "$")
            output.append("".join(_ESCAPE.get(char, char) for char in segment))
    return "".join(output)


def markdown_text(value: str) -> str:
    return "".join(segment if is_math else html.escape(segment, quote=False)
                   for is_math, segment in _math_segments(value))


def render_tex(snapshot: ApprovedExportSnapshot, version: DisplayVersion) -> str:
    template = files("app.services.exporter").joinpath("templates", "exam.tex").read_text(encoding="utf-8")
    return _ENV.from_string(template).render(
        title=latex_text(snapshot.title), code=latex_text(version.code),
        questions=[{
            "number": q.question_no, "content": latex_text(q.content),
            "options": [latex_text(option) for option in q.options],
            "correct_key": q.correct_key, "solution": latex_text(q.solution_md),
        } for q in version.questions],
    )


def render_markdown(snapshot: ApprovedExportSnapshot, version: DisplayVersion) -> str:
    lines = [f"# {markdown_text(snapshot.title)}", "", f"Mã đề: {version.code}", ""]
    for q in version.questions:
        lines.extend([f"## Câu {q.question_no}", "", markdown_text(q.content), ""])
        lines.extend(f"- **{key}.** {markdown_text(option)}" for key, option in zip("ABCD", q.options, strict=True))
        lines.append("")
    lines.extend(["# Đáp án và lời giải", ""])
    for q in version.questions:
        lines.extend([f"## Câu {q.question_no} — Đáp án {q.correct_key}", "", markdown_text(q.solution_md), ""])
    return "\n".join(lines)
