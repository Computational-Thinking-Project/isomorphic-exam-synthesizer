"""Producer provenance tests; no assertion of DB persistence or transactions."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.blueprint.artifacts import prepare_blueprint_artifact, prepare_source_artifacts
from app.services.blueprint.common import ToolError


@pytest.fixture
def source_row():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    source = fixture["source"]
    row = {
        "id": source["id"],
        "session_id": str(uuid4()),
        "raw_content": source["question_text"],
        "options": dict(zip("ABCD", source["options"], strict=True)),
        "correct_key": source["correct_answer"],
        "solution_md": None,
    }
    return row, fixture["blueprint"]


def test_source_confirmation_preserves_text_options_and_null_solution_mapping(source_row):
    row, _ = source_row
    before = deepcopy(row)
    prepared = prepare_source_artifacts(row["session_id"], [row])[0]
    assert row == before
    assert prepared["confirmed_input"] == {
        "id": row["id"],
        "question_text": row["raw_content"],
        "options": list(row["options"].values()),
        "correct_answer": row["correct_key"],
        "solution": "",
    }
    # Reconfirmation after edit-and-revert is a new revision even for identical input.
    again = prepare_source_artifacts(row["session_id"], [row])[0]
    assert again["source_revision_id"] != prepared["source_revision_id"]
    assert again["source_fingerprint"] == prepared["source_fingerprint"]


@pytest.mark.parametrize("field", ["raw_content", "options", "correct_key", "solution_md"])
def test_every_source_content_change_invalidates_fingerprint(source_row, field):
    row, _ = source_row
    before = prepare_source_artifacts(row["session_id"], [row])[0]
    changed = deepcopy(row)
    if field == "options":
        changed[field]["B"] += " changed"
    elif field == "correct_key":
        changed[field] = "B"
    else:
        changed[field] = (changed[field] or "") + " changed"
    after = prepare_source_artifacts(row["session_id"], [changed])[0]
    assert after["source_fingerprint"] != before["source_fingerprint"]


@pytest.mark.parametrize("damage", ["session", "duplicate", "option", "key", "solution"])
def test_malformed_or_cross_session_sources_are_not_confirmed(source_row, damage):
    row, _ = source_row
    rows = [row]
    if damage == "session":
        row["session_id"] = str(uuid4())
    elif damage == "duplicate":
        rows.append(deepcopy(row))
    elif damage == "option":
        row["options"]["A"] = 1
    elif damage == "key":
        row["correct_key"] = ""
    else:
        row["solution_md"] = False
    session = str(uuid4()) if damage == "session" else row["session_id"]
    with pytest.raises(ToolError, match="Nguồn"):
        prepare_source_artifacts(session, rows)


def test_blueprint_publication_binds_full_canonical_document_and_detaches_input(source_row):
    row, blueprint = source_row
    source = prepare_source_artifacts(row["session_id"], [row])[0]
    publication = prepare_blueprint_artifact(source, blueprint)
    assert publication["source_revision_id"] == source["source_revision_id"]
    assert publication["source_fingerprint"] == source["source_fingerprint"]
    assert publication["canonical_blueprint"] == blueprint
    publication["canonical_blueprint"]["requirement"]["blueprint_id"] = "changed"
    assert blueprint["requirement"]["blueprint_id"] != "changed"


@pytest.mark.parametrize("damage", ["missing_hash", "wrong_hash", "source", "revision", "legacy"])
def test_publication_never_manufactures_missing_confirmation_or_canonical_data(source_row, damage):
    row, blueprint = source_row
    source = prepare_source_artifacts(row["session_id"], [row])[0]
    if damage == "missing_hash":
        source.pop("source_fingerprint")
    elif damage == "wrong_hash":
        source["source_fingerprint"] = "not-confirmed"
    elif damage == "source":
        source["source_question_id"] = str(uuid4())
    elif damage == "revision":
        source["source_revision_id"] = "invalid"
    else:
        blueprint = {"variables": {}, "domains": {}, "confirmed_at": "2026-11-04"}
    before = deepcopy(source)
    with pytest.raises(ToolError, match="Blueprint"):
        prepare_blueprint_artifact(source, blueprint)
    assert source == before
