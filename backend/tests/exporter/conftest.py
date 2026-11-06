from uuid import uuid4

import pytest

from app.services.exporter.bundle_models import ApprovedExportSnapshot


@pytest.fixture
def snapshot_data():
    # Option order is deliberately shuffled: answer C is 5, not canonical A.
    questions = [
        {
            "id": str(uuid4()),
            "question_no": 1,
            "content": r"Giải phương trình $x+2=7$.",
            "options": ["3", "4", "5", "6"],
            "correct_key": "C",
            "solution_md": r"$x=7-2=5$. Đáp án C.",
            "status": "approved",
        },
        {
            "id": str(uuid4()),
            "question_no": 2,
            "content": r"Tính $\frac{1}{2}+\frac{1}{2}$.",
            "options": ["0", "1", "2", "3"],
            "correct_key": "B",
            "solution_md": r"$\frac{1}{2}+\frac{1}{2}=1$. Đáp án B.",
            "status": "approved",
        },
    ]
    return {
        "session_id": str(uuid4()),
        "revision": "approved-revision-7",
        "title": "Đề Toán — lớp 10",
        "status": "approved",
        "versions": [{"code": "101", "questions": questions}],
    }


@pytest.fixture
def snapshot(snapshot_data):
    return ApprovedExportSnapshot.model_validate(snapshot_data)
