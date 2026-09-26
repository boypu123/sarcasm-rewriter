/* ============================================================
   SarcasmMaster · 前端逻辑
   通过 fetch + SSE 读取 /api/sarcasm/stream 的流式结果
   ============================================================ */

const $ = (id) => document.getElementById(id);

const els = {
  input:      $("input"),
  charCount:  $("charCount"),
  go:         $("go"),
  clear:      $("clear"),
  copy:       $("copy"),
  examples:   $("examples"),
  resultPanel:$("resultPanel"),
  output:     $("output"),
  cursorHint: $("cursorHint"),
  tracePanel: $("tracePanel"),
  traceList:  $("traceList"),
  traceCount: $("traceCount"),
  traceDetails:$("traceDetails"),
  errorPanel: $("errorPanel"),
  errorText:  $("errorText"),
  health:     $("health"),
};

let running = false;
let timerId = null;
let startedAt = 0;

/* ---------------- 小工具 ---------------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function truncate(s, n = 160) {
  s = String(s == null ? "" : s).replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
}

/* ---------------- 界面状态 ---------------- */

function setRunning(on) {
  running = on;
  els.go.disabled = on;
  els.go.classList.toggle("loading", on);
  els.go.querySelector(".btn-label").textContent = on ? "正在阴阳怪气…" : "开始阴阳怪气";

  clearInterval(timerId);
  if (on) {
    startedAt = Date.now();
    els.cursorHint.hidden = false;
    els.cursorHint.textContent = "Agent 正在思考… 0s";
    timerId = setInterval(() => {
      const s = Math.round((Date.now() - startedAt) / 1000);
      els.cursorHint.textContent = "Agent 正在思考… " + s + "s";
    }, 1000);
  } else {
    els.cursorHint.hidden = true;
  }
}

function showError(msg) {
  els.errorPanel.hidden = false;
  els.errorText.textContent = msg;
}

function clearError() {
  els.errorPanel.hidden = true;
  els.errorText.textContent = "";
}

function addTrace(kind, title, detail) {
  els.tracePanel.hidden = false;
  const li = document.createElement("li");
  li.className = kind;
  const icon = { tool: "⚙", result: "✓", status: "…" }[kind] || "•";
  li.innerHTML =
    '<span class="mark">' + icon + "</span>" +
    '<div class="body">' +
      '<div class="name">' + escapeHtml(title) + "</div>" +
      (detail ? '<div class="arg">' + escapeHtml(detail) + "</div>" : "") +
    "</div>";
  els.traceList.appendChild(li);
  els.traceCount.textContent = els.traceList.children.length + " 步";
}

function resetTrace() {
  els.traceList.innerHTML = "";
  els.traceCount.textContent = "0 步";
  els.tracePanel.hidden = true;
  els.traceDetails.open = true;
}

/* ---------------- 健康检查 ---------------- */

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    els.health.innerHTML =
      '<span class="ok">● </span>后端已连接 · 模型 ' + escapeHtml(d.llm_model || "?") +
      " · 向量库 " + (d.vector_store_ready ? "就绪" : "未就绪");
  } catch (e) {
    els.health.innerHTML = '<span class="bad">● </span>后端未连接（请确认 app.py 正在运行）';
  }
}

/* ---------------- SSE 解析 ---------------- */

function handleEvent(name, payload, state) {
  switch (name) {
    case "status":
      addTrace("status", payload.message || "处理中…");
      break;

    case "tool":
      addTrace("tool", "调用工具 " + (payload.name || ""), truncate(
        payload.args && payload.args.question ? payload.args.question :
        payload.args && payload.args.sentences ? payload.args.sentences :
        payload.args && payload.args.original ? payload.args.original :
        JSON.stringify(payload.args || {}), 140));
      break;

    case "tool_result":
      addTrace("result", (payload.name || "工具") + " 返回", truncate(payload.preview, 140));
      break;

    case "token":
      if (!state.started) { state.started = true; els.output.textContent = ""; }
      els.output.textContent += payload.text || "";
      break;

    case "final":
      els.output.textContent = payload.text || els.output.textContent;
      state.final = payload.text || "";
      els.cursorHint.hidden = true;
      if (payload.elapsed) {
        addTrace("result", "完成", "耗时 " + payload.elapsed + " 秒");
      }
      break;

    case "error":
      showError(payload.message || "未知错误");
      break;

    case "done":
      state.done = true;
      break;
  }
}

async function run() {
  const text = els.input.value.trim();
  if (!text) {
    els.input.focus();
    return;
  }

  setRunning(true);
  clearError();
  resetTrace();
  els.resultPanel.hidden = false;
  els.output.textContent = "";

  const state = { started: false, final: "", done: false };

  try {
    const res = await fetch("/api/sarcasm/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => "");
      throw new Error("HTTP " + res.status + (body ? " · " + truncate(body, 200) : ""));
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let evName = "message";
        const dataLines = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) evName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) continue;

        let payload;
        try { payload = JSON.parse(dataLines.join("\n")); }
        catch (e) { continue; }

        handleEvent(evName, payload, state);
      }
    }

    if (!state.final && !els.output.textContent) {
      showError("模型没有返回任何内容，请重试。");
    }
  } catch (err) {
    showError(err && err.message ? err.message : String(err));
  } finally {
    setRunning(false);
  }
}

/* ---------------- 事件绑定 ---------------- */

els.input.addEventListener("input", () => {
  els.charCount.textContent = els.input.value.length;
});

els.input.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    if (!running) run();
  }
});

els.go.addEventListener("click", () => { if (!running) run(); });

els.clear.addEventListener("click", () => {
  els.input.value = "";
  els.charCount.textContent = "0";
  els.output.textContent = "";
  els.resultPanel.hidden = true;
  resetTrace();
  clearError();
  els.input.focus();
});

els.copy.addEventListener("click", async () => {
  const text = els.output.textContent;
  if (!text) return;
  const old = els.copy.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  els.copy.textContent = "已复制 ✓";
  setTimeout(() => { els.copy.textContent = old; }, 1400);
});

els.examples.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  els.input.value = chip.dataset.text || chip.textContent;
  els.charCount.textContent = els.input.value.length;
  els.input.focus();
});

/* ---------------- 启动 ---------------- */

checkHealth();
els.input.focus();
