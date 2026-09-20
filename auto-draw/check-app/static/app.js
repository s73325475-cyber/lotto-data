function ballClass(n) {
  if (n <= 10) return "c1";
  if (n <= 20) return "c2";
  if (n <= 30) return "c3";
  if (n <= 40) return "c4";
  return "c5";
}

const els = {
  statusLine: document.getElementById("statusLine"),
  balls: document.getElementById("balls"),
  meta: document.getElementById("meta"),
  idle: document.getElementById("idle"),
  error: document.getElementById("error"),
  refreshBtn: document.getElementById("refreshBtn"),
  forceBtn: document.getElementById("forceBtn"),
  tabLatest: document.getElementById("tabLatest"),
  tabHistory: document.getElementById("tabHistory"),
  panelLatest: document.getElementById("panelLatest"),
  panelHistory: document.getElementById("panelHistory"),
  historyList: document.getElementById("historyList"),
  historySub: document.getElementById("historySub"),
};

function ballsBoardHtml(draw, { animate = true, compact = false } = {}) {
  const delay = (i) => (animate ? ` style="animation-delay:${0.02 + i * 0.04}s"` : "");
  const boardClass = compact ? "balls-board is-compact" : "balls-board";
  const win = draw.win6
    .map((n, i) => `<span class="ball ${ballClass(n)}"${delay(i)}>${n}</span>`)
    .join("");
  return `
    <div class="${boardClass}">
      <div class="balls-row">
        ${win}
        <span class="plus"${delay(6)}>+</span>
        <span class="bonus-slot"${delay(7)}>
          <span class="ball bonus">${draw.bonus}</span>
          <span class="bonus-label">보너스</span>
        </span>
      </div>
    </div>
  `;
}

function showIdle(message) {
  els.idle.hidden = false;
  els.balls.hidden = true;
  els.meta.hidden = true;
  els.error.hidden = true;
  if (message) els.statusLine.textContent = message;
}

function showError(message) {
  els.idle.hidden = true;
  els.balls.hidden = true;
  els.meta.hidden = true;
  els.error.hidden = false;
  els.error.innerHTML = `
    <p class="error-title">조회 실패</p>
    <p class="error-desc">${escapeHtml(message)}</p>
  `;
}

function showDraw(draw) {
  els.idle.hidden = true;
  els.error.hidden = true;
  els.balls.hidden = false;
  els.meta.hidden = false;
  els.balls.innerHTML = ballsBoardHtml(draw, { animate: true });
  els.meta.innerHTML = `
    <div class="draw-no">${draw.drawNo}회</div>
    <div class="draw-date">${escapeHtml(draw.date)}</div>
  `;
  els.statusLine.textContent = "동행복권 최신 회차";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setTab(which) {
  const latest = which === "latest";
  els.tabLatest.classList.toggle("is-active", latest);
  els.tabHistory.classList.toggle("is-active", !latest);
  els.tabLatest.setAttribute("aria-selected", String(latest));
  els.tabHistory.setAttribute("aria-selected", String(!latest));
  els.panelLatest.hidden = !latest;
  els.panelHistory.hidden = latest;
  if (!latest) loadHistory();
}

function renderHistory(items) {
  if (!items.length) {
    els.historySub.textContent = "아직 저장된 회차가 없습니다";
    els.historyList.innerHTML = `
      <div class="history-empty">
        <p>이번 주 탭에서 번호를 조회하면<br />이력이 여기에 쌓입니다.</p>
      </div>
    `;
    return;
  }
  els.historySub.textContent = `누적 ${items.length}회`;
  els.historyList.innerHTML = items
    .map(
      (draw) => `
      <article class="history-item">
        <div class="history-head">
          <span class="history-draw">${draw.drawNo}회</span>
          <span class="history-date">${escapeHtml(draw.date || "")}</span>
        </div>
        ${ballsBoardHtml(draw, { animate: false, compact: true })}
      </article>
    `
    )
    .join("");
}

async function loadHistory() {
  els.historySub.textContent = "불러오는 중…";
  try {
    const res = await fetch("/api/history", { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.message || "이력을 불러오지 못했습니다.");
    renderHistory(data.items || []);
  } catch (err) {
    els.historySub.textContent = "이력 조회 실패";
    els.historyList.innerHTML = `
      <div class="history-empty">
        <p>${escapeHtml(err.message || String(err))}</p>
      </div>
    `;
  }
}

async function loadLatest({ force = false } = {}) {
  els.refreshBtn.disabled = true;
  els.forceBtn.disabled = true;
  els.statusLine.textContent = "조회 중…";
  els.error.hidden = true;

  try {
    const url = force ? "/api/latest?force=1" : "/api/latest";
    const res = await fetch(url, { cache: "no-store" });
    const data = await res.json();

    if (!data.ok && data.reason === "waiting") {
      showIdle(data.message || "토요일 20:45 이후 자동 조회");
      return;
    }
    if (!data.ok || !data.draw) {
      showError(data.message || "번호를 가져오지 못했습니다.");
      return;
    }
    showDraw(data.draw);
    if (!els.panelHistory.hidden) loadHistory();
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    els.refreshBtn.disabled = false;
    els.forceBtn.disabled = false;
  }
}

els.refreshBtn.addEventListener("click", () => loadLatest({ force: false }));
els.forceBtn.addEventListener("click", () => loadLatest({ force: true }));
els.tabLatest.addEventListener("click", () => setTab("latest"));
els.tabHistory.addEventListener("click", () => setTab("history"));

(async function boot() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    const st = await res.json();
    if (st.inAutoWindow) {
      await loadLatest({ force: false });
    } else {
      showIdle(st.autoHint || "토요일 20:45 이후 자동 조회");
    }
  } catch {
    showIdle("토요일 20:45 이후 자동 조회");
  }
})();
