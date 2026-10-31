"""
Deterministic Fisher-Yates Shuffler Service (TASK-303).

Provides deterministic, reproducible exam question and option shuffling,
canonical data model invariance protection, and solution markdown
synchronization across isomorphic exam versions.

Core Capabilities:
1. Deterministic Seeding:
   - Generates reproducible pseudo-random seeds via SHA-256 hash of
     session_id and version identifiers.
   - Guaranteed identical permutations when called with identical seeds.
2. Canonical Invariant Protection:
   - Strictly reads from canonical_* fields (canonical_question_no,
     canonical_options, canonical_correct_key, canonical_solution_md).
   - Zero mutation of input data models or canonical fields.
3. Fisher-Yates Shuffle Algorithm:
   - Standard unbiased Durstenfeld-Fisher-Yates permutation algorithm.
   - Independent control over question shuffling and option shuffling.
4. Solution Markdown Synchronization:
   - Automatically synchronizes Vietnamese answer references in solution_md
     (e.g., 'Đáp án A:', 'Chọn A', 'Phương án đúng là A') to match
     the newly permuted display answer letter.
5. Answer Keys and Permutations Matrix:
   - Produces answer key records for public.answer_keys table.
   - Generates full permutation audit metadata for exam_versions.permutations.
"""

import copy
import hashlib
import random
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar, Union

from app.services.shuffler.schemas import (
    AnswerKeyRecord,
    CanonicalQuestionInput,
    FinalizeShuffleResponse,
    OrderingPreferences,
    ShuffledQuestionOutput,
    VersionMetadata,
    VersionShuffleResult,
)

T = TypeVar("T")


def generate_deterministic_seed(
    session_id: str,
    version_code_or_index: Union[str, int],
) -> Tuple[str, int]:
    """
    Generate a deterministic seed string and 64-bit integer seed from
    session_id and version identifier using SHA-256.
    """
    seed_payload = f"{session_id}_{version_code_or_index}".encode("utf-8")
    seed_hash = hashlib.sha256(seed_payload).hexdigest()
    # 64-bit unsigned integer from first 16 hex characters
    seed_int = int(seed_hash[:16], 16)
    return seed_hash, seed_int


def fisher_yates_shuffle(items: Sequence[T], rng: random.Random) -> List[T]:
    """
    Perform an unbiased, in-place Fisher-Yates (Durstenfeld) shuffle
    on a shallow copy of the input sequence.
    """
    arr = list(items)
    for i in range(len(arr) - 1, 0, -1):
        j = rng.randint(0, i)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def sync_solution_text(
    canonical_solution_md: Optional[str],
    canonical_key: str,
    display_key: str,
) -> str:
    """
    Synchronize answer references in explanation markdown when option order changes.
    Replaces canonical correct answer letter with display answer letter in
    Vietnamese selection contexts without affecting mathematical or geometric variables.

    Handled contexts:
    - 'Đáp án A:' -> 'Đáp án C:'
    - 'Đáp án: A' -> 'Đáp án: C'
    - 'Đáp án đúng là A' -> 'Đáp án đúng là C'
    - 'Chọn A' / 'Chọn đáp án A' / 'Chọn phương án A' -> 'Chọn C'
    - 'Phương án đúng là A' / 'Phương án: A'
    - Markdown & LaTeX formatting: '**A**', '\\textbf{A}', '[A]', '(A)'
    """
    if not canonical_solution_md:
        return ""
    if canonical_key.strip().upper() == display_key.strip().upper():
        return canonical_solution_md

    c_k = re.escape(canonical_key.strip().upper())
    d_k = display_key.strip().upper()

    # Operator exclusion: Ensure conclusion/keyword letter is not followed by math relations/operators
    # such as '=', '!=', '<', '>', '<=', '>=', '\le', '\ge', '\in', '\notin', '+', '-', '*', '/' (F01).
    op_exclusion = r"(?!\s*(?:[=!<>]|<=|>=|!=|==|\\le|\\ge|\\in|\\notin|[\+\-\*/\\~]))"

    # Pattern 1: Keywords like Đáp án / Phương án / Câu trả lời / Chọn
    # Prefix allows optional: đúng, cần chọn, là, colon, period, whitespace
    # Wrapper allows markdown, LaTeX \\textbf, brackets, parentheses
    pattern_keyword = re.compile(
        rf"(?i)(\b(?:đáp\s+án|phương\s+án|câu\s+trả\s+lời|chọn(?:\s+đáp\s+án|\s+phương\s+án)?)(?:\s+đúng|\s+cần\s+chọn)?(?:\s+là)?\s*[:\.]?\s*)([\*_\[\(]*(?:\\textbf\{{)?)({c_k})((?:\}})?[\*_\]\)]*)(?=[\s\.,;:\n\)]|$){op_exclusion}"
    )

    def _replace_keyword(match: re.Match[str]) -> str:
        prefix = match.group(1)
        open_wrap = match.group(2)
        close_wrap = match.group(4)
        return f"{prefix}{open_wrap}{d_k}{close_wrap}"

    synced = pattern_keyword.sub(_replace_keyword, canonical_solution_md)

    # Pattern 2: Conclusion sentences: Kết luận: A / Suy ra: A / Do đó: A / Vậy: A
    pattern_conclusion = re.compile(
        rf"(?i)(\b(?:kết\s+luận|suy\s+ra|do\s+đó|vậy)\s*[:]\s*)([\*_\[\(]*(?:\\textbf\{{)?)({c_k})((?:\}})?[\*_\]\)]*)(?=[\s\.,;:\n\)]|$){op_exclusion}"
    )
    synced = pattern_conclusion.sub(_replace_keyword, synced)

    return synced


def _normalize_question_input(
    raw: Union[CanonicalQuestionInput, Dict[str, Any]],
) -> CanonicalQuestionInput:
    """Normalize raw question dict or model into CanonicalQuestionInput."""
    if isinstance(raw, CanonicalQuestionInput):
        return raw.model_copy(deep=True)

    data = copy.deepcopy(raw)
    # Adapt legacy field names if canonical_* are missing
    if "canonical_options" not in data and "options" in data:
        data["canonical_options"] = data["options"]
    if "canonical_correct_key" not in data:
        raw_key = data.get("correct_key") or data.get("correct_answer")
        if not raw_key:
            raise ValueError("Missing canonical_correct_key in question input.")
        raw_key_str = str(raw_key).strip().upper()
        if raw_key_str not in ("A", "B", "C", "D"):
            raise ValueError(
                f"Invalid canonical_correct_key '{raw_key_str}'. Must be one of ['A', 'B', 'C', 'D']."
            )
        data["canonical_correct_key"] = raw_key_str
    if "canonical_question_no" not in data:
        data["canonical_question_no"] = data.get("question_no", 1)
    if "canonical_solution_md" not in data:
        data["canonical_solution_md"] = data.get("solution_md") or data.get("solution_steps") or ""

    return CanonicalQuestionInput(**data)


def shuffle_exam_version(
    session_id: str,
    version_index: int,
    questions: Sequence[Union[CanonicalQuestionInput, Dict[str, Any]]],
    preferences: Optional[Union[OrderingPreferences, Dict[str, Any]]] = None,
    version_code: Optional[str] = None,
    version_id: Optional[str] = None,
) -> VersionShuffleResult:
    """
    Shuffle a single exam version deterministically from canonical source questions.

    Args:
        session_id: UUID string of the parent exam session.
        version_index: 1-based version index (1..N).
        questions: Sequence of questions with canonical_* fields.
        preferences: Ordering preferences (shuffle_questions, shuffle_options).
        version_code: Exam version code (e.g. '101', '102'). If None, defaults to str(100 + version_index).
        version_id: UUID string of exam_version record if available.

    Returns:
        VersionShuffleResult containing shuffled questions, answer keys, and permutations matrix.
    """
    if preferences is None:
        prefs = OrderingPreferences()
    elif isinstance(preferences, OrderingPreferences):
        prefs = preferences
    else:
        prefs = OrderingPreferences(**preferences)

    v_code = version_code if version_code is not None else str(100 + version_index)
    seed_str, seed_int = generate_deterministic_seed(session_id, v_code)
    rng = random.Random(seed_int)

    # 1. Filter and normalize questions: Only shuffle current active questions
    normalized_questions: List[CanonicalQuestionInput] = [
        _normalize_question_input(q)
        for q in questions
        if getattr(q, "is_current", True)
        if (isinstance(q, dict) and q.get("is_current", True))
        or (isinstance(q, CanonicalQuestionInput) and q.is_current)
    ]

    if not normalized_questions:
        return VersionShuffleResult(
            version_id=version_id,
            version_code=v_code,
            shuffle_seed=seed_str,
            total_questions=0,
            questions=[],
            answer_keys=[],
            permutations={"question_order": [], "option_permutations": {}},
        )

    # 2. Question Shuffling (Fisher-Yates)
    if prefs.shuffle_questions:
        shuffled_q_inputs = fisher_yates_shuffle(normalized_questions, rng)
    else:
        # Preserve stable canonical order sorted by canonical_question_no
        shuffled_q_inputs = sorted(normalized_questions, key=lambda q: q.canonical_question_no)

    shuffled_questions: List[ShuffledQuestionOutput] = []
    answer_keys: List[AnswerKeyRecord] = []
    option_permutations: Dict[int, Dict[str, str]] = {}

    labels = ["A", "B", "C", "D"]

    # 3. Option Shuffling & Solution Sync
    for idx, q_in in enumerate(shuffled_q_inputs):
        display_no = idx + 1
        canonical_opts = list(q_in.canonical_options)
        canon_key = q_in.canonical_correct_key.strip().upper()

        # Determine index of canonical correct answer (0..3)
        if canon_key in labels:
            canon_idx = labels.index(canon_key)
        else:
            raise ValueError(
                f"Invalid canonical_correct_key '{canon_key}'. Must be one of {labels}."
            )

        if prefs.shuffle_options:
            # Permute indices [0, 1, 2, 3] with deterministic RNG
            opt_indices = fisher_yates_shuffle([0, 1, 2, 3], rng)
            display_opts = [canonical_opts[i] for i in opt_indices]

            # The new correct key is the position where canonical correct option went
            new_key_idx = opt_indices.index(canon_idx)
            display_key = labels[new_key_idx]

            # Mapping canonical letter -> display letter
            canonical_to_display: Dict[str, str] = {
                labels[orig_i]: labels[new_pos] for new_pos, orig_i in enumerate(opt_indices)
            }
        else:
            display_opts = list(canonical_opts)
            display_key = canon_key
            canonical_to_display = {lbl: lbl for lbl in labels}

        # Synchronize solution text
        synced_solution = sync_solution_text(
            q_in.canonical_solution_md,
            canonical_key=canon_key,
            display_key=display_key,
        )

        shuffled_q = ShuffledQuestionOutput(
            id=q_in.id,
            source_question_id=q_in.source_question_id,
            display_no=display_no,
            content=q_in.content,
            options=display_opts,
            display_correct_key=display_key,
            solution_md=synced_solution,
            canonical_question_no=q_in.canonical_question_no,
            canonical_options=canonical_opts,
            canonical_correct_key=q_in.canonical_correct_key,
            canonical_solution_md=q_in.canonical_solution_md,
            is_current=True,
            permutation_map=canonical_to_display,
        )
        shuffled_questions.append(shuffled_q)

        # Answer key record for public.answer_keys table
        ans_key = AnswerKeyRecord(
            version_id=version_id,
            display_no=display_no,
            display_correct_key=display_key,
            canonical_question_no=q_in.canonical_question_no,
        )
        answer_keys.append(ans_key)
        option_permutations[display_no] = canonical_to_display

    # Full permutations audit matrix for exam_versions.permutations (JSONB)
    permutations_matrix: Dict[str, Any] = {
        "question_order": [q.canonical_question_no for q in shuffled_questions],
        "display_to_canonical": {q.display_no: q.canonical_question_no for q in shuffled_questions},
        "canonical_to_display": {q.canonical_question_no: q.display_no for q in shuffled_questions},
        "option_permutations": option_permutations,
    }

    return VersionShuffleResult(
        version_id=version_id,
        version_code=v_code,
        shuffle_seed=seed_str,
        total_questions=len(shuffled_questions),
        questions=shuffled_questions,
        answer_keys=answer_keys,
        permutations=permutations_matrix,
    )


def shuffle_session_versions(
    session_id: str,
    questions: Sequence[Union[CanonicalQuestionInput, Dict[str, Any]]],
    n_versions: int = 4,
    preferences: Optional[Union[OrderingPreferences, Dict[str, Any]]] = None,
    version_ids: Optional[List[str]] = None,
    version_codes: Optional[List[str]] = None,
) -> Tuple[List[VersionShuffleResult], FinalizeShuffleResponse]:
    """
    Shuffle all N exam versions for a session, guaranteeing deterministic permutations
    and constructing the response payload matching w3.md#L316 contract.

    Args:
        session_id: Exam session UUID string.
        questions: Canonical question inputs.
        n_versions: Number of exam versions (typically 4).
        preferences: Ordering preferences.
        version_ids: Optional list of version UUIDs.
        version_codes: Optional list of version codes (e.g. ['101', '102', '103', '104']).

    Returns:
        Tuple of (list of VersionShuffleResult, FinalizeShuffleResponse).
    """
    results: List[VersionShuffleResult] = []
    metadata_list: List[VersionMetadata] = []

    for v_idx in range(1, n_versions + 1):
        v_id = (
            version_ids[v_idx - 1]
            if version_ids and len(version_ids) >= v_idx
            else f"version-{session_id}-{v_idx}"
        )
        v_code = (
            version_codes[v_idx - 1]
            if version_codes and len(version_codes) >= v_idx
            else str(100 + v_idx)
        )

        res = shuffle_exam_version(
            session_id=session_id,
            version_index=v_idx,
            questions=questions,
            preferences=preferences,
            version_code=v_code,
            version_id=v_id,
        )
        results.append(res)
        metadata_list.append(
            VersionMetadata(
                version_id=v_id,
                version_code=v_code,
                total_questions=res.total_questions,
            )
        )

    response = FinalizeShuffleResponse(
        session_id=session_id,
        status="reviewed",
        is_finalized=True,
        versions=metadata_list,
    )

    return results, response
