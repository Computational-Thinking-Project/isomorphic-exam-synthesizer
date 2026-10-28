import copy
from argparse import Namespace

import pytest
from blueprint_tool.common import ToolError, canonical, strict_json
from blueprint_tool.config import resolve_config
from blueprint_tool.extractor import assemble
from blueprint_tool.input_adapter import Contracts, input_items
from blueprint_tool.schema_adapter import build_api_schema, generation_payload
from blueprint_tool.validators import schema_issues, validate_blueprint, validate_input
from jsonschema import Draft202012Validator


@pytest.mark.parametrize(
    "text", ['{"a":1,"a":2}', '{"x":{"a":1,"a":2}}', '{"x":NaN}', '{"x":Infinity}', "{} {}"]
)
def test_strict_json(text):
    with pytest.raises(ToolError):
        strict_json(text)


def test_canonical_round_trip_and_manifest(science_schema, example, item):
    api_schema, manifest = build_api_schema(science_schema)
    Draft202012Validator.check_schema(api_schema)
    payload = generation_payload(example)
    assert not schema_issues(payload, api_schema)
    final = assemble(payload, item["source"], "bp_test")
    assert not validate_blueprint(final, science_schema, item["source"], item["context"])
    assert canonical(final["requirement"]["source"]) == canonical(item["source"])
    assert final["constraint"]["source_check"]["methods"] == []
    assert any(m.get("keyword") == "conditional_allOf" for m in manifest)
    assert any(m.get("ownership") == "script" for m in manifest)


def test_adapter_fails_on_new_keyword(science_schema):
    science_schema["properties"]["unexpected"] = {"type": "string", "fancyConstraint": True}
    with pytest.raises(ToolError, match="keyword"):
        build_api_schema(science_schema)


def test_adapter_refuses_overlapping_oneof(science_schema):
    science_schema["$defs"]["value"]["oneOf"].append(
        copy.deepcopy(science_schema["$defs"]["value"]["oneOf"][0])
    )
    with pytest.raises(ToolError, match="oneOf"):
        build_api_schema(science_schema)


def test_missing_answer_is_not_inferred_into_source(science_schema, item):
    item["source"]["supplied_answer"] = None
    contracts = Contracts(science_schema)
    validate_input(item, contracts.single, contracts.registry)


def test_invariant_coverage_and_numeric_domain(science_schema, example, item):
    blueprint = assemble(generation_payload(example), item["source"], "bp_test")
    for rule in blueprint["constraint"]["rules"]:
        rule["requirement_refs"] = [blueprint["requirement"]["assessment"]["id"]]
    domain = blueprint["requirement"]["variation_policy"]["parameter_domains"][0]
    domain["minimum"] = {"type": "integer", "value": 100}
    domain["maximum"] = {"type": "integer", "value": 1}
    errors = validate_blueprint(blueprint, science_schema, item["source"], item["context"])
    assert {"invariant_without_required_rule", "domain_bounds"} <= {e["rule"] for e in errors}


def test_evaluation_fixture_preserves_vietnamese():
    from blueprint_tool.common import ROOT, load_json
    from blueprint_tool.validators import language_hint

    data = load_json(ROOT / "scripts/blueprint/tests/fixtures/live_evaluation_input.json")
    assert len(data["questions"]) == 12
    for item in data["questions"]:
        if item["context"]["language"] == "vi":
            assert language_hint(item["source"]) == "vi"


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            lambda b: b["requirement"]["semantic_model"]["target"].update(quantity_ref="MISSING"),
            "invalid_reference",
        ),
        (
            lambda b: b["requirement"]["reasoning_model"]["steps"][0]["depends_on"].append(
                b["requirement"]["reasoning_model"]["steps"][0]["id"]
            ),
            "reasoning_cycle",
        ),
        (lambda b: b["constraint"]["rules"].clear(), "minItems"),
        (lambda b: b["requirement"].update(language="en"), "source_language"),
        (
            lambda b: b["requirement"]["source"]["content"][0].update(text="AI đã thay câu nguồn."),
            "source_changed",
        ),
    ],
)
def test_semantic_invalid_cases(science_schema, example, item, mutation, expected):
    blueprint = assemble(generation_payload(example), item["source"], "bp_test")
    mutation(blueprint)
    errors = validate_blueprint(blueprint, science_schema, item["source"], item["context"])
    assert expected in {error["rule"] for error in errors}


def test_image_and_bad_table_fail_preflight(science_schema, item):
    contracts = Contracts(science_schema)
    item["source"]["content"][0]["text"] = "Tính theo hình vẽ bên dưới."
    with pytest.raises(ToolError) as info:
        validate_input(item, contracts.single, contracts.registry)
    assert info.value.code == "IMAGE_DEPENDENCY"
    item["source"]["content"][0]["text"] = "Tính gia tốc."
    item["source"]["content"][1]["rows"][0].append("extra")
    with pytest.raises(ToolError) as info:
        validate_input(item, contracts.single, contracts.registry)
    assert any(e["rule"] == "table_width" for e in info.value.details)


def test_duplicate_question_id_is_global(item):
    with pytest.raises(ToolError) as info:
        input_items({"questions": [item, item]}, "batch")
    assert info.value.code == "DUPLICATE_QUESTION_ID"


def test_config_precedence_and_relative_resources(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[ai]\nmodel="from_toml"\n[batch]\nconcurrency=2\n', encoding="utf-8")
    args = Namespace(config=str(path), model=None)
    assert (
        resolve_config(args, {"GEMINI_MODEL": "legacy", "BLUEPRINT_MODEL": "blueprint"}).model
        == "blueprint"
    )
    assert resolve_config(args, {"GEMINI_MODEL": "legacy"}).model == "legacy"
    assert resolve_config(args, {}).model == "from_toml"
    args.model = "cli"
    assert resolve_config(args, {"BLUEPRINT_MODEL": "env"}).model == "cli"


@pytest.mark.parametrize("value", ["nan", "-1", "0", "inf"])
def test_invalid_timeouts(value):
    with pytest.raises(ToolError):
        resolve_config(
            Namespace(config=None, model=None), {"BLUEPRINT_REQUEST_TIMEOUT_SECONDS": value}
        )
