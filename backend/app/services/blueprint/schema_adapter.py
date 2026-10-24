"""Project the canonical schema for generation; validate final output in full.

All deliberate relaxations are returned in a manifest. Unknown keywords fail closed.
The caller owns source/metadata/policies, so the model never rewrites those fields.
"""

from copy import deepcopy

from .common import ToolError

OWNED = (
    ("requirement", "blueprint_id"),
    ("requirement", "schema_version"),
    ("requirement", "language_policy"),
    ("requirement", "source"),
    ("requirement", "presentation", "allowed_content_types"),
    ("requirement", "presentation", "requires_image"),
    ("constraint", "validation_policy"),
    ("constraint", "source_check", "methods"),
    ("constraint", "source_check", "evidence"),
)


def remove_owned(schema):
    for path in OWNED:
        node = schema
        for part in path[:-1]:
            node = node["properties"][part]
        node["properties"].pop(path[-1], None)
        if path[-1] in node.get("required", []):
            node["required"].remove(path[-1])
    return schema


def generation_payload(blueprint):
    result = deepcopy(blueprint)
    for path in OWNED:
        node = result
        for part in path[:-1]:
            node = node[part]
        node.pop(path[-1], None)
    return result


def build_api_schema(canonical):
    manifest = []
    allowed = {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "anyOf",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "format",
    }
    deferred = {
        "pattern",
        "minLength",
        "maxLength",
        "uniqueItems",
        "exclusiveMinimum",
        "exclusiveMaximum",
    }

    def expand(node, path="$", refs=()):
        node = deepcopy(node)
        if "$ref" in node:
            ref = node.pop("$ref")
            if not ref.startswith("#/$defs/") or ref in refs:
                raise ToolError(
                    "SCHEMA_UNSUPPORTED", "Schema có tham chiếu ngoài hoặc đệ quy không hỗ trợ."
                )
            target = canonical["$defs"][ref.split("/")[-1]]
            base = expand(target, path, (*refs, ref))
            for key, value in node.items():
                if key in base and key != "description" and base[key] != value:
                    raise ToolError("SCHEMA_UNSUPPORTED", "Không gộp được ràng buộc tại $ref.")
                base[key] = value
            node = base
        if "allOf" in node:
            for index, branch in enumerate(node.pop("allOf")):
                if "if" in branch:
                    manifest.append(
                        {
                            "path": path,
                            "keyword": "conditional_allOf",
                            "validation": "canonical_only",
                        }
                    )
                    continue
                base = expand(branch, f"{path}/allOf/{index}", refs)
                for key, value in base.items():
                    if key in node and node[key] != value:
                        raise ToolError(
                            "SCHEMA_UNSUPPORTED", "Không gộp được allOf mà giữ nguyên điều kiện."
                        )
                    node[key] = value
        if "oneOf" in node:
            branches = node.pop("oneOf")
            tags = [b.get("properties", {}).get("type", {}) for b in branches]
            sets = [set(t.get("enum", [t["const"]] if "const" in t else [])) for t in tags]
            if (
                not all(sets)
                or any("type" not in b.get("required", []) for b in branches)
                or any(a & b for i, a in enumerate(sets) for b in sets[i + 1 :])
            ):
                raise ToolError("SCHEMA_UNSUPPORTED", "oneOf không có discriminator loại trừ nhau.")
            node["anyOf"] = branches
            manifest.append(
                {"path": path, "keyword": "oneOf", "conversion": "disjoint_discriminator_anyOf"}
            )
        # answer.anyOf is an assertion on fields, not a shape union. Keep in full validator.
        if "anyOf" in node and "properties" in node:
            manifest.append(
                {"path": path, "keyword": "anyOf_field_assertion", "validation": "canonical_only"}
            )
            node.pop("anyOf")
        if "const" in node:
            value = node.pop("const")
            if isinstance(value, dict):
                node.update(
                    type="object",
                    properties={k: {"const": v} for k, v in value.items()},
                    required=list(value),
                    additionalProperties=False,
                )
            elif isinstance(value, list):
                node.update(
                    type="array", items={"type": "string"}, minItems=len(value), maxItems=len(value)
                )
                manifest.append(
                    {"path": path, "keyword": "const_array", "validation": "canonical_only"}
                )
            else:
                node["enum"] = [value]
                node.setdefault("type", "boolean" if isinstance(value, bool) else "string")
        out = {}
        for key, value in node.items():
            if key in {"$schema", "$defs"}:
                continue
            if key in deferred:
                manifest.append({"path": path, "keyword": key, "validation": "canonical_only"})
            elif key not in allowed:
                raise ToolError(
                    "SCHEMA_UNSUPPORTED",
                    "Schema có keyword chưa được adapter hỗ trợ.",
                    [{"path": path, "keyword": key}],
                )
            elif key == "properties":
                out[key] = {k: expand(v, f"{path}/properties/{k}", refs) for k, v in value.items()}
            elif key == "items":
                out[key] = expand(value, path + "/items", refs)
            elif key == "anyOf":
                out[key] = [expand(v, f"{path}/anyOf/{i}", refs) for i, v in enumerate(value)]
            else:
                out[key] = value
        return out

    schema = remove_owned(expand(canonical))
    manifest.extend({"path": "/" + "/".join(path), "ownership": "script"} for path in OWNED)
    return schema, manifest
