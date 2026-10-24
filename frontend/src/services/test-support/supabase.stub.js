// Chỉ được nạp bởi loader của bộ test, không thuộc luồng chạy ứng dụng.
function unexpectedAuthCall() {
    throw new Error('Test chưa cấu hình phương thức Auth này.');
}

export const auth = {
    getSession: unexpectedAuthCall,
    refreshSession: unexpectedAuthCall,
};

export function getSupabase() {
    return { auth };
}
