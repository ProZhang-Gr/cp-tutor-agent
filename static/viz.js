/* ====================================================================
   算法图解 — 帧式确定性播放器
   每个算法把输入「编译」成一串帧；播放器逐帧渲染 + 高亮伪代码行。
   无第三方图表依赖：数组用条形、图用 SVG、DP 用表格，三套渲染器。
==================================================================== */
(function () {
  const $v = (s) => document.querySelector(s);

  /* ---------------- 通用工具 ---------------- */
  function parseArr(s) {
    return String(s || "").split(/[\s,]+/).map(Number).filter((x) => !isNaN(x));
  }
  function buildAdj(g) {
    const adj = {};
    g.nodes.forEach((n) => (adj[n.id] = []));
    g.edges.forEach((e) => { adj[e.a].push({ v: e.b, w: e.w }); adj[e.b].push({ v: e.a, w: e.w }); });
    for (const k in adj) adj[k].sort((x, y) => x.v - y.v);
    return adj;
  }
  const lbl = (g, id) => { const n = g.nodes.find((n) => n.id === id); return n ? n.label : id; };

  /* ==================================================================
     一、数组类算法（条形渲染）
  ================================================================== */
  function bubbleFrames(a) {
    a = a.slice(); const f = []; const placed = {};
    const snap = (mark, ptr, line, note) => f.push({ arr: a.slice(), mark: { ...placed, ...mark }, ptr: { ...ptr }, line, note });
    const n = a.length;
    snap({}, {}, 0, "开始：对 " + n + " 个元素做冒泡排序");
    for (let i = 0; i < n - 1; i++) {
      for (let j = 0; j < n - 1 - i; j++) {
        snap({ [j]: "cmp", [j + 1]: "cmp" }, {}, 2, `比较 a[${j}]=${a[j]} 与 a[${j + 1}]=${a[j + 1]}`);
        if (a[j] > a[j + 1]) {
          [a[j], a[j + 1]] = [a[j + 1], a[j]];
          snap({ [j]: "swap", [j + 1]: "swap" }, {}, 3, `逆序 → 交换`);
        }
      }
      placed[n - 1 - i] = "sorted";
      snap({}, {}, 1, `第 ${i + 1} 趟结束：a[${n - 1 - i}] 沉到位`);
    }
    placed[0] = "sorted";
    snap({}, {}, 0, "排序完成 ✓");
    return f;
  }

  function quickFrames(a) {
    a = a.slice(); const f = []; const placed = {};
    const snap = (mark, ptr, line, note) => f.push({ arr: a.slice(), mark: { ...placed, ...mark }, ptr: { ...ptr }, line, note });
    function qs(lo, hi) {
      if (lo > hi) return;
      if (lo === hi) { placed[lo] = "sorted"; snap({}, {}, 1, `区间 [${lo}] 只剩一个元素，已就位`); return; }
      const pivot = a[hi];
      snap({ [hi]: "pivot" }, {}, 2, `区间 [${lo},${hi}] 选 a[${hi}]=${pivot} 作枢轴`);
      let i = lo;
      for (let j = lo; j < hi; j++) {
        snap({ [hi]: "pivot", [j]: "cmp" }, { i: i, j: j }, 5, `比较 a[${j}]=${a[j]} 与枢轴 ${pivot}`);
        if (a[j] < pivot) {
          if (i !== j) { [a[i], a[j]] = [a[j], a[i]]; snap({ [hi]: "pivot", [i]: "swap", [j]: "swap" }, { i: i, j: j }, 6, `a[${j}] < 枢轴 → 换到左区`); }
          i++;
        }
      }
      [a[i], a[hi]] = [a[hi], a[i]];
      placed[i] = "sorted";
      snap({ [i]: "sorted" }, { i: i }, 7, `枢轴归位到下标 ${i}`);
      qs(lo, i - 1); qs(i + 1, hi);
    }
    snap({}, {}, 0, "快速排序开始");
    qs(0, a.length - 1);
    for (let k = 0; k < a.length; k++) placed[k] = "sorted";
    snap({}, {}, 0, "排序完成 ✓");
    return f;
  }

  function mergeFrames(a) {
    a = a.slice(); const f = [];
    const rng = (lo, hi, extra) => { const m = { ...extra }; for (let k = lo; k < hi; k++) if (!(k in m)) m[k] = "range"; return m; };
    const snap = (mark, ptr, line, note) => f.push({ arr: a.slice(), mark: mark, ptr: { ...ptr }, line, note });
    function ms(lo, hi) {
      if (hi - lo <= 1) return;
      const mid = (lo + hi) >> 1;
      snap(rng(lo, hi, {}), { mid: mid }, 2, `分治区间 [${lo},${hi}) → mid=${mid}`);
      ms(lo, mid); ms(mid, hi);
      const tmp = []; let i = lo, j = mid;
      snap(rng(lo, hi, {}), { i: i, j: j }, 5, `归并有序子段 [${lo},${mid}) 与 [${mid},${hi})`);
      while (i < mid && j < hi) { if (a[i] <= a[j]) { tmp.push(a[i]); i++; } else { tmp.push(a[j]); j++; } }
      while (i < mid) { tmp.push(a[i]); i++; }
      while (j < hi) { tmp.push(a[j]); j++; }
      for (let k = 0; k < tmp.length; k++) { a[lo + k] = tmp[k]; snap(rng(lo, hi, { [lo + k]: "swap" }), {}, 5, `写回 a[${lo + k}]=${tmp[k]}`); }
    }
    snap({}, {}, 0, "归并排序开始");
    ms(0, a.length);
    const done = {}; for (let k = 0; k < a.length; k++) done[k] = "sorted";
    snap(done, {}, 0, "排序完成 ✓");
    return f;
  }

  function binaryFrames(input) {
    const parts = String(input).split("/");
    const a = parseArr(parts[0]).sort((x, y) => x - y);
    const target = parts.length > 1 ? Number(parts[1]) : a[a.length >> 1];
    const f = [];
    const snap = (mark, ptr, line, note) => f.push({ arr: a.slice(), mark: mark, ptr: { ...ptr }, line, note, badge: "查找 " + target });
    let lo = 0, hi = a.length - 1;
    snap({}, { lo: lo, hi: hi }, 0, `在有序数组中查找 ${target}`);
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      snap({ [mid]: "mid" }, { lo: lo, hi: hi, mid: mid }, 2, `mid=${mid}, a[mid]=${a[mid]}`);
      if (a[mid] === target) { snap({ [mid]: "sorted" }, { lo: lo, hi: hi, mid: mid }, 4, `命中！下标 ${mid}`); return f; }
      if (a[mid] < target) { lo = mid + 1; snap({ [mid]: "range" }, { lo: lo, hi: hi }, 6, `a[mid] < 目标 → 区间收到右半 lo=${lo}`); }
      else { hi = mid - 1; snap({ [mid]: "range" }, { lo: lo, hi: hi }, 8, `a[mid] > 目标 → 区间收到左半 hi=${hi}`); }
    }
    snap({}, {}, 1, `区间为空，未找到 ${target}`);
    return f;
  }

  function twoPtrFrames(input) {
    const parts = String(input).split("/");
    const a = parseArr(parts[0]).sort((x, y) => x - y);
    const target = parts.length > 1 ? Number(parts[1]) : a[0] + a[a.length - 1];
    const f = [];
    const snap = (mark, ptr, line, note) => f.push({ arr: a.slice(), mark: mark, ptr: { ...ptr }, line, note, badge: "目标和 " + target });
    let lo = 0, hi = a.length - 1;
    snap({}, { lo: lo, hi: hi }, 0, `有序数组中找两数之和 = ${target}`);
    while (lo < hi) {
      const s = a[lo] + a[hi];
      snap({ [lo]: "cmp", [hi]: "cmp" }, { lo: lo, hi: hi }, 2, `a[${lo}]+a[${hi}] = ${a[lo]}+${a[hi]} = ${s}`);
      if (s === target) { snap({ [lo]: "sorted", [hi]: "sorted" }, { lo: lo, hi: hi }, 3, `找到！(${a[lo]}, ${a[hi]})`); return f; }
      if (s < target) { lo++; snap({}, { lo: lo, hi: hi }, 4, `和偏小 → 左指针右移 lo=${lo}`); }
      else { hi--; snap({}, { lo: lo, hi: hi }, 5, `和偏大 → 右指针左移 hi=${hi}`); }
    }
    snap({}, {}, 1, "两指针相遇，无解");
    return f;
  }

  /* ==================================================================
     二、图论算法（SVG 渲染）
  ================================================================== */
  const GRAPH = {
    nodes: [
      { id: 0, x: 80, y: 70, label: "A" }, { id: 1, x: 240, y: 48, label: "B" },
      { id: 2, x: 410, y: 70, label: "C" }, { id: 3, x: 120, y: 210, label: "D" },
      { id: 4, x: 300, y: 200, label: "E" }, { id: 5, x: 470, y: 210, label: "F" },
      { id: 6, x: 580, y: 120, label: "G" },
    ],
    edges: [
      { a: 0, b: 1, w: 2 }, { a: 0, b: 3, w: 6 }, { a: 1, b: 2, w: 4 }, { a: 1, b: 4, w: 5 },
      { a: 2, b: 6, w: 3 }, { a: 3, b: 4, w: 1 }, { a: 4, b: 5, w: 2 }, { a: 5, b: 6, w: 6 }, { a: 2, b: 5, w: 8 },
    ],
  };

  function bfsFrames() {
    const g = GRAPH, adj = buildAdj(g), f = [], state = {}, start = 0;
    const q = [start]; const visited = new Set([start]); state[start] = "frontier";
    const qstr = () => "队列: [" + q.map((x) => lbl(g, x)).join(" ") + "]";
    const snap = (line, note, active) => f.push({ graph: g, state: { ...state }, active: active || null, line, note: note + " ｜ " + qstr() });
    snap(0, `起点 ${lbl(g, start)} 入队`, null);
    while (q.length) {
      const u = q.shift(); state[u] = "visiting";
      snap(3, `出队 ${lbl(g, u)}，开始访问`, null);
      for (const { v } of adj[u]) {
        snap(4, `查看邻居 ${lbl(g, v)}`, [u, v]);
        if (!visited.has(v)) { visited.add(v); q.push(v); state[v] = "frontier"; snap(7, `${lbl(g, v)} 未访问 → 入队`, [u, v]); }
        else snap(5, `${lbl(g, v)} 已访问，跳过`, [u, v]);
      }
      state[u] = "visited";
      snap(2, `${lbl(g, u)} 处理完毕`, null);
    }
    snap(2, "队列为空，BFS 结束 ✓", null);
    return f;
  }

  function dfsFrames() {
    const g = GRAPH, adj = buildAdj(g), f = [], state = {}, start = 0;
    const st = [start]; const visited = new Set(); state[start] = "frontier";
    const sstr = () => "栈: [" + st.map((x) => lbl(g, x)).join(" ") + "]";
    const snap = (line, note, active) => f.push({ graph: g, state: { ...state }, active: active || null, line, note: note + " ｜ " + sstr() });
    snap(0, `起点 ${lbl(g, start)} 压栈`, null);
    while (st.length) {
      const u = st.pop();
      if (visited.has(u)) { snap(3, `${lbl(g, u)} 已访问，弹出跳过`, null); continue; }
      visited.add(u); state[u] = "visiting";
      snap(4, `弹出并访问 ${lbl(g, u)}`, null);
      const nb = adj[u].slice().reverse();
      for (const { v } of nb) {
        snap(5, `查看邻居 ${lbl(g, v)}`, [u, v]);
        if (!visited.has(v)) { st.push(v); if (state[v] !== "visited") state[v] = "frontier"; snap(6, `${lbl(g, v)} 未访问 → 压栈`, [u, v]); }
      }
      state[u] = "visited";
    }
    snap(2, "栈为空，DFS 结束 ✓", null);
    return f;
  }

  function dijkstraFrames() {
    const g = GRAPH, adj = buildAdj(g), f = [], state = {}, start = 0;
    const dist = {}; g.nodes.forEach((n) => (dist[n.id] = Infinity)); dist[start] = 0;
    const done = new Set();
    const snap = (line, note, active) => f.push({ graph: g, state: { ...state }, dist: { ...dist }, active: active || null, line, note });
    state[start] = "frontier";
    snap(0, `dist[${lbl(g, start)}]=0，其余为 ∞`, null);
    while (done.size < g.nodes.length) {
      let u = -1, best = Infinity;
      for (const n of g.nodes) if (!done.has(n.id) && dist[n.id] < best) { best = dist[n.id]; u = n.id; }
      if (u === -1) break;
      done.add(u); state[u] = "visiting";
      snap(3, `取出当前最近的 ${lbl(g, u)}（dist=${dist[u]}）`, null);
      for (const { v, w } of adj[u]) {
        if (done.has(v)) continue;
        snap(5, `松弛边 ${lbl(g, u)}→${lbl(g, v)} (权 ${w})`, [u, v]);
        if (dist[u] + w < dist[v]) {
          dist[v] = dist[u] + w; if (state[v] !== "visited") state[v] = "frontier";
          snap(7, `更新 dist[${lbl(g, v)}] = ${dist[v]}`, [u, v]);
        }
      }
      state[u] = "visited";
    }
    snap(2, "所有节点确定，最短路求解完成 ✓", null);
    return f;
  }

  /* ==================================================================
     三、动态规划（表格渲染）—— 0/1 背包
  ================================================================== */
  function knapsackFrames() {
    const wt = [0, 2, 3, 4, 5], val = [0, 3, 4, 5, 6], n = 4, W = 8;
    const dp = []; for (let i = 0; i <= n; i++) dp.push(new Array(W + 1).fill(0));
    const f = [];
    const meta = {
      rows: ["∅"].concat([1, 2, 3, 4].map((i) => `物品${i} (重${wt[i]},值${val[i]})`)),
      cols: Array.from({ length: W + 1 }, (_, w) => w),
      cap: W,
    };
    const snap = (cur, from, line, note) => f.push({ grid: dp.map((r) => r.slice()), cur: cur, from: from || [], line, note, meta: meta });
    snap(null, [], 0, `0/1 背包：容量 ${W}，4 件物品，dp[i][w]=前 i 件、容量 w 的最大价值`);
    for (let i = 1; i <= n; i++) {
      for (let w = 0; w <= W; w++) {
        dp[i][w] = dp[i - 1][w];
        if (w >= wt[i]) {
          const take = dp[i - 1][w - wt[i]] + val[i];
          if (take > dp[i][w]) {
            dp[i][w] = take;
            snap([i, w], [[i - 1, w], [i - 1, w - wt[i]]], 5, `dp[${i}][${w}]: 装物品${i} 更优 = dp[${i - 1}][${w - wt[i]}]+${val[i]} = ${take}`);
          } else {
            snap([i, w], [[i - 1, w], [i - 1, w - wt[i]]], 4, `dp[${i}][${w}]: 不装更优，保持 ${dp[i][w]}`);
          }
        } else {
          snap([i, w], [[i - 1, w]], 2, `dp[${i}][${w}]: 容量不够装物品${i}，继承 dp[${i - 1}][${w}]=${dp[i][w]}`);
        }
      }
    }
    snap([n, W], [], 0, `答案 dp[${n}][${W}] = ${dp[n][W]}`);
    return f;
  }

  /* ==================================================================
     算法登记表
  ================================================================== */
  const ALGOS = [
    { id: "bubble", name: "冒泡排序", cat: "排序", kind: "array", cx: "时间 O(n²) · 空间 O(1) · 稳定",
      desc: "相邻两两比较，把大的元素一趟趟「冒」到末尾。",
      input: "5 2 8 3 9 1 6 4", build: (s) => bubbleFrames(parseArr(s)),
      code: ["for i in range(n - 1):", "  # 这一趟结束，最大元素归位", "  if a[j] > a[j+1]:", "    a[j], a[j+1] = a[j+1], a[j]"] },
    { id: "quick", name: "快速排序", cat: "排序", kind: "array", cx: "时间 平均 O(n log n) · 空间 O(log n)",
      desc: "选枢轴 partition，小的甩到左、大的甩到右，再递归两侧。",
      input: "5 2 8 3 9 1 6 4", build: (s) => quickFrames(parseArr(s)),
      code: ["def quicksort(a, lo, hi):", "  if lo >= hi: return", "  pivot = a[hi]", "  i = lo", "  for j in range(lo, hi):", "    if a[j] < pivot:", "      swap(a[i], a[j]); i += 1", "  swap(a[i], a[hi])  # 枢轴归位"] },
    { id: "merge", name: "归并排序", cat: "排序", kind: "array", cx: "时间 O(n log n) · 空间 O(n) · 稳定",
      desc: "分治：拆到单元素，再两两归并成有序段。",
      input: "5 2 8 3 9 1 6 4", build: (s) => mergeFrames(parseArr(s)),
      code: ["def mergesort(a, lo, hi):", "  if hi - lo <= 1: return", "  mid = (lo + hi) // 2", "  mergesort(a, lo, mid)", "  mergesort(a, mid, hi)", "  merge(a, lo, mid, hi)  # 写回"] },
    { id: "binary", name: "二分查找", cat: "查找 / 双指针", kind: "array", cx: "时间 O(log n) · 空间 O(1)",
      desc: "在有序数组里每次砍掉一半搜索区间。输入格式：数组 / 目标值。",
      input: "1 3 5 7 9 11 13 15 / 11", build: (s) => binaryFrames(s),
      code: ["lo, hi = 0, n - 1", "while lo <= hi:", "  mid = (lo + hi) // 2", "  if a[mid] == target:", "    return mid", "  elif a[mid] < target:", "    lo = mid + 1", "  else:", "    hi = mid - 1"] },
    { id: "twoptr", name: "双指针 · 两数之和", cat: "查找 / 双指针", kind: "array", cx: "时间 O(n) · 空间 O(1)",
      desc: "有序数组首尾夹逼，按和的大小移动指针。输入格式：数组 / 目标和。",
      input: "1 3 4 6 8 10 13 / 14", build: (s) => twoPtrFrames(s),
      code: ["lo, hi = 0, n - 1", "while lo < hi:", "  s = a[lo] + a[hi]", "  if s == target: return (lo, hi)", "  elif s < target: lo += 1", "  else: hi -= 1"] },
    { id: "bfs", name: "广度优先 BFS", cat: "图论", kind: "graph", cx: "时间 O(V + E) · 队列",
      desc: "用队列一层层向外扩展，天然求无权图最短跳数。", input: "", build: () => bfsFrames(),
      code: ["queue = deque([start])", "visited = {start}", "while queue:", "  u = queue.popleft()", "  for v in adj[u]:", "    if v in visited: continue", "    visited.add(v)", "    queue.append(v)"] },
    { id: "dfs", name: "深度优先 DFS", cat: "图论", kind: "graph", cx: "时间 O(V + E) · 栈",
      desc: "用栈一条道走到底，再回溯换路。", input: "", build: () => dfsFrames(),
      code: ["stack = [start]", "visited = set()", "while stack:", "  u = stack.pop()", "  if u in visited: continue", "  visited.add(u)", "  for v in adj[u]:", "    if v not in visited: stack.append(v)"] },
    { id: "dijkstra", name: "Dijkstra 最短路", cat: "图论", kind: "graph", cx: "时间 O(E log V) · 优先队列",
      desc: "每次确定当前最近的点，再用它松弛邻居。节点上的数字是 dist。", input: "", build: () => dijkstraFrames(),
      code: ["dist = {start: 0, ...: inf}", "pq = [(0, start)]", "while pq:", "  d, u = heappop(pq)", "  for v, w in adj[u]:", "    if dist[u] + w < dist[v]:", "      dist[v] = dist[u] + w", "      heappush(pq, (dist[v], v))"] },
    { id: "knapsack", name: "0/1 背包 DP", cat: "动态规划", kind: "table", cx: "时间 O(nW) · 空间 O(nW)",
      desc: "经典二维 DP：每件物品「装 / 不装」二选一，填表求最大价值。", input: "", build: () => knapsackFrames(),
      code: ["for i in range(1, n + 1):", "  for w in range(0, W + 1):", "    dp[i][w] = dp[i-1][w]        # 不装", "    if w >= wt[i]:", "      # 不装 vs 装，取较大者", "      dp[i][w] = max(dp[i][w], dp[i-1][w-wt[i]] + val[i])"] },
  ];

  /* ==================================================================
     渲染器
  ================================================================== */
  function renderArray(stage, fr) {
    const arr = fr.arr, max = Math.max(...arr, 1), showVal = arr.length <= 24;
    let html = '<div class="vz-bars">';
    arr.forEach((v, i) => {
      const m = fr.mark && fr.mark[i] ? " " + fr.mark[i] : "";
      const ps = [];
      if (fr.ptr) for (const name in fr.ptr) if (fr.ptr[name] === i) ps.push(name);
      const h = Math.round(14 + 84 * (v / max));
      html += `<div class="vz-col">
        <div class="vz-bar${m}" style="height:${h}%">${showVal ? `<span class="vz-bv">${v}</span>` : ""}</div>
        <div class="vz-pt">${ps.map((p) => `<span class="vz-ptr ${p}">${p}</span>`).join("")}</div>
      </div>`;
    });
    html += "</div>";
    stage.innerHTML = html;
  }

  function renderGraph(stage, fr) {
    const g = fr.graph, st = fr.state || {}, act = fr.active, dist = fr.dist;
    let svg = '<svg class="vz-svg" viewBox="0 0 660 270" preserveAspectRatio="xMidYMid meet">';
    g.edges.forEach((e) => {
      const A = g.nodes.find((n) => n.id === e.a), B = g.nodes.find((n) => n.id === e.b);
      const on = act && ((act[0] === e.a && act[1] === e.b) || (act[0] === e.b && act[1] === e.a));
      svg += `<line class="vz-edge${on ? " on" : ""}" x1="${A.x}" y1="${A.y}" x2="${B.x}" y2="${B.y}"/>`;
      const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
      svg += `<text class="vz-ew" x="${mx}" y="${my - 4}">${e.w}</text>`;
    });
    g.nodes.forEach((n) => {
      const cls = st[n.id] ? " " + st[n.id] : "";
      svg += `<g class="vz-node${cls}"><circle cx="${n.x}" cy="${n.y}" r="20"/>`;
      svg += `<text class="vz-nl" x="${n.x}" y="${n.y + 5}">${n.label}</text>`;
      if (dist) { const d = dist[n.id]; svg += `<text class="vz-nd" x="${n.x}" y="${n.y - 27}">${d === Infinity ? "∞" : d}</text>`; }
      svg += "</g>";
    });
    svg += "</svg>";
    stage.innerHTML = svg;
  }

  function renderTable(stage, fr) {
    const grid = fr.grid, meta = fr.meta, cur = fr.cur, from = fr.from || [];
    const isCur = (r, c) => cur && cur[0] === r && cur[1] === c;
    const isFrom = (r, c) => from.some((p) => p[0] === r && p[1] === c);
    let html = '<div class="vz-tablewrap"><table class="vz-table"><thead><tr><th></th>';
    meta.cols.forEach((c) => (html += `<th>${c}</th>`));
    html += "</tr></thead><tbody>";
    grid.forEach((row, r) => {
      html += `<tr><th class="vz-rh">${meta.rows[r]}</th>`;
      row.forEach((val, c) => {
        const cls = isCur(r, c) ? " cur" : (isFrom(r, c) ? " from" : "");
        html += `<td class="vz-cell${cls}">${val}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    stage.innerHTML = html;
  }

  /* ==================================================================
     播放器
  ================================================================== */
  const VZ = { algo: null, frames: [], idx: 0, timer: null, speed: 850 };

  function renderList() {
    const cats = {};
    ALGOS.forEach((a) => (cats[a.cat] = cats[a.cat] || []).push(a));
    let html = "";
    Object.keys(cats).forEach((c) => {
      html += `<div class="vz-cat">${c}</div>`;
      html += cats[c].map((a) => `<button type="button" class="vz-item" data-id="${a.id}">${a.name}</button>`).join("");
    });
    $v("#vz-list").innerHTML = html;
    document.querySelectorAll("#vz-list .vz-item").forEach((b) => (b.onclick = () => select(b.dataset.id)));
  }

  function select(id) {
    const algo = ALGOS.find((a) => a.id === id);
    if (!algo) return;
    VZ.algo = algo;
    pause();
    document.querySelectorAll("#vz-list .vz-item").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
    $v("#vz-title").textContent = algo.name;
    $v("#vz-desc").textContent = algo.desc;
    $v("#vz-cx").textContent = algo.cx;
    $v("#vz-code").innerHTML = algo.code.map((l, i) => `<div class="vz-cline" data-i="${i}">${escc(l)}</div>`).join("");
    const inputRow = $v("#vz-input-row");
    if (algo.kind === "array") { inputRow.classList.remove("hidden"); $v("#vz-input").value = algo.input; }
    else inputRow.classList.add("hidden");
    rebuild();
  }

  function rebuild() {
    if (!VZ.algo) return;
    try { VZ.frames = VZ.algo.build(VZ.algo.kind === "array" ? $v("#vz-input").value : ""); }
    catch (e) { VZ.frames = []; }
    VZ.idx = 0;
    $v("#vz-progress").max = Math.max(0, VZ.frames.length - 1);
    render();
  }

  function render() {
    const fr = VZ.frames[VZ.idx];
    if (!fr) return;
    const stage = $v("#vz-stage");
    if (VZ.algo.kind === "array") renderArray(stage, fr);
    else if (VZ.algo.kind === "graph") renderGraph(stage, fr);
    else renderTable(stage, fr);
    const badge = fr.badge ? `<span class="vz-badge">${escc(fr.badge)}</span>` : "";
    $v("#vz-narr").innerHTML = badge + `<span class="vz-narr-step">第 ${VZ.idx + 1}/${VZ.frames.length} 帧</span>` + escc(fr.note || "");
    document.querySelectorAll("#vz-code .vz-cline").forEach((el) => el.classList.toggle("cur", Number(el.dataset.i) === fr.line));
    $v("#vz-progress").value = VZ.idx;
  }

  function step(d) { pause(); VZ.idx = Math.max(0, Math.min(VZ.frames.length - 1, VZ.idx + d)); render(); }
  function restart() { pause(); VZ.idx = 0; render(); }
  function seek(i) { pause(); VZ.idx = Math.max(0, Math.min(VZ.frames.length - 1, i)); render(); }

  function play() {
    if (!VZ.frames.length) return;
    if (VZ.idx >= VZ.frames.length - 1) VZ.idx = 0;
    setPlayBtn(true);
    VZ.timer = setInterval(() => {
      if (VZ.idx >= VZ.frames.length - 1) { pause(); return; }
      VZ.idx++; render();
    }, VZ.speed);
  }
  function pause() { if (VZ.timer) { clearInterval(VZ.timer); VZ.timer = null; } setPlayBtn(false); }
  function setPlayBtn(on) { const b = $v("#vz-play"); if (b) b.innerHTML = on ? "❚❚ 暂停" : "▶ 播放"; }

  function escc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  let inited = false;
  window.initVisualizer = function () {
    if (inited) return;
    inited = true;
    renderList();
    $v("#vz-play").onclick = () => (VZ.timer ? pause() : play());
    $v("#vz-next").onclick = () => step(1);
    $v("#vz-prev").onclick = () => step(-1);
    $v("#vz-restart").onclick = restart;
    $v("#vz-progress").oninput = (e) => seek(Number(e.target.value));
    $v("#vz-speed").onchange = (e) => { VZ.speed = Number(e.target.value); if (VZ.timer) { pause(); play(); } };
    $v("#vz-apply").onclick = rebuild;
    $v("#vz-random").onclick = () => {
      const n = 8 + Math.floor(Math.random() * 4);
      const a = Array.from({ length: n }, () => 1 + Math.floor(Math.random() * 99));
      const algo = VZ.algo;
      if (algo && (algo.id === "binary" || algo.id === "twoptr")) {
        a.sort((x, y) => x - y);
        const t = algo.id === "binary" ? a[Math.floor(Math.random() * a.length)] : a[0] + a[a.length - 1];
        $v("#vz-input").value = a.join(" ") + " / " + t;
      } else $v("#vz-input").value = a.join(" ");
      rebuild();
    };
    $v("#vz-input").onkeydown = (e) => { if (e.key === "Enter") rebuild(); };
    select("bubble");
  };
})();
