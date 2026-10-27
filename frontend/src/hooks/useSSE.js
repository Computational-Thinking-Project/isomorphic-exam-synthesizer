import { useCallback, useEffect, useRef, useState } from 'react';
import { requestEventTicket } from '../services/stage2Service.js';

/**
 * Custom Hook quản lý kết nối Server-Sent Events (SSE) cho tiến trình sinh đề bất đồng bộ.
 *
 * Tuân thủ bảo mật và kiến trúc:
 * - SEC-05 / SEC-13: Ticket handshake dùng 1 lần (TTL 60s), không lưu persistent storage.
 * - P1.6: Tự động xin lại ticket mới và tái kết nối kèm last_event_id khi rớt mạng.
 * - Dọn dẹp kết nối an toàn khi unmount hoặc khi hoàn thành (done).
 */
export function useSSE(sessionId, {
  enabled = true,
  requestTicket = requestEventTicket,
  eventSourceFactory = (url) => new EventSource(url),
  maxReconnectAttempts = 5,
  onProgress,
  onQuestionStatus,
  onDone,
  onError,
} = {}) {
  const [connectionState, setConnectionState] = useState('idle');
  // 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'completed' | 'disconnected' | 'failed'

  const [progress, setProgress] = useState({
    percent: 0,
    completedCount: 0,
    totalCount: 0,
    message: '',
    estimatedSeconds: null,
  });

  const [questionStatuses, setQuestionStatuses] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [error, setError] = useState(null);
  const [isDone, setIsDone] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);

  const eventSourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const lastEventIdRef = useRef(null);
  const isMountedRef = useRef(true);
  const reconnectAttemptRef = useRef(0);
  const isDoneRef = useRef(false);

  // Safe callback refs to avoid re-triggering effects
  const callbacksRef = useRef({
    onProgress,
    onQuestionStatus,
    onDone,
    onError,
    requestTicket,
    eventSourceFactory,
  });

  useEffect(() => {
    callbacksRef.current = {
      onProgress,
      onQuestionStatus,
      onDone,
      onError,
      requestTicket,
      eventSourceFactory,
    };
  });

  const cleanupConnection = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (eventSourceRef.current) {
      try {
        eventSourceRef.current.close();
      } catch {
        // Bỏ qua lỗi khi đóng kết nối đã hủy
      }
      eventSourceRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!isMountedRef.current || !sessionId || !enabled || isDoneRef.current) {
      return;
    }

    cleanupConnection();

    if (reconnectAttemptRef.current > 0) {
      setConnectionState('reconnecting');
    } else {
      setConnectionState('connecting');
    }
    setError(null);

    let ticket;
    try {
      const ticketRes = await callbacksRef.current.requestTicket(sessionId);
      ticket = ticketRes?.ticket;
      if (!ticket) {
        throw new Error('Không nhận được ticket xác thực từ máy chủ.');
      }
    } catch (ticketError) {
      if (!isMountedRef.current) return;

      const message = ticketError?.message || 'Không thể xin ticket kết nối tiến trình.';
      if (reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current += 1;
        setReconnectCount(reconnectAttemptRef.current);
        const delay = Math.min(1000 * 2 ** (reconnectAttemptRef.current - 1), 8000);
        reconnectTimerRef.current = setTimeout(connect, delay);
        return;
      }

      setConnectionState('failed');
      setError(message);
      callbacksRef.current.onError?.(ticketError);
      return;
    }

    if (!isMountedRef.current) return;

    let url = `/api/sessions/${encodeURIComponent(sessionId)}/events?ticket=${encodeURIComponent(ticket)}`;
    if (lastEventIdRef.current) {
      url += `&last_event_id=${encodeURIComponent(lastEventIdRef.current)}`;
    }

    let es;
    try {
      es = callbacksRef.current.eventSourceFactory(url);
      eventSourceRef.current = es;
    } catch (createError) {
      if (!isMountedRef.current) return;
      setConnectionState('failed');
      setError('Trình duyệt không thể khởi tạo kết nối EventSource.');
      callbacksRef.current.onError?.(createError);
      return;
    }

    es.onopen = () => {
      if (!isMountedRef.current) return;
      setConnectionState('connected');
      reconnectAttemptRef.current = 0;
      setReconnectCount(0);
    };

    const recordLastId = (event) => {
      if (event?.lastEventId) {
        lastEventIdRef.current = event.lastEventId;
      }
    };

    const parsePayload = (event) => {
      recordLastId(event);
      if (!event?.data) return null;
      try {
        const parsed = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (parsed?.event_id) {
          lastEventIdRef.current = parsed.event_id;
        }
        return parsed;
      } catch {
        return event.data;
      }
    };

    // Lắng nghe sự kiện progress
    es.addEventListener('progress', (e) => {
      if (!isMountedRef.current) return;
      const data = parsePayload(e);
      if (data) {
        setProgress((prev) => ({
          percent: data.percent ?? prev.percent,
          completedCount: data.completed_count ?? prev.completedCount,
          totalCount: data.total_count ?? prev.totalCount,
          message: data.message ?? prev.message,
          estimatedSeconds: data.estimated_seconds ?? prev.estimatedSeconds,
        }));
        callbacksRef.current.onProgress?.(data);
      }
    });

    // Lắng nghe cập nhật trạng thái từng câu hỏi
    const handleQuestionStatus = (e) => {
      if (!isMountedRef.current) return;
      const data = parsePayload(e);
      if (data && data.version_index && data.question_no) {
        const key = `${data.version_index}-${data.question_no}`;
        setQuestionStatuses((prev) => ({
          ...prev,
          [key]: {
            version_index: data.version_index,
            question_no: data.question_no,
            status: data.status, // 'analyzing' | 'generating' | 'validating' | 'retrying' | 'done'
            message: data.message,
          },
        }));
        callbacksRef.current.onQuestionStatus?.(data);
      }
    };
    es.addEventListener('question_status', handleQuestionStatus);

    // Lắng nghe sự kiện khi 1 câu hỏi sinh hoàn tất
    es.addEventListener('question_done', (e) => {
      if (!isMountedRef.current) return;
      const data = parsePayload(e);
      if (data && data.version_index && data.question_no) {
        const key = `${data.version_index}-${data.question_no}`;
        setQuestionStatuses((prev) => ({
          ...prev,
          [key]: {
            version_index: data.version_index,
            question_no: data.question_no,
            status: 'done',
            message: 'Đã hoàn thành',
            variant_id: data.variant_id,
          },
        }));
      }
    });

    // Lắng nghe cảnh báo
    es.addEventListener('warning', (e) => {
      if (!isMountedRef.current) return;
      const data = parsePayload(e);
      if (data) {
        setWarnings((prev) => [...prev, data]);
      }
    });

    // Lắng nghe sự kiện hoàn tất toàn bộ tiến trình
    es.addEventListener('done', (e) => {
      if (!isMountedRef.current) return;
      const data = parsePayload(e);
      isDoneRef.current = true;
      setIsDone(true);
      setConnectionState('completed');
      setProgress((prev) => ({
        ...prev,
        percent: 100,
        message: 'Hoàn tất quá trình sinh các mã đề!',
      }));
      cleanupConnection();
      callbacksRef.current.onDone?.(data);
    });

    // Xử lý lỗi và cơ chế Reconnect thông minh
    es.onerror = (err) => {
      if (!isMountedRef.current || isDoneRef.current) return;

      cleanupConnection();

      if (reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current += 1;
        setReconnectCount(reconnectAttemptRef.current);
        setConnectionState('reconnecting');
        const delay = Math.min(1000 * 2 ** (reconnectAttemptRef.current - 1), 8000);
        reconnectTimerRef.current = setTimeout(connect, delay);
      } else {
        setConnectionState('disconnected');
        setError('Mất kết nối với máy chủ sau nhiều lần thử lại. Bạn có thể bấm Kết nối lại.');
        callbacksRef.current.onError?.(err);
      }
    };
  }, [sessionId, enabled, maxReconnectAttempts, cleanupConnection]);

  // Kích hoạt kết nối khi mount hoặc khi sessionId / enabled thay đổi
  useEffect(() => {
    isMountedRef.current = true;
    isDoneRef.current = false;
    reconnectAttemptRef.current = 0;

    if (enabled && sessionId) {
      connect();
    } else {
      cleanupConnection();
      setConnectionState('idle');
    }

    return () => {
      isMountedRef.current = false;
      cleanupConnection();
    };
  }, [sessionId, enabled, connect, cleanupConnection]);

  // Hàm thủ công cho phép người dùng bấm "Kết nối lại" trên giao diện
  const manualReconnect = useCallback(() => {
    isDoneRef.current = false;
    reconnectAttemptRef.current = 0;
    setReconnectCount(0);
    setError(null);
    connect();
  }, [connect]);

  return {
    connectionState,
    progress,
    questionStatuses,
    warnings,
    error,
    isDone,
    reconnectCount,
    reconnect: manualReconnect,
  };
}
