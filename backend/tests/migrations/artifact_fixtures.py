"""Detached test artifacts, not a runtime confirmation/hash implementation.

The canonical sample is shared with the existing AI pipeline fixtures. SQL-only
control-plane tests seed it as a trusted worker would; consumer integration must
independently validate its hash using production source_to_item/source_fingerprint.
"""

import hashlib
import json
from pathlib import Path
from uuid import uuid4


def artifact_payload(source_id):
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/ai_pipeline.json").read_text(encoding="utf-8")
    )
    blueprint = fixture["blueprint"]
    old = blueprint["requirement"]["source"]["question_id"]
    new = "q_" + hashlib.sha256(source_id.encode()).hexdigest()[:24]
    blueprint = json.loads(json.dumps(blueprint).replace(old, new))
    source = fixture["source"] | {"id": source_id}
    confirmed = {
        k: source[k] for k in ("id", "question_text", "options", "correct_answer", "solution")
    }
    item = {
        "source": blueprint["requirement"]["source"],
        "context": {"subject": "mathematics", "language": "vi"},
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            [item], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    artifact = {
        "source_question_id": source_id,
        "source_revision_id": str(uuid4()),
        "confirmed_input": confirmed,
        "source_fingerprint": fingerprint,
    }
    publication = {
        "source_question_id": source_id,
        "source_revision_id": artifact["source_revision_id"],
        "source_fingerprint": fingerprint,
        "blueprint_revision_id": str(uuid4()),
        "schema_version": "0.4.0",
        "canonical_blueprint": blueprint,
    }
    return artifact, publication


def seed_artifacts(case, session_id, source_id, actor_id):
    """Seed trusted immutable evidence for isolated review tests, without AI.

    Producer tests instead call the actual confirmation/publication RPCs.
    """
    artifact, publication = artifact_payload(source_id)
    confirmation_id = str(uuid4())

    def lit(value):
        return "'" + str(value).replace("'", "''") + "'"

    source = artifact["confirmed_input"]
    receipt = {
        "confirmation_id": confirmation_id,
        "session_id": session_id,
        "actor_id": actor_id,
        "sources": [artifact],
    }
    case.sql(f"""
      UPDATE source_questions SET raw_content={lit(source["question_text"])},
        options={lit(json.dumps(source["options"]))},correct_key={lit(source["correct_answer"])},
        solution_md={lit(source["solution"])} WHERE id={lit(source_id)};
      UPDATE question_blueprints SET confirmed_at=now() WHERE source_question_id={lit(source_id)};
      INSERT INTO source_artifact_confirmations(confirmation_id,session_id,actor_id,result)
        VALUES ({lit(confirmation_id)},{lit(session_id)},{lit(actor_id)},{lit(json.dumps(receipt))});
      INSERT INTO source_artifact_revisions(source_revision_id,confirmation_id,source_question_id,confirmed_input,source_fingerprint)
        VALUES ({lit(artifact["source_revision_id"])},{lit(confirmation_id)},{lit(source_id)},
          {lit(json.dumps(source))},{lit(artifact["source_fingerprint"])});
      INSERT INTO canonical_blueprint_revisions(blueprint_revision_id,source_revision_id,source_question_id,canonical_blueprint,schema_version)
        VALUES ({lit(publication["blueprint_revision_id"])},{lit(artifact["source_revision_id"])},
          {lit(source_id)},{lit(json.dumps(publication["canonical_blueprint"]))},'0.4.0');
      INSERT INTO source_artifact_heads VALUES ({lit(source_id)},{lit(artifact["source_revision_id"])},{lit(publication["blueprint_revision_id"])});
    """)
    return artifact, publication


def lease_superseding_publication(case, source_id, publication):
    """Set up a trusted revision change, not a public ready-head retry path.

    Tests model a subsequent canonical revision to stress in-flight guards.
    The production claim RPC skips already-ready heads; this fixture deliberately
    grants the new revision a lease without replacing the current Blueprint yet.
    """
    job = publication["blueprint_revision_id"]
    publication = publication | {"producer_job_id": job}
    case.sql(
        f"UPDATE source_artifact_heads SET producer_job_id='{job}', "
        f"producer_expires_at=clock_timestamp()+interval '420 seconds' "
        f"WHERE source_question_id='{source_id}';"
    )
    return publication
