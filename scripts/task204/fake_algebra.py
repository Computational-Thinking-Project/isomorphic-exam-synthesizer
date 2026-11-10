"""Deterministic P4-only canonical producer for 2x+1=5; never calls a provider."""
import json
from pathlib import Path


class FakeAlgebra:
    def __init__(self, values=False):
        self.values = values

    async def extract_confirmed(self, items, **kwargs):
        item = items[0]
        if len(items) != 1 or item["source"]["content"][0]["text"] != "Giải phương trình 2x + 1 = 5.":
            raise ValueError("P4 fake producer only accepts its explicit algebra fixture")
        template = Path(__file__).resolve().parents[2] / "backend/tests/fixtures/ai_pipeline.json"
        blueprint = json.loads(template.read_text(encoding="utf-8"))["blueprint"]
        req = blueprint["requirement"]
        req["blueprint_id"] = "task204_linear_fixture"
        req["source"] = item["source"]
        req["assessment"] = {"id": "R_ASSESSMENT", "objective": "Giải phương trình bậc nhất.",
            "knowledge": ["Phương trình bậc nhất"], "cognitive_operations": ["Chuyển vế", "Chia hai vế"],
            "prerequisites": ["Phép tính số học"]}
        req["knowledge_basis"] = [{"id": "K_LINEAR", "description": "Thực hiện cùng phép toán trên hai vế.",
                                   "origin": "inferred", "evidence_refs": []}]
        req["semantic_model"] = {"id": "R_MODEL", "entities": [{"id": "E_X", "kind": "abstract_object",
            "description": "Ẩn số thực x."}], "quantities": [{"id": "Q_X", "symbol": "x", "description": "Nghiệm.",
            "role": "unknown", "value": None, "unit": None}], "relations": [{"id": "REL_EQ",
            "description": "Phương trình nguồn.", "role": "given", "formalism": "math_expression",
            "expression": "2*x+1=5", "refs": ["Q_X"]}], "assumptions": [],
            "target": {"id": "TARGET", "description": "Tìm x.", "quantity_ref": "Q_X"}}
        req["reasoning_model"] = {"id": "R_REASONING", "steps": [
            {"id": "STEP1", "description": "Trừ 1: 2x=4.", "depends_on": []},
            {"id": "STEP2", "description": "Chia 2: x=2.", "depends_on": ["STEP1"]}],
            "accepted_alternatives": ["Thế từng đáp án."], "forbidden_shortcuts": []}
        req["invariants"] = [{"id": "I_LINEAR", "category": "relations", "description": "Giữ phương trình bậc nhất."}]
        req["variation_policy"] = {"id": "R_VARIATION", "equivalence_level": "strict_structure",
            "allowed_transformations": [{"id": "V_ORDER", "dimension": "option_order",
                "description": "Hoán vị phương án và giữ ánh xạ đáp án.",
                "target_refs": [item["source"]["content"][0]["id"]], "preconditions": [], "limits": []}],
            "parameter_domains": [], "forbidden_changes": [], "workload_limits": []}
        if self.values:
            req["variation_policy"]["allowed_transformations"] = [{"id": "V_VALUES", "dimension": "values",
                "description": "Đổi hệ số và tính lại nghiệm.", "target_refs": ["REL_EQ"],
                "preconditions": ["Hệ số của x khác không."], "limits": []}]
        req["response_spec"]["distractor_policy"] = {"error_models": ["Chuyển vế sai dấu."],
                                                   "rules": ["Bốn phương án phân biệt, một đáp án đúng."]}
        blueprint["constraint"]["source_check"] = {"computed_answer": {"option_ids": item["source"]["supplied_answer"]["option_ids"],
            "value": {"type": "integer", "value": 2}, "explanation": "2*2+1=5."}, "methods": [], "evidence": []}
        blueprint["constraint"]["rules"] = [{"id": "C_LINEAR", "requirement_refs": ["I_LINEAR"],
            "scope": "candidate", "severity": "required", "description": "Kiểm nghiệm.",
            "verification_methods": ["exact_math"], "pass_criteria": "Thế x=2 thỏa phương trình.", "on_failure": "reject"}]
        from app.services.blueprint.common import load_json
        from app.services.blueprint.config import Config
        from app.services.blueprint.validators import validate_blueprint
        issues = validate_blueprint(blueprint, load_json(Config().schema_path), item["source"], item["context"])
        if issues:
            raise ValueError(json.dumps(issues, ensure_ascii=True))
        return [{"blueprint": blueprint}], []
