"""Legacy parser helpers remain covered; confirmation no longer invokes them."""
from unittest.mock import MagicMock
import pytest
MOCK_SESSION_ID="11111111-1111-1111-1111-111111111111"

@pytest.mark.asyncio
async def test_ensure_blueprints_safe_upsert_deduplication():
    """ensure_blueprints_for_session uses upsert with ignore_duplicates to prevent duplicate blueprints."""
    from app.services.parser.blueprint_service import ensure_blueprints_for_session

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    questions = [
        {"id": "sq-1", "question_no": 1, "raw_content": "Cho x = 5"},
        {"id": "sq-2", "question_no": 2, "raw_content": "Cho y = 10"},
    ]

    total = await ensure_blueprints_for_session(mock_db, MOCK_SESSION_ID, questions)

    assert total == 2
    mock_db.table("question_blueprints").upsert.assert_called_once()
    _, kwargs = mock_db.table("question_blueprints").upsert.call_args
    assert kwargs.get("on_conflict") == "source_question_id"
    assert kwargs.get("ignore_duplicates") is True


@pytest.mark.asyncio
async def test_ensure_blueprints_preserves_confirmed():
    """ensure_blueprints_for_session does not re-insert or modify questions that already have blueprints."""
    from app.services.parser.blueprint_service import ensure_blueprints_for_session

    mock_db = MagicMock()
    # Question 1 already has a blueprint in DB
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"source_question_id": "sq-1"}
    ]

    questions = [
        {"id": "sq-1", "question_no": 1, "raw_content": "Cho x = 5"},
        {"id": "sq-2", "question_no": 2, "raw_content": "Cho y = 10"},
    ]

    total = await ensure_blueprints_for_session(mock_db, MOCK_SESSION_ID, questions)

    assert total == 2
    # Only question 2 should be in the upsert payload
    mock_db.table("question_blueprints").upsert.assert_called_once()
    args, _ = mock_db.table("question_blueprints").upsert.call_args
    inserted_blueprints = args[0]
    assert len(inserted_blueprints) == 1
    assert inserted_blueprints[0]["source_question_id"] == "sq-2"
    assert inserted_blueprints[0]["is_fallback"] is True
    assert inserted_blueprints[0]["extraction_source"] == "FALLBACK_DETERMINISTIC"


def test_extract_default_blueprint_unsupported_non_numerical_question():
    """Questions without numerical parameters are marked as invariant with variation_modes=['NONE']."""
    from app.services.parser.blueprint_service import extract_default_blueprint

    q_verbal = {
        "id": "sq-verbal-1",
        "question_no": 7,
        "raw_content": "Đặc điểm nào sau đây là của quá trình giảm phân?",
    }
    bp = extract_default_blueprint(q_verbal)
    assert bp["source_question_id"] == "sq-verbal-1"
    assert bp["variables"] == {}
    assert bp["domains"] == {}
    assert bp["variation_modes"] == ["NONE"]
    assert "PRESERVE_CONTENT_VERBATIM" in bp["invariants"]
    assert bp["is_fallback"] is True
    assert bp["extraction_source"] == "FALLBACK_DETERMINISTIC"
    assert "no numerical parameters" in bp["rule_summary"]


