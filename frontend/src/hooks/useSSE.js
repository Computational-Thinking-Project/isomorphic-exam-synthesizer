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
 * - F04: Phục hồi mất lịch sử (single recovery flight, HTTP 409 diagnostic, resume_after_event_id & stream_epoch).
 * - F06: Loại bỏ kết quả trả muộn từ phiên A khi đã chuyển sang phiên B hoặc unmount.
 */
export function useSSE(sessionId, {
  enabled = true,
  initialProgress = null,
  initialQuestionStatuses = null,
  initialResumeAfterEventId = null,
  initialStreamEpoch = null,
  requestTicket = requestEventTicket,
  eventSourceFactory = (url) => new EventSource(url),
  maxReconnectAttempts = 5,
  onProgress,
  onQuestionStatus,
  onDone,
  onError,
  onResync,
} = {}) {
  const [connectionState, setConnectionState] = useState('idle');
  // 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'completed' | 'disconnected' | 'failed'

  const createDefaultProgress = (initial) => {
    if (initial) {
      return {
        hasData: initial.hasData ?? true,
        percent: initial.percent ?? (initial.percent_complete ?? 0),
        completedCount: initial.completedCount ?? (initial.completed_count ?? 0),
        totalCount: initial.totalCount ?? (initial.total_count ?? 0),
        message: initial.message || '',
        estimatedSeconds: initial.estimatedSeconds ?? (initial.estimated_seconds ?? null),
        session_status: initial.session_status || initial.status || null,
        is_partial: Boolean(initial.is_partial),
      };
    }
    return {
      hasData: false,
      percent: 0,
      completedCount: 0,
      totalCount: 0,
      message: '',
      estimatedSeconds: null,
      session_status: null,
      is_partial: false,
    };
  };

  // F02: Khởi tạo progress có cờ hasData để phân biệt snapshot thật với trạng thái rỗng chưa có dữ liệu
  const [progress, setProgress] = useState(() => createDefaultProgress(initialProgress));
  const [questionStatuses, setQuestionStatuses] = useState(() => initialQuestionStatuses || {});
  const [warnings, setWarnings] = useState([]);
  const [error, setError] = useState(null);
  const [isDone, setIsDone] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);

  const eventSourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const lastEventIdRef = useRef(
    initialResumeAfterEventId ?? initialProgress?.resume_after_event_id ?? null,
  );
  const epochRef = useRef(
    initialStreamEpoch ?? initialProgress?.stream_epoch ?? null,
  );
  const isMountedRef = useRef(true);
  const reconnectAttemptRef = useRef(0);
  const isDoneRef = useRef(false);
  const isRecoveringRef = useRef(false);
  const hasOpenedRef = useRef(false);
  const connectRef = useRef(null);
  const recoveryFlightTokenRef = useRef(0);

  // Bộ định danh phiên và lượt kết nối để cô lập tuyệt đối tác vụ
  const activeSessionIdRef = useRef(sessionId);
  const connectionTokenRef = useRef(0);
  const prevSessionIdRef = useRef(sessionId);
  const lastInitialProgressRef = useRef(initialProgress);
  const lastInitialStatusesRef = useRef(initialQuestionStatuses);

  // Safe callback refs to avoid re-triggering effects
  const callbacksRef = useRef({
    onProgress,
    onQuestionStatus,
    onDone,
    onError,
    onResync,
    requestTicket,
    eventSourceFactory,
  });

  useEffect(() => {
    callbacksRef.current = {
      onProgress,
      onQuestionStatus,
      onDone,
      onError,
      onResync,
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

  // F04 / F06: Quy trình phục hồi mất lịch sử duy nhất (Single-Flight Recovery Lock)
  const triggerRecovery = useCallback(async () => {
    if (isRecoveringRef.current || isDoneRef.current || !isMountedRef.current) {
      return;
    }
    isRecoveringRef.current = true;
    cleanupConnection();

    const currentToken = connectionTokenRef.current;
    const targetSessionId = activeSessionIdRef.current;
    const thisFlight = ++recoveryFlightTokenRef.current;

    try {
      if (callbacksRef.current.onResync) {
        const freshSnapshot = await callbacksRef.current.onResync(targetSessionId);

        // F06: Kiểm tra phiên, token kết nối và flight sau khi onResync hoàn tất (await network)
        // Nếu đã unmount, đổi phiên hoặc có lượt phục hồi mới -> HỦY BỎ kết quả snapshot cũ!
        if (
          !isMountedRef.current ||
          recoveryFlightTokenRef.current !== thisFlight ||
          connectionTokenRef.current !== currentToken ||
          activeSessionIdRef.current !== targetSessionId
        ) {
          isRecoveringRef.current = false;
          return;
        }

        if (freshSnapshot) {
          // Áp dụng mốc đồng bộ từ snapshot mới (resume_after_event_id, stream_epoch)
          if (
            freshSnapshot.resume_after_event_id !== undefined &&
            freshSnapshot.resume_after_event_id !== null
          ) {
            lastEventIdRef.current = freshSnapshot.resume_after_event_id;
          } else {
            lastEventIdRef.current = null;
          }

          if (
            freshSnapshot.stream_epoch !== undefined &&
            freshSnapshot.stream_epoch !== null
          ) {
            epochRef.current = freshSnapshot.stream_epoch;
          } else {
            epochRef.current = null;
          }

          if (freshSnapshot.progress) {
            setProgress((prev) => ({
              ...(prev || {}),
              hasData: true,
              ...freshSnapshot.progress,
            }));
          }

          if (freshSnapshot.question_statuses) {
            setQuestionStatuses((prev) => ({
              ...prev,
              ...freshSnapshot.question_statuses,
            }));
          }

          // F07 / F09: Chỉ hoàn tất ngay khi backend XÁC NHẬN generated (status hoặc session_status === 'generated').
          // Nếu backend vẫn là 'generating' (kể cả khi tiến độ đã 100%), KHÔNG đánh dấu done,
          // mà tiếp tục nối lại stream để lắng nghe sự kiện done hoặc lỗi máy chủ.
          const freshStatus =
            freshSnapshot.status ||
            freshSnapshot.session_status ||
            freshSnapshot.progress?.session_status ||
            freshSnapshot.progress?.status;

          const isSnapshotDone =
            String(freshStatus || '').trim().toLowerCase() === 'generated';

          if (isSnapshotDone) {
            isDoneRef.current = true;
            setIsDone(true);
            setConnectionState('completed');
            isRecoveringRef.current = false;
            callbacksRef.current.onDone?.(freshSnapshot);
            return;
          }
        }
      }

      // F06: Tái kiểm tra trước khi lên lịch kết nối lại
      if (
        !isMountedRef.current ||
        recoveryFlightTokenRef.current !== thisFlight ||
        connectionTokenRef.current !== currentToken ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        isRecoveringRef.current = false;
        return;
      }

      if (reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current += 1;
        setReconnectCount(reconnectAttemptRef.current);
        setConnectionState('reconnecting');
        reconnectTimerRef.current = setTimeout(() => {
          isRecoveringRef.current = false;
          connectRef.current?.();
        }, 600);
      } else {
        isRecoveringRef.current = false;
        setConnectionState('failed');
        setError('Mất lịch sử sự kiện và vượt quá số lần thử kết nối lại.');
      }
    } catch {
      isRecoveringRef.current = false;
      if (
        !isMountedRef.current ||
        recoveryFlightTokenRef.current !== thisFlight ||
        connectionTokenRef.current !== currentToken ||
        activeSessionIdRef.current !== targetSessionId
      ) {
        return;
      }

      if (reconnectAttemptRef.current < maxReconnectAttempts) {
        reconnectAttemptRef.current += 1;
        setReconnectCount(reconnectAttemptRef.current);
        setConnectionState('reconnecting');
        reconnectTimerRef.current = setTimeout(() => {
          connectRef.current?.();
        }, 1000);
      } else {
        setConnectionState('failed');
        setError('Không thể phục hồi tiến trình sau khi mất lịch sử sự kiện.');
      }
    }
  }, [cleanupConnection, maxReconnectAttempts]);

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
      const ticketRes = await callbacksRef.current.requestTicket(
        sessionId,
        lastEventIdRef.current,
        epochRef.current,
      );
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
      if (ticketRes?.reset_cursor) {
        lastEventIdRef.current = null;
        epochRef.current = null;
      }
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

      const status = ticketError?.response?.status ?? ticketError?.status;
      const isHistoryLostOrConflict =
        status === 409 ||
        ticketError?.code === 'ERR_CURSOR_OUTDATED' ||
        ticketError?.error_code === 'ERR_CURSOR_OUTDATED' ||
        ticketError?.code === 'ERR_EVENT_HISTORY_LOST' ||
        ticketError?.error_code === 'ERR_EVENT_HISTORY_LOST' ||
        ticketError?.reset_cursor === true;

      // F04: Nếu mất lịch sử hoặc xung đột con trỏ trước khi mở stream
      if (isHistoryLostOrConflict) {
        void triggerRecovery();
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
    if (lastEventIdRef.current !== null && lastEventIdRef.current !== undefined) {
      url += `&last_event_id=${encodeURIComponent(lastEventIdRef.current)}`;
    }
    if (epochRef.current !== null && epochRef.current !== undefined) {
      url += `&stream_epoch=${encodeURIComponent(epochRef.current)}`;
    }

    hasOpenedRef.current = false;
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
      hasOpenedRef.current = true;
      isRecoveringRef.current = false;
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

      // F04: Xử lý cơ chế phục hồi khi cursor sự kiện bị trôi (> 50 events buffer overflow), mất lịch sử hoặc server restart
      const isHistoryLost =
        data?.error_code === 'ERR_CURSOR_OUTDATED' ||
        data?.code === 'ERR_CURSOR_OUTDATED' ||
        data?.error_code === 'ERR_EVENT_HISTORY_LOST' ||
        data?.code === 'ERR_EVENT_HISTORY_LOST' ||
        data?.error_code === 'ERR_HISTORY_LOST' ||
        data?.code === 'ERR_HISTORY_LOST' ||
        data?.requires_resync === true ||
        data?.reset_cursor === true ||
        data?.status === 409;

      if (isHistoryLost) {
        void triggerRecovery();
        return;
      }

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
          ...(prev || {}),
          hasData: true,
          percent: percentVal !== undefined ? percentVal : (prev?.percent ?? 0),
          completedCount: data.completed_count ?? data.completedCount ?? (prev?.completedCount ?? 0),
          totalCount: data.total_count ?? data.totalCount ?? (prev?.totalCount ?? null),
          message: data.message ?? prev?.message ?? '',
          estimatedSeconds: data.estimated_seconds ?? data.estimatedSeconds ?? prev?.estimatedSeconds ?? null,
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
          data?.completed_count ?? data?.completedCount ?? prev?.completedCount ?? 0;
        const currentTotal =
          data?.total_count ?? data?.totalCount ?? prev?.totalCount ?? null;
        const currentPercent =
          data?.percent_complete ??
          data?.percent ??
          (isPartial ? (prev?.percent ?? 50) : 100);

        return {
          ...(prev || {}),
          hasData: true,
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

    // 7. Xử lý lỗi kết nối EventSource (onerror)
    es.onerror = (err) => {
      if (!isMountedRef.current || connectionTokenRef.current !== currentToken || isDoneRef.current) return;

      if (err?.data) {
        handleJobError(err);
        return;
      }

      cleanupConnection();

      // F04: Chỉ kích hoạt phục hồi ngay nếu server phát tín hiệu rõ ràng về mã 409 hoặc mất lịch sử
      const errStatus = err?.status ?? err?.target?.status;
      const isExplicit409 =
        errStatus === 409 ||
        err?.message?.includes('409') ||
        err?.code === 'ERR_EVENT_HISTORY_LOST' ||
        err?.error_code === 'ERR_EVENT_HISTORY_LOST' ||
        err?.code === 'ERR_CURSOR_OUTDATED' ||
        err?.error_code === 'ERR_CURSOR_OUTDATED';

      if (isExplicit409) {
        void triggerRecovery();
        return;
      }

      // F04 Ca còn lỗi 2: Với lỗi kết nối mạng thông thường (kể cả trước onopen), FE thử kết nối lại từ mốc cũ.
      // Quá trình connect() sẽ gửi ticket request kèm lastEventIdRef.current và epochRef.current.
      // Nếu backend báo mất lịch sử (HTTP 409), connect() sẽ bắt lỗi và kích hoạt triggerRecovery().

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
  }, [sessionId, enabled, maxReconnectAttempts, cleanupConnection, triggerRecovery]);

  // Lưu connect ref để triggerRecovery gọi lại mà không bị vòng lặp phụ thuộc
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // F04 / F06: Quản lý khởi tạo marks và cô lập trạng thái khi đổi phiên (A -> B -> A)
  useEffect(() => {
    const isNewSession = prevSessionIdRef.current !== sessionId;
    prevSessionIdRef.current = sessionId;

    if (isNewSession) {
      activeSessionIdRef.current = sessionId;
      connectionTokenRef.current += 1;
      recoveryFlightTokenRef.current += 1;
      isDoneRef.current = false;
      isRecoveringRef.current = false;
      hasOpenedRef.current = false;
      reconnectAttemptRef.current = 0;

      // Reset sạch sẽ trạng thái của phiên cũ để tránh rò rỉ sang phiên mới
      setProgress(createDefaultProgress(initialProgress));
      setQuestionStatuses(initialQuestionStatuses || {});
      setWarnings([]);
      setError(null);
      setIsDone(false);
      setReconnectCount(0);

      lastEventIdRef.current =
        initialResumeAfterEventId ?? initialProgress?.resume_after_event_id ?? null;
      epochRef.current =
        initialStreamEpoch ?? initialProgress?.stream_epoch ?? null;
    } else {
      // Cùng phiên: Khi trang nạp snapshot ban đầu bất đồng bộ (hoặc áp dụng snapshot)
      // KHÔNG reset null cursor/epoch, mà bảo tồn hoặc áp dụng marks từ snapshot
      if (
        lastEventIdRef.current === null &&
        initialResumeAfterEventId !== null &&
        initialResumeAfterEventId !== undefined
      ) {
        lastEventIdRef.current = initialResumeAfterEventId;
      }
      if (
        epochRef.current === null &&
        initialStreamEpoch !== null &&
        initialStreamEpoch !== undefined
      ) {
        epochRef.current = initialStreamEpoch;
      }

      const isProgressEqual = (a, b) => {
        if (a === b) return true;
        if (!a || !b) return false;
        const pa = a.percent ?? a.percent_complete ?? 0;
        const pb = b.percent ?? b.percent_complete ?? 0;
        const ca = a.completedCount ?? a.completed_count ?? 0;
        const cb = b.completedCount ?? b.completed_count ?? 0;
        const ta = a.totalCount ?? a.total_count ?? null;
        const tb = b.totalCount ?? b.total_count ?? null;
        return pa === pb && ca === cb && ta === tb && Boolean(a.hasData) === Boolean(b.hasData);
      };

      if (
        (initialProgress?.hasData ||
          (initialProgress?.percent !== undefined && initialProgress?.percent !== null)) &&
        !isProgressEqual(lastInitialProgressRef.current, initialProgress)
      ) {
        lastInitialProgressRef.current = initialProgress;
        if (!hasOpenedRef.current) {
          setProgress(createDefaultProgress(initialProgress));
        }
      }

      if (
        initialQuestionStatuses &&
        Object.keys(initialQuestionStatuses).length > 0 &&
        JSON.stringify(lastInitialStatusesRef.current) !== JSON.stringify(initialQuestionStatuses)
      ) {
        lastInitialStatusesRef.current = initialQuestionStatuses;
        if (!hasOpenedRef.current) {
          setQuestionStatuses(initialQuestionStatuses);
        }
      }
    }
  }, [sessionId, initialProgress, initialQuestionStatuses, initialResumeAfterEventId, initialStreamEpoch]);

  // Quản lý kết nối SSE: CHỈ chạy khi sessionId hoặc enabled thay đổi, KHÔNG phụ thuộc snapshot props
  useEffect(() => {
    isMountedRef.current = true;
    activeSessionIdRef.current = sessionId;

    if (enabled && sessionId) {
      connect();
    } else {
      cleanupConnection();
      if (!enabled) {
        setConnectionState((prev) => (prev === 'completed' ? prev : 'idle'));
      }
    }

    return () => {
      isMountedRef.current = false;
      cleanupConnection();
    };
  }, [sessionId, enabled, connect, cleanupConnection]);

  // Hàm thủ công cho phép người dùng bấm "Kết nối lại" hoặc kích hoạt vòng theo dõi mới khi sinh bù trong cùng một phiên
  const manualReconnect = useCallback(() => {
    isDoneRef.current = false;
    isRecoveringRef.current = false;
    hasOpenedRef.current = false;
    setIsDone(false);
    setProgress((prev) => ({
      ...(prev || {}),
      session_status: 'generating',
    }));
    reconnectAttemptRef.current = 0;
    setReconnectCount(0);
    setError(null);
    connect();
  }, [connect]);

  const isPartial = Boolean(
    progress?.is_partial ||
    progress?.session_status === 'partial_generated' ||
    (isDone && (progress?.percent ?? 100) < 100),
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
