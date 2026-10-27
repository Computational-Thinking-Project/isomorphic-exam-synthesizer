// app.js - Single Page Application controller, View navigation & Rendering
document.addEventListener("DOMContentLoaded", function () {
  // Navigation State
  window.APP_STATE = {
    currentView: "view-dashboard",
    activeCode: "101",
    activeQuestionIndex: 0,
    acknowledgedSecurity: false,
    session: window.MOCK_DATA.session,
    sourceQuestions: window.MOCK_DATA.source_questions,
    variants: window.MOCK_DATA.variants
  };

  // View Routing Function
  window.navigateTo = function (viewId) {
    document.querySelectorAll(".view-section").forEach(function (el) {
      el.classList.remove("active");
    });
    var target = document.getElementById(viewId);
    if (target) {
      target.classList.add("active");
      window.APP_STATE.currentView = viewId;
      updateStepper(viewId);
      window.scrollTo(0, 0);

      // Trigger re-render of LaTeX when view changes
      if (window.renderMathInElement) {
        setTimeout(function () {
          window.renderMathInElement(target, {
            delimiters: [
              { left: "$$", right: "$$", display: true },
              { left: "$", right: "$", display: false }
            ],
            throwOnError: false
          });
        }, 50);
      }
    }
  };

  // Update Top Stepper
  function updateStepper(viewId) {
    var stepper = document.getElementById("main-stepper");
    var step1 = document.getElementById("step-1");
    var step2 = document.getElementById("step-2");
    var step3 = document.getElementById("step-3");

    // Hide stepper on dashboard
    if (viewId === "view-dashboard") {
      stepper.style.display = "none";
      return;
    }
    stepper.style.display = "block";

    [step1, step2, step3].forEach(function (s) {
      s.className = "step-item";
    });

    if (viewId === "view-stage1") {
      step1.classList.add("active");
    } else if (viewId === "view-stage2") {
      step1.classList.add("completed");
      step2.classList.add("active");
    } else if (viewId === "view-stage3" || viewId === "view-approval" || viewId === "view-export") {
      step1.classList.add("completed");
      step2.classList.add("completed");
      step3.classList.add("active");
    }
  }

  // Render Initial Math
  function renderAllMath() {
    if (window.renderMathInElement) {
      window.renderMathInElement(document.body, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false }
        ],
        throwOnError: false
      });
    }
  }

  // Initialize
  renderSourcePreview();
  renderReviewScreen();
  renderMatrixTable();
  renderAllMath();

  // Modal handlers
  window.loginMockUser = function () {
    alert("Đăng nhập thành công với tài khoản Google: ThS. Nguyễn Văn A");
    navigateTo("view-dashboard");
  };

  window.openCloneModal = function () {
    document.getElementById("clone-modal").classList.add("active");
  };
  window.closeCloneModal = function () {
    document.getElementById("clone-modal").classList.remove("active");
  };
  window.confirmClone = function () {
    var title = document.getElementById("clone-title-input").value;
    alert("Đã nhân bản thành công: " + (title || "Bản sao mới"));
    closeCloneModal();
    navigateTo("view-stage1");
  };
});

// Render Stage 1 Source Question Previewer
function renderSourcePreview() {
  var container = document.getElementById("source-questions-container");
  if (!container) return;

  var html = "";
  window.MOCK_DATA.source_questions.forEach(function (q, idx) {
    var hasWarn = q.has_unparsed_omml || q.has_missing_answer;
    var badgeHtml = '<span class="badge" style="background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;">✓ Hợp lệ</span>';
    
    if (q.has_missing_answer) {
      badgeHtml = '<span class="badge" style="background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa;">⚠️ Chưa có đáp án</span>';
    } else if (q.has_unparsed_omml) {
      badgeHtml = '<span class="badge" style="background: #fef3c7; color: #92400e; border: 1px solid #fde68a;">⚠️ Công thức chưa nhận diện đủ</span>';
    }

    html += `
      <div class="card" style="margin-bottom: 1.25rem; border-left: 4px solid ${hasWarn ? 'var(--warning)' : 'var(--slate-300)'};">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
          <span style="font-weight: 700; color: var(--slate-900);">Câu ${q.question_no}</span>
          ${badgeHtml}
        </div>
        <div class="math-content">${q.stem}</div>
        <div class="options-grid">
          ${q.options.map(function (opt) {
            var isCorrect = opt.key === q.correct_key;
            return `
              <div class="option-item ${isCorrect ? 'correct' : ''}">
                <strong>${opt.key}.</strong> <span>${opt.text}</span>
                ${isCorrect ? '<span style="margin-left: auto; font-size: 0.8rem;">(Đáp án đúng)</span>' : ''}
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Stage 2 Fake SSE Generation Runner
window.startGenerationJob = function () {
  var btn = document.getElementById("btn-generate-start");
  var progressBox = document.getElementById("sse-progress-box");
  var bar = document.getElementById("sse-bar-fill");
  var statusText = document.getElementById("sse-status-text");

  btn.style.display = "none";
  progressBox.style.display = "block";

  var percent = 0;
  var timer = setInterval(function () {
    percent += 20;
    if (percent === 20) {
      statusText.innerHTML = "Đang phân tích và kích hoạt Blueprint...";
    } else if (percent === 40) {
      statusText.innerHTML = "Đang tổng hợp 4 mã đề qua Gemini API (Mã 101, 102, 103, 104)...";
    } else if (percent === 70) {
      statusText.innerHTML = "Đang kiểm định toán học SymPy CAS & Rule Fallback...";
    } else if (percent === 90) {
      statusText.innerHTML = "Đang biên dịch bảng đáp án và giải pháp chi tiết...";
    } else if (percent >= 100) {
      clearInterval(timer);
      bar.style.width = "100%";
      statusText.innerHTML = "✅ Hoàn tất sinh đề! Đang chuyển sang màn hình Thẩm định 1-1...";
      setTimeout(function () {
        navigateTo("view-stage3");
      }, 1000);
    }
    bar.style.width = percent + "%";
  }, 700);
};

// Render Stage 3 Review 1-1 Screen
function renderReviewScreen() {
  var code = window.APP_STATE.activeCode;
  var idx = window.APP_STATE.activeQuestionIndex;

  var sourceQ = window.APP_STATE.sourceQuestions[idx];
  var variantList = window.APP_STATE.variants[code];
  var variantQ = variantList[idx];

  // Render Source Column
  var srcContainer = document.getElementById("review-source-col");
  if (srcContainer) {
    srcContainer.innerHTML = `
      <div class="column-header">
        <span class="column-title">📄 Đề Gốc — Câu ${sourceQ.question_no}</span>
        <span class="badge" style="background: var(--slate-100);">Bất biến (Original)</span>
      </div>
      <div class="math-content" style="font-weight: 500;">${sourceQ.stem}</div>
      <div class="options-grid" style="grid-template-columns: 1fr;">
        ${sourceQ.options.map(function (opt) {
          var isCor = opt.key === sourceQ.correct_key;
          return `
            <div class="option-item ${isCor ? 'correct' : ''}">
              <strong>${opt.key}.</strong> <span>${opt.text}</span>
            </div>
          `;
        }).join('')}
      </div>
      <div class="solution-box">
        <div class="solution-title">Lời giải câu gốc:</div>
        <div class="math-content">${sourceQ.solution}</div>
      </div>
    `;
  }

  // Render Variant Column
  var varContainer = document.getElementById("review-variant-col");
  if (varContainer) {
    var isAppr = variantQ.status === "approved";
    varContainer.innerHTML = `
      <div class="column-header">
        <span class="column-title">✨ Mã Đề ${code} — Câu ${variantQ.question_no}</span>
        <span class="badge ${isAppr ? 'badge-approved' : 'badge-generated'}">
          ${isAppr ? '✓ Đã duyệt' : 'Đang chờ duyệt'}
        </span>
      </div>
      <div class="math-content" style="font-weight: 500;">${variantQ.stem}</div>
      <div class="options-grid" style="grid-template-columns: 1fr;">
        ${variantQ.options.map(function (opt) {
          var isCor = opt.key === variantQ.correct_key;
          return `
            <div class="option-item ${isCor ? 'correct' : ''}">
              <strong>${opt.key}.</strong> <span>${opt.text}</span>
            </div>
          `;
        }).join('')}
      </div>
      <div class="solution-box" style="border-left-color: var(--success);">
        <div class="solution-title">Lời giải biến thể:</div>
        <div class="math-content">${variantQ.solution}</div>
      </div>
    `;
  }

  // Update Review Progress Counter
  var approvedCount = 0;
  var totalCount = 0;
  Object.keys(window.APP_STATE.variants).forEach(function (c) {
    window.APP_STATE.variants[c].forEach(function (v) {
      totalCount++;
      if (v.status === "approved") approvedCount++;
    });
  });

  document.getElementById("review-progress-counter").innerText = `Đã duyệt ${approvedCount}/${totalCount} câu`;
  document.getElementById("review-progress-bar").style.width = ((approvedCount / totalCount) * 100) + "%";

  // Re-run MathJax/KaTeX
  if (window.renderMathInElement) {
    window.renderMathInElement(document.getElementById("side-by-side-wrapper"), {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false }
      ],
      throwOnError: false
    });
  }
}

// Stage 3 Switch Exam Code (101, 102, 103, 104)
window.switchExamCode = function (code, btn) {
  window.APP_STATE.activeCode = code;
  document.querySelectorAll(".code-tab-btn").forEach(function (b) {
    b.classList.remove("active");
  });
  btn.classList.add("active");
  renderReviewScreen();
};

// Stage 3 Actions
window.handleReviewAction = function (action) {
  var code = window.APP_STATE.activeCode;
  var idx = window.APP_STATE.activeQuestionIndex;
  var q = window.APP_STATE.variants[code][idx];

  if (action === "accept") {
    q.status = "approved";
    // Tự động nhảy sang câu tiếp theo
    if (idx < window.APP_STATE.sourceQuestions.length - 1) {
      window.APP_STATE.activeQuestionIndex++;
    } else {
      alert("Đã duyệt hết câu hỏi của mã đề " + code + "!");
    }
    renderReviewScreen();
  } else if (action === "reject") {
    var varCol = document.getElementById("review-variant-col");
    varCol.style.opacity = "0.5";
    setTimeout(function () {
      q.stem = "Biến thể sinh lại lần 2 cho phương trình $\\log_2(2x + 1) = 3$";
      q.solution = "Lời giải tự động mới: $2x + 1 = 8 \\Leftrightarrow 2x = 7 \\Leftrightarrow x = 3.5$.";
      q.status = "pending_review";
      varCol.style.opacity = "1";
      renderReviewScreen();
    }, 600);
  } else if (action === "revert") {
    var src = window.APP_STATE.sourceQuestions[idx];
    q.stem = src.stem;
    q.options = JSON.parse(JSON.stringify(src.options));
    q.correct_key = src.correct_key;
    q.solution = src.solution;
    q.is_reverted = true;
    q.status = "approved";
    renderReviewScreen();
  }
};

// Render Matrix Answer Table
function renderMatrixTable() {
  var tbody = document.getElementById("matrix-table-body");
  if (!tbody) return;

  var html = "";
  for (var i = 0; i < 5; i++) {
    html += `
      <tr>
        <td style="font-weight: 700;">Câu ${i + 1}</td>
        <td class="matrix-key-cell">${window.MOCK_DATA.variants["101"][i].correct_key}</td>
        <td class="matrix-key-cell">${window.MOCK_DATA.variants["102"][i].correct_key}</td>
        <td class="matrix-key-cell">${window.MOCK_DATA.variants["103"][i].correct_key}</td>
        <td class="matrix-key-cell">${window.MOCK_DATA.variants["104"][i].correct_key}</td>
      </tr>
    `;
  }
  tbody.innerHTML = html;
}

// Keyboard shortcuts for Review
document.addEventListener("keydown", function (e) {
  if (window.APP_STATE && window.APP_STATE.currentView === "view-stage3") {
    if (e.key === "a" || e.key === "A") {
      handleReviewAction("accept");
    } else if (e.key === "r" || e.key === "R") {
      handleReviewAction("reject");
    } else if (e.key === "z" || e.key === "Z") {
      handleReviewAction("revert");
    }
  }
});
