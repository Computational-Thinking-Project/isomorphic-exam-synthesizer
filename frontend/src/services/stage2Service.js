import { api } from './api.js';

/**
 * Service giao tiếp API cho Stage 2: Cấu hình và Sinh đề bất đồng bộ.
 */

export async function fetchSessionDetail(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.get(`/sessions/${encodeURIComponent(sessionId)}`);
  const data = response.data;

  // Lấy cấu hình đã lưu (nếu có) từ backend để phục hồi state khi F5/reload
  const rawConfig = data.generation_config || data.config || null;
  const savedConfig = rawConfig
    ? {
        n_versions: rawConfig.n_versions ?? rawConfig.num_versions ?? 2,
        num_versions: rawConfig.num_versions ?? rawConfig.n_versions ?? 2,
        active_variation_modes: rawConfig.active_variation_modes ?? rawConfig.variation_modes ?? [],
        variation_modes: rawConfig.variation_modes ?? rawConfig.active_variation_modes ?? [],
        ordering_preferences: rawConfig.ordering_preferences
          ? {
              shuffle_questions: Boolean(rawConfig.ordering_preferences.shuffle_questions ?? false),
              shuffle_options: Boolean(rawConfig.ordering_preferences.shuffle_options ?? false),
            }
          : { shuffle_questions: false, shuffle_options: false },
      }
    : data.n_versions
    ? {
        n_versions: data.n_versions,
        num_versions: data.n_versions,
        active_variation_modes: data.active_variation_modes || [],
        variation_modes: data.active_variation_modes || [],
        ordering_preferences: data.ordering_preferences
          ? {
              shuffle_questions: Boolean(data.ordering_preferences.shuffle_questions ?? false),
              shuffle_options: Boolean(data.ordering_preferences.shuffle_options ?? false),
            }
          : { shuffle_questions: false, shuffle_options: false },
      }
    : null;

  // Chuẩn hóa blueprint_summary: hỗ trợ cả backend trả summary đầy đủ lẫn fallback bóc tách từ source_questions
  let blueprintSummary = null;

  // Hàm phụ trợ tính supported_modes từ source_questions
  function computeModesFromSourceQuestions(sourceQuestions) {
    if (!Array.isArray(sourceQuestions) || sourceQuestions.length === 0) {
      return null;
    }
    const totalQuestions = sourceQuestions.length;

    // F01: Kiểm tra metadata modes của từng câu hỏi nguồn.
    // Nếu có bất kỳ câu nào KHÔNG có trường variation_modes (hoặc blueprint.variation_modes, question_blueprints.variation_modes) dạng Array
    // -> nghĩa là dữ liệu modes bị thiếu -> trả về null để khóa submit!
    for (const q of sourceQuestions) {
      const modes =
        q.question_blueprints?.variation_modes ??
        q.blueprint?.variation_modes ??
        q.variation_modes;
      if (!Array.isArray(modes)) {
        return null;
      }
    }

    const CANONICAL_MAP = {
      parameter_variation: 'parameter_variation',
      numerical: 'parameter_variation',
      context_swap: 'context_swap',
      contextual: 'context_swap',
      variable_inversion: 'variable_inversion',
      inversion: 'variable_inversion',
    };

    const MODE_METADATA = {
      parameter_variation: {
        label: 'Thay đổi số liệu / tham số',
        description: 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.',
      },
      context_swap: {
        label: 'Đổi ngữ cảnh thực tế',
        description: 'Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.',
      },
      variable_inversion: {
        label: 'Hoán đổi ẩn số',
        description: 'Đổi vị trí đại lượng đã cho và đại lượng cần tìm trong bài toán.',
      },
    };

    const modeCounts = {};

    sourceQuestions.forEach((q) => {
      const rawModes =
        q.question_blueprints?.variation_modes ??
        q.blueprint?.variation_modes ??
        q.variation_modes ??
        [];
      const distinctInQuestion = new Set();
      rawModes.forEach((raw) => {
        const trimmed = String(raw).trim();
        // Loại bỏ NONE ra khỏi danh sách modes biến thể thật
        if (trimmed && trimmed.toUpperCase() !== 'NONE') {
          distinctInQuestion.add(trimmed);
        }
      });

      distinctInQuestion.forEach((rawId) => {
        modeCounts[rawId] = (modeCounts[rawId] || 0) + 1;
      });
    });

    // Theo quy tắc Blueprint (DEC-TV1 / 207a):
    // Một mode CHỈ được coi là is_available: true nếu TẤT CẢ câu hỏi trong đề (phần giao) đều hỗ trợ nó!
    // QUAN TRỌNG: Giữ nguyên ID mode gốc và phân biệt chữ hoa/thường chính xác theo Policy 207a
    return Object.entries(modeCounts)
      .filter(([, count]) => count > 0)
      .map(([rawId, count]) => {
        const canonical = CANONICAL_MAP[rawId.toLowerCase()] || rawId.toLowerCase();
        const meta = MODE_METADATA[canonical] || {
          label: rawId,
          description: `Chế độ biến thể ${rawId}`,
        };
        const isFullySupported = count === totalQuestions;
        return {
          id: rawId,
          label: meta.label,
          description: meta.description,
          question_count: count,
          is_available: isFullySupported,
          unavailable_reason: isFullySupported
            ? undefined
            : `Chỉ hỗ trợ ${count}/${totalQuestions} câu trong đề (yêu cầu toàn bộ câu hỏi hỗ trợ).`,
        };
      });
  }

  if (data.blueprint_summary) {
    const rawSummary = data.blueprint_summary;
    const isReady = rawSummary.is_ready !== false;

    if (!isReady) {
      // Trường hợp Blueprint chưa hoàn thành bóc tách
      blueprintSummary = {
        ...rawSummary,
        is_ready: false,
        supported_modes: null,
      };
    } else if (Array.isArray(rawSummary.supported_modes)) {
      // Backend đã tự tính và trả supported_modes
      const CANONICAL_MAP = {
        parameter_variation: 'parameter_variation',
        numerical: 'parameter_variation',
        context_swap: 'context_swap',
        contextual: 'context_swap',
        variable_inversion: 'variable_inversion',
        inversion: 'variable_inversion',
      };

      const MODE_METADATA = {
        parameter_variation: {
          label: 'Thay đổi số liệu / tham số',
          description: 'Giữ nguyên cấu trúc đề bài toán, thay đổi tham số số học đảm bảo nghiệm đẹp.',
        },
        context_swap: {
          label: 'Đổi ngữ cảnh thực tế',
          description: 'Giữ nguyên mô hình giải tích, thay đổi tình huống hoặc đối tượng thực tiễn.',
        },
        variable_inversion: {
          label: 'Hoán đổi ẩn số',
          description: 'Đổi vị trí đại lượng đã cho và đại lượng cần tìm trong bài toán.',
        },
      };

      const totalQ = rawSummary.total_questions ?? data.source_questions?.length ?? 10;
      // F01: Lọc bỏ 'NONE' nếu backend trả supported_modes có chứa 'NONE'
      const filteredModes = rawSummary.supported_modes.filter((m) => {
        const id = typeof m === 'string' ? m : m?.id;
        return id && String(id).trim().toUpperCase() !== 'NONE';
      });

      const normalizedModes = filteredModes.map((m) => {
        if (typeof m === 'string') {
          const rawId = m.trim();
          const canonical = CANONICAL_MAP[rawId.toLowerCase()] || rawId.toLowerCase();
          const meta = MODE_METADATA[canonical] || { label: rawId, description: `Chế độ biến thể ${rawId}` };
          return {
            id: rawId,
            label: meta.label,
            description: meta.description,
            question_count: totalQ,
            is_available: true,
          };
        }
        return {
          id: m.id,
          label: m.label || m.id,
          description: m.description || `Chế độ biến thể ${m.id}`,
          question_count: m.question_count ?? totalQ,
          is_available: m.is_available !== false,
          unavailable_reason: m.unavailable_reason,
        };
      });

      blueprintSummary = {
        ...rawSummary,
        is_ready: true,
        supported_modes: normalizedModes,
      };
    } else {
      // Backend trả blueprint_summary nhưng chưa có supported_modes (như PR #32),
      // FE tính fallback từ source_questions nếu có đầy đủ dữ liệu
      const computedModes = computeModesFromSourceQuestions(data.source_questions);
      if (computedModes !== null) {
        blueprintSummary = {
          ...rawSummary,
          is_ready: rawSummary.is_ready !== false,
          total_questions: rawSummary.total_questions ?? data.source_questions.length,
          supported_modes: computedModes,
        };
      } else {
        blueprintSummary = {
          ...rawSummary,
          is_ready: false,
          supported_modes: null,
        };
      }
    }
  } else if (Array.isArray(data.source_questions) && data.source_questions.length > 0) {
    const computedModes = computeModesFromSourceQuestions(data.source_questions);
    if (computedModes !== null) {
      blueprintSummary = {
        total_questions: data.source_questions.length,
        supported_modes: computedModes,
        is_ready: true,
      };
    } else {
      blueprintSummary = null;
    }
  }

  // F02: Khôi phục lưới câu hỏi và chuẩn hóa snapshot tiến độ
  let hasAnyGeneratedQuestions = false;
  let computedCompleted = 0;
  const computedStatuses = {};

  if (Array.isArray(data.exam_versions) && data.exam_versions.length > 0) {
    data.exam_versions.forEach((ver, verIdx) => {
      const vIndex = ver.version_index ?? (verIdx + 1);
      const qList = ver.questions || ver.version_questions || [];
      qList.forEach((q, qIdx) => {
        const qNo = q.question_no ?? q.source_question_no ?? (qIdx + 1);
        const key = `${vIndex}-${qNo}`;
        const isFailed = q.status === 'failed' || Boolean(q.error || q.error_message);
        const isDone = q.status === 'done' || (!isFailed && Boolean(q.variant_text || q.content || q.raw_content));

        if (isFailed) {
          hasAnyGeneratedQuestions = true;
          computedStatuses[key] = {
            status: 'failed',
            message: q.error_message || q.error || q.message || 'Sinh câu hỏi thất bại',
          };
          // QUAN TRỌNG: Câu failed KHÔNG tăng số hoàn tất!
        } else if (isDone) {
          hasAnyGeneratedQuestions = true;
          computedCompleted += 1;
          computedStatuses[key] = {
            status: 'done',
            message: q.message || 'Đã hoàn thành',
          };
        } else if (q.status) {
          hasAnyGeneratedQuestions = true;
          computedStatuses[key] = {
            status: q.status,
            message: q.message || `Đang xử lý (${q.status})`,
          };
        }
      });
    });
  }

  let restoredProgress = null;
  let restoredQuestionStatuses = {};

  const totalSourceQuestions =
    data.source_questions?.length ||
    data.blueprint_summary?.total_questions ||
    data.total_source_questions ||
    0;
  const nVersions =
    savedConfig?.n_versions ||
    (Array.isArray(data.exam_versions) && data.exam_versions.length > 0 ? data.exam_versions.length : 2);
  const totalCount = nVersions * (totalSourceQuestions || 1);

  if (data.progress) {
    // API có trả progress (kể cả với tên trường percent_complete, completed_count theo TASK-207b)
    const apiProg = data.progress;
    const completedCount =
      apiProg.completedCount ??
      apiProg.completed_count ??
      computedCompleted;
    const finalTotal =
      apiProg.totalCount ??
      apiProg.total_count ??
      totalCount;
    const percentVal =
      apiProg.percent ??
      apiProg.percent_complete ??
      (finalTotal > 0 ? Math.round((completedCount / finalTotal) * 100) : 0);
    const isDone = Boolean(
      apiProg.isDone ??
      apiProg.is_done ??
      (data.status === 'generated' || (data.status === 'partial_generated' && completedCount === finalTotal))
    );

    restoredProgress = {
      hasData: true,
      percent: percentVal,
      completedCount,
      totalCount: finalTotal,
      isDone,
      session_status: data.status,
      is_partial: data.status === 'partial_generated' || (percentVal < 100 && isDone),
      message: apiProg.message || (data.status === 'partial_generated' ? 'Đã sinh một phần' : ''),
    };
    restoredQuestionStatuses = {
      ...computedStatuses,
      ...(data.question_statuses || {}),
    };
  } else if (hasAnyGeneratedQuestions) {
    // Không có data.progress nhưng có dữ liệu câu hỏi thực tế trong exam_versions
    const percentVal = totalCount > 0 ? Math.round((computedCompleted / totalCount) * 100) : 0;
    const isPartial = data.status === 'partial_generated' || (data.status === 'generated' && computedCompleted < totalCount);

    restoredProgress = {
      hasData: true,
      percent: percentVal,
      completedCount: computedCompleted,
      totalCount,
      session_status: data.status,
      is_partial: isPartial,
      isDone: Boolean(data.status === 'generated' || data.status === 'partial_generated'),
      message: isPartial
        ? `Tiến trình kết thúc ở trạng thái sinh một phần (partial_generated). Đã sinh được ${computedCompleted} / ${totalCount} câu.`
        : 'Đang tải tiến trình...',
    };
    restoredQuestionStatuses = computedStatuses;
  }

  // F02 / F07 / F08: Nếu phiên partial_generated hoặc generating chưa có progress (ví dụ PR #32 chỉ có metadata mã đề),
  // thử tải generation-snapshot nếu endpoint đã có kết quả
  if (!restoredProgress && (data.status === 'partial_generated' || data.status === 'generating')) {
    try {
      const snap = await fetchGenerationSnapshot(sessionId);
      if (snap?.progress) {
        restoredProgress = snap.progress;
        restoredQuestionStatuses = {
          ...restoredQuestionStatuses,
          ...(snap.question_statuses || {}),
        };
        const snapStatus =
          snap.status ||
          snap.session_status ||
          snap.progress?.session_status ||
          snap.progress?.status;
        if (snapStatus) {
          data.status = snapStatus;
        }
        if (snap.generation_error_code) {
          data.generation_error_code = snap.generation_error_code;
        }
        data.stream_epoch = snap.stream_epoch;
        data.resume_after_event_id = snap.resume_after_event_id;
      }
    } catch {
      // Bỏ qua nếu endpoint generation-snapshot chưa có
    }
  }

  return {
    ...data,
    blueprint_summary: blueprintSummary,
    config: savedConfig,
    progress: restoredProgress,
    question_statuses: restoredQuestionStatuses,
    stream_epoch: data.stream_epoch || null,
    resume_after_event_id: data.resume_after_event_id ?? null,
  };
}

export async function saveSessionConfig(sessionId, configPayload) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  // CHỈ gửi đúng tên trường theo contract BE2 (TASK-207a).
  // Tuyệt đối không gửi num_versions hay variation_modes để tránh lỗi 422 từ model Pydantic backend.
  const rawModes = Array.isArray(configPayload.active_variation_modes)
    ? configPayload.active_variation_modes
    : Array.isArray(configPayload.variation_modes)
    ? configPayload.variation_modes
    : [];

  // F01: Chuẩn hóa NONE: loại bỏ 'NONE' để gửi [] khi ở chế độ không biến thể theo contract 207a
  const normalizedModes = rawModes
    .map((m) => (typeof m === 'string' ? m : m?.id))
    .filter((m) => typeof m === 'string' && m.trim().toUpperCase() !== 'NONE');

  const payload = {
    n_versions: Number(configPayload.n_versions ?? configPayload.num_versions ?? 2),
    active_variation_modes: normalizedModes,
    ordering_preferences: {
      shuffle_questions: Boolean(
        configPayload.ordering_preferences?.shuffle_questions ?? false,
      ),
      shuffle_options: Boolean(
        configPayload.ordering_preferences?.shuffle_options ?? false,
      ),
    },
  };

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/config`,
    payload,
  );
  return response.data;
}

export async function startGeneration(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/generate`,
  );
  return response.data;
}

export async function retryGeneration(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/retry-generation`,
  );
  return response.data;
}

export async function fetchGenerationSnapshot(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.get(`/sessions/${encodeURIComponent(sessionId)}/generation-snapshot`);
  const data = response.data;
  const rawProgress = data.progress;

  let normalizedProgress = null;
  if (rawProgress) {
    const completedCount = rawProgress.completed_count ?? rawProgress.completedCount ?? 0;
    const totalCount = rawProgress.total_count ?? rawProgress.totalCount ?? 0;
    const percentVal =
      rawProgress.percent_complete ??
      rawProgress.percent ??
      (totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0);

    normalizedProgress = {
      hasData: true,
      completedCount,
      totalCount,
      percent: percentVal,
      session_status: data.session_status || data.status,
      is_partial: Boolean(data.session_status === 'partial_generated' || data.is_partial),
      message: rawProgress.message || '',
    };
  }

  return {
    session_id: data.session_id || sessionId,
    session_status: data.session_status || data.status,
    generation_error_code: data.generation_error_code ?? null,
    progress: normalizedProgress,
    question_statuses: data.question_statuses || {},
    stream_epoch: data.stream_epoch || null,
    resume_after_event_id: data.resume_after_event_id ?? null,
  };
}

export async function requestEventTicket(sessionId, lastEventId = null, streamEpoch = null) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const params = new URLSearchParams();
  if (lastEventId !== null && lastEventId !== undefined) {
    params.set('last_event_id', lastEventId);
  }
  if (streamEpoch !== null && streamEpoch !== undefined) {
    params.set('stream_epoch', streamEpoch);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/events/ticket${query}`,
  );
  return response.data;
}
