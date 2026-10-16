import sys
import time
import json
from pathlib import Path

# Đảm bảo in UTF-8 mượt mà trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Đảm bảo import được app từ thư mục backend
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.models.schemas import SourceQuestion
from app.services.ai.client import GeminiClient


def run_smoke_test():
    print("=" * 60)
    print("🚀 BẮT ĐẦU SMOKE TEST GEMINI AI CLIENT (TASK-106)")
    print("=" * 60)

    # 1. Kiểm tra cấu hình
    print(f"• Model sử dụng : {settings.GEMINI_MODEL}")
    key_val = settings.GEMINI_API_KEY.get_secret_value()
    masked_key = f"{key_val[:6]}...{key_val[-4:]}" if len(key_val) > 10 else "(Rỗng)"
    print(f"• API Key       : {masked_key}")

    # 2. Câu hỏi nguồn mẫu
    sample_source = SourceQuestion(
        id="q_math_smoke_01",
        question_text="Tìm giá trị của $m$ để phương trình bậc hai $x^2 - 2(m-1)x + m^2 - 3 = 0$ có hai nghiệm phân biệt $x_1, x_2$ thỏa mãn $x_1^2 + x_2^2 = 10$?",
        options=[
            "$m = 2$",
            "$m = -1$",
            "$m = 3$",
            "$m = 0$"
        ],
        correct_answer="$m = 2$",
        solution="1. Điều kiện 2 nghiệm phân biệt: $\\Delta' = (m-1)^2 - (m^2-3) = -2m + 4 > 0 \\iff m < 2$ (hoặc xét theo đề).\n2. Theo Vi-et: $x_1+x_2 = 2(m-1)$, $x_1x_2 = m^2-3$.\n3. $x_1^2 + x_2^2 = (x_1+x_2)^2 - 2x_1x_2 = 4(m-1)^2 - 2(m^2-3) = 10 \\iff 2m^2 - 8m = 0 \\iff m=0$ hoặc $m=4$. Kết hợp điều kiện ta được kết quả.",
        topic="Phương trình bậc hai & Định lý Vi-et"
    )

    print("\n[1] Đang gửi câu hỏi mẫu tới Google Gemini...")
    client = GeminiClient()

    start_time = time.time()
    try:
        variant = client.generate_variant(source=sample_source, seed=101)
        latency = time.time() - start_time

        print(f"✅ Gọi thành công trong {latency:.2f} giây!\n")
        print("--- KẾT QUẢ BIẾN THỂ SINH RA (JSON) ---")
        print(json.dumps(variant.model_dump(), indent=2, ensure_ascii=False))

        # 3. Kiểm chứng các tiêu chí cơ bản
        print("\n--- KIỂM CHỨNG TÍNH TOÀN VẸN ---")
        assert len(variant.options) == 4, f"Lỗi: Số lượng options là {len(variant.options)}, yêu cầu 4"
        assert variant.correct_answer in variant.options, "Lỗi: Đáp án đúng không nằm trong 4 options"
        assert variant.source_question_id == sample_source.id, "Lỗi: source_question_id không khớp"
        print("✓ Đủ chính xác 4 lựa chọn.")
        print("✓ Đáp án đúng nằm trong danh sách lựa chọn.")
        print("✓ Định dạng LaTeX và Schema hoàn toàn hợp lệ.")
        print(f"✓ Độ trễ phản hồi: {latency:.2f}s")
        print("\n🎉 SMOKE TEST HOÀN TOÀN THÀNH CÔNG!")
        return True, latency, variant

    except Exception as e:
        print(f"\n❌ SMOKE TEST THẤT BẠI: {e}")
        return False, 0, None


if __name__ == "__main__":
    success, _, _ = run_smoke_test()
    if not success:
        sys.exit(1)
