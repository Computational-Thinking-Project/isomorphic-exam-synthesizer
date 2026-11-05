"""Explicit cross-PR check: real RPC fixture + pinned consumer + offline provider.

Run with TASK-301/TASK-304 modules on PYTHONPATH, not as a default unit suite.
See README for the immutable upstream commit and fixture-generation command.
"""

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("candidate_fixture", type=Path)
    args = parser.parse_args()

    # These optional modules resolve from the pinned upstream PYTHONPATH. Do not
    # classify half of that package by files available on the current branch.
    # isort: off
    from app.models.generation import ValidationReport
    from app.models.schemas import ReviewDomainException
    from app.services.blueprint.artifacts import (
        prepare_blueprint_artifact,
        prepare_source_artifacts,
    )
    from app.services.blueprint.common import canonical
    from app.services.generation.attempts import AttemptPermit
    from app.services.generation.service import GenerationService
    from app.services.generation.targeted_service import TargetedRegenerator
    from app.services.review.receipts import ReservationReceipt
    from app.services.review.validation import frozen_inputs, validate_candidate
    from app.services.validator.base import CheckResult
    from app.services.validator.pipeline import validate_solution
    # isort: on

    receipt_data = json.loads(args.receipt.read_text(encoding="utf-8"))
    fixture = json.loads(args.candidate_fixture.read_text(encoding="utf-8"))
    original = deepcopy(receipt_data)
    receipt = ReservationReceipt.model_validate(receipt_data)
    inputs = frozen_inputs(receipt)
    source = inputs["source_snapshot"]
    prepared = prepare_source_artifacts(
        str(receipt.session_id),
        [
            {
                "id": source["id"],
                "session_id": str(receipt.session_id),
                "raw_content": source["question_text"],
                "options": source["options"],
                "correct_key": source["correct_answer"],
                "solution_md": source["solution"],
            }
        ],
    )[0]
    assert prepared["source_fingerprint"] == source["content_hash"]
    prepare_blueprint_artifact(prepared, inputs["blueprint"])
    grants, dispatches = [], []

    async def acquire(operation_id, attempt_id):
        assert UUID(str(operation_id)) == receipt.operation_id
        grants.append(attempt_id)
        return AttemptPermit(
            operation_id=operation_id,
            attempt_id=attempt_id,
            dispatch_permitted=True,
            calls_used=len(grants),
            remaining_calls=30 - len(grants),
            replayed=False,
        )

    async def generate(**kwargs):
        await kwargs["context"].reserve_request()
        dispatches.append(True)
        return SimpleNamespace(
            text=canonical(fixture["candidates"][1]),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            model_version="offline",
            usage_metadata=None,
        )

    async def validate(candidate, **kwargs):
        return ValidationReport(
            checks=[
                *validate_solution(candidate),
                CheckResult(
                    check_name="answer_verified",
                    passed=False,
                    status="unsupported",
                    detail="Teacher review required",
                ),
            ]
        )

    adapter = TargetedRegenerator(
        GenerationService(
            SimpleNamespace(model="offline", generate_content=generate),
            SimpleNamespace(validate=validate),
        )
    )

    async def run():
        result = await adapter(
            session_id=receipt.session_id,
            question_id=receipt.question_id,
            operation_id=receipt.operation_id,
            acquire_attempt=acquire,
            **inputs,
        )
        validated = validate_candidate(result)
        assert validated["api_calls_count"] == 1
        assert len(grants) == len(dispatches) == 1
        assert not validated["validation_report"]["math_verified"]
        assert validated["validation_report"]["requires_teacher_review"]
        assert receipt_data == original
        # Each negative starts with a receipt emitted by PostgreSQL. These are
        # explicitly corrupted copies, not claims that the DB emitted invalid JSON.
        mutations = {
            "missing_artifacts": lambda x: x.pop("source_snapshot"),
            "legacy_format": lambda x: x.update(format="database_rows"),
            "wrong_revision": lambda x: x.update(blueprint_source_revision_id=str(uuid4())),
            "wrong_hash": lambda x: x.update(blueprint_source_fingerprint="f" * 64),
            "missing_hash": lambda x: x["source_snapshot"].pop("content_hash"),
            "invalid_blueprint": lambda x: x.update(blueprint={"variables": {}}),
            "current_identity": lambda x: x["current_variant"].update(id=str(uuid4())),
            "peer_identity": lambda x: x["peer_variants"][0].update(
                source_question_id=str(uuid4())
            ),
        }
        for name, mutate in mutations.items():
            broken = deepcopy(original)
            mutate(broken["snapshot"])
            before = len(grants), len(dispatches)
            try:
                mapped = frozen_inputs(ReservationReceipt.model_validate(broken))
                await adapter(
                    session_id=receipt.session_id,
                    question_id=receipt.question_id,
                    operation_id=receipt.operation_id,
                    acquire_attempt=acquire,
                    **mapped,
                )
            except ReviewDomainException:
                pass
            else:
                raise AssertionError("Invalid snapshot accepted: " + name)
            assert (len(grants), len(dispatches)) == before, name
        print(
            "PASS: actual RPC receipt, production artifact/hash/schema checks, frozen mapping, "
            "real adapter/offline provider; 8 corruptions rejected before permit/dispatch"
        )

    asyncio.run(run())


if __name__ == "__main__":
    main()
