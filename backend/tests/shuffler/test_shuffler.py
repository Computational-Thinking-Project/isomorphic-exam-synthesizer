"""
Unit Test Suite for Deterministic Fisher-Yates Shuffler (TASK-303).

Verifies:
1. Deterministic idempotence across runs.
2. Distinct permutations across different versions.
3. Canonical Data Model invariance (zero in-place mutation).
4. Option permutation and correct key tracking integrity.
5. Selective ordering preferences (shuffle_questions, shuffle_options).
6. Solution markdown synchronization for Vietnamese math explanations.
7. Answer key records generation for database persistence.
8. Session finalize response structure matching w3.md#L316 contract.
9. Edge cases (inactive questions, empty lists, legacy input formats).
"""

import copy
import random
from typing import List

import pytest

from app.services.shuffler.schemas import (
    AnswerKeyRecord,
    CanonicalQuestionInput,
    FinalizeShuffleResponse,
    OrderingPreferences,
    VersionShuffleResult,
)
from app.services.shuffler.service import (
    fisher_yates_shuffle,
    generate_deterministic_seed,
    shuffle_exam_version,
    shuffle_session_versions,
    sync_solution_text,
)


def _make_sample_questions() -> List[CanonicalQuestionInput]:
    """Create 5 sample canonical questions for testing."""
    return [
        CanonicalQuestionInput(
            id="q-uuid-1",
            source_question_id="src-1",
            question_no=1,
            content=r"Câu 1: Giá trị của biểu thức $\sqrt{16} + 1$ là:",
            canonical_question_no=1,
            canonical_options=["5", "4", "3", "2"],
            canonical_correct_key="A",
            canonical_solution_md="Ta có $\\sqrt{16} + 1 = 4 + 1 = 5$.\n\nĐáp án A: 5",
            is_current=True,
            status="approved",
        ),
        CanonicalQuestionInput(
            id="q-uuid-2",
            source_question_id="src-2",
            question_no=2,
            content=r"Câu 2: Nghiệm của phương trình $2x - 4 = 0$ là:",
            canonical_question_no=2,
            canonical_options=["x = 1", "x = 2", "x = 3", "x = 4"],
            canonical_correct_key="B",
            canonical_solution_md="Phương trình tương đương $2x = 4 \\implies x = 2$.\n\nDo đó ta chọn B.",
            is_current=True,
            status="approved",
        ),
        CanonicalQuestionInput(
            id="q-uuid-3",
            source_question_id="src-3",
            question_no=3,
            content=r"Câu 3: Đạo hàm của hàm số $y = x^2$ tại $x = 3$ là:",
            canonical_question_no=3,
            canonical_options=["9", "3", "6", "12"],
            canonical_correct_key="C",
            canonical_solution_md="Ta có $y' = 2x$. Tại $x = 3$, $y'(3) = 6$.\n\nVậy phương án đúng là C.",
            is_current=True,
            status="approved",
        ),
        CanonicalQuestionInput(
            id="q-uuid-4",
            source_question_id="src-4",
            question_no=4,
            content=r"Câu 4: Cho tam giác ABC vuông tại A có AB = 3, AC = 4. Độ dài cạnh BC là:",
            canonical_question_no=4,
            canonical_options=["7", "6", "1", "5"],
            canonical_correct_key="D",
            canonical_solution_md="Trong tam giác ABC, đỉnh A vuông nên $BC = \\sqrt{AB^2+AC^2} = 5$.\n\nChọn **D**.",
            is_current=True,
            status="approved",
        ),
        CanonicalQuestionInput(
            id="q-uuid-5",
            source_question_id="src-5",
            question_no=5,
            content=r"Câu 5: Tập nghiệm của bất phương trình $x - 1 > 0$ là:",
            canonical_question_no=5,
            canonical_options=[
                r"$(1; +\infty)$",
                r"$(-\infty; 1)$",
                r"$[1; +\infty)$",
                r"$(-\infty; 1]$",
            ],
            canonical_correct_key="A",
            canonical_solution_md="Bất phương trình tương đương $x > 1$.\n\nKết luận: \\textbf{A}",
            is_current=True,
            status="approved",
        ),
    ]


class TestFisherYatesShuffleAlgorithm:
    def test_shuffle_preserves_all_elements(self):
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        rng = random.Random(42)
        shuffled = fisher_yates_shuffle(items, rng)
        assert len(shuffled) == len(items)
        assert sorted(shuffled) == items

    def test_shuffle_is_deterministic_with_same_seed(self):
        items = ["A", "B", "C", "D", "E"]
        res1 = fisher_yates_shuffle(items, random.Random(12345))
        res2 = fisher_yates_shuffle(items, random.Random(12345))
        assert res1 == res2

    def test_shuffle_differs_with_different_seeds(self):
        items = list(range(20))
        res1 = fisher_yates_shuffle(items, random.Random(101))
        res2 = fisher_yates_shuffle(items, random.Random(202))
        assert res1 != res2


class TestDeterministicSeedGeneration:
    def test_seed_generation_is_reproducible(self):
        s1, i1 = generate_deterministic_seed("session-abc", "101")
        s2, i2 = generate_deterministic_seed("session-abc", "101")
        assert s1 == s2
        assert i1 == i2

    def test_seed_generation_differs_across_versions(self):
        s1, i1 = generate_deterministic_seed("session-abc", "101")
        s2, i2 = generate_deterministic_seed("session-abc", "102")
        assert s1 != s2
        assert i1 != i2

    def test_seed_generation_differs_across_sessions(self):
        s1, i1 = generate_deterministic_seed("session-1", "101")
        s2, i2 = generate_deterministic_seed("session-2", "101")
        assert s1 != s2
        assert i1 != i2


class TestCanonicalInvariantAndIntegrity:
    def test_shuffler_does_not_mutate_input_questions(self):
        questions = _make_sample_questions()
        original_snapshot = copy.deepcopy([q.model_dump() for q in questions])

        res = shuffle_exam_version(
            session_id="test-session-001",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        assert isinstance(res, VersionShuffleResult)
        # Verify inputs are untouched
        current_snapshot = [q.model_dump() for q in questions]
        assert original_snapshot == current_snapshot

    def test_shuffler_does_not_mutate_dict_inputs(self):
        questions = [q.model_dump() for q in _make_sample_questions()]
        original_snapshot = copy.deepcopy(questions)

        res = shuffle_exam_version(
            session_id="test-session-001",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        assert isinstance(res, VersionShuffleResult)
        assert questions == original_snapshot

    def test_canonical_fields_preserved_verbatim_in_outputs(self):
        questions = _make_sample_questions()
        res = shuffle_exam_version(
            session_id="test-session-001",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        for out_q in res.questions:
            # Find the original input question
            orig_q = next(
                q for q in questions if q.canonical_question_no == out_q.canonical_question_no
            )
            assert out_q.canonical_options == orig_q.canonical_options
            assert out_q.canonical_correct_key == orig_q.canonical_correct_key
            assert out_q.canonical_solution_md == orig_q.canonical_solution_md


class TestOptionPermutationAndCorrectKeyTracking:
    def test_correct_answer_content_strictly_tracks_display_key(self):
        questions = _make_sample_questions()
        labels = ["A", "B", "C", "D"]

        for v_idx in range(1, 5):
            res = shuffle_exam_version(
                session_id="test-session-xyz",
                version_index=v_idx,
                questions=questions,
                version_code=f"10{v_idx}",
            )

            for out_q in res.questions:
                orig_q = next(
                    q for q in questions if q.canonical_question_no == out_q.canonical_question_no
                )
                orig_key = orig_q.canonical_correct_key
                new_key = out_q.display_correct_key

                # Canonical correct option content
                orig_correct_content = orig_q.canonical_options[labels.index(orig_key)]
                # Display correct option content
                new_correct_content = out_q.options[labels.index(new_key)]

                assert orig_correct_content == new_correct_content, (
                    f"Version 10{v_idx} Q{out_q.display_no}: Expected correct content "
                    f"'{orig_correct_content}' at display key {new_key}, but got '{new_correct_content}'"
                )

    def test_permutation_map_is_bijective(self):
        questions = _make_sample_questions()
        labels = ["A", "B", "C", "D"]

        res = shuffle_exam_version(
            session_id="test-session-bijection",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        for out_q in res.questions:
            p_map = out_q.permutation_map
            # All 4 letters present as keys and values
            assert sorted(p_map.keys()) == labels
            assert sorted(p_map.values()) == labels

            # Verify that canonical option at orig letter matches display option at new letter
            for orig_letter, new_letter in p_map.items():
                orig_content = out_q.canonical_options[labels.index(orig_letter)]
                new_content = out_q.options[labels.index(new_letter)]
                assert orig_content == new_content


class TestOrderingPreferences:
    def test_disable_question_shuffling(self):
        questions = _make_sample_questions()
        prefs = OrderingPreferences(shuffle_questions=False, shuffle_options=True)

        res = shuffle_exam_version(
            session_id="test-session-no-q-shuffle",
            version_index=1,
            questions=questions,
            preferences=prefs,
            version_code="101",
        )

        # Questions maintain canonical order 1..5
        assert [q.canonical_question_no for q in res.questions] == [1, 2, 3, 4, 5]
        assert [q.display_no for q in res.questions] == [1, 2, 3, 4, 5]

    def test_disable_option_shuffling(self):
        questions = _make_sample_questions()
        prefs = OrderingPreferences(shuffle_questions=True, shuffle_options=False)

        res = shuffle_exam_version(
            session_id="test-session-no-opt-shuffle",
            version_index=1,
            questions=questions,
            preferences=prefs,
            version_code="101",
        )

        # Options and correct keys remain completely unpermuted
        for out_q in res.questions:
            orig_q = next(
                q for q in questions if q.canonical_question_no == out_q.canonical_question_no
            )
            assert out_q.options == orig_q.canonical_options
            assert out_q.display_correct_key == orig_q.canonical_correct_key
            assert out_q.permutation_map == {"A": "A", "B": "B", "C": "C", "D": "D"}

    def test_disable_both_shufflings(self):
        questions = _make_sample_questions()
        prefs = OrderingPreferences(shuffle_questions=False, shuffle_options=False)

        res = shuffle_exam_version(
            session_id="test-session-identity",
            version_index=1,
            questions=questions,
            preferences=prefs,
            version_code="101",
        )

        assert [q.canonical_question_no for q in res.questions] == [1, 2, 3, 4, 5]
        for out_q in res.questions:
            orig_q = next(
                q for q in questions if q.canonical_question_no == out_q.canonical_question_no
            )
            assert out_q.options == orig_q.canonical_options
            assert out_q.display_correct_key == orig_q.canonical_correct_key


class TestSolutionTextSynchronization:
    def test_sync_various_vietnamese_solution_patterns(self):
        # 1. 'Đáp án A: <text>' pattern
        text1 = "1. Giải phương trình.\n\nĐáp án A: 5"
        assert sync_solution_text(text1, "A", "C") == "1. Giải phương trình.\n\nĐáp án C: 5"

        # 2. 'Do đó ta chọn A.' pattern
        text2 = "Do đó ta chọn A."
        assert sync_solution_text(text2, "A", "B") == "Do đó ta chọn B."

        # 3. 'Vậy phương án đúng là A.' pattern
        text3 = "Vậy phương án đúng là A."
        assert sync_solution_text(text3, "A", "D") == "Vậy phương án đúng là D."

        # 4. Bold markdown 'Chọn **A**'
        text4 = "Chọn **A** vì nghiệm là 2."
        assert sync_solution_text(text4, "A", "C") == "Chọn **C** vì nghiệm là 2."

        # 5. LaTeX formatted 'Kết luận: \\textbf{A}'
        text5 = "Kết luận: \\textbf{A}"
        assert sync_solution_text(text5, "A", "B") == "Kết luận: \\textbf{B}"

        # 6. 'Đáp án: A'
        text6 = "Đáp án: A"
        assert sync_solution_text(text6, "A", "D") == "Đáp án: D"

    def test_sync_preserves_geometric_and_math_variables(self):
        # Mathematical variables like 'tam giác ABC', 'đỉnh A', 'cạnh AB', 'ma trận A' must NOT change
        math_text = (
            "Trong tam giác ABC vuông tại A có AB = 3, AC = 4.\n"
            "Tọa độ điểm A(1, 2) và điểm B(4, 6).\n"
            "Suy ra cạnh BC = 5.\n\n"
            "Đáp án đúng: A"
        )
        synced = sync_solution_text(math_text, "A", "C")
        assert "tam giác ABC" in synced
        assert "vuông tại A" in synced
        assert "AB = 3" in synced
        assert "AC = 4" in synced
        assert "điểm A(1, 2)" in synced
        assert "điểm B(4, 6)" in synced
        assert "Đáp án đúng: C" in synced

    def test_sync_no_op_when_keys_match(self):
        text = "Đáp án A: x = 2"
        assert sync_solution_text(text, "A", "A") == text
        assert sync_solution_text("", "A", "B") == ""
        assert sync_solution_text(None, "A", "B") == ""


class TestAnswerKeysAndPermutationsAudit:
    def test_answer_keys_records_align_with_shuffled_questions(self):
        questions = _make_sample_questions()
        res = shuffle_exam_version(
            session_id="test-session-ans-keys",
            version_index=1,
            questions=questions,
            version_code="101",
            version_id="ver-uuid-101",
        )

        assert len(res.answer_keys) == len(res.questions)
        for ans_key, out_q in zip(res.answer_keys, res.questions):
            assert ans_key.version_id == "ver-uuid-101"
            assert ans_key.display_no == out_q.display_no
            assert ans_key.display_correct_key == out_q.display_correct_key
            assert ans_key.question_no == out_q.display_no
            assert ans_key.correct_option == out_q.display_correct_key
            assert ans_key.canonical_question_no == out_q.canonical_question_no

    def test_permutations_matrix_jsonb_structure(self):
        questions = _make_sample_questions()
        res = shuffle_exam_version(
            session_id="test-session-perm-matrix",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        perms = res.permutations
        assert "question_order" in perms
        assert "display_to_canonical" in perms
        assert "canonical_to_display" in perms
        assert "option_permutations" in perms
        assert len(perms["question_order"]) == 5
        assert len(perms["option_permutations"]) == 5


class TestShuffleSessionVersionsWorkflow:
    def test_shuffle_all_four_versions(self):
        questions = _make_sample_questions()
        results, response = shuffle_session_versions(
            session_id="session-full-run",
            questions=questions,
            n_versions=4,
            version_codes=["101", "102", "103", "104"],
        )

        assert len(results) == 4
        assert isinstance(response, FinalizeShuffleResponse)
        assert response.session_id == "session-full-run"
        assert response.status == "reviewed"
        assert response.is_finalized is True
        assert len(response.versions) == 4

        # Version codes and counts align
        for v_meta, exp_code in zip(response.versions, ["101", "102", "103", "104"]):
            assert v_meta.version_code == exp_code
            assert v_meta.total_questions == 5

        # Different versions have different shuffle seeds
        seeds = [r.shuffle_seed for r in results]
        assert len(set(seeds)) == 4


class TestEdgeCases:
    def test_inactive_questions_are_filtered_out(self):
        questions = _make_sample_questions()
        # Mark question 3 as reverted/inactive
        questions[2].is_current = False

        res = shuffle_exam_version(
            session_id="test-session-inactive",
            version_index=1,
            questions=questions,
            version_code="101",
        )

        assert res.total_questions == 4
        assert 3 not in [q.canonical_question_no for q in res.questions]

    def test_empty_questions_list(self):
        res = shuffle_exam_version(
            session_id="test-session-empty",
            version_index=1,
            questions=[],
            version_code="101",
        )
        assert res.total_questions == 0
        assert len(res.questions) == 0
        assert len(res.answer_keys) == 0

    def test_raw_dict_adaptation_with_legacy_fields(self):
        raw_dict_questions = [
            {
                "id": "dict-1",
                "question_no": 1,
                "content": "Câu hỏi test 1",
                "options": ["A1", "B1", "C1", "D1"],
                "correct_answer": "B",
                "solution_steps": "Đáp án B: đúng",
                "is_current": True,
            }
        ]

        res = shuffle_exam_version(
            session_id="test-session-dict",
            version_index=1,
            questions=raw_dict_questions,
            version_code="101",
        )

        assert res.total_questions == 1
        q = res.questions[0]
        assert q.canonical_options == ["A1", "B1", "C1", "D1"]
        assert q.canonical_correct_key == "B"
        assert q.canonical_question_no == 1


class TestReviewerFindingsF01ToF03:
    """Regression tests for reviewer findings F01, F02, F03 (Round 1 from Duy)."""

    def test_f01_sync_solution_text_excludes_math_equations(self):
        """F01: Mathematical equations and assignments (e.g. 'Vậy: A = 5') must not be replaced."""
        # 1. Equality / assignment: Vậy: A = 5 must NOT change to Vậy: C = 5
        text_eq = "Từ hệ thức lượng trong tam giác, ta có Vậy: A = 5."
        assert (
            sync_solution_text(text_eq, "A", "C")
            == "Từ hệ thức lượng trong tam giác, ta có Vậy: A = 5."
        )

        # 2. Inequality / comparison: Suy ra: A > 0 must NOT change
        text_ineq = "Suy ra: A > 0 và B < 10."
        assert sync_solution_text(text_ineq, "A", "C") == "Suy ra: A > 0 và B < 10."

        # 3. Set membership: Do đó: A \in (0, 1) must NOT change
        text_set = r"Do đó: A \in (0, 1)"
        assert sync_solution_text(text_set, "A", "C") == r"Do đó: A \in (0, 1)"

        # 4. Arithmetic addition: Vậy: A + B = 10 must NOT change
        text_add = "Vậy: A + B = 10"
        assert sync_solution_text(text_add, "A", "C") == "Vậy: A + B = 10"

        # 5. True conclusion answer selections: Vậy: A. and Do đó: A must be synchronized
        text_valid1 = "Vậy: A."
        assert sync_solution_text(text_valid1, "A", "C") == "Vậy: C."

        text_valid2 = "Do đó: A"
        assert sync_solution_text(text_valid2, "A", "C") == "Do đó: C"

        text_valid3 = "Kết luận: **A**"
        assert sync_solution_text(text_valid3, "A", "C") == "Kết luận: **C**"

        text_valid4 = "Vậy ta chọn A."
        assert sync_solution_text(text_valid4, "A", "C") == "Vậy ta chọn C."

    def test_f02_answer_key_record_schema_and_alias_compatibility(self):
        """F02: AnswerKeyRecord must support both W3 contract and legacy schema baseline via aliases."""
        # W3 contract creation: display_no and display_correct_key
        rec1 = AnswerKeyRecord(
            version_id="ver-101",
            display_no=1,
            display_correct_key="B",
            canonical_question_no=3,
        )
        assert rec1.display_no == 1
        assert rec1.display_correct_key == "B"
        # Backward-compatible attribute access
        assert rec1.question_no == 1
        assert rec1.correct_option == "B"

        # Legacy baseline creation via alias: question_no and correct_option
        rec2 = AnswerKeyRecord(
            version_id="ver-102",
            question_no=2,
            correct_option="D",
            canonical_question_no=4,
        )
        assert rec2.display_no == 2
        assert rec2.display_correct_key == "D"
        assert rec2.question_no == 2
        assert rec2.correct_option == "D"

        # Serialization checks
        dump_standard = rec1.model_dump()
        assert "display_no" in dump_standard
        assert "display_correct_key" in dump_standard

        dump_aliased = rec1.model_dump(by_alias=True)
        assert "question_no" in dump_aliased
        assert "correct_option" in dump_aliased

    def test_f03_strict_validation_for_canonical_correct_key(self):
        """F03: canonical_correct_key must be strictly validated as Literal['A', 'B', 'C', 'D'] with no silent fallback."""
        from pydantic import ValidationError

        # Invalid key in CanonicalQuestionInput raises ValidationError
        with pytest.raises(ValidationError):
            CanonicalQuestionInput(
                canonical_question_no=1,
                content="Test question",
                canonical_options=["A", "B", "C", "D"],
                canonical_correct_key="E",  # Invalid
            )

        with pytest.raises(ValidationError):
            CanonicalQuestionInput(
                canonical_question_no=1,
                content="Test question",
                canonical_options=["A", "B", "C", "D"],
                canonical_correct_key="INVALID",
            )

        # Legacy raw dict input with invalid key raises ValueError instead of silent fallback to 'A'
        invalid_dict = [
            {
                "canonical_question_no": 1,
                "content": "Test",
                "options": ["1", "2", "3", "4"],
                "correct_key": "X",
            }
        ]
        with pytest.raises(ValueError) as exc_info:
            shuffle_exam_version("sess-err", 1, invalid_dict)
        assert "Invalid canonical_correct_key" in str(exc_info.value)
