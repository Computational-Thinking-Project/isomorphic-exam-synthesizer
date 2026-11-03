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
        ordering_preferences: rawConfig.ordering_preferences ?? { shuffle_questions: true },
      }
    : data.n_versions
    ? {
        n_versions: data.n_versions,
        num_versions: data.n_versions,
        active_variation_modes: data.active_variation_modes || [],
        variation_modes: data.active_variation_modes || [],
        ordering_preferences: data.ordering_preferences || { shuffle_questions: true },
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
    const questionsWithBlueprints = sourceQuestions.filter(
      (q) => q.question_blueprints || q.blueprint || q.variation_modes,
    );

    // Chỉ coi Blueprint đã sẵn sàng khi TOÀN BỘ câu hỏi trong đề nguồn đều có Blueprint
    if (questionsWithBlueprints.length !== totalQuestions) {
      return null;
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

    questionsWithBlueprints.forEach((q) => {
      const rawModes =
        q.question_blueprints?.variation_modes ||
        q.blueprint?.variation_modes ||
        q.variation_modes ||
        [];
      if (Array.isArray(rawModes)) {
        const distinctInQuestion = new Set();
        rawModes.forEach((raw) => {
          const trimmed = String(raw).trim();
          if (trimmed && trimmed.toUpperCase() !== 'NONE') {
            distinctInQuestion.add(trimmed);
          }
        });

        distinctInQuestion.forEach((rawId) => {
          modeCounts[rawId] = (modeCounts[rawId] || 0) + 1;
        });
      }
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
      const normalizedModes = rawSummary.supported_modes.map((m) => {
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
          is_ready: true,
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
    }
  }

  // Khôi phục snapshot tiến độ bền vững (Durable Progress Snapshot) cho F5/reload
  let restoredProgress = data.progress || null;
  let restoredQuestionStatuses = data.question_statuses || {};

  if (!restoredProgress && Array.isArray(data.exam_versions) && data.exam_versions.length > 0) {
    let completedCount = 0;
    const statuses = {};

    data.exam_versions.forEach((ver, verIdx) => {
      const vIndex = ver.version_index ?? (verIdx + 1);
      const qList = ver.questions || ver.version_questions || [];
      qList.forEach((q, qIdx) => {
        const qNo = q.question_no ?? q.source_question_no ?? (qIdx + 1);
        const key = `${vIndex}-${qNo}`;
        statuses[key] = {
          status: q.status || 'done',
          message: q.message || 'Đã hoàn thành',
        };
        completedCount += 1;
      });
    });

    const nVersions = savedConfig?.n_versions || data.exam_versions.length || 2;
    const totalSourceQ = data.source_questions?.length || data.total_source_questions || 10;
    const totalCount = nVersions * totalSourceQ;
    const percent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;
    const isPartial = data.status === 'partial_generated' || (data.status === 'generated' && completedCount < totalCount);

    restoredProgress = {
      percent,
      completedCount,
      totalCount,
      session_status: data.status,
      is_partial: isPartial,
      message: isPartial
        ? `Tiến trình kết thúc ở trạng thái sinh một phần (partial_generated). Đã sinh được ${completedCount} / ${totalCount} câu.`
        : 'Đang tải tiến trình...',
    };
    restoredQuestionStatuses = statuses;
  }

  return {
    ...data,
    blueprint_summary: blueprintSummary,
    config: savedConfig,
    progress: restoredProgress,
    question_statuses: restoredQuestionStatuses,
  };
}

export async function saveSessionConfig(sessionId, configPayload) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  // CHỈ gửi đúng tên trường theo contract BE2 (TASK-207a).
  // Tuyệt đối không gửi num_versions hay variation_modes để tránh lỗi 422 từ model Pydantic backend.
  const payload = {
    n_versions: Number(configPayload.n_versions ?? configPayload.num_versions ?? 2),
    active_variation_modes: Array.isArray(configPayload.active_variation_modes)
      ? configPayload.active_variation_modes
      : Array.isArray(configPayload.variation_modes)
      ? configPayload.variation_modes
      : [],
    ordering_preferences: {
      shuffle_questions: Boolean(
        configPayload.ordering_preferences?.shuffle_questions ?? true,
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

export async function requestEventTicket(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/events/ticket`,
  );
  return response.data;
}
