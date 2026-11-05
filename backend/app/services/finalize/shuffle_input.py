"""Validate an immutable shuffle snapshot and calculate per-version results.

This module does not write to the database. The eventual RPC must independently
validate the snapshot and results under the session row lock before persisting.
"""

from uuid import UUID

from app.models.schemas import ReviewDomainException
from app.services.shuffler.schemas import CanonicalQuestionInput, OrderingPreferences
from app.services.shuffler.service import (
    generate_deterministic_seed,
    shuffle_exam_version,
    sync_solution_text,
)


def _invalid():
    return ReviewDomainException(
        409, "ERR_SHUFFLE_INPUT_INCOMPLETE", "Dữ liệu hoán vị không hợp lệ"
    )


def _uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise _invalid() from exc


def prepare_shuffle(session_id, config, versions, sources, questions):
    """Return deterministic shuffler results for one complete N x M snapshot."""
    session_id = _uuid(session_id)
    try:
        if not isinstance(config, dict) or type(config.get("n_versions")) is not int:
            raise _invalid()
        n = config["n_versions"]
        prefs_data = config.get("ordering_preferences")
        if not isinstance(prefs_data, dict) or any(
            type(v) is not bool for v in prefs_data.values()
        ):
            raise _invalid()
        prefs = OrderingPreferences.model_validate(prefs_data)
        if not 1 <= n <= 4 or len(versions) != n or not sources:
            raise _invalid()
        source_numbers = {_uuid(row["id"]): row["question_no"] for row in sources}
        numbers = list(source_numbers.values())
        if (
            len(source_numbers) != len(sources)
            or any(type(x) is not int or x < 1 for x in numbers)
            or len(set(numbers)) != len(numbers)
        ):
            raise _invalid()
        version_ids = [_uuid(row["id"]) for row in versions]
        codes = [row["version_code"] for row in versions]
        if (
            len(set(version_ids)) != n
            or any(not isinstance(c, str) or not c for c in codes)
            or len(set(codes)) != n
        ):
            raise _invalid()
        expected = {(vid, sid) for vid in version_ids for sid in source_numbers}
        current = {}
        ids = set()
        for row in questions:
            if row.get("is_current") is not True:
                continue
            vid, sid, qid = (
                _uuid(row["version_id"]),
                _uuid(row["source_question_id"]),
                _uuid(row["id"]),
            )
            pair = (vid, sid)
            options = row.get("canonical_options")
            if (
                pair not in expected
                or pair in current
                or qid in ids
                or row.get("status") != "approved"
                or row.get("canonical_question_no") != source_numbers[sid]
                or type(row.get("canonical_question_no")) is not int
                or not isinstance(options, list)
                or len(options) != 4
                or any(not isinstance(option, str) for option in options)
                or row.get("canonical_correct_key") not in ("A", "B", "C", "D")
                or not isinstance(row.get("content"), str)
                or (
                    row.get("canonical_solution_md") is not None
                    and not isinstance(row["canonical_solution_md"], str)
                )
            ):
                raise _invalid()
            ids.add(qid)
            current[pair] = CanonicalQuestionInput.model_validate(row)
        if set(current) != expected:
            raise _invalid()
        ordered = sorted(versions, key=lambda v: (v["version_code"], v["id"]))
        results = []
        for index, version in enumerate(ordered, 1):
            vid = _uuid(version["id"])
            inputs = sorted(
                (current[(vid, sid)] for sid in source_numbers),
                key=lambda q: (q.canonical_question_no, q.source_question_id),
            )
            result = shuffle_exam_version(
                session_id,
                index,
                inputs,
                prefs,
                version_code=version["version_code"],
                version_id=vid,
            )
            expected_seed, _ = generate_deterministic_seed(session_id, version["version_code"])
            if (
                result.version_id != vid
                or result.version_code != version["version_code"]
                or result.total_questions != len(sources)
                or result.shuffle_seed != expected_seed
            ):
                raise _invalid()
            if (
                len(result.questions) != len(sources)
                or len(result.answer_keys) != len(sources)
                or {q.display_no for q in result.questions} != set(range(1, len(sources) + 1))
            ):
                raise _invalid()
            labels = "ABCD"
            for q, key in zip(result.questions, result.answer_keys):
                original = current.get((vid, q.source_question_id))
                mapping = q.permutation_map
                if (
                    original is None
                    or q.id != original.id
                    or set(mapping) != set(labels)
                    or set(mapping.values()) != set(labels)
                    or q.canonical_question_no != original.canonical_question_no
                    or q.canonical_options != original.canonical_options
                    or q.canonical_correct_key != original.canonical_correct_key
                    or q.canonical_solution_md != original.canonical_solution_md
                    or q.content != original.content
                    or q.display_correct_key != mapping[original.canonical_correct_key]
                    or any(
                        q.options[labels.index(mapping[label])] != original.canonical_options[i]
                        for i, label in enumerate(labels)
                    )
                    or q.solution_md
                    != sync_solution_text(
                        original.canonical_solution_md,
                        canonical_key=original.canonical_correct_key,
                        display_key=q.display_correct_key,
                    )
                    or key.version_id != vid
                    or key.display_no != q.display_no
                    or key.display_correct_key != q.display_correct_key
                    or key.canonical_question_no != q.canonical_question_no
                ):
                    raise _invalid()
            if len({q.id for q in result.questions}) != len(sources):
                raise _invalid()
            if not prefs.shuffle_questions and [
                q.canonical_question_no for q in result.questions
            ] != sorted(numbers):
                raise _invalid()
            if not prefs.shuffle_options and any(
                q.permutation_map != {c: c for c in labels} for q in result.questions
            ):
                raise _invalid()
            expected_permutations = {
                "question_order": [q.canonical_question_no for q in result.questions],
                "display_to_canonical": {
                    q.display_no: q.canonical_question_no for q in result.questions
                },
                "canonical_to_display": {
                    q.canonical_question_no: q.display_no for q in result.questions
                },
                "option_permutations": {q.display_no: q.permutation_map for q in result.questions},
            }
            if result.permutations != expected_permutations:
                raise _invalid()
            results.append(result)
        return results
    except ReviewDomainException:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid() from exc
