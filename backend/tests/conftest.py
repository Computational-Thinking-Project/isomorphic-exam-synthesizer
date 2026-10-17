import sys
from pathlib import Path

# Đảm bảo thư mục backend luôn nằm trong sys.path khi chạy test từ bất kỳ thư mục nào
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
