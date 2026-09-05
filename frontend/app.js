/* ============================================================
   DocMind 知库 前端逻辑（原生 JS，无框架）
   核心教学点：
   1. SSE 流式解析：EventSource 只支持 GET，聊天用 POST，
      因此用 fetch + ReadableStream 手动按帧解析；
   2. 安全：所有服务端/用户内容一律用 textContent 插入 DOM，
      绝不使用 innerHTML 拼接（防 XSS）；
   3. 多轮对话：完整历史保存在客户端，随每次请求发给后端。
   ============================================================ */

// ---------- 状态 ----------

const state = {
  docs: [],
  /** 对话历史（发给后端的格式）：{role, content} */
  messages: [],
  streaming: false,
};

// ---------- DOM ----------

const $ = (sel) => document.querySelector(sel);
const docListEl = $("#doc-list");
const docCountEl = $("#doc-count-label");
const messagesEl = $("#messages");
const welcomeEl = $("#welcome");
const chatScrollEl = $("#chat-scroll");
const inputEl = $("#input");
const sendBtn = $("#send-btn");
const uploadStatusEl = $("#upload-status");

// ---------- 文档管理 ----------

async function loadDocs() {
  const resp = await fetch("/api/documents");
  state.docs = await resp.json();
  renderDocs();
}

function renderDocs() {
  docCountEl.textContent = state.docs.length ? `（${state.docs.length} 册）` : "";
  docListEl.textContent = "";
  if (!state.docs.length) {
    const li = document.createElement("li");
    li.className = "doc-item";
    li.style.opacity = "0.5";
    li.textContent = "书架空空如也，先放入文档吧";
    docListEl.appendChild(li);
    return;
  }
  for (const doc of state.docs) {
    const li = document.createElement("li");
    li.className = "doc-item";

    const info = document.createElement("div");
    info.style.flex = "1";
    info.style.minWidth = "0";
    const title = document.createElement("div");
    title.className = "doc-title";
    title.textContent = doc.title;
    title.title = doc.original_name;
    const meta = document.createElement("div");
    meta.className = "doc-meta";
    meta.textContent = `${doc.chunk_count} 个片段 · ${doc.created_at.slice(0, 10)}`;
    info.append(title, meta);

    const del = document.createElement("button");
    del.className = "doc-del";
    del.textContent = "✕";
    del.title = "删除该文档（向量与元数据一并清理）";
    del.addEventListener("click", async () => {
      if (!confirm(`确定删除《${doc.title}》？相关内容将从知识库中移除。`)) return;
      await fetch(`/api/documents/${doc.doc_id}`, { method: "DELETE" });
      loadDocs();
    });

    li.append(info, del);
    docListEl.appendChild(li);
  }
}

async function handleUpload(file) {
  if (!file) return;
  const maxMB = 20;
  if (file.size > maxMB * 1024 * 1024) {
    uploadStatusEl.textContent = `文件超过 ${maxMB}MB 限制`;
    return;
  }
  uploadStatusEl.textContent = `正在解析入库：《${file.name}》…`;
  const form = new FormData();
  form.append("file", file);
  try {
    const resp = await fetch("/api/documents/upload", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "上传失败");
    uploadStatusEl.textContent = `已入库：《${data.title}》· ${data.chunk_count} 个片段`;
    loadDocs();
  } catch (e) {
    uploadStatusEl.textContent = `失败：${e.message}`;
  }
}

// ---------- 聊天 ----------

/** 追加一条消息到页面（role: user / assistant） */
function renderMessage(role, content, sources = null) {
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;

  if (role === "user") {
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = content;
    wrap.appendChild(bubble);
  } else {
    const answer = document.createElement("div");
    answer.className = "answer";
    answer.textContent = content;
    wrap.appendChild(answer);
    if (sources && sources.length) wrap.appendChild(renderSources(sources));
  }

  messagesEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

/** 引用来源卡片：朱砂侧线 + 书摘排版，点击展开/收起全文 */
function renderSources(sources) {
  const box = document.createElement("div");
  box.className = "sources";
  sources.forEach((s, i) => {
    const card = document.createElement("div");
    card.className = "source-card";

    const head = document.createElement("div");
    head.className = "src-head";
    const no = document.createElement("span");
    no.className = "src-no";
    no.textContent = `[${i + 1}]`;
    const title = document.createElement("span");
    title.className = "src-title";
    title.textContent = s.title || "文档";
    const score = document.createElement("span");
    score.className = "src-score";
    score.textContent = s.score != null ? `相关度 ${(s.score * 100).toFixed(1)}%` : "";
    head.append(no, title, score);

    const text = document.createElement("div");
    text.className = "src-text";
    text.textContent = s.text;

    card.addEventListener("click", () => {
      text.classList.toggle("expanded");
      card.classList.remove("flash");
      void card.offsetWidth; // 强制重排以重启动画
      card.classList.add("flash");
    });

    card.append(head, text);
    box.appendChild(card);
  });
  return box;
}

function scrollToBottom() {
  chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
}

/** 发送聊天请求并流式渲染回答 */
async function sendMessage(text) {
  if (state.streaming) return;
  const question = text.trim();
  if (!question) return;

  state.streaming = true;
  sendBtn.disabled = true;
  welcomeEl.style.display = "none";

  // 记录并渲染用户消息
  state.messages.push({ role: "user", content: question });
  renderMessage("user", question);

  // 助手回答占位（先显示"检索中"状态行）
  const statusEl = document.createElement("div");
  statusEl.className = "status-line";
  statusEl.textContent = "正在检索知识库…";
  messagesEl.appendChild(statusEl);
  scrollToBottom();

  // 回答正文与光标
  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  const answerEl = document.createElement("div");
  answerEl.className = "answer";
  const cursor = document.createElement("span");
  cursor.className = "typing-cursor";
  wrap.appendChild(answerEl);
  wrap.appendChild(cursor);
  messagesEl.appendChild(wrap);

  let fullAnswer = "";
  let sources = null;
  let failed = false;

  try {
    await postChatSSE(
      {
        messages: state.messages,
        top_k: 5,
        stream: true,
      },
      (event) => {
        if (event.type === "sources") {
          sources = event.sources;
          // 来源先于回答到达，立即渲染引用卡
          const existing = wrap.querySelector(".sources");
          if (existing) existing.remove();
          if (sources.length) wrap.appendChild(renderSources(sources));
        } else if (event.type === "delta") {
          fullAnswer += event.content;
          answerEl.textContent = fullAnswer;
          scrollToBottom();
        } else if (event.type === "error") {
          failed = true;
          fullAnswer = fullAnswer || `出错了：${event.message}`;
          answerEl.textContent = fullAnswer;
        }
      }
    );
  } catch (e) {
    failed = true;
    answerEl.textContent = `请求失败：${e.message}`;
  }

  statusEl.remove();
  cursor.remove();

  // 正常结束时把助手回答写入历史（失败的回答不参与上下文）
  if (!failed) state.messages.push({ role: "assistant", content: fullAnswer });

  state.streaming = false;
  sendBtn.disabled = false;
  inputEl.focus();
}

/**
 * POST + SSE 流式解析。
 * 事件帧格式：每个事件以 "data: {...}" 行开始，事件之间空行分隔，
 * 流以 "data: [DONE]" 结束。
 */
async function postChatSSE(body, onEvent) {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // stream: true —— 多字节字符（中文）可能被切在两块之间，交给 decoder 缓存
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") {
          onEvent({ type: "done" });
          return;
        }
        try {
          onEvent(JSON.parse(payload));
        } catch {
          /* 忽略无法解析的坏帧 */
        }
      }
    }
  }
}

// ---------- 检索台（调试面板） ----------

const STRATEGY_LABELS = { vector: "向量检索", bm25: "BM25 关键词", hybrid: "混合 RRF" };

function openDebug() {
  $("#debug-overlay").hidden = false;
  $("#debug-query").focus();
}

function closeDebug() {
  $("#debug-overlay").hidden = true;
}

/** 一次检索同时请求三种策略，并排渲染，直观对比"混合检索为什么更好" */
async function runDebugSearch() {
  const query = $("#debug-query").value.trim();
  if (!query) return;
  const topK = Number($("#debug-topk").value);
  const rerank = $("#debug-rerank").checked;
  const columnsEl = $("#debug-columns");

  columnsEl.textContent = "";
  const colEls = ["vector", "bm25", "hybrid"].map((strategy) => {
    const col = document.createElement("div");
    col.className = "debug-col";
    col.appendChild(makeDebugHead(STRATEGY_LABELS[strategy]));
    const loading = document.createElement("div");
    loading.className = "debug-loading";
    loading.textContent = "检索中…";
    col.appendChild(loading);
    columnsEl.appendChild(col);
    return col;
  });

  const hitsByStrategy = await Promise.all(
    ["vector", "bm25", "hybrid"].map((s) =>
      fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, strategy: s, top_k: topK, rerank }),
      })
        .then((r) => r.json())
        .catch(() => [])
    )
  );

  colEls.forEach((col, i) => {
    col.textContent = "";
    col.appendChild(makeDebugHead(STRATEGY_LABELS[["vector", "bm25", "hybrid"][i]]));
    renderDebugColumn(col, hitsByStrategy[i]);
  });
}

function makeDebugHead(label) {
  const h = document.createElement("h3");
  h.textContent = label;
  return h;
}

function renderDebugColumn(colEl, hits) {
  if (!hits.length) {
    const empty = document.createElement("div");
    empty.className = "debug-empty";
    empty.textContent = "无命中";
    colEl.appendChild(empty);
    return;
  }
  hits.forEach((hit, i) => {
    const card = document.createElement("div");
    card.className = "debug-card";

    const rank = document.createElement("span");
    rank.className = "debug-rank";
    rank.textContent = String(i + 1);

    const body = document.createElement("div");
    body.className = "debug-card-body";
    const title = document.createElement("div");
    title.className = "debug-card-title";
    title.textContent = hit.title || "（未命名文档）";
    const text = document.createElement("div");
    text.className = "debug-card-text";
    text.textContent = hit.text;
    const meta = document.createElement("div");
    meta.className = "debug-card-meta";
    if (hit.rank_vector != null) meta.appendChild(makeBadge(`向量路 #${hit.rank_vector}`, "badge-vector"));
    if (hit.rank_bm25 != null) meta.appendChild(makeBadge(`BM25 路 #${hit.rank_bm25}`, "badge-bm25"));
    const scoreLabel =
      hit.rerank_score != null
        ? `重排分 ${hit.rerank_score.toFixed(3)}`
        : `score ${hit.score != null ? hit.score.toFixed(3) : "-"}`;
    meta.appendChild(makeBadge(scoreLabel, "badge-score"));

    body.append(title, text, meta);
    card.append(rank, body);
    colEl.appendChild(card);
  });
}

function makeBadge(label, cls) {
  const b = document.createElement("span");
  b.className = `debug-badge ${cls}`;
  b.textContent = label;
  return b;
}

function bindDebug() {
  $("#debug-btn").addEventListener("click", openDebug);
  $("#debug-close").addEventListener("click", closeDebug);
  $("#debug-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeDebug(); // 点击遮罩关闭
  });
  $("#debug-run").addEventListener("click", runDebugSearch);
  $("#debug-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runDebugSearch();
    if (e.key === "Escape") closeDebug();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#debug-overlay").hidden) closeDebug();
  });
}

// ---------- 交互绑定 ----------

function bindSend() {
  const doSend = () => {
    const text = inputEl.value;
    if (!text.trim() || state.streaming) return;
    inputEl.value = "";          // 发送后清空输入框
    inputEl.style.height = "auto"; // 输入框高度复位为单行
    sendMessage(text);
  };
  sendBtn.addEventListener("click", doSend);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  });
  // 输入框自适应高度
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
  });
}

function bindUpload() {
  $("#file-input").addEventListener("change", (e) => {
    handleUpload(e.target.files[0]);
    e.target.value = ""; // 允许重复上传同一文件
  });
}

function bindMisc() {
  $("#refresh-btn").addEventListener("click", loadDocs);
  $("#sidebar-toggle").addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
  });
  // 示例问题
  $("#suggestions").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) {
      inputEl.value = chip.dataset.q;
      sendMessage(chip.dataset.q);
    }
  });
}

// ---------- 初始化 ----------

loadDocs();
bindSend();
bindUpload();
bindMisc();
bindDebug();
