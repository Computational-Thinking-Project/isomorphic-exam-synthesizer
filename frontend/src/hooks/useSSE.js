import { useCallback, useEffect, useRef, useState } from 'react';
import { requestEventTicket } from '../services/stage2Service.js';

/**
 * Custom Hook quản lý kết nối Server-Sent Events (SSE) cho tiến trình sinh đề bất đồng bộ.
 *
 * Tuân thủ bảo mật và kiến trúc:
 * - SEC-05 / SEC-13: Ticket handshake dùng 1 lần (TTL 60s), không lưu persistent storage.
 * - P1.6: Tự động xin lại ticket mới và tái kết nối kèm last_event_id khi rớt mạng.
 * - Phân biệt rành mạch giữa Lỗi nghiệp vụ máy chủ (Job Error - dừng ngay) và Lỗi kết nối mạng (Network Error - reconnect).
 * - Cô lập phiên làm việc hoàn toàn: huỷ các ticket trả muộn, chặn rò rỉ state/stream giữa phiên A và B.
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

  // Bộ định danh phiên và lượt kết nối để cô lập tuyệt đối tác vụ
  const activeSessionIdRef = useRef(sessionId);
  const connectionTokenRef = useRef(0);

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
    const currentToken = ++connectionTokenRef.current;
    const currentSessionId = sessionId;

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
      // Kiểm tra xem lượt gọi này còn hợp lệ không trước khi tiếp tục
      if (
        !isMountedRef.current ||
        connectionTokenRef.current !== currentToken ||
        activeSessionIdRef.current !== currentSessionId ||
        !enabled
      ) {
        return;
      }

      ticket = ticketRes?.ticket;
      if (!ticket) {
        throw new Error('Không nhận được ticket xác thực từ máy chủ.');
      }
    } catch (ticketError) {
      if (
        !isMountedRef.current ||
        connectionTokenRef.current !== currentToken ||
        activeSessionIdRef.current !== currentSessionId ||
        !enabled
      ) {
        return;
      }

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

    if (
      !isMountedRef.current ||
      connectionTokenRef.current !== currentToken ||
      activeSessionIdRef.current !== currentSessionId ||
      !enabled
    ) {
      return;
    }

    let url = `/api/sessions/${encodeURIComponent(sessionId)}/events?ticket=${encodeURIComponent(ticket)}`;
    if (lastEventIdRef.current) {
      url += `&last_event_id=${encodeURIComponent(lastEventIdRef.current)}`;
    }

    let es;
    try {
      es = callbacksRef.current.eventSourceFactory(url);
      eventSourceRef.current = es;
    } catch (createError) {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
      setConnectionState('failed');
      setError('Trình duyệt không thể khởi tạo kết nối EventSource.');
      callbacksRef.current.onError?.(createError);
      return;
    }

    es.onopen = () => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
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

    // Handler xử lý lỗi nghiệp vụ từ job AI / máy chủ (terminal state - không reconnect)
    const handleJobError = (payloadOrEvent) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
      const data = payloadOrEvent?.data !== undefined ? parsePayload(payloadOrEvent) : payloadOrEvent;
      const errorMsg =
        data?.error_message ||
        data?.message ||
        data?.detail ||
        (typeof data?.error === 'string' ? data.error : null) ||
        (typeof data === 'string' ? data : null) ||
        'Tiến trình sinh đề bị lỗi từ máy chủ.';

      isDoneRef.current = true;
      cleanupConnection();
      setConnectionState('failed');
      setError(errorMsg);
      callbacksRef.current.onError?.(data || new Error(errorMsg));
    };

    // 1. Lắng nghe sự kiện progress (hỗ trợ cả percent_complete và percent theo TASK-207b)
    es.addEventListener('progress', (e) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
      const data = parsePayload(e);
      if (data) {
        const percentVal = data.percent_complete ?? data.percent;
        setProgress((prev) => ({
          percent: percentVal !== undefined ? percentVal : prev.percent,
          completedCount: data.completed_count ?? data.completedCount ?? prev.completedCount,
          totalCount: data.total_count ?? data.totalCount ?? prev.totalCount,
          message: data.message ?? prev.message,
          estimatedSeconds: data.estimated_seconds ?? data.estimatedSeconds ?? prev.estimatedSeconds,
        }));

        // Hỗ trợ cập nhật trạng thái câu hỏi trực tiếp trong payload progress
        const qList = Array.isArray(data.questions)
          ? data.questions
          : Array.isArray(data.question_statuses)
          ? data.question_statuses
          : data.question_no && data.version_index
          ? [data]
          : null;

        if (qList && qList.length > 0) {
          setQuestionStatuses((prev) => {
            const next = { ...prev };
            qList.forEach((q) => {
              if (q.version_index && q.question_no) {
                const key = `${q.version_index}-${q.question_no}`;
                next[key] = {
                  version_index: q.version_index,
                  question_no: q.question_no,
                  status: q.status || next[key]?.status || 'generating',
                  message: q.message ?? next[key]?.message ?? '',
                  variant_id: q.variant_id ?? next[key]?.variant_id,
                };
              }
            });
            return next;
          });
        }

        callbacksRef.current.onProgress?.(data);
      }
    });

    // 2. Lắng nghe cập nhật trạng thái từng câu hỏi (question_status)
    const handleQuestionStatus = (e) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
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

    // 3. Lắng nghe sự kiện khi 1 câu hỏi sinh hoàn tất (question_done)
    es.addEventListener('question_done', (e) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
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

    // 4. Lắng nghe cảnh báo nghiệp vụ (warning)
    es.addEventListener('warning', (e) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
      const data = parsePayload(e);
      if (data) {
        setWarnings((prev) => [...prev, data]);
      }
    });

    // 5. Lắng nghe sự kiện lỗi job từ server (error, job_error, failed)
    es.addEventListener('error', (e) => {
      if (e?.data) {
        handleJobError(e);
      }
    });
    es.addEventListener('job_error', handleJobError);
    es.addEventListener('failed', handleJobError);

    // 6. Lắng nghe sự kiện kết thúc tiến trình (done)
    es.addEventListener('done', (e) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken) return;
      const data = parsePayload(e);
      isDoneRef.current = true;
      setIsDone(true);
      setConnectionState('completed');

      const isPartial =
        data?.session_status === 'partial_generated' ||
        data?.status === 'partial_generated' ||
        (data?.percent_complete !== undefined && data.percent_complete < 100) ||
        (data?.percent !== undefined && data.percent < 100);

      setProgress((prev) => {
        const currentCompleted =
          data?.completed_count ?? data?.completedCount ?? prev.completedCount ?? 0;
        const currentTotal =
          data?.total_count ?? data?.totalCount ?? prev.totalCount ?? null;
        const currentPercent =
          data?.percent_complete ??
          data?.percent ??
          (isPartial ? (prev.percent ?? 50) : 100);

        return {
          ...prev,
          percent: currentPercent,
          completedCount: currentCompleted,
          totalCount: currentTotal,
          session_status:
            data?.session_status || data?.status || (isPartial ? 'partial_generated' : 'generated'),
          is_partial: isPartial,
          message:
            data?.message ||
            (isPartial
              ? `Tiến trình kết thúc ở trạng thái sinh một phần (partial_generated). Đã sinh được ${currentCompleted}${
                  currentTotal ? ` / ${currentTotal}` : ''
                } câu.`
              : 'Hoàn tất quá trình sinh các mã đề!'),
        };
      });
      cleanupConnection();
      callbacksRef.current.onDone?.(data);
    });

    // 7. Xử lý rớt mạng thực sự (onerror không có payload data)
    es.onerror = (err) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken || isDoneRef.current) return;

      if (err?.data) {
        handleJobError(err);
        return;
      }

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

  // Kích hoạt kết nối và RESET state sạch sẽ khi sessionId hoặc enabled thay đổi
  useEffect(() => {
    isMountedRef.current = true;
    activeSessionIdRef.current = sessionId;
    connectionTokenRef.current += 1;
    isDoneRef.current = false;
    reconnectAttemptRef.current = 0;

    // Reset sạch sẽ trạng thái của phiên cũ để tránh rò rỉ sang phiên mới
    setProgress({
      percent: 0,
      completedCount: 0,
      totalCount: 0,
      message: '',
      estimatedSeconds: null,
    });
    setQuestionStatuses({});
    setWarnings([]);
    setError(null);
    setIsDone(false);
    setReconnectCount(0);
    lastEventIdRef.current = null;

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

  // Hàm thủ công cho phép người dùng bấm "Kết nối lại" hoặc kích hoạt vòng theo dõi mới khi sinh bù trong cùng một phiên
  const manualReconnect = useCallback(() => {
    isDoneRef.current = false;
    setIsDone(false);
    reconnectAttemptRef.current = 0;
    setReconnectCount(0);
    setError(null);
    // Giữ nguyên lastEventIdRef.current của phiên hiện tại để tiếp tục mốc sự kiện đã nhận,
    // tránh bị từ chối do backend broker chỉ lưu buffer giới hạn (ví dụ: 50 sự kiện gần nhất).
    setProgress((prev) => ({
      ...prev,
      session_status: 'generating',
      is_partial: false,
      message: 'Đang kết nối lại tiến trình sinh đề...',
    }));
    connect();
  }, [connect]);

  const isPartial = Boolean(
    progress.is_partial ||
      progress.session_status === 'partial_generated' ||
      (isDone && (progress.percent ?? 100) < 100),
  );

  return {
    connectionState,
    progress,
    questionStatuses,
    warnings,
    error,
    isDone,
    isPartial,
    reconnectCount,
    reconnect: manualReconnect,
    manualReconnect,
  };
}
