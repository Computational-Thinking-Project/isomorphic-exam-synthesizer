"""Local schema registry and global input preflight; no network schema resolution."""

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .common import TOOL_DIR, ToolError, load_json
from .validators import ID

SCIENCE_URI = "urn:blueprint:science:0.4.0"


class Contracts:
    def __init__(self, canonical):
        self.single = load_json(TOOL_DIR / "contracts/single-input.schema.json")
        self.batch = load_json(TOOL_DIR / "contracts/batch-input.schema.json")
        self.result = load_json(TOOL_DIR / "contracts/result.schema.json")
        schemas = [
            (SCIENCE_URI, canonical),
            *[(schema["$id"], schema) for schema in (self.single, self.batch, self.result)],
        ]
        for _, schema in schemas:
            Draft202012Validator.check_schema(schema)
        self.registry = Registry(retrieve=self.reject_external).with_resources(
            [(uri, Resource.from_contents(schema)) for uri, schema in schemas]
        )

    @staticmethod
    def reject_external(uri):
        from referencing.exceptions import NoSuchResource

        raise NoSuchResource(ref=uri)


def question_id(item):
    value = (
        item.get("source", {}).get("question_id")
        if isinstance(item, dict) and isinstance(item.get("source"), dict)
        else None
    )
    return value if isinstance(value, str) and ID.fullmatch(value) else None


def input_items(raw, mode):
    if mode == "single":
        if not isinstance(raw, dict) or "questions" in raw:
            raise ToolError("INPUT_SHAPE", "Mode single nhận một object source/context.")
        items = [raw]
    else:
        if (
            not isinstance(raw, dict)
            or set(raw) != {"questions"}
            or not isinstance(raw["questions"], list)
            or not raw["questions"]
        ):
            raise ToolError(
                "INPUT_SHAPE", "Mode batch nhận object questions là danh sách không rỗng."
            )
        items = raw["questions"]
    found = set()
    for item in items:
        qid = question_id(item)
        if qid is not None:
            if qid in found:
                raise ToolError("DUPLICATE_QUESTION_ID", "question_id phải duy nhất trong batch.")
            found.add(qid)
    return items
