
import {
  AlertCircle,
  ArrowRight,
  Check,
  Clock,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import './stage2.css';

/**
 * GenerationProgressView: Màn hình tiến trình sinh biến thể đề thi (Stage 2 - S05)
 * Thiết kế lại theo chuẩn prototype docs/ui-walkthrough/PREVIEW.html và Issue #94.
 *
 * Tiêu chí cốt lõi:
 * 1. Flow Heading & Stepper 3 bước đặt liền trước tiến trình
 * 2. Meta badge "Có thể duyệt câu đã nhận" khi completedCount >= 1
 * 3. Bảng tiến độ từng mã đề (.generation-table) với badge chữ nhật bo góc 4px
 * 4. Xử lý rớt mạng/offline: banner đỏ "Chưa cập nhật được tiến độ. Đang hiển thị lần nhận gần nhất; không kết luận job thất bại." + nút "Đọc lại trạng thái"
 * 5. Duyệt sớm: nút "Bắt đầu duyệt ->" được bật ngay khi có >= 1 câu hoàn tất
 */
export default function GenerationProgressView({
  sessionId,
  sessionTitle = '',
  numVersions = null,
  totalSourceQuestions = 10,
  progress = null,
  questionStatuses = {},
  warnings = [],
  connectionState = 'connected',
  isDone = false,
  error = null,
  reconnectCount = 0,
  onReconnect,
  isReadingStatus = false,
  onRetryGeneration,
  isRetrying = false,
  onComplete,
  onBackToDashboard,
}) {
  // Suy ra numVersions nếu chưa truyền trực tiếp
  const statusVersions = Object.keys(questionStatuses || {}).map((k) =>
    parseInt(k.split('-')[0], 10),
  );
  const maxVersionFromStatuses =
    statusVersions.length > 0
      ? Math.max(...statusVersions.filter((n) => !isNaN(n) && n > 0))
      : null;
  const effectiveNumVersions =
    numVersions || (maxVersionFromStatuses && maxVersionFromStatuses > 0 ? maxVersionFromStatuses : 2);

  // F02: Phân biệt giữa "Chưa có snapshot" và "Đã xác nhận 0 câu"
  const hasSnapshotData = Boolean(
    progress &&
    (progress.hasData === true ||
     (progress.completedCount !== undefined && progress.completedCount !== null) ||
     (progress.percent !== undefined && progress.percent !== null))
  );

  const totalVariants = effectiveNumVersions * totalSourceQuestions;
  const percent = hasSnapshotData ? Math.min(100, Math.max(0, progress.percent ?? 0)) : 0;
  const completedCount = hasSnapshotData ? (progress.completedCount ?? 0) : null;

  const isPartial =
    progress?.session_status === 'partial_generated' ||
    Boolean(progress?.is_partial) ||
    (isDone && (progress?.percent ?? 100) < 100);

  const isComplete = isDone && !isPartial;
  const isOffline = connectionState === 'disconnected' || connectionState === 'offline';
  const canEarlyReview = completedCount !== null && completedCount >= 1;

  // F108-05: Dựng missing slots theo từng mã × câu ở terminal partial và các câu failed/missing
  const failedSet = new Set();
  const failedList = [];

  function addFailed(v, q) {
    const code = Number(v) > 100 ? v : 100 + Number(v);
    const label = `Câu ${q} · Mã ${code}`;
    if (!failedSet.has(label)) {
      failedSet.add(label);
      failedList.push(label);
    }
  }

  // 1. Quét theo lưới chuẩn version × question
  if (effectiveNumVersions > 0 && totalSourceQuestions > 0) {
    for (let v = 1; v <= effectiveNumVersions; v++) {
      for (let q = 1; q <= totalSourceQuestions; q++) {
        const item = questionStatuses?.[`${v}-${q}`];
        if (
          item?.status === 'failed' ||
          item?.status === 'missing' ||
          (isPartial && !item)
        ) {
          addFailed(v, q);
        }
      }
    }
  }

  // 2. Bổ sung các key failed/missing nằm ngoài dải chuẩn nếu có
  Object.entries(questionStatuses || {}).forEach(([key, item]) => {
    if (item?.status === 'failed' || item?.status === 'missing') {
      const [v, q] = key.split('-');
      if (v && q) {
        addFailed(v, q);
      }
    }
  });

  // F108-04: Chỉ tính từng mã từ trạng thái câu đã xác nhận trong questionStatuses
  const hasPerVersionData =
    Object.keys(questionStatuses || {}).length > 0 ||
    (isDone && !isPartial) ||
    (hasSnapshotData && completedCount === 0);

  // Tạo danh sách các dòng cho từng mã đề
  const rows = [];
  for (let v = 1; v <= effectiveNumVersions; v++) {
    const code = v > 100 ? v : 100 + v;
    let vCompleted = 0;
    let vFailed = 0;
    let vActive = 0;

    for (let q = 1; q <= totalSourceQuestions; q++) {
      const item = questionStatuses[`${v}-${q}`];
      if (item?.status === 'done' || (!item && isDone && !isPartial)) {
        vCompleted++;
      } else if (
        item?.status === 'failed' ||
        item?.status === 'missing' ||
        (isPartial && !item)
      ) {
        vFailed++;
      } else if (
        item?.status === 'generating' ||
        item?.status === 'analyzing' ||
        item?.status === 'retrying' ||
        item?.status === 'validating'
      ) {
        if (isDone && !isPartial) {
          vCompleted++;
        } else {
          vActive++;
        }
      }
    }

    let kind = 'pending';
    let label = 'Chờ lượt';
    if (vCompleted === totalSourceQuestions) {
      kind = 'complete';
      label = 'Đã hoàn tất';
    } else if (vFailed > 0) {
      kind = 'failed';
      label = 'Cần thử lại';
    } else if (vActive > 0 || (vCompleted > 0 && vCompleted < totalSourceQuestions)) {
      kind = 'active';
      label = 'Đang xử lý';
    }

    rows.push({
      vIndex: v,
      code,
      count: vCompleted,
      target: totalSourceQuestions,
      kind,
      label,
    });
  }

  return (
    <div className="stage2-flow">
      <main className="flow-main" role="region" aria-label="Tiến độ tạo biến thể">
        {/* Stepper chuẩn 3 bước kết nối đặt trước tiến trình */}
        <ol className="flow-stepper connected" aria-label="Các bước thực hiện">
          <li className="completed">
            <span className="step-indicator" aria-hidden="true">
              ✓
            </span>
            <span>01. Chuẩn bị đề gốc</span>
          </li>
          <li className="current" aria-current="step">
            <span className="step-indicator" aria-hidden="true">
              02
            </span>
            <span>02. Cấu hình và tạo mã</span>
          </li>
          <li>
            <span className="step-indicator" aria-hidden="true">
              03
            </span>
            <span>03. Duyệt và sử dụng</span>
          </li>
        </ol>

        {/* Flow Heading S05 */}
        <header className="flow-heading">
          <div>
            <span className="sr-only">Tiến trình sinh đề AI</span>
            <h1 className="heading-title">
              {isComplete ? 'Đã tạo đủ biến thể' : 'Đang tạo biến thể'}
            </h1>
            <p className="heading-subtitle">
              <span className="sr-only">Đang tạo các biến thể đề thi · </span>
              {sessionTitle || `Phiên làm việc: ${sessionId}`}
            </p>
            {isComplete && (
              <span className="sr-only">
                Đã hoàn tất sinh đề! Đã sinh xong tất cả các mã đề thi đẳng cấu! Đã sinh xong {effectiveNumVersions} mã đề thi đẳng cấu!
              </span>
            )}
          </div>
          {canEarlyReview && (
            <span className="flow-badge gold">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Có thể duyệt câu đã nhận
            </span>
          )}
        </header>

        {/* Khối hiển thị Tổng tiến độ */}
        <section className="generation-progress" aria-label="Tiến độ tổng thể">
          {!hasSnapshotData ? (
            <div className="flow-notice" role="status">
              <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
              <div>
                <strong>Chưa có dữ liệu tiến độ.</strong> Đang đồng bộ tiến trình sinh đề từ máy chủ...
                <span className="sr-only">--%</span>
              </div>
            </div>
          ) : (
            <>
              <div className="progress-heading">
                <div>
                  <strong>
                    {completedCount} / {totalVariants}
                  </strong>
                  <span>biến thể hoàn tất ({percent}%)</span>
                </div>
                {connectionState === 'reconnecting' && (
                  <span className="flow-badge gold">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Đang kết nối lại ({reconnectCount})
                  </span>
                )}
                {connectionState === 'connected' && (
                  <span className="flow-badge">
                    Kết nối thời gian thực
                  </span>
                )}
                {progress?.estimatedSeconds > 0 && (
                  <small className="muted" style={{ marginLeft: '12px' }}>
                    Ước tính: ~{progress.estimatedSeconds}s
                  </small>
                )}
              </div>
              <p className="progress-subtext">
                {totalSourceQuestions} câu gốc × {effectiveNumVersions} mã đề
              </p>
              <div className="flow-progress-bar" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
                <div
                  className="flow-progress-bar-fill"
                  style={{ width: `${percent}%` }}
                />
              </div>

              {/* Bảng tiến độ từng mã đề */}
              <div
                className="generation-table"
                tabIndex={0}
                role="region"
                aria-label="Tiến độ từng mã đề"
              >
                <div className="generation-table-heading">
                  <span>MÃ ĐỀ</span>
                  <span>TIẾN ĐỘ</span>
                  <span>TRẠNG THÁI</span>
                </div>

                {hasPerVersionData ? (
                  rows.map((row) => {
                    const rowPercent = Math.round((row.count / row.target) * 100);
                    return (
                      <div key={row.code} className="generation-row">
                        <div>
                          <h3>Mã {row.code}</h3>
                          <small>{row.target} câu gốc</small>
                        </div>
                        <div>
                          <p>
                            {row.count}/{row.target} hoàn tất
                          </p>
                          <div className="row-progress-bar">
                            <div
                              className="row-progress-bar-fill"
                              style={{ width: `${rowPercent}%` }}
                            />
                          </div>
                        </div>
                        <div className="generation-state">
                          {row.kind === 'complete' && (
                            <span className="flow-badge approved">
                              <Check className="h-3.5 w-3.5" aria-hidden="true" />
                              Đã hoàn tất
                            </span>
                          )}
                          {row.kind === 'active' && (
                            <span className="flow-badge gold">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                              Đang xử lý
                            </span>
                          )}
                          {row.kind === 'pending' && (
                            <span className="flow-badge">
                              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                              Chờ lượt
                            </span>
                          )}
                          {row.kind === 'failed' && (
                            <span className="flow-badge danger">
                              <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
                              Cần thử lại
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div
                    className="generation-table-empty"
                    style={{
                      padding: '24px 16px',
                      textAlign: 'center',
                      color: 'var(--muted)',
                      fontStyle: 'italic',
                    }}
                  >
                    Chưa có dữ liệu tiến độ từng mã
                  </div>
                )}
              </div>
            </>
          )}

          {/* Hiển thị danh sách cảnh báo từ SSE */}
          {warnings && warnings.length > 0 && (
            <div role="status" className="flow-notice">
              <AlertCircle className="h-5 w-5 shrink-0 text-amber-400" />
              <div>
                <strong>Có {warnings.length} cảnh báo trong quá trình sinh đề:</strong>
                <ul style={{ margin: '4px 0 0', paddingLeft: '20px' }}>
                  {warnings.map((w, idx) => (
                    <li key={idx}>
                      {w.message || `Cảnh báo câu ${w.question_no} (Mã ${w.version_index})`}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Alert lỗi khi có error prop */}
          {error && (
            <div role="alert" className="flow-notice is-error">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <div className="flex-1">
                <span>{error}</span>
                {onReconnect && (
                  <div style={{ marginTop: '8px' }}>
                    <button
                      type="button"
                      onClick={onReconnect}
                      disabled={isReadingStatus}
                      className="quiet-button"
                      style={{ padding: '4px 12px', fontSize: '13px' }}
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isReadingStatus ? 'animate-spin' : ''}`} />
                      {isReadingStatus ? 'Đang kết nối lại...' : 'Kết nối lại'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Thông báo sự cố mất kết nối / Offline theo đúng yêu cầu người dùng */}
          {isOffline && !error && (
            <div role="alert" className="flow-notice is-error">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <div className="flex-1">
                <span>
                  Chưa cập nhật được tiến độ. Đang hiển thị lần nhận gần nhất; không kết luận job thất bại.
                </span>
                {onReconnect && (
                  <div style={{ marginTop: '8px' }}>
                    <button
                      type="button"
                      onClick={onReconnect}
                      disabled={isReadingStatus}
                      className="quiet-button"
                      style={{ padding: '4px 12px', fontSize: '13px' }}
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isReadingStatus ? 'animate-spin' : ''}`} />
                      {isReadingStatus ? 'Đang đọc...' : 'Đọc lại trạng thái'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Thông báo câu bị lỗi */}
          {failedList.length > 0 && (
            <div role="alert" className="flow-notice is-error">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <div>
                <strong>
                  {failedList.join(', ')} chưa tạo được.
                </strong>
                <p>
                  Giữ {completedCount ?? 0} biến thể hoàn tất. Thử lại chỉ phần lỗi; phần chờ vẫn được theo dõi riêng.
                </p>
              </div>
            </div>
          )}

          {/* Thông báo phiên partial_generated */}
          {isPartial && (
            <div role="alert" className="flow-notice is-error">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <div className="flex-1">
                <div>
                  <strong>Phiên ở trạng thái partial_generated:</strong> Một số câu hỏi chưa hoàn thành. {hasSnapshotData && completedCount !== null ? `Còn thiếu ${totalVariants - completedCount} câu.` : ''}
                </div>
                {onRetryGeneration && (
                  <div style={{ marginTop: '8px' }}>
                    <button
                      type="button"
                      onClick={onRetryGeneration}
                      className="quiet-button"
                      style={{ padding: '4px 12px', fontSize: '13px', borderColor: 'var(--danger)', color: 'var(--danger)' }}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Sinh bù các câu còn thiếu
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>

        {/* Flow Footer S05 */}
        <footer className="flow-footer">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="quiet-button"
          >
            Quay về Dashboard
          </button>

          <div className="footer-right">
            <small>
              {hasSnapshotData
                ? `${completedCount ?? 0}/${totalVariants}`
                : `—/${totalVariants}`}{' '}
              biến thể đã nhận · Có thể duyệt ngay khi có câu đầu tiên
            </small>

            {failedList.length > 0 && onRetryGeneration && (
              <button
                type="button"
                onClick={onRetryGeneration}
                disabled={isRetrying || isOffline}
                className="quiet-button"
                style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
              >
                {isRetrying ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Đang thử lại…
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Thử lại phần lỗi
                  </>
                )}
              </button>
            )}

            <button
              type="button"
              disabled={!canEarlyReview}
              onClick={onComplete}
              className="button-primary"
            >
              Bắt đầu duyệt
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </footer>
      </main>
    </div>
  );
}
