"""Parsing utilities, Unicode NFC normalization, separate answer key detection, and security checks (SEC-02)."""

import re
import unicodedata
from typing import Dict, Optional, Tuple

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
        r"(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key|answers)(?:\s*:|\s*\n)",
        re.IGNORECASE,
    ),
]

# Pattern for answer key pairs: 1.A, 1-A, 1: A, 1/A, 1) A, Câu 1: A, Câu 1. A, 1. [A]
KEY_PAIR_PATTERN = re.compile(
    r"(?:câu\s+(?P<num1>\d+)\s*(?:[\.:\-\)]|\s*)\s*\[?(?P<key1>[A-D])\]?|(?P<num2>\d+)\s*[\.:\-\)\/]\s*\[?(?P<key2>[A-D])\]?)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)


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


def parse_separate_answer_key(full_text: str) -> Tuple[Dict[int, str], str]:
    """Search for separate answer table or key list at the end of the document.

    Guarantees that question stems (e.g. 'Câu 1: A, B là...') are never falsely
    recognized as answer key tables.

    Returns:
        (answer_map, text_without_answer_section)
        where answer_map is {question_no: 'A'|'B'|'C'|'D'}
    """
    answer_map: Dict[int, str] = {}
    remaining_text = full_text

    # 1. Search for answer section heading near the end
    section_heading_pattern = re.compile(
        r"(?:^|\n)\s*(?P<header>(?:bảng\s+đáp\s+án|đáp\s+án|hướng\s+dẫn\s+chấm|answer\s+key|answers))\s*[:\n]",
        re.IGNORECASE,
    )

    matches = list(section_heading_pattern.finditer(full_text))
    if matches:
        # Check from last match backwards
        for m in reversed(matches):
            candidate_pos = m.start()
            candidate_text = full_text[candidate_pos:]
            # Must contain valid key pairs
            candidate_pairs = list(KEY_PAIR_PATTERN.finditer(candidate_text))
            if candidate_pairs:
                # Ensure candidate_text does not contain questions with complete option sets
                # (which would indicate the heading was part of a question stem)
                _, found_opts, _ = extract_options_from_text(candidate_text)
                if len(found_opts) < 4:
                    for p in candidate_pairs:
                        q_num, key = extract_key_pair(p)
                        answer_map[q_num] = key
                    remaining_text = full_text[:candidate_pos].rstrip()
                    return answer_map, remaining_text

    # 2. If no explicit section heading, inspect trailing block strictly from the end of the document
    # Avoid scanning across question stems/options. Scan lines backwards from the tail.
    lines = full_text.splitlines()
    trailing_key_line_indices: list[int] = []
    trailing_pairs = []

    # Find the last non-empty line
    idx = len(lines) - 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    while idx >= 0:
        line = lines[idx].strip()
        if not line:
            trailing_key_line_indices.append(idx)
            idx -= 1
            continue

        # An answer key line never starts with option markers like 'A.', '*A.', '- A.'
        if re.search(r"^\s*[\-\*\_]*[A-D][\.\)]", line):
            break

        # If line contains question options, it is not an answer key line
        _, found_opts, _ = extract_options_from_text(line)
        if len(found_opts) >= 2:
            break

        # Each line in a compact trailing answer key block must contain key pairs
        line_pairs = list(KEY_PAIR_PATTERN.finditer(line))
        if not line_pairs:
            break

        # Check for non-answer words: strip out all matched key pairs and delimiters
        residual = KEY_PAIR_PATTERN.sub("", line)
        # If words with length >= 2 remain (e.g. 'là', 'các', 'cho', 'tìm'), this is question text, NOT an answer key line!
        if re.search(r"[a-zA-Zà-ỹÀ-Ỹ]{2,}", residual):
            break

        trailing_key_line_indices.append(idx)
        trailing_pairs.extend(line_pairs)
        idx -= 1

    # Only accept as an answer block if at least 2 distinct pairs were found strictly in the tail
    if len(trailing_pairs) >= 2 and trailing_key_line_indices:
        first_key_line_idx = min(trailing_key_line_indices)
        for p in trailing_pairs:
            q_num, key = extract_key_pair(p)
            answer_map[q_num] = key
        remaining_lines = lines[:first_key_line_idx]
        remaining_text = "\n".join(remaining_lines).rstrip()

    return answer_map, remaining_text


def extract_options_from_text(text: str) -> Tuple[str, Dict[str, str], Optional[str]]:
    """Extract options A, B, C, D from question body text if inline.

    Returns:
        (question_stem, options_dict, detected_inline_correct_key)
    """
    # Detect patterns like:
    # A. <text>  B. <text>  C. <text>  D. <text>
    # or separate lines:
    # A. ...
    # B. ...
    # C. ...
    # D. ...
    # Also catches bolded/underlined or asterisked correct answer like *A.* or **A.**

    detected_key: Optional[str] = None

    # Check if any option is marked as correct with asterisk or bold
    marker_match = re.search(r"[\*\_]+([A-D])[\*\_]*[\.\)]", text)
    if marker_match:
        detected_key = marker_match.group(1).upper()

    # Regex to split on option prefixes A., B., C., D., A), B), C), D), (A), [A] (with optional bullet markers like - or * or bold **)
    opt_pattern = re.compile(
        r"(?:\n|\s{2,}|\b)(?:(?:[\-\+]|[\*\_]{1,2})\s*)?\(?\[?(?P<opt>[A-D])[\)\]\.\:]\s*(?:\*{1,2}|_{1,2})?\s*(?P<content>.*?)(?=(?:\n|\s{2,}|\b)(?:(?:[\-\+]|[\*\_]{1,2})\s*)?\(?\[?[A-D][\)\]\.\:]|$)",
        re.DOTALL,
    )

    matches = list(opt_pattern.finditer(text))
    # We require finding all 4 options A, B, C, D in order
    found_opts: Dict[str, str] = {}
    stem = text

    if len(matches) >= 4:
        # Check if matched options contain A, B, C, D
        first_opt_pos = matches[0].start()
        for m in matches:
            label = m.group("opt").upper()
            content = m.group("content").strip()
            # Clean up trailing asterisks, underscores, or stray prefix characters
            content = re.sub(r"^[\*\_]+|[\*\_]+$", "", content).strip()
            found_opts[label] = content

        if all(k in found_opts for k in ["A", "B", "C", "D"]):
            stem = text[:first_opt_pos].strip()
            stem = re.sub(r"[\*\_]+$", "", stem).strip()

    return stem, found_opts, detected_key
