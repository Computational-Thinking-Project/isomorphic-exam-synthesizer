"""Opt-in live demo: python backend/scripts/demo_ai_live.py --live.

Uses configured Gemini credentials, at most ten requests, and writes local reports.
No routes, shared DB or teacher account state is changed.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.models.schemas import SourceQuestion  # noqa: E402
from app.services.ai.gateway import GeminiGateway, RequestBudget, RequestContext  # noqa: E402
from app.services.blueprint.adapters import prepare_sources  # noqa: E402
from app.services.blueprint.service import BlueprintService, source_fingerprint  # noqa: E402
from app.services.generation.service import GenerationService  # noqa: E402


async def main(resume: bool):
    root = Path(__file__).resolve().parents[2]
    source = SourceQuestion(
        id="live-demo-quadratic-01", question_text="Giải phương trình $x^2-5x+6=0$.",
        options=["2 và 3", "-2 và -3", "1 và 6", "-1 và -6"], correct_answer="A",
        solution="Phân tích thành $(x-2)(x-3)=0$, suy ra x=2 hoặc x=3.",
        topic="Phương trình bậc hai",
    )
    budget = RequestBudget(10)
    context = RequestContext(time.monotonic() + 600, budget.reserve)
    confirmed = source_fingerprint(prepare_sources([source]))
    settings = Settings(_env_file=root / ".env")
    ready = None
    saved_file = root / "outputs/blueprint/ai-live-demo.json"
    if resume and saved_file.exists():
        saved = json.loads(saved_file.read_text(encoding="utf-8"))
        if saved["source"] == source.model_dump() and saved["model"] == settings.GEMINI_MODEL:
            ready = {result["source_question_id"]: result for result in saved["blueprints"]
                     if result["blueprint"] is not None and result["error"] is None}
    output = {"mode": "live Gemini", "model": settings.GEMINI_MODEL,
              "source": source.model_dump(), "source_confirmation": "demo source confirmed locally"}
    async with GeminiGateway(settings) as gateway:
        print("Extracting Blueprint from confirmed source...", flush=True)
        results, metadata = await BlueprintService(gateway).extract_sources(
            [source], confirmed_source_hash=confirmed, context=context, ready=ready)
        output.update(blueprints=results, extraction_metadata=metadata)
        if results[0]["blueprint"] is not None:
            print("Generating two variants with answers and solutions...", flush=True)
            drafts = await GenerationService(gateway).generate_exam_drafts(
                [source], {source.id: results[0]["blueprint"]}, confirmed_source_hash=confirmed,
                n_versions=2, context=context)
            output["drafts"] = drafts.model_dump()
    output["reserved_requests"] = budget.used
    directory = root / "outputs/blueprint"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "ai-live-demo.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Demo Gemini thật — sinh hai câu theo cùng Blueprint", "",
             f"Model: `{settings.GEMINI_MODEL}` · Lượt cấp quota: **{budget.used}/10**.", "",
             "Chạy module AI thật; chưa đi qua UI/DB. Nguồn mẫu được xác nhận cục bộ trước khi gọi Blueprint.", "",
             "## 1. Đề nguồn đã xác nhận", "", source.question_text, ""]
    lines += [f"- **{key}.** {text}" for key, text in zip("ABCD", source.options, strict=True)]
    lines += ["", "Đáp án nguồn: **A — 2 và 3**.", "", source.solution, "",
              "## 2. Blueprint", ""]
    blueprint = results[0]["blueprint"]
    if blueprint is None:
        lines += ["Chưa tạo được Blueprint; pipeline dừng trước sinh đề.", "", "```json",
                  json.dumps(results[0]["error"], ensure_ascii=False, indent=2), "```"]
    else:
        # Show the exact stored policy rather than a second AI-generated summary.
        lines += ["Giữ nguyên Blueprint này cho cả hai mã đề. Quy tắc thay đổi do Gemini trích xuất:", "", "```json",
                  json.dumps(blueprint["requirement"]["variation_policy"], ensure_ascii=False, indent=2), "```", ""]
        for result in output["drafts"]["results"]:
            lines += [f"## 3.{result['version_index']}. Câu sinh cho mã {result['version_index']:02}", ""]
            candidate = result["candidate"]
            if candidate is None:
                lines += [f"Chưa tạo thành công: `{result['error_code']}`.", ""]
                continue
            lines += [candidate["question_text"], ""]
            lines += [f"- **{key}.** {text}" for key, text in zip("ABCD", candidate["options"], strict=True)]
            lines += ["", f"**Đáp án Gemini: {candidate['correct_key']}**", "", candidate["solution_md"], "",
                      "| Kiểm tra | Kết quả |", "|---|---|"]
            for check in result["validation"]["checks"]:
                status = "Pass" if check["passed"] else check["status"] or "failed"
                lines.append(f"| {check['check_name']} | {status} |")
            lines += ["", "**Cần giáo viên duyệt.** Unknown/unsupported chưa được chứng minh đúng bởi checker.", ""]
    lines += ["", "Kết quả JSON đầy đủ: [ai-live-demo.json](ai-live-demo.json)."]
    report = directory / "ai-live-demo.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"requests": budget.used, "report": str(report),
                      "status": output.get("drafts", {}).get("status", "blueprint_failed")}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow live Gemini calls")
    parser.add_argument("--resume", action="store_true", help="Reuse an existing valid Blueprint")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to spend Gemini quota; otherwise use demo_ai_pipeline.py")
    asyncio.run(main(args.resume))
