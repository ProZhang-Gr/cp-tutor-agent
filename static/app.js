/* ====================================================================
   算法竞赛辅导智能体 — 前端逻辑
   Monaco 编辑器 · SSE 流式 · 智能体可视化 · Chart.js 仪表盘
==================================================================== */

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// 新建/换题时编辑器的空白模板
const DEFAULT_CODE = "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    # 在此编写你的解法\n    print()\n\nmain()\n";
const AD_REWARD_PTS = 5;   // 看广告奖励算力点（与后端 AD_REWARD_POINTS 一致，仅前端展示）
const AD_SECONDS = 8;      // 模拟激励广告倒计时秒数

let editor = null;            // Monaco 实例
let currentAnalysis = {};     // 最近一次题目分析结果
let hintLevel = 0;            // 当前提示层级
let hintHistory = [];         // 已给提示文本
let chatHistory = [];         // 对话历史
let charts = {};              // Chart.js 实例缓存
let pendingSelection = "";     // 当前引用的选中代码片段
let pendingSimilar = [];       // 检索到的相似题（待确认是有效题目后再渲染）
let analysisStale = true;      // 当前题目是否尚未分析 / 分析已过期
let currentProblemId = "";     // 当前题目在题单中的 id（题库 P..../ 自建 U....），空=未入库的新题
let currentProblemMeta = null; // 当前题目元信息 {title,type,difficulty}：题库/自建题选入时记下，未分析直接提交也能正确命名

// 已明确判定「当前题面不是算法题」（且分析未过期）
function isKnownNonProblem() {
  return !analysisStale && currentAnalysis.is_problem === false;
}
function nonProblemHint() {
  toast("这不是一道算法题～点题目下方「💬 让导师解答」，或直接在右下角问导师");
}
function resetAnalysisState() {
  currentAnalysis = {}; analysisStale = true;
  $("#analysis-result").classList.add("hidden");
  $("#strategies").classList.add("hidden");
  hintLevel = 0; hintHistory = [];
  $("#hint-level-num").textContent = "0"; $("#hint-box").innerHTML = "";
  lastStrategies = null;
  const av = $("#ana-viz"); if (av) { av.classList.add("hidden"); av.innerHTML = ""; }
  const ps = $("#prob-solutions"); if (ps) { ps.classList.add("hidden"); ps.innerHTML = ""; }
  resetSolveState();   // 换题/新题：判题结果、导师审阅、导师对话也一并清空，杜绝残留上一题
}

// 清空与「当前这道题」绑定的解题区：判题结果 / 导师审阅批注 / 导师对话
function resetSolveState() {
  const vb = $("#verdict-bar"); if (vb) { vb.classList.add("hidden"); vb.innerHTML = ""; }
  const tr = $("#test-results");
  if (tr) tr.innerHTML = "<div class='empty-hint'>提交评测后，这里显示判题结果与最小反例。</div>";
  reviewData = null;
  lastEval = { problem: "", code: "", counter: null };
  // 导师审阅：清面板 + 编辑器行内批注 + 待应用修订快照
  const rp = $("#review-panel"); if (rp) { rp.classList.add("hidden"); rp.innerHTML = ""; }
  reviewFix = null; preApplySnapshot = null;
  if (editor && window.monaco) reviewDecorations = editor.deltaDecorations(reviewDecorations, []);
  // 导师对话：清空消息、历史与引用
  const cl = $("#chat-log"); if (cl) cl.innerHTML = "";
  chatHistory = [];
  clearQuote();
}

/* 智能体定义：node 名 -> 卡片 */
const AGENTS = [
  { id: "retrieve", icon: "🔍", name: "题库检索官", role: "RAG 相似题检索" },
  { id: "analyze",  icon: "🧠", name: "题目分析师", role: "题型/难度/突破口" },
  { id: "plan",     icon: "🗺️", name: "策略规划师", role: "多解法 + 复杂度" },
  { id: "tutor",    icon: "🎓", name: "苏格拉底导师", role: "分层提示 / 答疑" },
  { id: "review",   icon: "🔬", name: "代码审查师", role: "bug 定位 + 优化" },
  { id: "test",     icon: "⚖️", name: "判题官", role: "真值判定 / 差分对拍" },
  { id: "debug",    icon: "🛠️", name: "调试工程师", role: "ReAct 实验定位 bug" },
];
const NODE2AGENT = { retrieve:"retrieve", analyze:"analyze", plan:"plan",
                     review:"review", judge:"test", summarize:null };

/* ---------------- 初始化 ---------------- */
function initAgentTeam() {
  $("#agent-team").innerHTML = AGENTS.map(a => `
    <div class="agent" id="agent-${a.id}">
      <div class="a-icon">${a.icon}</div>
      <div class="a-info"><div class="a-name">${a.name}</div><div class="a-role">${a.role}</div></div>
      <div class="a-state">待命</div>
    </div>`).join("");
  $("#team-dots").innerHTML = AGENTS.map(a =>
    `<span class="team-dot" id="dot-${a.id}" title="${a.name}">${a.icon}</span>`).join("");
}
function setAgent(id, state) {
  const el = $(`#agent-${id}`);
  if (el) {
    el.classList.remove("working", "done");
    const label = $(`#agent-${id} .a-state`);
    if (state === "working") { el.classList.add("working"); label.textContent = "工作中"; }
    else if (state === "done") { el.classList.add("done"); label.textContent = "完成 ✓"; }
    else { label.textContent = "待命"; }
  }
  const dot = $(`#dot-${id}`);
  if (dot) {
    dot.classList.remove("working", "done");
    if (state === "working" || state === "done") dot.classList.add(state);
  }
  updateTeamProgress();
}
let teamRunIds = [];
function resetAgents(ids) { teamRunIds = ids.slice(); ids.forEach(id => setAgent(id, "idle")); }
function updateTeamProgress() {
  const ids = teamRunIds.length ? teamRunIds : AGENTS.map(a => a.id);
  let done = 0, active = 0;
  ids.forEach(id => {
    const e = $(`#agent-${id}`); if (!e) return;
    if (e.classList.contains("done")) { done++; active++; }
    else if (e.classList.contains("working")) active++;
  });
  const bar = $("#team-prog");
  if (bar) bar.style.width = (active ? Math.round(100 * done / active) : 0) + "%";
}

/* ---- 智能体面板：常驻迷你状态条 ----
   不自动展开；图标随状态点亮(工作中脉冲、完成打勾)，下方进度条显示本轮完成度。
   点状态条仍可手动展开查看各智能体职责。 */
function setTeamOpenClass(open) { $("#team").classList.toggle("open", open); }
function toggleTeam() { setTeamOpenClass(!$("#team").classList.contains("open")); }
function expandPanel(name) { const p = $("#panel-" + name); if (p) p.classList.remove("collapsed"); }

/* Monaco */
require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs" } });
require(["vs/editor/editor.main"], () => {
  // 自定义主题：暖深色「屏幕」，与浅色书桌形成对比，青绿语法点缀
  monaco.editor.defineTheme("arena", {
    base: "vs-dark", inherit: true,
    rules: [
      { token: "comment", foreground: "7d8a72", fontStyle: "italic" },
      { token: "keyword", foreground: "5fb3a1" },
      { token: "string", foreground: "d9b777" },
      { token: "number", foreground: "e0a96d" },
      { token: "function", foreground: "84b6d8" },
    ],
    colors: {
      "editor.background": "#211E18",
      "editor.foreground": "#E8E2D4",
      "editorLineNumber.foreground": "#5a554a",
      "editorLineNumber.activeForeground": "#5fb3a1",
      "editor.selectionBackground": "#1f6f6644",
      "editor.lineHighlightBackground": "#2a261f",
      "editorCursor.foreground": "#5fb3a1",
      "editorIndentGuide.background": "#322e26",
    },
  });
  editor = monaco.editor.create($("#editor"), {
    value: "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    # 在此编写你的解法\n    print()\n\nmain()\n",
    language: "python", theme: "arena", fontSize: 14, minimap: { enabled: false },
    fontFamily: "JetBrains Mono, Consolas, monospace",
    automaticLayout: true, scrollBeyondLastLine: false, padding: { top: 12 },
    glyphMargin: true,   // 供导师审阅在出问题的行打批注图标
    // 自动补全
    quickSuggestions: { other: true, comments: false, strings: false },
    suggestOnTriggerCharacters: true, tabCompletion: "on",
    wordBasedSuggestions: "allDocuments",   // 0.45 用字符串枚举；传 true 会失效
    suggest: { showWords: true, showSnippets: true, preview: true },
  });
  registerPyCompletions();
  // 恢复上次代码
  const savedCode = localStorage.getItem("cp_code");
  if (savedCode) editor.setValue(savedCode);
  // 自动保存（防抖）
  let codeTimer;
  editor.onDidChangeModelContent(() => {
    clearTimeout(codeTimer);
    codeTimer = setTimeout(() => localStorage.setItem("cp_code", editor.getValue()), 500);
  });
  // 编辑器内快捷键
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => runCode());
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => submitCode());
  // 右键菜单：框选代码后「问导师这段」
  editor.addAction({
    id: "ask-tutor-selection",
    label: "💬 问导师这段代码",
    contextMenuGroupId: "navigation",
    contextMenuOrder: 1,
    run: () => captureSelection(),
  });
});

/* ---------------- 代码自动补全（Python 常用片段） ---------------- */
let _pyComplDone = false;
function registerPyCompletions() {
  if (_pyComplDone || !window.monaco) return;
  _pyComplDone = true;
  const K = monaco.languages.CompletionItemKind;
  const SNIP = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
  const SNIPPETS = [
    { label: "readall", detail: "读入全部并按空白切分", insert: "data = sys.stdin.buffer.read().split()" },
    { label: "main", detail: "竞赛 main 模板", insert: "import sys\n\ndef main():\n    data = sys.stdin.buffer.read().split()\n    ${1:pass}\n\nif __name__ == \"__main__\":\n    main()" },
    { label: "forr", detail: "for i in range(n)", insert: "for ${1:i} in range(${2:n}):\n    ${3:pass}" },
    { label: "fori", detail: "枚举下标与值", insert: "for ${1:i}, ${2:x} in enumerate(${3:arr}):\n    ${4:pass}" },
    { label: "readint", detail: "读一个整数", insert: "${1:n} = int(input())" },
    { label: "readints", detail: "读一行整数到列表", insert: "${1:a} = list(map(int, input().split()))" },
    { label: "defaultdict", detail: "from collections import defaultdict", insert: "from collections import defaultdict\n${1:d} = defaultdict(${2:int})" },
    { label: "Counter", detail: "from collections import Counter", insert: "from collections import Counter\n${1:cnt} = Counter(${2:arr})" },
    { label: "deque", detail: "from collections import deque", insert: "from collections import deque\n${1:q} = deque()" },
    { label: "heap", detail: "heapq 小根堆", insert: "import heapq\n${1:h} = []\nheapq.heappush(${1:h}, ${2:x})" },
    { label: "memo", detail: "记忆化搜索装饰器", insert: "from functools import lru_cache\n\n@lru_cache(maxsize=None)\ndef ${1:dfs}(${2:x}):\n    ${3:pass}" },
  ];
  monaco.languages.registerCompletionItemProvider("python", {
    provideCompletionItems(model, position) {
      const w = model.getWordUntilPosition(position);
      const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber,
                      startColumn: w.startColumn, endColumn: w.endColumn };
      return { suggestions: SNIPPETS.map(s => ({
        label: s.label, kind: K.Snippet, detail: s.detail,
        insertText: s.insert, insertTextRules: SNIP, range,
      })) };
    },
  });
}

/* ---------------- SSE 流式工具 ---------------- */
async function sseStream(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {   // 非流式错误（如 402 PRO_REQUIRED / 429 限流）：解析 JSON 并引导
    let data = {};
    try { data = await resp.json(); } catch (e) {}
    if (data.error === "PRO_REQUIRED") { promptUnlock("该功能"); refreshBilling(); return; }
    throw new Error(data.message || data.error || ("请求失败 HTTP " + resp.status));
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const line = block.split("\n").find(l => l.startsWith("data:"));
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch (e) {} }
    }
  }
}

/* ---------------- 题目分析流 ---------------- */
async function runAnalyze() {
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目");
  setProblemText(problem);       // 分析开始即切到全文展示
  const btn = $("#btn-analyze");
  btn.disabled = true; btn.textContent = "🧠 智能体分析中…";
  $("#analysis-result").classList.add("hidden");
  $("#strategies").classList.add("hidden");
  resetAgents(["retrieve", "analyze", "plan"]);
  setAgent("retrieve", "working");
  hintLevel = 0; hintHistory = []; $("#hint-level-num").textContent = "0"; $("#hint-box").innerHTML = "";

  try {
    const deep = $("#deep-check") && $("#deep-check").checked && currentBilling.is_pro;
    await sseStream("/api/analyze", { problem, deep }, (ev) => {
      if (ev.event !== "node") { if (ev.event === "error") toast("分析出错：" + ev.message); return; }
      const aid = NODE2AGENT[ev.node];
      if (aid) setAgent(aid, "done");
      if (ev.node === "retrieve") {
        pendingSimilar = ev.data.similar || [];
        setAgent("analyze", "working");
      } else if (ev.node === "analyze") {
        // 先判断是不是有效题目：是 → 继续渲染并规划；不是 → 提示去问导师
        if (renderAnalysis(ev.data.analysis)) {
          renderSimilar(pendingSimilar);
          setAgent("plan", "working");
        }
      } else if (ev.node === "plan") {
        renderStrategies(ev.data.strategies);
      }
    });
    // 有效新题 → 用分析师起的标题自动命名、纳入「我的题目」
    if (currentAnalysis.is_problem !== false && !currentProblemId) {
      try {
        const r = await fetch("/api/save-problem", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: currentAnalysis.title || "未命名题目",
            type: currentAnalysis.type || "其他",
            difficulty: currentAnalysis.difficulty || "未知",
            description: problem,
          }),
        }).then(r => r.json());
        if (r.id) {
          currentProblemId = r.id;
          currentProblemMeta = { title: currentAnalysis.title || "未命名", type: currentAnalysis.type || "其他", difficulty: currentAnalysis.difficulty || "未知" };
          await loadProblemList();
          loadProblemSolutions(currentProblemId);
          setPbCurrent(currentAnalysis.title || "未命名");
          toast("📌 已加入「我的题目」：" + (currentAnalysis.title || ""));
        }
      } catch (e) {}
    } else {
      toast(currentAnalysis.is_problem === false ? "这看起来不是一道算法题" : "✅ 分析完成");
    }
  } catch (e) { toast("请求失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "🚀 启动智能体分析"; refreshBilling(); }
}

function renderAnalysis(a) {
  currentAnalysis = a || {};
  analysisStale = false;      // 刚对当前题面做完分析
  $("#analysis-result").classList.remove("hidden");
  // 非有效题目：只给友好提示 + 转交导师的入口
  if (a && a.is_problem === false) {
    $("#analysis-notice-text").textContent = a.message ||
      "这看起来不像一道完整的算法题。你可以粘贴含输入/输出与样例的题面再分析，或点下方让导师直接解答～";
    $("#analysis-notice").classList.remove("hidden");
    $("#analysis-body").classList.add("hidden");
    $("#strategies").classList.add("hidden");
    return false;
  }
  $("#analysis-notice").classList.add("hidden");
  $("#analysis-body").classList.remove("hidden");
  $("#ana-type").textContent = a.type || "—";
  $("#ana-diff").textContent = a.difficulty || "—";
  const score = a.difficulty_score || 0;
  $("#ana-stars").textContent = "★".repeat(Math.round(score / 2)) + "☆".repeat(5 - Math.round(score / 2));
  $("#ana-complexity").textContent = a.target_complexity || "—";
  $("#ana-insight").textContent = a.key_insight || "—";
  const dd = a.deep_dive;
  const hasDeep = Array.isArray(dd) ? dd.length > 0 : !!(dd && String(dd).trim());
  if (hasDeep) { $("#ana-deepdive").innerHTML = renderDeepDive(dd); $("#ana-deepdive-wrap").classList.remove("hidden"); }
  else $("#ana-deepdive-wrap").classList.add("hidden");
  $("#ana-pitfalls").innerHTML = (a.pitfalls || []).map(p => `<li>${esc(p)}</li>`).join("") || "<li>—</li>";
  $("#ana-knowledge").innerHTML = (a.knowledge_points || []).map(k => `<span class="chip">${esc(k)}</span>`).join("");
  refreshVizLinks();
  return true;
}

// 在题目剖析里挂出「相关算法图解」超链接：检索到对应算法 → 一键跳到图解看动图
let lastStrategies = null;
function refreshVizLinks() {
  const box = $("#ana-viz");
  if (!box || !window.vizMatch) return;
  const a = currentAnalysis || {};
  let text = [a.type, a.key_insight, a.title, (a.knowledge_points || []).join(" ")].join(" ");
  if (lastStrategies && lastStrategies.strategies)
    text += " " + lastStrategies.strategies.map(s => s.name + " " + (s.idea || "")).join(" ");
  const matches = window.vizMatch(text);
  if (!matches.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  box.classList.remove("hidden");
  box.innerHTML = `<span class="ana-viz-label">🎬 相关算法图解 · 点开看动图</span>` +
    `<div class="ana-viz-chips">` +
    matches.map(m => `<button type="button" class="ana-viz-chip" data-id="${esc(m.id)}">${esc(m.name)} ›</button>`).join("") +
    `</div>`;
  $$("#ana-viz .ana-viz-chip").forEach(b => b.onclick = () => openVisualizer(b.dataset.id));
}
// 切到「算法图解」标签并定位到指定算法
function openVisualizer(id) {
  const tab = document.querySelector('.tab[data-view="visualizer"]');
  if (tab) tab.click();
  if (window.vizOpen) window.vizOpen(id);
}
// 解题推演：分步卡片，避免一大坨文字墙
function renderDeepDive(dd) {
  if (Array.isArray(dd)) {
    return `<ol class="dd-steps">` + dd.map(s => {
      const t = s.step ? `<span class="dd-step-t">${esc(s.step)}</span>` : "";
      return `<li class="dd-step">${t}<span class="dd-step-d">${esc(s.detail || "")}</span></li>`;
    }).join("") + `</ol>`;
  }
  // 兼容旧的纯字符串：按段落断开，至少别糊成一团
  return String(dd).split(/\n+/).map(p => `<p class="dd-para">${esc(p.trim())}</p>`).join("");
}
function askTutorAbout() {
  const text = $("#problem-input").value.trim();
  if (!text) return;
  if ($("#workspace").classList.contains("right-collapsed")) setCollapsed("right", false);
  $("#chat-input").value = text;
  sendChat();
  $("#chat-log").scrollIntoView({ behavior: "smooth", block: "center" });
  toast("已转交导师解答");
}
function renderSimilar(list) {
  $("#ana-similar").innerHTML = (list || []).map(s =>
    `<span class="chip clickable" data-pid="${s.id}">${esc(s.title)} · ${esc(s.type)}</span>`).join("") || "<span class='chip'>无</span>";
  $$("#ana-similar .chip.clickable").forEach(c =>
    c.onclick = () => loadProblem(c.dataset.pid));
}
function renderStrategies(s) {
  if (!s || !s.strategies) return;
  lastStrategies = s; refreshVizLinks();   // 策略里也常点名具体算法，纳入图解匹配
  $("#strategies").classList.remove("hidden");
  $("#strategy-list").innerHTML = s.strategies.map(st => {
    const rec = (st.name === s.recommended) ? `<span class="recommend-tag">推荐</span>` : "";
    const stars = "★".repeat(st.rating || 0);
    return `<div class="strategy">
      <div class="strategy-head"><span class="strategy-name">${esc(st.name)} ${rec}</span>
        <span class="strategy-rating">${stars}</span></div>
      <div class="strategy-idea">${esc(st.idea || "")}</div>
      <div class="strategy-meta">
        <span class="cx">⏱ ${esc(st.time || "?")}</span>
        <span class="cx space">💾 ${esc(st.space || "?")}</span>
        ${st.when_to_use ? `<span class="cx" style="color:var(--ink-dim)">${esc(st.when_to_use)}</span>` : ""}
      </div></div>`;
  }).join("");
  $("#strategy-path").textContent = s.learning_path ? "📈 学习路径：" + s.learning_path : "";
}

/* ---------------- 运行代码（自定义输入） ---------------- */
async function runCode() {
  if (!editor) return;
  const code = editor.getValue();
  const stdin = $("#custom-input").value;
  $("#run-output").textContent = "运行中…";
  switchIO("custom");
  try {
    const r = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, stdin }),
    }).then(r => r.json());
    if (r.status === "OK") $("#run-output").textContent = r.stdout || "(无输出)";
    else $("#run-output").textContent = `[${r.status}] ${r.stderr || ""}\n${r.stdout || ""}`;
  } catch (e) { $("#run-output").textContent = "运行失败：" + e.message; }
}

/* ---------------- 提交评测流 ---------------- */
async function submitCode() {
  if (!editor) return;
  const code = editor.getValue();
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目并分析");
  if (isKnownNonProblem()) return nonProblemHint();
  if (!code.trim()) return toast("请先在编辑器里写代码");
  const btn = $("#btn-submit");
  btn.disabled = true; btn.textContent = "⚙️ 评测中…";
  switchIO("result");
  $("#verdict-bar").classList.add("hidden");
  $("#test-results").innerHTML = "<div class='empty-hint'>智能体评测进行中…</div>";
  resetAgents(["review", "test", "debug"]);
  setAgent("review", "working");
  lastEval.problem = problem; lastEval.code = code; lastEval.counter = null;

  try {
    // 新鲜分析优先；否则回落到题库/自建题选入时记下的元信息；都没有才「未命名」
    const fresh = (!analysisStale && currentAnalysis.is_problem !== false) ? currentAnalysis : {};
    const pm = currentProblemMeta || {};
    await sseStream("/api/evaluate", {
      problem, code, language: $("#lang-select").value,
      problem_id: currentProblemId,
      problem_title: fresh.title || pm.title || "未命名",
      problem_type: fresh.type || pm.type || "其他",
      difficulty: fresh.difficulty || pm.difficulty || "未知",
    }, (ev) => {
      if (ev.event === "node") {
        if (ev.node === "review") { setAgent("review", "done"); setAgent("test", "working"); renderReview(ev.data.review); }
        if (ev.node === "judge") renderTests(ev.data.judge);
        if (ev.node === "summarize") { setAgent("test", "done"); renderVerdict(ev.data.summary); }
      } else if (ev.event === "error") { toast("评测出错：" + ev.message); }
    });
    toast("✅ 评测完成");
    if ($("#io-history").classList.contains("active")) loadSubmissions();
  } catch (e) { toast("评测失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "✅ 提交评测"; refreshBilling(); }
}

let reviewData = null;
let lastEval = { problem: "", code: "", counter: null };
function renderReview(r) { reviewData = r; }
function renderTests(judge) {
  if (!judge) return;
  lastEval.counter = judge.counter = judge.counterexample || null;
  const mode = judge.mode;
  const modeLabel = mode === "truth"
    ? `🟢 真值判定 · 官方测试数据 ${judge.passed}/${judge.total} 通过`
    : `🟡 差分对拍 · 暴力解当真值${judge.stress ? "（" + esc(judge.stress.note) + "）" : ""}`;

  // 最小反例 + 调试入口（最重要，放最上面）
  let counterHtml = "";
  const ce = judge.counterexample;
  if (ce) {
    counterHtml = `
      <div class="counter-box">
        <div class="counter-head">⚠️ 最小反例 · ${esc(ce.reason || "WA")}</div>
        <div class="io-row"><label>输入</label><pre>${esc(ce.input || "(空)")}</pre></div>
        <div class="io-row"><label>正确答案</label><pre>${esc(ce.expected || "")}</pre></div>
        <div class="io-row"><label>你的输出</label><pre>${esc(ce.actual || "(空)")}</pre></div>
        <button id="btn-debug" class="btn btn-accent btn-block" onclick="startDebug()">🛠️ 让调试 agent 帮我定位</button>
        <div id="debug-panel" class="debug-panel"></div>
      </div>`;
  }

  const cases = (judge.results || []).map((t, i) => `
    <div class="test-case">
      <div class="tc-head" onclick="this.nextElementSibling.classList.toggle('open')">
        <span class="tc-status ${t.status}">${t.status}</span>
        <span class="tc-name">用例 ${(t.index != null ? t.index : i) + 1}</span>
        <span class="tc-cat">${esc(t.kind || "")}</span>
      </div>
      <div class="tc-detail">
        <div class="io-row"><label>输入</label><pre>${esc(t.input || "(空)")}</pre></div>
        <div class="io-row"><label>期望输出</label><pre>${esc(t.expected || "(未提供)")}</pre></div>
        <div class="io-row"><label>实际输出</label><pre>${esc(t.actual || "(空)")}</pre></div>
      </div>
    </div>`).join("");

  $("#test-results").innerHTML =
    `<div class="judge-mode ${mode}">${modeLabel}</div>` + counterHtml +
    (cases ? `<div class="cases-wrap">${cases}</div>` : "");
}

/* ---------------- Agentic 调试回路 ---------------- */
async function startDebug() {
  const ce = lastEval.counter;
  if (!ce) return toast("没有可用于调试的反例");
  const panel = $("#debug-panel");
  if (!panel) return;
  panel.innerHTML = "";
  const btn = $("#btn-debug");
  if (btn) { btn.disabled = true; btn.textContent = "🛠️ 调试 agent 工作中…"; }
  setAgent("debug", "working");
  let stepEl = null;
  try {
    await sseStream("/api/debug",
      { problem: lastEval.problem, code: lastEval.code, counterexample: ce },
      (ev) => {
        const d = ev.data || {};
        if (ev.event === "thought") {
          stepEl = document.createElement("div");
          stepEl.className = "dbg-step";
          stepEl.innerHTML = `<div class="dbg-thought"><span class="dbg-step-no">第 ${d.step} 步</span><b>💭 思考</b></div>
            <div class="dbg-thought-body">${marked.parse(d.text || "")}</div>`;
          panel.appendChild(stepEl);
        } else if (ev.event === "action") {
          const a = document.createElement("div");
          a.className = "dbg-action";
          a.innerHTML = `<div class="dbg-label">🔧 运行探针${d.stdin ? " · stdin: " + esc((d.stdin || "").slice(0, 40)) : ""}</div><pre class="dbg-code"></pre>`;
          (stepEl || panel).appendChild(a);
          highlightInto(a.querySelector(".dbg-code"), d.code || "", "python");
        } else if (ev.event === "observation") {
          const o = document.createElement("div");
          o.className = "dbg-obs";
          o.innerHTML = `<div class="dbg-label">👁 观察 · ${esc(d.status)}</div><pre>${esc(d.stdout || d.stderr || "(空)")}</pre>`;
          (stepEl || panel).appendChild(o);
        } else if (ev.event === "conclusion") {
          const c = document.createElement("div");
          c.className = "dbg-conclusion";
          c.innerHTML = `<div class="dbg-label">✅ 定位结论</div>
            <div><b>根因：</b>${esc(d.root_cause || "")}</div>
            ${d.evidence ? `<div><b>证据：</b>${esc(d.evidence)}</div>` : ""}
            ${d.fix_hint ? `<div class="dbg-fix"><b>修复方向：</b>${esc(d.fix_hint)}</div>` : ""}`;
          panel.appendChild(c);
        } else if (ev.event === "error") { toast("调试出错：" + ev.message); }
        panel.scrollTop = panel.scrollHeight;
      });
  } catch (e) { toast("调试失败：" + e.message); }
  finally {
    setAgent("debug", "done");
    if (btn) { btn.disabled = false; btn.textContent = "🛠️ 再调试一次"; }
    refreshBilling();
  }
}
function renderVerdict(s) {
  if (!s) return;
  const bar = $("#verdict-bar");
  bar.classList.remove("hidden", "pass", "partial", "fail");
  const pass = s.passed === s.total && s.total > 0;
  bar.classList.add(pass ? "pass" : (s.passed > 0 ? "partial" : "fail"));
  if (s.total === 0 && reviewData && reviewData.syntax_ok === false)
    $("#test-results").innerHTML = "<div class='empty-hint'>代码存在语法错误，已跳过测试。请先修复后再提交。</div>";
  let extra = "";
  if (reviewData) extra = ` · 静态审查 ${reviewData.score}分 · ${reviewData.bugs.length} 个问题`;
  bar.innerHTML = `<span>${pass ? "🎉" : "🔧"} ${esc(s.verdict)}（${s.passed}/${s.total} 用例）${extra}</span>
                   <span>综合得分 ${s.final_score}</span>`;
  // 把审查师的建议推给导师区
  if (reviewData && reviewData.next_step) {
    addHintEntry("审查师建议", reviewData.next_step + (reviewData.bugs.length ?
      "\n\n主要问题：" + reviewData.bugs.map(b => `[${b.severity}] ${b.issue}`).join("；") : ""));
  }
  if (pass && currentProblemId) { toast("🎉 已通过，已在题单标记"); loadProblemList(); }
}

/* ---------------- 苏格拉底提示流 ---------------- */
async function requestHint() {
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目");
  if (!currentBilling.is_pro) return promptUnlock("苏格拉底导师");
  if (isKnownNonProblem()) return nonProblemHint();
  expandPanel("tutor");
  if (hintLevel >= 4) return toast("已到最深提示层级");
  hintLevel++;
  $("#hint-level-num").textContent = hintLevel;
  setAgent("tutor", "working");
  const entry = addHintEntry("第 " + hintLevel + " 层提示", "");
  const body = entry.querySelector(".hint-text");
  let acc = "";
  body.classList.add("cursor-blink");
  try {
    await sseStream("/api/hint", {
      problem, analysis: analysisStale ? {} : currentAnalysis, question: "",
      hint_level: hintLevel, history: hintHistory.join("\n---\n"),
    }, (ev) => {
      if (ev.event === "token") { acc += ev.text; body.innerHTML = marked.parse(acc); }
    });
    hintHistory.push(acc);
  } catch (e) { toast("提示获取失败"); }
  finally { body.classList.remove("cursor-blink"); setAgent("tutor", "done"); refreshBilling(); }
}
function addHintEntry(label, text) {
  const div = document.createElement("div");
  div.className = "hint-entry";
  div.innerHTML = `<div class="lvl">${esc(label)}</div><div class="hint-text">${text ? marked.parse(text) : ""}</div>`;
  $("#hint-box").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return div;
}

/* ---------------- 自由对话流 ---------------- */
async function sendChat() {
  const q = $("#chat-input").value.trim();
  if (!q) return;
  if (!currentBilling.is_pro) return promptUnlock("导师对话");
  expandPanel("chat");
  $("#chat-input").value = "";
  const sel = pendingSelection;
  addMsg("user", q + (sel ? "  〔已引用选中代码 " + sel.split("\n").length + " 行〕" : ""));
  clearQuote();
  setAgent("tutor", "working");
  const aMsg = addMsg("assistant", "");
  let acc = "";
  aMsg.classList.add("cursor-blink");
  try {
    await sseStream("/api/chat", {
      problem: $("#problem-input").value.trim(), question: q, history: chatHistory,
      code: editor ? editor.getValue() : "", selection: sel,
      hints: hintHistory.join("\n---\n"),   // 把苏格拉底分层提示带进对话上下文，保持连贯
    }, (ev) => {
      if (ev.event === "token") { acc += ev.text; aMsg.innerHTML = marked.parse(acc);
        $("#chat-log").scrollTop = $("#chat-log").scrollHeight; }
    });
    chatHistory.push({ role: "user", content: q }, { role: "assistant", content: acc });
  } catch (e) { aMsg.textContent = "回复失败"; }
  finally { aMsg.classList.remove("cursor-blink"); setAgent("tutor", "done"); refreshBilling(); }
}
function captureSelection() {
  if (!editor) return;
  const sel = editor.getModel().getValueInRange(editor.getSelection());
  if (!sel || !sel.trim()) { toast("请先在编辑器里选中一段代码"); return; }
  pendingSelection = sel;
  $("#quote-lines").textContent = sel.split("\n").length;
  $("#quote-chip").classList.remove("hidden");
  $("#chat-input").focus();
}
function clearQuote() {
  pendingSelection = "";
  $("#quote-chip").classList.add("hidden");
}
function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.innerHTML = text ? (role === "assistant" ? marked.parse(text) : esc(text)) : "";
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  return div;
}

/* ---------------- 导师审阅：行内批注 + 修订补丁 ---------------- */
let reviewDecorations = [];   // 当前 Monaco 批注装饰 id
let reviewFix = null;         // 待应用的修订 {code, explain}
let preApplySnapshot = null;  // 应用修订前的代码快照（用于撤销）
let diffEditor = null;        // diff 弹窗里的 Monaco diff 编辑器实例
const SEV_LABEL = { high: "严重", med: "注意", low: "建议" };

async function requestReview() {
  const code = editor ? editor.getValue() : "";
  if (!code.trim()) return toast("请先在编辑器里写代码");
  expandPanel("review");
  const btn = $("#btn-review");
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = "🔎 导师审阅中…";
  setAgent("review", "working");
  const panel = $("#review-panel");
  panel.classList.remove("hidden");
  panel.innerHTML = '<div class="empty-hint">导师正在逐行通读你的代码…</div>';
  try {
    const r = await fetch("/api/review-code", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        problem: $("#problem-input").value.trim(),
        code, language: $("#lang-select").value,
      }),
    });
    const data = await r.json();
    if (!r.ok || data.error) {
      panel.innerHTML = `<div class="empty-hint">${esc(data.error || "审阅失败")}</div>`;
      return;
    }
    renderReviewResult(data);
  } catch (e) {
    panel.innerHTML = '<div class="empty-hint">审阅失败，请稍后再试</div>';
  } finally {
    btn.disabled = false; btn.textContent = old;
    setAgent("review", "done");
    refreshBilling();
  }
}

function renderReviewResult(data) {
  const panel = $("#review-panel");
  const anns = data.annotations || [];
  applyReviewDecorations(anns);
  let html = `<div class="rv-head">🔎 导师审阅<button class="rv-clear" id="rv-clear" title="清除代码上的批注高亮">清除批注</button></div>`;
  if (data.summary) html += `<div class="rv-summary">${esc(data.summary)}</div>`;
  if (anns.length) {
    html += `<div class="rv-anns">` + anns.map(a => `
      <button type="button" class="rv-ann sev-${a.severity}" data-line="${a.line}" title="点击跳到第 ${a.line} 行">
        <span class="rv-ann-line">L${a.line}</span>
        <span class="rv-ann-sev">${SEV_LABEL[a.severity] || "注意"}</span>
        <span class="rv-ann-note">${esc(a.note)}</span>
      </button>`).join("") + `</div>`;
  } else {
    html += `<div class="rv-summary-sub">没有需要单独标注的行。</div>`;
  }
  if (data.has_fix && data.proposed_code) {
    reviewFix = { code: data.proposed_code, explain: data.fix_explanation || "" };
    html += `<div class="rv-fix">
        <div class="rv-fix-txt">🔧 导师准备了一份修订版${data.fix_explanation ? "：" + esc(data.fix_explanation) : ""}</div>
        <button class="btn btn-primary btn-block" id="rv-view-diff">查看修订对比 · 决定是否应用</button>
      </div>`;
  } else { reviewFix = null; }
  panel.innerHTML = html;
  $$("#review-panel .rv-ann").forEach(b => b.onclick = () => jumpToLine(parseInt(b.dataset.line)));
  const clr = $("#rv-clear"); if (clr) clr.onclick = clearReviewDecorations;
  const vd = $("#rv-view-diff"); if (vd) vd.onclick = openDiffModal;
}

function jumpToLine(line) {
  if (!editor || !line) return;
  editor.revealLineInCenter(line);
  editor.setPosition({ lineNumber: line, column: 1 });
  editor.focus();
}

function applyReviewDecorations(anns) {
  if (!editor || !window.monaco) return;
  const total = editor.getModel().getLineCount();
  const decos = (anns || []).filter(a => a.line >= 1 && a.line <= total).map(a => ({
    range: new monaco.Range(a.line, 1, a.line, 1),
    options: {
      isWholeLine: true,
      className: "ann-line sev-" + a.severity,
      glyphMarginClassName: "ann-glyph sev-" + a.severity,
      glyphMarginHoverMessage: { value: "**导师批注**：" + a.note },
      overviewRuler: { color: "rgba(191,74,48,.7)", position: monaco.editor.OverviewRulerLane.Right },
    },
  }));
  reviewDecorations = editor.deltaDecorations(reviewDecorations, decos);
}

function clearReviewDecorations() {
  if (editor) reviewDecorations = editor.deltaDecorations(reviewDecorations, []);
  const clr = $("#rv-clear"); if (clr) { clr.textContent = "已清除"; clr.disabled = true; }
}

/* ----- 修订 diff 弹窗：预览 → 应用/拒绝（应用后可撤销） ----- */
function openDiffModal() {
  if (!reviewFix || !window.monaco) return;
  $("#diff-explain").textContent = reviewFix.explain || "";
  $("#diff-modal").classList.remove("hidden");
  const orig = monaco.editor.createModel(editor.getValue(), "python");
  const modi = monaco.editor.createModel(reviewFix.code, "python");
  if (diffEditor) { diffEditor.dispose(); diffEditor = null; }
  diffEditor = monaco.editor.createDiffEditor($("#diff-editor"), {
    theme: "arena", readOnly: true, automaticLayout: true,
    fontSize: 13, renderSideBySide: true, minimap: { enabled: false },
    fontFamily: "JetBrains Mono, Consolas, monospace",
  });
  diffEditor.setModel({ original: orig, modified: modi });
}

function closeDiffModal() {
  $("#diff-modal").classList.add("hidden");
  if (diffEditor) {
    const m = diffEditor.getModel();
    diffEditor.dispose(); diffEditor = null;
    if (m) { if (m.original) m.original.dispose(); if (m.modified) m.modified.dispose(); }
  }
}

function applyFix() {
  if (!reviewFix || !editor) return closeDiffModal();
  preApplySnapshot = editor.getValue();
  const model = editor.getModel();
  editor.pushUndoStop();
  editor.executeEdits("tutor-fix", [{ range: model.getFullModelRange(), text: reviewFix.code }]);
  editor.pushUndoStop();
  closeDiffModal();
  clearReviewDecorations();
  toast("✅ 已应用导师修订 · Ctrl+Z 或下方「撤销」可回退");
  const panel = $("#review-panel");
  if (!$("#rv-undo-btn")) {
    const bar = document.createElement("div");
    bar.className = "rv-undo";
    bar.innerHTML = `<span>已应用修订</span><button class="btn btn-ghost" id="rv-undo-btn">↶ 撤销，恢复我原来的代码</button>`;
    panel.appendChild(bar);
    $("#rv-undo-btn").onclick = undoFix;
  }
}

function undoFix() {
  if (preApplySnapshot == null || !editor) return;
  const model = editor.getModel();
  editor.pushUndoStop();
  editor.executeEdits("tutor-fix-undo", [{ range: model.getFullModelRange(), text: preApplySnapshot }]);
  editor.pushUndoStop();
  preApplySnapshot = null;
  const b = $("#rv-undo-btn"); if (b) b.closest(".rv-undo").remove();
  toast("已恢复你原来的代码");
}

/* ---------------- 结果区高度可拖动 ---------------- */
function initIoResize() {
  const panel = $("#io-panel"), handle = $("#io-resize");
  if (!panel || !handle) return;
  const saved = parseInt(localStorage.getItem("cp_io_h") || "0");
  if (saved >= 160) panel.style.height = saved + "px";
  let startY = 0, startH = 0;
  const onMove = (e) => {
    const dy = startY - e.clientY;   // 把手往上拖 → 结果区增高
    const h = Math.max(160, Math.min(window.innerHeight - 230, startH + dy));
    panel.style.height = h + "px";
  };
  const onUp = () => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    document.body.style.userSelect = "";
    localStorage.setItem("cp_io_h", String(Math.round(panel.offsetHeight)));
  };
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startY = e.clientY; startH = panel.offsetHeight;
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
}

/* ---------------- 题库浮层下拉 ---------------- */
let problemItems = [];      // 合并后的题目（题库 + 我的题目）
let pbDiffFilter = "";      // 当前难度筛选（""=全部）
let pbAcOnly = false;       // 只看未通过

async function loadProblemList() {
  const [bank, mine, solvedResp] = await Promise.all([
    fetch("/api/problems").then(r => r.json()),
    fetch("/api/my-problems").then(r => r.json()).catch(() => []),
    fetch("/api/solved").then(r => r.json()).catch(() => ({ solved: [] })),
  ]);
  const solved = new Set(solvedResp.solved || []);
  const toItem = (p, group) => ({
    id: String(p.id), title: p.title || "未命名",
    difficulty: p.difficulty || "未知", type: p.type || "其他",
    solved: solved.has(p.id), group,
  });
  problemItems = (bank || []).map(p => toItem(p, "题库"));
  if (mine && mine.length)
    problemItems = problemItems.concat(mine.map(p => toItem(p, "我的题目")));
  renderProblemList();
}

function renderPbProgress(solved, total) {
  const el = $("#pb-progress");
  if (!el) return;
  const pct = total ? Math.round(100 * solved / total) : 0;
  el.innerHTML = `
    <div class="pb-prog-top">
      <span class="pb-prog-label">题库完成进度</span>
      <span class="pb-prog-num"><b>${solved}</b> / ${total}</span>
    </div>
    <div class="pb-prog-bar"><i style="width:${pct}%"></i></div>`;
}

function renderProblemList() {
  const q = ($("#pb-search").value || "").trim().toLowerCase();
  const match = (p) => {
    if (pbDiffFilter && p.difficulty !== pbDiffFilter) return false;
    if (pbAcOnly && p.solved) return false;
    if (q && !(p.title.toLowerCase().includes(q) || p.type.toLowerCase().includes(q))) return false;
    return true;
  };
  const list = problemItems.filter(match);
  $("#pb-count").textContent = list.length + " 题";

  // 进度条按题库全量统计（不随筛选变化）
  const bankAll = problemItems.filter(p => p.group === "题库");
  renderPbProgress(bankAll.filter(p => p.solved).length, bankAll.length);

  if (!list.length) { $("#pb-list").innerHTML = '<div class="pb-empty">没有匹配的题目</div>'; return; }

  const diffTag = (d) => {
    const cls = (d === "简单" || d === "入门") ? "easy" : (d === "困难" ? "hard" : "mid");
    return `<span class="pb-diff ${cls}">${esc(d)}</span>`;
  };
  const ico = (solved) => `<span class="pb-ico ${solved ? "ac" : "todo"}">${solved ? "✓" : ""}</span>`;
  const row = (p, showType) => `
    <button type="button" class="pb-item${p.id === String(currentProblemId) ? " active" : ""}" data-id="${esc(p.id)}">
      ${ico(p.solved)}
      <span class="pb-name">${esc(p.title)}</span>
      ${showType ? `<span class="pb-type">${esc(p.type)}</span>` : ""}
      ${diffTag(p.difficulty)}
    </button>`;

  // 题库按题型分组（仿 LeetCode 分类），「我的题目」单独成组
  const bankList = list.filter(p => p.group === "题库");
  const mineList = list.filter(p => p.group === "我的题目");
  let html = "";
  if (bankList.length) {
    const byType = {};
    bankList.forEach(p => (byType[p.type] = byType[p.type] || []).push(p));
    Object.keys(byType).forEach(t => {
      html += `<div class="pb-group">${esc(t)}<span class="pb-group-n">${byType[t].length}</span></div>`;
      html += byType[t].map(p => row(p, false)).join("");
    });
  }
  if (mineList.length) {
    html += `<div class="pb-group">我的题目<span class="pb-group-n">${mineList.length}</span></div>`;
    html += mineList.map(p => row(p, true)).join("");
  }
  $("#pb-list").innerHTML = html;
  $$("#pb-list .pb-item").forEach(b => b.onclick = () => { loadProblem(b.dataset.id); closePbPanel(); });
}

function setPbCurrent(title) { $("#pb-current").textContent = title || "题库"; }
function openPbPanel() {
  $("#pb-overlay").classList.add("open");
  $("#pb-drawer").classList.add("open");
  $("#pb-dropdown").classList.add("open");
  renderProblemList();
  setTimeout(() => $("#pb-search").focus(), 60);
}
function closePbPanel() {
  $("#pb-overlay").classList.remove("open");
  $("#pb-drawer").classList.remove("open");
  $("#pb-dropdown").classList.remove("open");
}
function togglePbPanel() {
  $("#pb-drawer").classList.contains("open") ? closePbPanel() : openPbPanel();
}
function pasteNewProblem() {       // 抽屉里「粘贴自己的题目」：切回可编辑空白输入
  currentProblemId = "";
  currentProblemMeta = null;
  resetAnalysisState();
  setProblemText("");
  editProblem();
  closePbPanel();
}

async function loadProblem(pid) {
  if (!pid) return;
  const p = await fetch("/api/problems/" + pid).then(r => r.json());
  if (!p || p.error) return;
  let text = p.description;
  if (p.sample_input) text += `\n\n样例输入：\n${p.sample_input}\n\n样例输出：\n${p.sample_output}`;
  setProblemText(text);          // 全文展示（只读），同时写入数据源
  resetAnalysisState();          // 换题 → 旧分析/提示作废
  currentProblemId = pid;        // 记住当前题目 id（用于 AC 标记）
  currentProblemMeta = { title: p.title || "未命名", type: p.type || "其他", difficulty: p.difficulty || "未知" };
  setPbCurrent(p.title);
  await loadProblemCode(pid);    // 换题 → 编辑器恢复该题上次代码，否则回到空白模板
  if ($("#io-history").classList.contains("active")) loadSubmissions();
  loadProblemSolutions(pid);     // 聚合这道题的社群题解
  toast("已载入：" + p.title);
}

// 换题时同步编辑器：有该题历史提交则载入最近一次代码，否则重置为空白模板
async function loadProblemCode(pid) {
  if (!editor) return;
  try {
    const r = await fetch("/api/submissions?problem_id=" + encodeURIComponent(pid)).then(r => r.json());
    const last = (r.submissions || []).find(s => s.code && s.code.trim());
    editor.setValue(last ? last.code : DEFAULT_CODE);
  } catch (e) { editor.setValue(DEFAULT_CODE); }
}

/* ---------------- 题解聚合：本题的社群帖子 ---------------- */
function tagClsOf(t) { return ({ "求助": "ask", "题解": "solu", "讨论": "disc", "反馈": "fb" })[t] || "disc"; }
// 把「这道题」的社群题解/讨论聚合到题目下方，一键跳到社群看
async function loadProblemSolutions(pid) {
  const box = $("#prob-solutions");
  if (!box) return;
  if (!pid) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  try {
    const r = await fetch("/api/community/posts?problem_id=" + encodeURIComponent(pid)).then(r => r.json());
    const posts = r.posts || [];
    if (!posts.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }
    box.classList.remove("hidden");
    box.innerHTML = `<div class="ps-head">💬 社群里这道题的讨论 · ${posts.length} 篇</div>` +
      `<div class="ps-list">` + posts.slice(0, 6).map(p =>
        `<button type="button" class="ps-item" data-id="${p.id}">
           <span class="cm-tag-badge ${tagClsOf(p.tag)}">${esc(p.tag)}</span>
           <span class="ps-title">${esc(p.title)}</span>
           <span class="ps-meta">👍${p.likes} · 💬${p.reply_count}</span>
         </button>`).join("") + `</div>`;
    box.querySelectorAll(".ps-item").forEach(b => b.onclick = () => openCommunityPost(Number(b.dataset.id)));
  } catch (e) { box.classList.add("hidden"); box.innerHTML = ""; }
}
// 切到「社群」标签并打开指定帖子
function openCommunityPost(id) {
  const tab = document.querySelector('.tab[data-view="community"]');
  if (tab) tab.click();
  if (window.cmOpenPost) window.cmOpenPost(id);
}
// 供 community.js 复用：当前正在做的题（发帖时默认关联） / 从社群跳回工作台载题
window.cpCurrentProblem = () => currentProblemId
  ? { id: currentProblemId, title: (currentProblemMeta && currentProblemMeta.title) || "" } : null;
window.cpLoadProblem = (pid) => {
  const tab = document.querySelector('.tab[data-view="workspace"]');
  if (tab) tab.click();
  loadProblem(pid);
};

/* ---------------- 每日报告（Pro） ---------------- */
let lastReport = null;
async function genReport() {
  const btn = $("#btn-gen-report"); btn.disabled = true; btn.textContent = "生成中…";
  try {
    const r = await fetch("/api/daily-report");
    const data = await r.json();
    if (!r.ok) { $("#report-body").innerHTML = `<span class="empty-hint">${esc(data.error || "生成失败")}</span>`; $("#btn-dl-report").classList.add("hidden"); return; }
    lastReport = data;
    const st = data.stats || {};
    $("#report-body").innerHTML =
      `<div class="r-stats">📅 ${esc(data.date)} ｜ 尝试 ${st.attempted} · 通过 ${st.ac} · AI互动 ${st.llm_calls} 次</div>` +
      `<div class="r-narr">${marked.parse(data.narrative || "")}</div>`;
    $("#btn-dl-report").classList.remove("hidden");
    $("#btn-share-report").classList.remove("hidden");
  } catch (e) { toast("生成失败"); }
  finally { btn.disabled = false; btn.textContent = "生成今日报告"; }
}

/* ---------------- 分享卡片（客户端 Canvas 生成，平台无关） ---------------- */
function openShareCard() {
  if (!lastReport) return toast("请先生成今日报告");
  $("#share-modal").classList.remove("hidden");
  drawShareCard(lastReport);
}
function closeShareCard() { $("#share-modal").classList.add("hidden"); }

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
// 朴素分词换行（中文逐字、英文按词），返回绘制的行数
function wrapText(ctx, text, x, y, maxW, lh, maxLines) {
  const tokens = String(text || "").replace(/\s+/g, " ").trim().split(/(?<=[一-龥])|(?=[一-龥])|\s/);
  let line = "", lines = 0;
  for (let i = 0; i < tokens.length; i++) {
    const test = line + tokens[i];
    if (ctx.measureText(test).width > maxW && line) {
      if (maxLines && lines >= maxLines - 1) { ctx.fillText(line.replace(/\s+$/, "") + "…", x, y); return lines + 1; }
      ctx.fillText(line, x, y); line = tokens[i].trim() ? tokens[i] : ""; y += lh; lines++;
    } else { line = test; }
  }
  if (line.trim()) { ctx.fillText(line, x, y); lines++; }
  return lines;
}

async function drawShareCard(rep) {
  const canvas = $("#share-canvas");
  const SC = 2, W = 720, H = 940;
  canvas.width = W * SC; canvas.height = H * SC;
  const ctx = canvas.getContext("2d");
  ctx.scale(SC, SC);
  try { await document.fonts.ready; } catch (e) {}
  const SERIF = '"Fraunces","Songti SC",serif', SANS = '"IBM Plex Sans","PingFang SC",sans-serif',
        MONO = '"JetBrains Mono",monospace';
  const ink = "#2E2A22", inkDim = "#6E6657", inkMute = "#9C9484",
        accent = "#1F6F66", gold = "#BE8E2C", paper = "#FBF7EF", line = "#E1D8C6", tint = "#F0E9D9";
  const st = rep.stats || {};

  // 背景 + 卡片
  ctx.fillStyle = "#EBE3D3"; ctx.fillRect(0, 0, W, H);
  roundRect(ctx, 26, 26, W - 52, H - 52, 24); ctx.fillStyle = paper; ctx.fill();
  ctx.strokeStyle = line; ctx.lineWidth = 1.5; ctx.stroke();

  const M = 60;
  // 品牌标记
  roundRect(ctx, M, 64, 52, 52, 14); ctx.fillStyle = accent; ctx.fill();
  ctx.fillStyle = paper; ctx.font = "700 24px " + MONO; ctx.textBaseline = "middle"; ctx.textAlign = "left";
  ctx.fillText("/A", M + 11, 91);
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = ink; ctx.font = "700 30px " + SERIF; ctx.fillText("ARENA", M + 68, 88);
  ctx.fillStyle = inkMute; ctx.font = "400 14px " + SANS; ctx.fillText("算法竞赛辅导智能体 · 学习日报", M + 68, 109);

  // 分隔线
  ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(M, 150); ctx.lineTo(W - M, 150); ctx.stroke();

  // 日期
  ctx.fillStyle = gold; ctx.font = "700 15px " + MONO; ctx.fillText("📅 " + (rep.date || ""), M, 188);

  // 标语
  ctx.fillStyle = ink; ctx.font = "600 26px " + SERIF;
  ctx.fillText("今天，我又往前走了一步", M, 232);

  // 统计三宫格
  const tiles = [
    { n: st.attempted != null ? st.attempted : 0, l: "今日尝试" },
    { n: st.ac != null ? st.ac : 0, l: "成功攻克" },
    { n: st.llm_calls != null ? st.llm_calls : 0, l: "AI 互动" },
  ];
  const tw = (W - 2 * M - 2 * 18) / 3, ty = 268, th = 132;
  tiles.forEach((t, i) => {
    const tx = M + i * (tw + 18);
    roundRect(ctx, tx, ty, tw, th, 16); ctx.fillStyle = tint; ctx.fill();
    ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = accent; ctx.font = "700 46px " + SERIF; ctx.textAlign = "center";
    ctx.fillText(String(t.n), tx + tw / 2, ty + 68);
    ctx.fillStyle = inkDim; ctx.font = "500 15px " + SANS;
    ctx.fillText(t.l, tx + tw / 2, ty + 102);
  });
  ctx.textAlign = "left";

  // AI 点评
  ctx.fillStyle = inkMute; ctx.font = "700 13px " + MONO; ctx.fillText("AI 导师寄语", M, 452);
  ctx.fillStyle = ink; ctx.font = "400 17px " + SANS;
  const narr = String(rep.narrative || "").replace(/[#*`>_\-]/g, "").replace(/\n+/g, " ").trim();
  wrapText(ctx, narr, M, 484, W - 2 * M, 30, 9);

  // 底部品牌条
  roundRect(ctx, M, H - 132, W - 2 * M, 56, 14); ctx.fillStyle = accent; ctx.fill();
  ctx.fillStyle = paper; ctx.font = "600 16px " + SANS; ctx.textAlign = "left";
  ctx.fillText("🎓 和 ARENA 一起刷题，每天进步一点点", M + 22, H - 98);
  ctx.fillStyle = inkMute; ctx.font = "400 13px " + MONO; ctx.textAlign = "center";
  ctx.fillText("cp-tutor-agent · LangGraph 多智能体辅导", W / 2, H - 52);
  ctx.textAlign = "left";
}

function downloadShareCard() {
  const canvas = $("#share-canvas");
  canvas.toBlob((blob) => {
    if (!blob) return toast("生成失败");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "ARENA学习卡片_" + (lastReport ? lastReport.date : "") + ".png";
    a.click(); URL.revokeObjectURL(url);
    toast("已保存图片");
  });
}
async function copyShareCard() {
  const canvas = $("#share-canvas");
  try {
    const blob = await new Promise((res) => canvas.toBlob(res));
    if (!blob || !navigator.clipboard || !window.ClipboardItem) throw new Error("unsupported");
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
    toast("✅ 图片已复制，可直接粘贴发送");
  } catch (e) { toast("此浏览器不支持复制图片，请用「保存图片」"); }
}
async function downloadReport() {
  if (!lastReport) return;
  try {
    const r = await fetch("/api/daily-report/pdf", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: lastReport.date, narrative: lastReport.narrative, stats: lastReport.stats }),
    });
    if (!r.ok) return toast("下载失败");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "ARENA学习日报_" + lastReport.date + ".pdf";
    a.click(); URL.revokeObjectURL(url);
  } catch (e) { toast("下载失败"); }
}

/* ---------------- 仪表盘 ---------------- */
async function loadDashboard() {
  const s = await fetch("/api/stats").then(r => r.json());
  $("#st-total").textContent = s.total;
  $("#st-solved").textContent = s.solved;
  $("#st-rate").textContent = s.solve_rate + "%";
  $("#st-avg").textContent = s.avg_score;

  // 刷题日历：GitHub 风格贡献热力图
  renderHeatmap(s.daily_activity || {}, s.active_days || 0);
  // 判题结果分布
  const errColors = { AC: "#3C8B57", WA: "#BF4A30", TLE: "#C2922E", RE: "#7C5BC0", CE: "#7C5BC0", RUN: "#3A6EA5" };
  const eLabels = Object.keys(s.error_dist);
  drawChart("error", "chart-error", {
    type: "doughnut",
    data: { labels: eLabels.length ? eLabels : ["暂无数据"],
      datasets: [{ data: eLabels.length ? Object.values(s.error_dist) : [1],
        backgroundColor: eLabels.length ? eLabels.map(k => errColors[k] || "#1F6F66") : ["#E1D8C6"],
        borderColor: "#FBF7EF", borderWidth: 3 }] },
    options: { plugins: { legend: { labels: { color: "#6E6657", font: { family: "IBM Plex Sans" } } } } },
  });
  // 薄弱点
  $("#weak-list").innerHTML = s.weak_points.length ? s.weak_points.map(w => `
    <div class="weak-item"><span class="weak-name">${esc(w.type)}</span>
      <div class="weak-bar-wrap"><div class="weak-bar"><div class="weak-fill" style="width:${w.rate}%"></div></div>
      <span class="weak-pct">${w.rate}%</span></div></div>`).join("")
    : "<div class='empty-hint'>暂无薄弱点，继续加油！</div>";
  // 近期
  $("#recent-body").innerHTML = s.recent.length ? s.recent.map(r => `
    <tr><td>${esc(r.problem_title)}</td><td>${esc(r.problem_type)}</td>
    <td><span class="res-pill ${r.error_kind}">${r.error_kind}</span></td><td>${r.score}</td>
    <td class="recent-time">${r.ts ? fmtSubTime(r.ts) : "—"}</td></tr>`).join("")
    : "<tr><td colspan='5' class='empty-hint'>还没有提交记录</td></tr>";
}
// GitHub 风格刷题日历：近 53 周 × 7 天的贡献热力图
function renderHeatmap(daily, activeDays) {
  const heat = $("#cal-heat"), monthsEl = $("#cal-months");
  if (!heat) return;
  const DAY = 86400000, WEEKS = 53;
  const MON = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  // 网格右下角对齐到本周六；左上角是约一年前的周日
  const startSunday = new Date(today.getTime() - today.getDay() * DAY - (WEEKS - 1) * 7 * DAY);
  // 提交次数→色阶（按学生低频提交场景用绝对计数，比分位更直观）
  const level = (c) => c <= 0 ? 0 : c === 1 ? 1 : c === 2 ? 2 : c === 3 ? 3 : 4;

  let cells = "", total = 0;
  const cur = new Date(startSunday);
  for (let w = 0; w < WEEKS; w++) {
    for (let d = 0; d < 7; d++) {
      const key = fmt(cur), c = daily[key] || 0;
      total += c;
      if (cur > today) cells += `<i class="cal-cell future"></i>`;
      else cells += `<i class="cal-cell l${level(c)}" title="${key} · ${c} 次提交"></i>`;
      cur.setTime(cur.getTime() + DAY);
    }
  }
  heat.style.gridTemplateColumns = `repeat(${WEEKS},13px)`;
  heat.innerHTML = cells;
  // 月份轴：每当某周的周日落入新的月份就在该列打一个标签
  let months = "", lastMon = -1;
  for (let w = 0; w < WEEKS; w++) {
    const d0 = new Date(startSunday.getTime() + w * 7 * DAY), m = d0.getMonth();
    if (m !== lastMon) { lastMon = m; months += `<span class="cal-mon" style="grid-column:${w + 1}">${MON[m]}</span>`; }
  }
  if (monthsEl) { monthsEl.style.gridTemplateColumns = `repeat(${WEEKS},13px)`; monthsEl.innerHTML = months; }
  const sub = $("#cal-sub");
  if (sub) sub.textContent = `近一年 ${total} 次提交 · 活跃 ${activeDays} 天`;
}
function drawChart(key, canvasId, cfg) {
  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart($("#" + canvasId), cfg);
}

/* ---------------- 通用 ---------------- */
function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function switchIO(which) {
  $$(".io-tab").forEach(t => t.classList.toggle("active", t.dataset.io === which));
  $$(".io-pane").forEach(p => p.classList.toggle("active", p.id === "io-" + which));
  if (which === "history") loadSubmissions();
}

/* ---------------- 本题提交记录 ---------------- */
function fmtSubTime(ts) {
  const d = new Date(ts * 1000), p = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
async function loadSubmissions() {
  const wrap = $("#sub-list");
  if (!currentProblemId) {
    wrap.innerHTML = '<div class="empty-hint">从题库选择、或保存为「我的题目」后，这里会按题记录你每次提交的代码与结果。</div>';
    return;
  }
  wrap.innerHTML = '<div class="empty-hint">加载提交记录…</div>';
  try {
    const r = await fetch("/api/submissions?problem_id=" + encodeURIComponent(currentProblemId)).then(r => r.json());
    renderSubmissions(r.submissions || []);
  } catch (e) { wrap.innerHTML = '<div class="empty-hint">加载失败</div>'; }
}
function renderSubmissions(subs) {
  const wrap = $("#sub-list");
  if (!subs.length) {
    wrap.innerHTML = '<div class="empty-hint">本题还没有提交记录，提交评测后会自动记录。</div>';
    return;
  }
  const n = subs.length;
  wrap.innerHTML = subs.map((s, i) => {
    const kind = s.error_kind || (s.passed ? "AC" : "WA");
    const cls = kind === "AC" ? "ac" : (kind === "CE" ? "ce" : "wa");
    const tests = s.tests_total ? `${s.tests_passed}/${s.tests_total} 用例 · ` : "";
    return `<div class="sub-item">
        <div class="sub-head" onclick="this.parentElement.querySelector('.sub-code').classList.toggle('open');this.querySelector('.sub-toggle').classList.toggle('open')">
          <span class="sub-verdict ${cls}">${esc(kind)}</span>
          <span class="sub-no">#${n - i}</span>
          <span class="sub-meta">${tests}得分 ${s.score}</span>
          <span class="sub-time">${fmtSubTime(s.ts)}</span>
          <span class="sub-toggle">▾</span>
        </div>
        <div class="sub-code">
          <div class="sub-code-bar"><span>提交 #${n - i} 的代码</span><button class="sub-copy" data-idx="${i}">⎘ 复制</button></div>
          <pre>${esc(s.code || "(这条记录未保存代码)")}</pre>
        </div>
      </div>`;
  }).join("");
  $$("#sub-list .sub-copy").forEach(b => b.onclick = (e) => {
    e.stopPropagation();
    const code = subs[parseInt(b.dataset.idx)].code || "";
    navigator.clipboard.writeText(code)
      .then(() => { b.textContent = "✓ 已复制"; setTimeout(() => { b.textContent = "⎘ 复制"; }, 1500); })
      .catch(() => toast("复制失败"));
  });
}
let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

function copyCode() {
  if (!editor) return;
  navigator.clipboard.writeText(editor.getValue())
    .then(() => toast("已复制代码")).catch(() => toast("复制失败"));
}
// 用 Monaco 的着色器把一段代码渲染成带语法高亮的 HTML（沿用编辑器主题配色）
function highlightInto(preEl, code, lang) {
  if (!preEl) return;
  if (window.monaco && monaco.editor && monaco.editor.colorize) {
    monaco.editor.colorize(code || "", lang || "python", {})
      .then(html => { preEl.innerHTML = html; })
      .catch(() => { preEl.textContent = code || ""; });
  } else { preEl.textContent = code || ""; }
}

/* ---------------- 面板：折叠 / 拖宽 / 记忆 ---------------- */
const MIN_W = 220, MAX_W = 560;
function setCollapsed(side, on) {
  const ws = $("#workspace");
  ws.classList.toggle(side + "-collapsed", on);   // Flex 下 display:none 即可，中间自动占满
  localStorage.setItem(side === "left" ? "cp_lc" : "cp_rc", on ? "1" : "0");
  const btn = document.querySelector(`.col-toggle[data-side="${side}"]`);
  if (btn) btn.textContent = side === "left" ? (on ? "›" : "‹") : (on ? "‹" : "›");
}
function initPanels() {
  const ws = $("#workspace");
  const lw = localStorage.getItem("cp_lw"), rw = localStorage.getItem("cp_rw");
  if (lw) ws.style.setProperty("--left-w", lw + "px");
  if (rw) ws.style.setProperty("--right-w", rw + "px");
  if (localStorage.getItem("cp_lc") === "1") setCollapsed("left", true);
  if (localStorage.getItem("cp_rc") === "1") setCollapsed("right", true);

  $$(".col-toggle").forEach(btn => btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const side = btn.dataset.side;
    setCollapsed(side, !ws.classList.contains(side + "-collapsed"));
  }));

  $$(".gutter").forEach(g => g.addEventListener("mousedown", (e) => {
    if (e.target.classList.contains("col-toggle")) return;     // 点按钮不拖
    const side = g.dataset.side;
    if (ws.classList.contains(side + "-collapsed")) return;    // 折叠时不拖
    e.preventDefault();
    document.body.classList.add("resizing");
    const rect = ws.getBoundingClientRect();
    const move = (ev) => {
      let w = side === "left" ? ev.clientX - rect.left - 18 : rect.right - ev.clientX - 18;
      w = Math.max(MIN_W, Math.min(MAX_W, w));
      ws.style.setProperty(side === "left" ? "--left-w" : "--right-w", w + "px");
      localStorage.setItem(side === "left" ? "cp_lw" : "cp_rw", Math.round(w));
    };
    const up = () => {
      document.body.classList.remove("resizing");
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }));
}

/* ---------------- 题目自动保存 ---------------- */
/* ---------------- 题目：全文展示 / 编辑切换 ---------------- */
// 把题库/用户题面转成更易读的 markdown：小节标题加粗、样例数据代码块化、幂次转上标
function beautifyProblem(raw) {
  let t = String(raw || "");
  // 1) 【小节标题】单独成行 → 加粗小标题
  t = t.replace(/^[ \t]*【\s*(.+?)\s*】[ \t]*$/gm, "\n**$1**\n");
  // 2) 「样例输入/输出：」后紧跟的数据块 → 代码块（边界：空行 / 下个标题 / 串尾）
  t = t.replace(
    /(样例输入|样例输出|输入样例|输出样例)\s*[:：][ \t]*\n([\s\S]*?)(?=\n[ \t]*\n|\n[ \t]*【|\n[ \t]*\*\*|$)/g,
    (m, label, block) => "\n**" + label + "**\n\n```\n" + block.replace(/[ \t\r\n]+$/, "") + "\n```\n"
  );
  // 3) 幂次 10^9 / O(n^2) / x^{-3} → 上标
  t = t.replace(/\^\{?(-?\w+)\}?/g, "<sup>$1</sup>");
  return t;
}
function renderProblemDisplay(text) {
  const el = $("#problem-display");
  if (!el) return;
  const raw = text || "";
  if (window.marked && raw.trim()) {
    try { el.innerHTML = marked.parse(beautifyProblem(raw)); el.classList.add("rich"); return; }
    catch (e) {}
  }
  el.classList.remove("rich");
  el.textContent = raw;
}
function setProblemDisplayMode(on) {
  $("#problem-input").classList.toggle("hidden", on);
  $("#problem-display").classList.toggle("hidden", !on);
}
function setProblemText(text) {
  $("#problem-input").value = text || "";
  renderProblemDisplay(text);
  localStorage.setItem("cp_problem", text || "");
  setProblemDisplayMode(!!(text && text.trim()));   // 有题 → 全文展示；无题 → 编辑框
}
function editProblem() { setProblemDisplayMode(false); $("#problem-input").focus(); }

function initPersistence() {
  const inp = $("#problem-input");
  const saved = localStorage.getItem("cp_problem");
  if (saved) { inp.value = saved; renderProblemDisplay(saved); }
  setProblemDisplayMode(!!(saved && saved.trim()));
  let t;
  inp.addEventListener("input", () => {
    analysisStale = true;        // 题面改了 → 之前的分析判定作废
    currentProblemId = "";       // 手动改题 → 视为新题（待分析后入库）
    currentProblemMeta = null;   // 元信息随之失效，待分析后重建
    clearTimeout(t); t = setTimeout(() => localStorage.setItem("cp_problem", inp.value), 400);
  });
}

/* ---------------- 事件绑定 ---------------- */
function bind() {
  $("#btn-analyze").onclick = runAnalyze;
  $("#btn-run").onclick = runCode;
  $("#btn-submit").onclick = submitCode;
  $("#btn-copy").onclick = copyCode;
  $("#btn-hint").onclick = requestHint;
  $("#btn-chat").onclick = sendChat;
  $("#btn-quote").onclick = captureSelection;
  $("#quote-clear").onclick = clearQuote;
  $("#team-strip").onclick = toggleTeam;
  $$(".panel-head").forEach(h => h.onclick = () => h.closest(".panel").classList.toggle("collapsed"));
  $("#btn-ask-tutor").onclick = askTutorAbout;
  $("#btn-gen-report").onclick = genReport;
  $("#btn-dl-report").onclick = downloadReport;
  $("#btn-share-report").onclick = openShareCard;
  $("#share-close").onclick = closeShareCard;
  $("#share-copy").onclick = copyShareCard;
  $("#share-download").onclick = downloadShareCard;
  $("#share-modal").onclick = (e) => { if (e.target.id === "share-modal") closeShareCard(); };
  $("#chat-input").onkeydown = (e) => { if (e.key === "Enter") sendChat(); };
  $("#btn-review").onclick = requestReview;
  // 题库左侧抽屉
  $("#pb-toggle").onclick = togglePbPanel;
  $("#pb-close").onclick = closePbPanel;
  $("#pb-overlay").onclick = closePbPanel;
  $("#pb-paste").onclick = pasteNewProblem;
  $("#pb-search").oninput = renderProblemList;
  $$("#pb-filters .pb-chip").forEach(c => c.onclick = () => {
    if (c.dataset.ac != null) {            // 「只看未过」独立开关
      pbAcOnly = !pbAcOnly; c.classList.toggle("active", pbAcOnly);
    } else {                               // 难度单选
      pbDiffFilter = c.dataset.diff || "";
      $$("#pb-filters .pb-chip[data-diff]").forEach(x => x.classList.toggle("active", x === c));
    }
    renderProblemList();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closePbPanel(); closeDiffModal(); } });
  $$(".io-tab").forEach(t => t.onclick = () => switchIO(t.dataset.io));
  $$(".tab").forEach(t => t.onclick = () => {
    $$(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $$(".view").forEach(v => v.classList.remove("active"));
    $("#view-" + t.dataset.view).classList.add("active");
    if (t.dataset.view === "dashboard") loadDashboard();
    if (t.dataset.view === "visualizer" && window.initVisualizer) window.initVisualizer();
    if (t.dataset.view === "community" && window.loadCommunity) window.loadCommunity();
  });
  // 导师修订 diff 弹窗
  $("#diff-close").onclick = closeDiffModal;
  $("#diff-reject").onclick = closeDiffModal;
  $("#diff-apply").onclick = applyFix;
  $("#diff-modal").onclick = (e) => { if (e.target.id === "diff-modal") closeDiffModal(); };
  // 全局快捷键：Ctrl+S 提交（编辑器外也生效）
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); submitCode(); }
  });
}

/* ---------------- 认证 / 画像 ---------------- */
let currentUser = null, currentProfile = null, currentBilling = { credits: 0, is_pro: false }, authMode = "login";

async function loadMe() {
  try {
    const r = await fetch("/api/me").then(r => r.json());
    currentUser = r.user; currentProfile = r.profile; currentBilling = r.billing || currentBilling;
    window.currentUser = currentUser;   // 暴露给 community.js（let 绑定不会挂到 window 上）
    renderAuthArea(); renderAdaptiveNote();
  } catch (e) {}
}
// LLM 操作会在服务端按次扣算力点；操作后即时刷新顶栏，免得用户以为没扣还要手动刷新页面
function refreshBilling() { if (currentUser) loadMe(); }
function renderAuthArea() {
  const a = $("#auth-area");
  if (currentUser) {
    const p = currentProfile || {}, b = currentBilling || {};
    const member = b.is_pro
      ? `<span class="pro-badge" title="算力点 ${b.credits}">PRO · ${b.credits}点</span>`
      : `<span class="credits-chip">${b.credits || 0} 点</span>`;
    a.innerHTML = `<span class="user-chip">
        <span class="user-name">${esc(currentUser.username)}</span>
        <span class="tier-badge ${p.tier || "novice"}" title="${esc(p.summary || "")}">${esc(p.tier_label || "新手")}</span>
        ${member}
      </span><button class="ad-link" id="ad-btn" title="看广告免费得算力点">看广告得点</button><button class="recharge-link" id="recharge-btn">充值</button><button class="logout-btn" id="logout-btn">退出</button>`;
    $("#logout-btn").onclick = logout;
    $("#recharge-btn").onclick = () => $("#recharge-modal").classList.remove("hidden");
    $("#ad-btn").onclick = openAdModal;
  } else {
    a.innerHTML = `<button class="auth-btn ghost" data-open="login">登录</button>
                   <button class="auth-btn" data-open="register">注册</button>`;
    a.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openAuth(b.dataset.open));
  }
}
function renderAdaptiveNote() {
  const n = $("#adaptive-note");
  if (currentUser && currentProfile && !currentProfile.is_empty) {
    n.classList.remove("hidden");
    n.innerHTML = `已按你的画像 <b>${esc(currentProfile.tier_label)}档</b> 因材施教` +
      (currentProfile.weak_types && currentProfile.weak_types.length
        ? `（薄弱：${esc(currentProfile.weak_types.join("、"))}）` : "");
  } else { n.classList.add("hidden"); }
}
function openAuth(mode) {
  authMode = mode;
  $("#auth-modal").classList.remove("hidden");
  $("#auth-err").textContent = "";
  $$(".modal-tab").forEach(t => t.classList.toggle("active", t.dataset.auth === mode));
  $("#auth-submit").textContent = mode === "login" ? "登录" : "注册";
  $("#auth-username").focus();
}
function closeAuth() { $("#auth-modal").classList.add("hidden"); }
async function submitAuth() {
  const username = $("#auth-username").value.trim(), password = $("#auth-password").value;
  if (!username || !password) { $("#auth-err").textContent = "请输入用户名和密码"; return; }
  const url = authMode === "login" ? "/api/login" : "/api/register";
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }) });
    const data = await r.json();
    if (!r.ok) { $("#auth-err").textContent = data.error || "操作失败"; return; }
    closeAuth(); $("#auth-password").value = "";
    await loadMe();
    toast(authMode === "login" ? "已登录" : "注册成功，已登录");
    if ($("#view-dashboard").classList.contains("active")) loadDashboard();
  } catch (e) { $("#auth-err").textContent = "网络错误"; }
}
async function logout() {
  await fetch("/api/logout", { method: "POST" });
  await loadMe(); toast("已退出");
  if ($("#view-dashboard").classList.contains("active")) loadDashboard();
}
async function recharge(yuan) {
  try {
    const r = await fetch("/api/recharge", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yuan }),
    }).then(r => r.json());
    if (r.error) return toast(r.error);
    $("#recharge-modal").classList.add("hidden");
    await loadMe();
    toast("✨ 充值成功，当前 " + r.credits + " 算力点，Pro 已开通");
  } catch (e) { toast("充值失败"); }
}

/* ---------------- 功能解锁 / 模拟激励广告 ---------------- */
// 非 Pro 触碰高级能力时的引导：未登录先登录，已登录则弹解锁选项（看广告 / 充值）
function promptUnlock(feature) {
  if (!currentUser) {
    toast("「" + feature + "」是 Pro 能力，请先登录后看广告免费得点或充值");
    openAuth("login");
    return;
  }
  $("#unlock-feature").textContent = feature;
  $("#unlock-ad-pts").textContent = AD_REWARD_PTS;
  $("#unlock-modal").classList.remove("hidden");
}
function closeUnlock() { $("#unlock-modal").classList.add("hidden"); }

let adTimer = null;
function openAdModal() {
  if (!currentUser) { toast("请先登录再看广告领算力点"); openAuth("login"); return; }
  const claim = $("#ad-claim"), count = $("#ad-count"), close = $("#ad-close");
  $("#ad-modal").classList.remove("hidden");
  claim.disabled = true; claim.textContent = "领取奖励"; close.classList.add("hidden");
  let left = AD_SECONDS;
  count.textContent = "广告 " + left + "s";
  clearInterval(adTimer);
  adTimer = setInterval(() => {
    left--;
    if (left > 0) { count.textContent = "广告 " + left + "s"; return; }
    clearInterval(adTimer);
    count.textContent = "✓ 可领取奖励";
    claim.disabled = false; close.classList.remove("hidden");
  }, 1000);
}
function closeAdModal() { clearInterval(adTimer); $("#ad-modal").classList.add("hidden"); }
async function claimAdReward() {
  const claim = $("#ad-claim");
  claim.disabled = true; claim.textContent = "发放中…";
  try {
    const r = await fetch("/api/ad-reward", { method: "POST" });
    const data = await r.json();
    if (!r.ok) { toast(data.error || "领取失败"); closeAdModal(); return; }
    closeAdModal();
    await loadMe();
    toast("🎉 已到账 " + data.gained + " 算力点，今日还可看 " + data.remaining_today + " 次");
  } catch (e) { toast("领取失败，请重试"); claim.disabled = false; claim.textContent = "领取奖励"; }
}
function bindAuth() {
  $("#auth-close").onclick = closeAuth;
  $("#auth-submit").onclick = submitAuth;
  $$("#auth-modal .modal-tab").forEach(t => t.onclick = () => openAuth(t.dataset.auth));
  $("#auth-modal").onclick = (e) => { if (e.target.id === "auth-modal") closeAuth(); };
  $("#auth-password").onkeydown = (e) => { if (e.key === "Enter") submitAuth(); };
  // 充值
  $("#recharge-close").onclick = () => $("#recharge-modal").classList.add("hidden");
  $("#recharge-modal").onclick = (e) => { if (e.target.id === "recharge-modal") $("#recharge-modal").classList.add("hidden"); };
  $$("#recharge-pkgs .pkg").forEach(b => b.onclick = () => recharge(parseInt(b.dataset.yuan)));
  // 解锁引导 + 模拟激励广告
  $("#unlock-close").onclick = closeUnlock;
  $("#unlock-modal").onclick = (e) => { if (e.target.id === "unlock-modal") closeUnlock(); };
  $("#unlock-ad").onclick = () => { closeUnlock(); openAdModal(); };
  $("#unlock-recharge").onclick = () => { closeUnlock(); $("#recharge-modal").classList.remove("hidden"); };
  $("#ad-close").onclick = closeAdModal;
  $("#ad-claim").onclick = claimAdReward;
  // 倒计时未结束（领取键禁用）时点遮罩不关闭，避免跳过广告
  $("#ad-modal").onclick = (e) => { if (e.target.id === "ad-modal" && !$("#ad-claim").disabled) closeAdModal(); };
  $("#recharge-ad-link").onclick = () => { $("#recharge-modal").classList.add("hidden"); openAdModal(); };
  // 深度分析仅 Pro
  $("#deep-check").onchange = (e) => {
    if (e.target.checked && !currentBilling.is_pro) {
      e.target.checked = false; promptUnlock("深度分析");
    }
  };
}

/* ---------------- 启动 ---------------- */
initAgentTeam();
setTeamOpenClass(false);   // 默认收起为迷你状态条，工作时自动展开
bind();
bindAuth();
initPanels();
initPersistence();
initIoResize();
loadProblemList();
loadMe();
