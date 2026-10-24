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

# Pattern for answer key pairs: 1.A, 1-A, 1: A, Câu 1: A, Câu 1. A, 1. [A]
KEY_PAIR_PATTERN = re.compile(
    r"(?:câu\s+)?(?P<num>\d+)\s*(?:[\.:\-\)]|\s+)\s*\[?(?P<key>[A-D])\]?(?![a-zA-Z0-9])",
    re.IGNORECASE,
)


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

    Returns:
        (answer_map, text_without_answer_section)
        where answer_map is {question_no: 'A'|'B'|'C'|'D'}
    """
    answer_map: Dict[int, str] = {}
    remaining_text = full_text

    # Search for answer section heading
    split_pos = -1
    for pat in ANSWER_SECTION_PATTERNS:
        matches = list(pat.finditer(full_text))
        if matches:
            # Usually the answer table is towards the end of the exam
            last_match = matches[-1]
            # Ensure it's not at the very top (e.g. at least after some content)
            if last_match.start() > 50 or len(matches) == 1:
                split_pos = last_match.start()
                break

    if split_pos != -1:
        answer_text = full_text[split_pos:]
        remaining_text = full_text[:split_pos].rstrip()
        # Scan for key pairs in answer_text
        for m in KEY_PAIR_PATTERN.finditer(answer_text):
            q_num = int(m.group("num"))
            key = m.group("key").upper()
            answer_map[q_num] = key

    # Also scan for trailing compact key format like "1.A 2.B 3.C 4.D" even without explicit header
    if not answer_map:
        # Check last 500 characters
        trailing_chunk = full_text[-500:] if len(full_text) > 500 else full_text
        pairs = list(KEY_PAIR_PATTERN.finditer(trailing_chunk))
        # If there are at least 3 consecutive pairs in the tail, treat as answer key
        if len(pairs) >= 3:
            first_pair = pairs[0]
            cutoff = (len(full_text) - len(trailing_chunk)) + first_pair.start()
            for p in pairs:
                q_num = int(p.group("num"))
                key = p.group("key").upper()
                answer_map[q_num] = key
            remaining_text = full_text[:cutoff].rstrip()

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

    # Regex to split on option prefixes A., B., C., D. or A), B), C), D)
    opt_pattern = re.compile(
        r"(?:\n|\s{2,}|\b)(?P<opt>[A-D])\s*[\.\)]\s*(?P<content>.*?)(?=(?:\n|\s{2,}|\b)[A-D]\s*[\.\)]|$)",
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
            # Clean up trailing asterisks or underscores from markdown
            content = re.sub(r"^[\*\_]+|[\*\_]+$", "", content).strip()
            found_opts[label] = content

        if all(k in found_opts for k in ["A", "B", "C", "D"]):
            stem = text[:first_opt_pos].strip()

    return stem, found_opts, detected_key
