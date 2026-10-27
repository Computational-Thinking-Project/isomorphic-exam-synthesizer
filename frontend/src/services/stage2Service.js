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

  // Chuẩn hóa blueprint_summary: KHÔNG tự tạo chế độ giả lập nếu backend chưa có
  let blueprintSummary = data.blueprint_summary || null;

  // Nếu API chưa nhóm blueprint_summary nhưng có dữ liệu blueprint trong source_questions
  if (!blueprintSummary && Array.isArray(data.source_questions) && data.source_questions.length > 0) {
    const questionsWithBlueprints = data.source_questions.filter(
      (q) => q.question_blueprints || q.blueprint || q.variation_modes,
    );

    if (questionsWithBlueprints.length > 0) {
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
        const modes =
          q.question_blueprints?.variation_modes ||
          q.blueprint?.variation_modes ||
          q.variation_modes ||
          [];
        if (Array.isArray(modes)) {
          modes.forEach((m) => {
            modeCounts[m] = (modeCounts[m] || 0) + 1;
          });
        }
      });

      const supportedModes = Object.entries(modeCounts)
        .filter(([, count]) => count > 0)
        .map(([id, count]) => ({
          id,
          label: MODE_METADATA[id]?.label || id,
          description: MODE_METADATA[id]?.description || '',
          question_count: count,
          is_available: true,
        }));

      if (supportedModes.length > 0) {
        blueprintSummary = {
          total_questions: data.source_questions.length,
          supported_modes: supportedModes,
        };
      }
    }
  }

  return {
    ...data,
    blueprint_summary: blueprintSummary,
    config: savedConfig,
  };
}

export async function saveSessionConfig(sessionId, configPayload) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  // Đồng bộ payload cả schema BE2 (n_versions, active_variation_modes) và backward compatibility
  const payload = {
    n_versions: configPayload.n_versions ?? configPayload.num_versions,
    num_versions: configPayload.num_versions ?? configPayload.n_versions,
    active_variation_modes: configPayload.active_variation_modes ?? configPayload.variation_modes ?? [],
    variation_modes: configPayload.variation_modes ?? configPayload.active_variation_modes ?? [],
    ordering_preferences: configPayload.ordering_preferences ?? {
      shuffle_questions: true,
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

export async function requestEventTicket(sessionId) {
  if (!sessionId) {
    throw new Error('Mã phiên làm việc (sessionId) không được để trống.');
  }

  const response = await api.post(
    `/sessions/${encodeURIComponent(sessionId)}/events/ticket`,
  );
  return response.data;
}
