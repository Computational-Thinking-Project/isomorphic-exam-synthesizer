"""Structural and referential checks. These do not prove subject correctness."""

import re
from collections import Counter
from fractions import Fraction
from itertools import islice

from jsonschema import Draft202012Validator

from .common import ToolError, canonical, pointer

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
VI = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]")
IMAGE = re.compile(
    r"!\[|<img\b|data:image/|https?://\S+\.(?:png|jpe?g|svg|gif|webp)\b|"
    r"(?:như|theo|trong|ở|xem)\s+hình\s+(?:vẽ|bên|dưới|sau|trên|\d)|"
    r"(?:see|refer to|shown in|following)\s+(?:the\s+)?(?:figure|diagram|image|graph)\b",
    re.I,
)


def walk(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, (*path, index))


def schema_issues(value, schema, registry=None):
    kwargs = {"registry": registry} if registry is not None else {}
    return [
        {
            "pointer": pointer(error.absolute_path),
            "rule": error.validator,
            "message": "Giá trị không thỏa schema tại vị trí này.",
        }
        for error in islice(Draft202012Validator(schema, **kwargs).iter_errors(value), 24)
    ]


def ids(value):
    return {node["id"] for _, node in walk(value) if isinstance(node, dict) and "id" in node}


def table_issues(value):
    errors = []
    for path, node in walk(value):
        if isinstance(node, dict) and node.get("type") == "table":
            for index, row in enumerate(node["rows"]):
                if len(row) != len(node["columns"]):
                    errors.append(
                        {"pointer": pointer((*path, "rows", index)), "rule": "table_width"}
                    )
    return errors


def unique_id_issues(value):
    found = Counter(
        node["id"] for _, node in walk(value) if isinstance(node, dict) and "id" in node
    )
    return [{"rule": "duplicate_id", "id": key} for key, count in found.items() if count > 1]


def language_hint(source):
    text = " ".join(node for _, node in walk(source["content"]) if isinstance(node, str))
    if VI.search(text):
        return "vi"
    if re.search(r"\b(the|find|calculate|explain|which|what|given|compute)\b", text, re.I):
        return "en"
    return None


def validate_input(item, single_schema, registry=None):
    errors = schema_issues(item, single_schema, registry)
    if errors:
        raise ToolError("ITEM_INPUT_INVALID", "Câu nguồn hoặc context không hợp lệ.", errors)
    source = item["source"]
    errors = unique_id_issues(source) + table_issues(source)
    options = {option["id"] for option in source["options"]}
    supplied = source["supplied_answer"]
    if supplied and set(supplied["option_ids"]) - options:
        errors.append({"pointer": "/source/supplied_answer/option_ids", "rule": "unknown_option"})
    if IMAGE.search(canonical(source)):
        raise ToolError(
            "IMAGE_DEPENDENCY",
            "Câu có dữ kiện phụ thuộc hình; phase này chỉ nhận văn bản, công thức và bảng.",
        )
    if errors:
        raise ToolError("ITEM_INPUT_INVALID", "Câu nguồn có lỗi ID, tham chiếu hoặc bảng.", errors)
    return item


def validate_blueprint(blueprint, canonical_schema, source, context):
    errors = schema_issues(blueprint, canonical_schema)
    if errors:
        return errors
    req, con = blueprint["requirement"], blueprint["constraint"]
    errors += unique_id_issues(blueprint) + table_issues(blueprint)
    if canonical(req["source"]) != canonical(source):
        errors.append({"pointer": "/requirement/source", "rule": "source_changed"})
    req_ids = ids(req)
    source_ids = ids(source)
    reference_ids = {ref["id"] for ref in source["references"]}
    quantity_ids = {q["id"] for q in req["semantic_model"]["quantities"]}

    def refs(values, allowed, path):
        for value in values:
            if value not in allowed:
                errors.append({"pointer": path, "rule": "invalid_reference", "reference": value})

    for index, relation in enumerate(req["semantic_model"]["relations"]):
        refs(
            relation["refs"],
            ids(req["semantic_model"]) | ids(req["knowledge_basis"]) | source_ids,
            f"/requirement/semantic_model/relations/{index}/refs",
        )
    for path, claim in walk(req):
        if isinstance(claim, dict) and {"origin", "evidence_refs"} <= claim.keys():
            allowed = (
                reference_ids if claim["origin"] == "reference" else source_ids - reference_ids
            )
            if claim["origin"] == "inferred":
                allowed = req_ids
            refs(claim["evidence_refs"], allowed, pointer((*path, "evidence_refs")))
    target = req["semantic_model"]["target"]["quantity_ref"]
    if target is not None:
        refs([target], quantity_ids, "/requirement/semantic_model/target/quantity_ref")
    for index, domain in enumerate(req["variation_policy"]["parameter_domains"]):
        refs(
            [domain["quantity_ref"]],
            quantity_ids,
            f"/requirement/variation_policy/parameter_domains/{index}",
        )

        def number(value):
            if value is None:
                return None
            if value["type"] in {"integer", "decimal"}:
                raw = str(value["value"])
                if value["type"] == "decimal":
                    from decimal import Decimal, InvalidOperation

                    try:
                        if len(raw) > 2048 or abs(Decimal(raw).adjusted()) > 2048:
                            return None
                    except InvalidOperation:
                        return None
                return Fraction(raw)
            if value["type"] == "rational":
                return Fraction(value["numerator"], value["denominator"])
            return None

        lower, upper = number(domain["minimum"]), number(domain["maximum"])
        if lower is not None and upper is not None and lower > upper:
            errors.append(
                {
                    "pointer": f"/requirement/variation_policy/parameter_domains/{index}",
                    "rule": "domain_bounds",
                }
            )
        for allowed in domain["allowed_values"] or []:
            value = number(allowed)
            if value is not None and (
                (lower is not None and value < lower) or (upper is not None and value > upper)
            ):
                errors.append(
                    {
                        "pointer": f"/requirement/variation_policy/parameter_domains/{index}",
                        "rule": "allowed_value_outside_bounds",
                    }
                )
    for index, transform in enumerate(req["variation_policy"]["allowed_transformations"]):
        refs(
            transform["target_refs"],
            req_ids,
            f"/requirement/variation_policy/allowed_transformations/{index}/target_refs",
        )
    covered = set()
    for index, rule in enumerate(con["rules"]):
        refs(rule["requirement_refs"], req_ids, f"/constraint/rules/{index}/requirement_refs")
        if rule["severity"] == "required":
            covered.update(rule["requirement_refs"])
    for invariant in req["invariants"]:
        if invariant["id"] not in covered:
            errors.append({"rule": "invariant_without_required_rule", "id": invariant["id"]})
    graph = {step["id"]: step["depends_on"] for step in req["reasoning_model"]["steps"]}
    for key, dependencies in graph.items():
        refs(dependencies, set(graph), "/requirement/reasoning_model/steps/" + key)
    visited, active = set(), set()

    def visit(key):
        if key in active:
            return False
        if key in visited or key not in graph:
            return True
        active.add(key)
        for child in graph[key]:
            if not visit(child):
                return False
        active.remove(key)
        visited.add(key)
        return True

    if not all(visit(key) for key in graph):
        errors.append({"pointer": "/requirement/reasoning_model/steps", "rule": "reasoning_cycle"})
    response = req["response_spec"]
    options = {option["id"] for option in source["options"]}
    if response["format"] in {"single_choice", "multiple_choice"}:
        if response["option_count"] != len(options) or response["correct_option_count"] > len(
            options
        ):
            errors.append({"pointer": "/requirement/response_spec", "rule": "option_counts"})
        supplied = source["supplied_answer"]
        if (
            supplied
            and supplied["option_ids"]
            and len(supplied["option_ids"]) != response["correct_option_count"]
        ):
            errors.append(
                {"pointer": "/requirement/response_spec", "rule": "supplied_answer_count"}
            )
    computed = con["source_check"]["computed_answer"]
    if computed:
        refs(computed["option_ids"], options, "/constraint/source_check/computed_answer/option_ids")
        if (
            computed["option_ids"]
            and len(computed["option_ids"]) != response["correct_option_count"]
        ):
            errors.append(
                {
                    "pointer": "/constraint/source_check/computed_answer",
                    "rule": "computed_answer_count",
                }
            )
    if con["source_check"]["methods"] or con["source_check"]["evidence"]:
        errors.append({"pointer": "/constraint/source_check", "rule": "unverified_evidence"})
    expected_language = context.get("language") or language_hint(source)
    if expected_language and req["language"] != expected_language:
        errors.append({"pointer": "/requirement/language", "rule": "source_language"})
    if context.get("subject") and req["subject"] != context["subject"]:
        errors.append({"pointer": "/requirement/subject", "rule": "context_subject"})
    # A conservative smoke check, not a language classifier for every language.
    descriptions = " ".join(
        value
        for path, value in walk(req)
        if isinstance(value, str)
        and path
        and path[-1] in {"description", "objective"}
        and "source" not in path
    )
    if expected_language == "vi" and len(descriptions) > 200 and not VI.search(descriptions):
        errors.append({"rule": "descriptive_language", "language": "vi"})
    if expected_language == "en" and len(VI.findall(descriptions)) > 20:
        errors.append({"rule": "descriptive_language", "language": "en"})
    return errors[:32]
