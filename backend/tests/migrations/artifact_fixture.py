"""Publish validated fixture artifacts through the actual worker RPCs."""

import json
import sys
from pathlib import Path
from uuid import uuid4

from test_stage3_schema import ROOT


def publish_fixture(case, sid, source_id, owner):
    sys.path.insert(0, str(ROOT / "backend"))
    from test_review_rpcs import literal

    from app.models.schemas import SourceQuestion
    from app.services.blueprint.adapters import source_to_item
    from app.services.blueprint.artifacts import (
        prepare_blueprint_artifact,
        prepare_source_artifacts,
    )

    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    source = fixture["source"]
    old_id = source_to_item(SourceQuestion.model_validate(source))["source"]["question_id"]
    source["id"] = source_id
    new_id = source_to_item(SourceQuestion.model_validate(source))["source"]["question_id"]
    blueprint = json.loads(json.dumps(fixture["blueprint"]).replace(old_id, new_id))
    prior = case.value(f"SELECT status FROM exam_sessions WHERE id='{sid}';")
    case.sql(
        f"UPDATE exam_sessions SET status='draft' WHERE id='{sid}'; UPDATE source_questions SET raw_content={literal(source['question_text'])},options={literal(json.dumps(source['options']))},correct_key='A',solution_md=NULL WHERE id='{source_id}';"
    )
    timestamp = case.value(f"SELECT updated_at FROM exam_sessions WHERE id='{sid}';")
    row = dict(
        id=source_id,
        session_id=sid,
        raw_content=source["question_text"],
        options=source["options"],
        correct_key="A",
        solution_md=None,
    )
    prepared = prepare_source_artifacts(sid, [row])
    publication = prepare_blueprint_artifact(prepared[0], blueprint)
    publication["producer_job_id"] = publication["blueprint_revision_id"]
    auth = f"SET ROLE service_role; SET request.jwt.claim.role='service_role'; SET request.jwt.claim.sub='{owner}'; "
    case.sql(
        auth
        + f"SELECT confirm_source_artifacts('{sid}','{owner}','{uuid4()}',{literal(timestamp)},{literal(json.dumps(prepared))});"
    )
    case.sql(
        auth
        + f"SELECT claim_source_production('{sid}','{prepared[0]['source_revision_id']}','{publication['producer_job_id']}');"
    )
    case.sql(
        auth + f"SELECT publish_canonical_blueprint('{sid}',{literal(json.dumps(publication))});"
    )
    case.sql(f"UPDATE exam_sessions SET status={literal(prior)} WHERE id='{sid}';")
