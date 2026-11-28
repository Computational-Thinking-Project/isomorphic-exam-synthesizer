import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { register } from 'node:module';
import React, { act } from 'react';
import { ensureDomEnvironment } from '../../test-support/domHarness.js';
import { useAuthStore } from '../auth/authStore.js';
import { auth } from '../../services/test-support/supabase.stub.js';

ensureDomEnvironment();
document.oninput = null;
const { createRoot } = await import('react-dom/client');
const { MemoryRouter, Route, Routes } = await import('react-router-dom');
register('../../test-loader.mjs', import.meta.url);
register('../../services/test-support/auth-loader.js', import.meta.url);
const { api } = await import('../../services/api.js');
const { default: SessionExportPage } = await import('./SessionExportPage.jsx');

function findButtons(root, text) {
  const buttons = [];
  const walk = (node) => {
    if (!node) return;
    if (node.nodeName === 'BUTTON' && node.textContent.includes(text)) {
      buttons.push(node);
    }
    if (Array.isArray(node.childNodes)) {
      node.childNodes.forEach(walk);
    }
  };
  walk(root);
  return buttons;
}

async function mountExportPage(props, initialPath = '/session/s1/export') {
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => {
    root.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [initialPath] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, {
            path: '/session/:sessionId/export',
            element: React.createElement(SessionExportPage, props),
          }),
          React.createElement(Route, {
            path: '/dashboard',
            element: React.createElement('div', null, 'Dashboard'),
          }),
        ),
      ),
    );
  });
  await act(async () => {
    await Promise.resolve();
  });

  return {
    container,
    unmount: async () => {
      await act(async () => {
        root.unmount();
      });
    },
  };
}

beforeEach(() => {
  useAuthStore.getState().setSession({ user: { id: 'account-a' }, access_token: 'token-a' });
  useAuthStore.getState().setProfile(
    { id: 'account-a', email: 'teacher@example.test' },
    useAuthStore.getState().sessionVersion,
  );
  auth.getSession = async () => ({
    data: { session: useAuthStore.getState().session },
    error: null,
  });
});

test('SessionExportPage hiển thị trạng thái unwired khi chưa truyền Q10 API adapters', async () => {
  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề Đại số 12',
      subject: 'Toán',
      grade: 12,
      status: 'approved',
    }),
    getStatus: null,
    triggerExport: null,
    issueDownloadUrl: null,
  });

  assert.match(view.container.textContent, /Đề Đại số 12/);
  assert.match(view.container.textContent, /chưa được nối vào giao diện/);
  assert.match(view.container.textContent, /Thư viện đề/);
  await view.unmount();
});

test('SessionExportPage chặn phiên chưa approved/exported', async () => {
  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề đang soạn',
      subject: 'Toán',
      grade: 12,
      status: 'reviewed',
    }),
    getStatus: async () => {
      throw new Error('Must not call getStatus');
    },
  });

  assert.match(view.container.textContent, /Phiên chưa ở trạng thái đã duyệt cuối/);
  await view.unmount();
});

test('SessionExportPage cho phép tạo gói ZIP và tải xuống khi đã nối adapter', async () => {
  let statusCalls = 0;
  let exportCalls = 0;
  let downloadCalls = 0;
  const opened = [];

  const view = await mountExportPage({
    loadSession: async (id) => ({
      id,
      title: 'Đề HK1',
      subject: 'Toán',
      grade: 12,
      status: 'approved',
    }),
    getStatus: async () => {
      statusCalls += 1;
      return { status: 'idle' };
    },
    triggerExport: async (id) => {
      exportCalls += 1;
      return { status: 'ready', filename: `exam_bundle_${id}.zip` };
    },
    issueDownloadUrl: async (id) => {
      downloadCalls += 1;
      return {
        url: `https://storage.example.test/${id}.zip`,
        expires_in: 3600,
        filename: `exam_bundle_${id}.zip`,
      };
    },
    openDownload: (url, filename) => opened.push({ url, filename }),
  });

  assert.equal(statusCalls, 1);
  assert.equal(exportCalls, 0);

  const exportBtn = findButtons(view.container, 'Tạo gói ZIP')[0];
  assert.ok(exportBtn);

  await act(async () => {
    exportBtn.click();
    await Promise.resolve();
  });

  assert.equal(exportCalls, 1);
  assert.match(view.container.textContent, /exam_bundle_s1\.zip/);

  const downloadBtn = findButtons(view.container, 'Tải gói ZIP')[0];
  assert.ok(downloadBtn);

  await act(async () => {
    downloadBtn.click();
    await Promise.resolve();
  });

  assert.equal(downloadCalls, 1);
  assert.deepEqual(opened, [{
    url: 'https://storage.example.test/s1.zip',
    filename: 'exam_bundle_s1.zip',
  }]);

  await view.unmount();
});

test('SessionExportPage chạy trọn luồng qua exportService mặc định với api adapter Q10', async () => {
  const requests = [];
  const opened = [];
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    if (config.method === 'get' && config.url === '/sessions/s1') {
      return {
        status: 200,
        data: {
          id: 's1',
          user_id: 'account-a',
          title: 'Đề thi thử Q10',
          subject: 'Toán',
          grade: 12,
          status: 'approved',
          created_at: '2026-11-01T00:00:00Z',
          updated_at: '2026-11-15T00:00:00Z',
          source_questions: [],
          exam_versions: [],
        },
        headers: {},
        config,
      };
    }
    if (config.method === 'get' && config.url === '/sessions/s1/export') {
      return { status: 200, data: { state: 'idle' }, headers: {}, config };
    }
    if (config.method === 'post' && config.url === '/sessions/s1/export') {
      return {
        status: 200,
        data: {
          state: 'ready',
          filename: 'exam_bundle_s1.zip',
          sha256: 'hash-q10',
          size_bytes: 5120,
        },
        headers: {},
        config,
      };
    }
    if (config.method === 'post' && config.url === '/sessions/s1/export/download-url') {
      return {
        status: 200,
        data: {
          url: 'https://storage.example.test/exam_bundle_s1.zip?sig=q10',
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
          expires_in: 3600,
          filename: 'exam_bundle_s1.zip',
        },
        headers: {},
        config,
      };
    }
    throw new Error(`Unexpected HTTP call: ${config.method} ${config.url}`);
  };

  const view = await mountExportPage({
    openDownload: (url, filename) => opened.push({ url, filename }),
  });
  // Đợi getSessionDetail -> getExportStatus hoàn tất
  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  const exportBtn = findButtons(view.container, 'Tạo gói ZIP')[0];
  assert.ok(exportBtn);
  await act(async () => {
    exportBtn.click();
    await new Promise((r) => setTimeout(r, 10));
  });

  const downloadBtn = findButtons(view.container, 'Tải gói ZIP')[0];
  assert.ok(downloadBtn);
  await act(async () => {
    downloadBtn.click();
    await new Promise((r) => setTimeout(r, 10));
  });

  assert.deepEqual(
    requests.map((r) => `${r.method.toUpperCase()} ${r.url}`),
    [
      'GET /sessions/s1',
      'GET /sessions/s1/export',
      'POST /sessions/s1/export',
      'POST /sessions/s1/export/download-url',
    ],
  );
  assert.deepEqual(JSON.parse(requests[2].data), {
    config: {
      visible_fields: ['title', 'student_name', 'student_id', 'student_class'],
      answer_sheet: 'none',
      formats: ['pdf'],
    },
  });
  assert.equal(requests[3].data, undefined);
  assert.deepEqual(opened, [{
    url: 'https://storage.example.test/exam_bundle_s1.zip?sig=q10',
    filename: 'exam_bundle_s1.zip',
  }]);

  await view.unmount();
});

test('SessionExportPage: hiển thị Bước 3/3, link preview URL-encoded, hộp cấu trúc w4-export-v2, dung lượng ZIP và không rò rỉ signed URL', async () => {
  const signedUrl = 'https://storage.example.test/signed/exam_bundle_special.zip?token=secret-sig';
  const opened = [];
  const view = await mountExportPage(
    {
      loadSession: async () => ({
        id: 'sess with/1',
        title: 'Đề kiểm tra Đại số 10',
        subject: 'Toán',
        grade: 10,
        status: 'exported',
        question_count: 10,
        variant_count: 4,
      }),
      getStatus: async () => ({
        status: 'ready',
        filename: 'exam_bundle_special.zip',
        size_bytes: 5120,
      }),
      issueDownloadUrl: async () => ({
        url: signedUrl,
        expires_in: 3600,
        filename: 'exam_bundle_special.zip',
      }),
      openDownload: (url, filename) => opened.push({ url, filename }),
    },
    '/session/sess%20with%2F1/export',
  );

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  const textBeforeDownload = view.container.textContent;
  assert.ok(textBeforeDownload.includes('Bước 3/3 · Xuất đề & Tải gói ZIP'));
  assert.ok(textBeforeDownload.includes('Đã xuất gói đề'));
  assert.ok(textBeforeDownload.includes('5.0 KB'));
  assert.ok(!textBeforeDownload.includes(signedUrl), 'Không được lộ signed URL trực tiếp trong DOM');

  const previewLink = view.container.querySelector('[data-testid="export-link-preview"]');
  assert.ok(previewLink, 'Phải có link quay lại Stage 3 Preview');
  assert.equal(previewLink.getAttribute('href'), '/session/sess%20with%2F1/stage3/preview');

  const zipInfo = view.container.querySelector('[data-testid="zip-structure-info"]');
  assert.ok(zipInfo, 'Phải hiển thị hộp thông tin cấu trúc gói ZIP w4-export-v2');
  assert.ok(zipInfo.textContent.includes('w4-export-v2'));
  assert.ok(zipInfo.textContent.includes('pdf/exam_<mã>.pdf'));
  assert.ok(zipInfo.textContent.includes('latex/exam_<mã>.tex'));
  assert.ok(zipInfo.textContent.includes('markdown/exam_<mã>.md'));
  assert.ok(zipInfo.textContent.includes('không hỗ trợ tải lẻ từng file hoặc từng mã'));

  // Không có nút tải lẻ PDF/TeX/MD
  const allButtons = [];
  const collectButtons = (node) => {
    if (!node) return;
    if (node.nodeName === 'BUTTON') allButtons.push(node.textContent);
    if (Array.isArray(node.childNodes)) node.childNodes.forEach(collectButtons);
  };
  collectButtons(view.container);
  assert.deepEqual(
    allButtons.map((b) => b.trim()),
    ['Khôi phục mặc định', 'Tải đáp án (CSV)', 'Tải đáp án (JSON)', 'Tải gói ZIP', 'Làm mới trạng thái'],
  );

  const downloadBtn = findButtons(view.container, 'Tải gói ZIP')[0];
  assert.ok(downloadBtn);
  await act(async () => {
    downloadBtn.click();
    await Promise.resolve();
  });

  assert.deepEqual(opened, [{ url: signedUrl, filename: 'exam_bundle_special.zip' }]);
  assert.ok(!view.container.textContent.includes(signedUrl), 'Không được lộ signed URL sau khi tải');

  await view.unmount();
});

test('SessionExportPage: pha failed cho phép Thử đóng gói lại và chuyển sang sẵn sàng tải khi retry thành công', async () => {
  let startCalls = 0;
  const view = await mountExportPage({
    loadSession: async () => ({
      id: 's1',
      title: 'Đề cuối kỳ',
      subject: 'Toán',
      grade: 11,
      status: 'approved',
    }),
    getStatus: async () => ({
      status: 'failed',
      error_code: 'ERR_EXPORT_BUILD_FAILED',
    }),
    triggerExport: async () => {
      startCalls += 1;
      return {
        status: 'ready',
        filename: 'exam_bundle_retry.zip',
        size_bytes: 2048,
      };
    },
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  assert.ok(view.container.textContent.includes('Quá trình đóng gói đề thi gặp lỗi. Bạn có thể bấm thử đóng gói lại.'));
  const retryBtn = findButtons(view.container, 'Thử đóng gói lại')[0];
  assert.ok(retryBtn, 'Phải hiển thị nút Thử đóng gói lại khi export failed');

  await act(async () => {
    retryBtn.click();
    await Promise.resolve();
  });

  assert.equal(startCalls, 1);
  assert.ok(view.container.textContent.includes('exam_bundle_retry.zip'));
  assert.ok(view.container.textContent.includes('2.0 KB'));
  assert.ok(findButtons(view.container, 'Tải gói ZIP').length > 0);

  await view.unmount();
});

test('SessionExportPage: form tùy chọn cấu hình cho phép chọn ô điền A/B/C/D và hiển thị written-boxes-preview', async () => {
  let exportedConfig = null;
  const view = await mountExportPage({
    loadSession: async () => ({
      id: 's1',
      title: 'Đề Toán 12',
      subject: 'Toán',
      grade: 12,
      status: 'approved',
    }),
    getStatus: async () => ({ status: 'idle' }),
    triggerExport: async (id, config) => {
      exportedConfig = config;
      return {
        status: 'ready',
        filename: 'exam_boxes.zip',
        packaging_key: 'pkg_boxes_1',
        identity_kind: 'configured',
      };
    },
    issueDownloadUrl: async () => ({
      url: 'https://storage.example.test/boxes.zip',
      filename: 'exam_boxes.zip',
    }),
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  // Ban đầu answer_sheet là none -> chưa hiển thị preview written_boxes
  assert.equal(view.container.querySelector('[data-testid="written-boxes-preview"]'), null);

  // Tìm radio Ô điền A/B/C/D
  const writtenRadio = view.container.querySelector('[data-testid="radio-sheet-written"]');
  assert.ok(writtenRadio, 'Phải có radio Ô điền A/B/C/D');

  await act(async () => {
    writtenRadio.click();
    await Promise.resolve();
  });

  // Sau khi click -> written-boxes-preview xuất hiện
  const preview = view.container.querySelector('[data-testid="written-boxes-preview"]');
  assert.ok(preview, 'Phải hiển thị written-boxes-preview khi chọn ô điền A/B/C/D');
  assert.ok(preview.textContent.includes('BẢNG ĐIỀN ĐÁP ÁN TRẮC NGHIỆM'));
  assert.ok(preview.textContent.includes('Học sinh điền A, B, C hoặc D'));

  // Bấm Tạo gói ZIP
  const exportBtn = findButtons(view.container, 'Tạo gói ZIP')[0];
  assert.ok(exportBtn);
  await act(async () => {
    exportBtn.click();
    await Promise.resolve();
  });

  assert.ok(exportedConfig);
  assert.equal(exportedConfig.answer_sheet, 'written_boxes');

  await view.unmount();
});

test('SessionExportPage: tùy chọn OMR bị khóa (disabled) kèm ghi chú kiểm định mẫu in thực tế', async () => {
  const view = await mountExportPage({
    loadSession: async () => ({
      id: 's1',
      title: 'Đề Vật Lý 11',
      subject: 'Vật Lý',
      grade: 11,
      status: 'approved',
    }),
    getStatus: async () => ({ status: 'idle' }),
    triggerExport: async () => ({ status: 'ready', filename: 'exam.zip' }),
    issueDownloadUrl: async () => ({ url: 'https://storage.test/exam.zip', filename: 'exam.zip' }),
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  const omrRadio = view.container.querySelector('[data-testid="radio-sheet-omr"]');
  assert.ok(omrRadio, 'Phải có radio OMR');
  assert.ok(omrRadio.disabled || omrRadio.getAttribute('disabled') !== null, 'Radio OMR phải có thuộc tính disabled');
  assert.ok(view.container.textContent.includes('Đang kiểm định mẫu in'));
  assert.ok(view.container.textContent.includes('Tô tròn OMR'));

  await view.unmount();
});

test('SessionExportPage: tải riêng bảng đáp án CSV và JSON độc lập với gói ZIP', async () => {
  const opened = [];
  const answerKeyCalls = [];

  const view = await mountExportPage({
    loadSession: async () => ({
      id: 's1',
      title: 'Đề Hóa 12',
      subject: 'Hóa',
      grade: 12,
      status: 'approved',
    }),
    getStatus: async () => ({ status: 'idle' }),
    triggerExport: async () => ({ status: 'ready', filename: 'exam.zip' }),
    issueDownloadUrl: async () => ({ url: 'https://storage.test/exam.zip', filename: 'exam.zip' }),
    fetchAnswerKey: async (id, opts) => {
      answerKeyCalls.push({ id, ...opts });
      if (opts.format === 'csv') return 'cau,dap_an\n1,A\n2,C';
      return { answers: { 1: 'A', 2: 'C' } };
    },
    openDownload: (url, filename) => opened.push({ url, filename }),
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  // Tải CSV
  const csvBtn = view.container.querySelector('[data-testid="download-answer-key-csv"]');
  assert.ok(csvBtn, 'Phải có nút tải đáp án CSV');
  await act(async () => {
    csvBtn.click();
    await Promise.resolve();
  });

  assert.equal(answerKeyCalls.length, 1);
  assert.equal(answerKeyCalls[0].format, 'csv');
  assert.equal(opened.length, 1);
  assert.equal(opened[0].filename, 'answer_key_s1_session.csv');

  // Tải JSON
  const jsonBtn = view.container.querySelector('[data-testid="download-answer-key-json"]');
  assert.ok(jsonBtn, 'Phải có nút tải đáp án JSON');
  await act(async () => {
    jsonBtn.click();
    await Promise.resolve();
  });

  assert.equal(answerKeyCalls.length, 2);
  assert.equal(answerKeyCalls[1].format, 'json');
  assert.equal(opened.length, 2);
  assert.equal(opened[1].filename, 'answer_key_s1_session.json');

  await view.unmount();
});

test('SessionExportPage: hiển thị badge định danh gói (configured, ext_default)', async () => {
  const view = await mountExportPage({
    loadSession: async () => ({
      id: 's_identity',
      title: 'Đề Sinh 12',
      status: 'approved',
    }),
    getStatus: async () => ({
      status: 'ready',
      filename: 'bundle.zip',
      packaging_key: 'pkg_conf_999',
      identity_kind: 'configured',
    }),
  });

  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });

  assert.ok(view.container.textContent.includes('Gói xuất tùy chỉnh'));
  assert.ok(view.container.textContent.includes('pkg_conf_999'));

  await view.unmount();
});
