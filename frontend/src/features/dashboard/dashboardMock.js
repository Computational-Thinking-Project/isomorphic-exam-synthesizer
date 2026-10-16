const mockSessions = [
    {
        id: 'mock-session-001',
        title: 'Đề mẫu — Tích phân',
        subject: 'Toán',
        created_at: '2026-10-16T02:00:00Z',
        status: 'draft',
    },
    {
        id: 'mock-session-002',
        title: 'Đề mẫu — Xác suất',
        subject: 'Toán',
        created_at: '2026-10-15T07:30:00Z',
        status: 'approved',
    },
    {
        id: 'mock-session-003',
        title: 'Đề mẫu — Hàm số',
        subject: 'Toán',
        created_at: '2026-10-14T03:00:00Z',
        status: 'exported',
    },
];

export async function listDashboardSessions({
    scenario = 'success',
} = {}) {
    // Độ trễ mẫu để thử trạng thái loading của giao diện.
    await new Promise((resolve) => setTimeout(resolve, 400));

    if (scenario === 'error') {
        throw new Error('Không tải được danh sách mẫu. Vui lòng thử lại.');
    }

    if (scenario === 'empty') {
        return [];
    }

    // Mỗi lần gọi trả bản sao để không sửa nhầm fixture dùng chung.
    return mockSessions.map((session) => ({ ...session }));
}