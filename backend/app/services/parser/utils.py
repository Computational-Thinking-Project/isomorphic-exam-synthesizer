"""Parsing utilities, Unicode NFC normalization, separate answer key detection, and security checks (SEC-02)."""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

# Patterns for prompt injection detection (SEC-02)
SUSPICIOUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?prior\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+[a-z]+", re.IGNORECASE),
    re.compile(r"output\s+the\s+system\s+instructions", re.IGNORECASE),
    re.compile(r"bypass\s+(?:all\s+)?security", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
]

# Patterns for separate answer key section detection
ANSWER_SECTION_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:#{1,6}\s*|\*{1,2}|_{1,2})?(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key|answers)(?:\*{1,2}|_{1,2})?(?:\s*:|\s*\n)",
        re.IGNORECASE,
    ),
]

# Pattern for answer key pairs: 1.A, 1-A, 1: A, 1/A, 1) A, Câu 1: A, Câu 1. A, 1. [A], 1. (A)
KEY_PAIR_PATTERN = re.compile(
    r"(?:câu\s+(?P<num1>\d+)\s*(?:[\.:\-\)]|\s*)\s*[\(\[]?(?P<key1>[A-D])[\)\]]?|(?P<num2>\d+)\s*[\.:\-\)\/]\s*[\(\[]?(?P<key2>[A-D])[\)\]]?)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)


@dataclass
class RawAnswerKeyInfo:
    """Detailed metadata about detected separate answer key pairs and structural conflicts."""

    raw_pairs: List[Tuple[int, str]] = field(default_factory=list)
    duplicate_keys: List[int] = field(default_factory=list)
    conflicts: Dict[int, List[str]] = field(default_factory=dict)
    mapped_keys: Dict[int, str] = field(default_factory=dict)
    unmatched_keys: List[int] = field(default_factory=list)


class OptionExtractionResult(tuple):
    """3-tuple compatible return object for extract_options_from_text with error_type metadata."""

    def __new__(
        cls,
        stem: str,
        options: Dict[str, str],
        detected_key: Optional[str],
        error_type: Optional[str] = None,
    ):
        return super().__new__(cls, (stem, options, detected_key))

    def __init__(
        self,
        stem: str,
        options: Dict[str, str],
        detected_key: Optional[str],
        error_type: Optional[str] = None,
    ):
        self.stem = stem
        self.options = options
        self.detected_key = detected_key
        self.error_type = error_type


def extract_key_pair(match: re.Match) -> Tuple[int, str]:
    """Extract (question_number, key) from a KEY_PAIR_PATTERN regex match."""
    num_str = match.group("num1") if match.group("num1") is not None else match.group("num2")
    key_str = match.group("key1") if match.group("key1") is not None else match.group("key2")
    return int(num_str), key_str.upper()


def normalize_unicode_nfc(text: str) -> str:
    """Normalize string to Unicode NFC standard and clean up carriage returns."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    # Standardize line breaks to \n
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def check_prompt_injection(text: str) -> bool:
    """Check text for known prompt injection / control keywords (SEC-02).

    Returns True if any suspicious pattern is detected.
    """
    if not text:
        return False
    for pat in SUSPICIOUS_PATTERNS:
        if pat.search(text):
            return True
    return False


def parse_separate_answer_key(
    full_text: str,
    return_info: bool = False,
) -> Any:
    """Search for separate answer table or key list at the end of the document.

    Guarantees that question stems (e.g. 'Câu 1: A, B là...') are never falsely
    recognized as answer key tables. Detects duplicate and conflicting keys.

    Returns:
        If return_info=False: (answer_map, text_without_answer_section)
        If return_info=True: (answer_map, text_without_answer_section, key_info: RawAnswerKeyInfo)
    """
    raw_pairs: List[Tuple[int, str]] = []
    duplicate_keys: List[int] = []
    conflicts: Dict[int, List[str]] = {}
    mapped_keys: Dict[int, str] = {}
    remaining_text = full_text

    def _process_pairs(pairs: List[re.Match]) -> None:
        seen_map: Dict[int, str] = {}
        for p in pairs:
            q_num, key = extract_key_pair(p)
            raw_pairs.append((q_num, key))
            if q_num in seen_map:
                duplicate_keys.append(q_num)
                if seen_map[q_num] != key:
                    if q_num not in conflicts:
                        conflicts[q_num] = [seen_map[q_num]]
                    if key not in conflicts[q_num]:
                        conflicts[q_num].append(key)
            else:
                seen_map[q_num] = key

        # Mapped keys only include non-conflicting keys
        for q_num, key in seen_map.items():
            if q_num not in conflicts:
                mapped_keys[q_num] = key

    # 1. Search for answer section heading near the end
    section_heading_pattern = re.compile(
        r"(?:^|\n)\s*(?:#{1,6}\s*|\*{1,2}|_{1,2})?(?P<header>(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key|answers))(?:\*{1,2}|_{1,2})?\s*[:\n]",
        re.IGNORECASE,
    )

    matches = list(section_heading_pattern.finditer(full_text))
    if matches:
        # Check from last match backwards
        for m in reversed(matches):
            candidate_pos = m.start()
            candidate_text = full_text[candidate_pos:]
            candidate_pairs = list(KEY_PAIR_PATTERN.finditer(candidate_text))
            if candidate_pairs:
                _, found_opts, _ = extract_options_from_text(candidate_text)
                if len(found_opts) < 4:
                    _process_pairs(candidate_pairs)
                    remaining_text = full_text[:candidate_pos].rstrip()
                    key_info = RawAnswerKeyInfo(
                        raw_pairs=raw_pairs,
                        duplicate_keys=duplicate_keys,
                        conflicts=conflicts,
                        mapped_keys=mapped_keys,
                    )
                    if return_info:
                        return mapped_keys, remaining_text, key_info
                    return mapped_keys, remaining_text

    # 2. If no explicit section heading, inspect trailing block strictly from the end of the document
    lines = full_text.splitlines()
    trailing_key_line_indices: list[int] = []
    trailing_pairs = []

    idx = len(lines) - 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    while idx >= 0:
        line = lines[idx].strip()
        if not line:
            trailing_key_line_indices.append(idx)
            idx -= 1
            continue

        if re.search(r"^\s*[\-\*\_]*[A-D][\.\)]", line):
            break

        _, found_opts, _ = extract_options_from_text(line)
        if len(found_opts) >= 2:
            break

        line_pairs = list(KEY_PAIR_PATTERN.finditer(line))
        if not line_pairs:
            break

        residual = KEY_PAIR_PATTERN.sub("", line)
        if re.search(r"[a-zA-Zà-ỹÀ-Ỹ]{2,}", residual):
            break

        trailing_key_line_indices.append(idx)
        trailing_pairs.extend(line_pairs)
        idx -= 1

    if len(trailing_pairs) >= 2 and trailing_key_line_indices:
        first_key_line_idx = min(trailing_key_line_indices)
        _process_pairs(trailing_pairs)
        remaining_lines = lines[:first_key_line_idx]
        remaining_text = "\n".join(remaining_lines).rstrip()

    key_info = RawAnswerKeyInfo(
        raw_pairs=raw_pairs,
        duplicate_keys=duplicate_keys,
        conflicts=conflicts,
        mapped_keys=mapped_keys,
    )
    if return_info:
        return mapped_keys, remaining_text, key_info
    return mapped_keys, remaining_text


def mask_markdown_code_blocks(text: str) -> str:
    """Mask multi-line code fences (```...```) and inline code (`...`) with '~'
    preserving EXACT character length and newline positions.
    Guarantees that question headers, answer keys, or option labels inside
    code blocks are never misidentified as exam structure.
    """
    def _repl_fence(m: re.Match) -> str:
        s = m.group(0)
        lines = s.split("\n")
        masked_lines = [lines[0]]
        for line in lines[1:-1]:
            masked_lines.append("~" * len(line))
        if len(lines) > 1:
            masked_lines.append(lines[-1])
        return "\n".join(masked_lines)

    def _repl_inline(m: re.Match) -> str:
        s = m.group(0)
        if len(s) <= 2:
            return s
        return "`" + ("~" * (len(s) - 2)) + "`"

    # Multi-line code fence
    masked = re.sub(r"```[\s\S]*?```", _repl_fence, text)
    # Inline code (not spanning lines)
    masked = re.sub(r"`[^`\n]+`", _repl_inline, masked)
    return masked


def mask_math_blocks(text: str) -> str:
    """Mask mathematical blocks ($...$, $$...$$, \\(...\\)) and code blocks with equal-length '~'
    during option label scanning so math contents (e.g. P(A), f(B)) and code are never misidentified as options.
    """
    # First mask code blocks
    masked = mask_markdown_code_blocks(text)
    # Display math $$ ... $$
    masked = re.sub(r"\$\$.*?\$\$", lambda m: "~" * len(m.group(0)), masked, flags=re.DOTALL)
    # Inline math $ ... $ (does not span newlines, preserves offsets)
    masked = re.sub(r"(?<!\\)\$[^$\n]+(?<!\\)\$", lambda m: "~" * len(m.group(0)), masked)
    # Inline LaTeX math \( ... \)
    masked = re.sub(r"\\\(.*?\\\)", lambda m: "~" * len(m.group(0)), masked)
    return masked


class OptionMatch(NamedTuple):
    opt: str
    start: int
    end: int
    is_newline: bool
    has_bullet: bool
    fmt: str


def extract_options_from_text(text: str) -> OptionExtractionResult:
    """Extract options A, B, C, D from question body text with strict boundary and context awareness.

    Guarantees:
    - Linear complexity O(n) preventing CPU exhaustion (ReDoS/Combinatorial explosion).
    - Protects mathematical formulas such as P(A), P(B), f(A), coordinates A(x; y), and LaTeX delimiters
      from being misidentified as option labels.
    - Scoped marker detection: only identifies bold/asterisk markers directly attached to true option prefixes.
    - Fails safely with AMBIGUOUS_FORMAT error_type when option structure is unresolvable or conflicting.
    """
    masked = mask_math_blocks(text)

    # Strict option label prefix pattern:
    pattern = re.compile(
        r"(?P<raw>(?:^|[\n\r]|[ \t]+)"
        r"(?:(?P<bullet>[\-\*\+]|[\*\_]{1,2})\s*)?"
        r"(?<![a-zA-Z0-9_\\])"
        r"(?:"
        r"\((?P<p_opt>[A-D])\)(?P<p_del>[\.\:]?)"
        r"|\[(?P<b_opt>[A-D])\](?P<b_del>[\.\:]?)"
        r"|(?P<l_opt>[A-D])(?P<l_del>[\.\:\)])"
        r")"
        r"(?:\*{1,2}|_{1,2})?"
        r"(?=\s|$))",
        re.MULTILINE,
    )

    matches: list[OptionMatch] = []
    for m in pattern.finditer(masked):
        opt = m.group("p_opt") or m.group("b_opt") or m.group("l_opt")
        raw_slice = text[m.start():m.end()]
        is_newline = ("\n" in raw_slice or "\r" in raw_slice or m.start() == 0)
        has_bullet = bool(m.group("bullet"))
        fmt = "p" if m.group("p_opt") else ("b" if m.group("b_opt") else "l")
        matches.append(
            OptionMatch(
                opt=opt,
                start=m.start(),
                end=m.end(),
                is_newline=is_newline,
                has_bullet=has_bullet,
                fmt=fmt,
            )
        )

    if not matches:
        return OptionExtractionResult(text, {}, None)

    # Protection against hostile / pathological inputs with excessive candidate markers
    MAX_CANDIDATES = 120
    if len(matches) > MAX_CANDIDATES:
        return OptionExtractionResult(text, {}, None, error_type="AMBIGUOUS_FORMAT")

    # Linear scan state machine to find candidate quadruplets:
    # A quadruplet is an ordered sequence of 4 options A -> B -> C -> D
    candidate_quads: list[Tuple[OptionMatch, OptionMatch, OptionMatch, OptionMatch]] = []

    # Method 1: Global sequential pass
    current_chain: list[OptionMatch] = []
    for cand in matches:
        if cand.opt == "A":
            current_chain = [cand]
        elif cand.opt == "B":
            if len(current_chain) == 1 and current_chain[0].opt == "A":
                current_chain.append(cand)
            elif len(current_chain) > 1 and current_chain[1].opt == "B":
                current_chain = []
        elif cand.opt == "C":
            if len(current_chain) == 2 and current_chain[1].opt == "B":
                current_chain.append(cand)
            elif len(current_chain) > 2 and current_chain[2].opt == "C":
                current_chain = []
        elif cand.opt == "D":
            if len(current_chain) == 3 and current_chain[2].opt == "C":
                candidate_quads.append(
                    (current_chain[0], current_chain[1], current_chain[2], cand)
                )
                current_chain = []

    # Method 2: Format-scoped passes if Method 1 found nothing (e.g. mixed noise)
    if not candidate_quads:
        for target_fmt in ("l", "p", "b"):
            fmt_matches = [item for item in matches if item.fmt == target_fmt]
            c_chain: list[OptionMatch] = []
            for cand in fmt_matches:
                if cand.opt == "A":
                    c_chain = [cand]
                elif cand.opt == "B":
                    if len(c_chain) == 1 and c_chain[0].opt == "A":
                        c_chain.append(cand)
                    else:
                        c_chain = []
                elif cand.opt == "C":
                    if len(c_chain) == 2 and c_chain[1].opt == "B":
                        c_chain.append(cand)
                    else:
                        c_chain = []
                elif cand.opt == "D":
                    if len(c_chain) == 3 and c_chain[2].opt == "C":
                        candidate_quads.append((c_chain[0], c_chain[1], c_chain[2], cand))
                        c_chain = []

    if not candidate_quads:
        return OptionExtractionResult(text, {}, None)

    # Score candidate quadruplets
    scored_candidates: list[Tuple[float, Tuple[OptionMatch, OptionMatch, OptionMatch, OptionMatch]]] = []
    for quad in candidate_quads:
        a, b, c, d = quad
        span_a = text[a.end:b.start].strip()
        span_b = text[b.end:c.start].strip()
        span_c = text[c.end:d.start].strip()
        span_d = text[d.end:].strip()
        if not (span_a and span_b and span_c):
            continue

        score = 0.0
        if a.fmt == b.fmt == c.fmt == d.fmt:
            score += 20.0
        if a.is_newline == b.is_newline == c.is_newline == d.is_newline:
            score += 10.0
        if a.has_bullet == b.has_bullet == c.has_bullet == d.has_bullet:
            score += 5.0
        score += a.start * 0.001
        scored_candidates.append((score, quad))

    if not scored_candidates:
        return OptionExtractionResult(text, {}, None)

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_quad = scored_candidates[0]

    # Check for ambiguity: multiple top candidates with identical high scores but different spans
    if len(scored_candidates) > 1:
        second_score, second_quad = scored_candidates[1]
        if abs(best_score - second_score) < 0.0001 and best_quad != second_quad:
            return OptionExtractionResult(text, {}, None, error_type="AMBIGUOUS_FORMAT")

    a, b, c, d = best_quad
    stem = text[:a.start].strip()
    stem = re.sub(r"[\*\_]+$", "", stem).strip()

    quad_items = [a, b, c, d]
    opts: Dict[str, str] = {}
    marked_keys: list[str] = []

    for i in range(4):
        item = quad_items[i]
        next_start = quad_items[i + 1].start if i < 3 else len(text)
        content = text[item.end:next_start].strip()
        content = re.sub(r"^[\*\_]+|[\*\_]+$", "", content).strip()
        content = re.sub(r"[\(\[\s]+$", "", content).strip()
        opts[item.opt] = content

        # Scoped marker detection: check if label prefix is marked as correct with bold or asterisks
        raw_label = text[item.start:item.end]
        if re.search(r"[\*\_]{1,2}[A-D][\*\_]{0,2}[\.\:\)]|[\(\[][\*\_]{1,2}[A-D][\*\_]{0,2}[\)\]]", raw_label):
            marked_keys.append(item.opt)

    detected_key = marked_keys[0] if marked_keys else None
    return OptionExtractionResult(stem, opts, detected_key)

