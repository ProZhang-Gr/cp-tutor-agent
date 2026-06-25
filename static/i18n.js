/* ====================================================================
   轻量国际化（中 / EN）—— 纯前端，无依赖
   机制：静态 UI 用 data-i18n / data-i18n-ph / data-i18n-title 标记，
   运行时按 key 查字典替换；动态生成的界面文案在各 JS 里调用 window.t(key)。
   只翻译「界面框架」文案；题面、题解、LLM 输出等内容数据保持原文。
==================================================================== */
(function () {
  const DICT = {
    zh: {
      "brand.sub": "算法竞赛辅导智能体",
      "tab.workspace": "[ 辅导工作台 ]",
      "tab.visualizer": "[ 算法图解 ]",
      "tab.community": "[ 社群 ]",
      "tab.dashboard": "[ 学习仪表盘 ]",
      "status.online": "MODEL ONLINE",
      "lang.toggle": "EN",
      "lang.toggle.title": "Switch to English",

      // 工作台 · 左
      "ws.problem": "题目",
      "ws.bank": "题库",
      "ws.bank.title": "打开题库",
      "ws.problem.ph": "粘贴题目描述（含输入/输出格式与样例），或点右上角「题库」选择。",
      "ws.analyze": "▶ 启动智能体分析",
      "ws.deep": "🧠 深度分析",
      "ws.dissect": "题目剖析",
      "ws.askTutor": "💬 让导师解答",
      "ws.complexity": "目标复杂度",
      "ws.insight": "核心突破口",
      "ws.deepdive": "🧠 解题推演 · PRO",
      "ws.pitfalls": "易错点",
      "ws.knowledge": "知识点",
      "ws.similar": "相似题 · 举一反三",
      "ws.strategies": "策略谱系",

      // 工作台 · 中
      "ed.title": "⌗ 代码工作区",
      "ed.copy": "⎘ 复制",
      "ed.copy.title": "复制代码",
      "ed.run": "▷ 运行",
      "ed.run.title": "运行（Ctrl+Enter）",
      "ed.submit": "⏍ 提交评测",
      "ed.submit.title": "提交评测（Ctrl+S）",
      "io.custom": "自定义输入",
      "io.result": "判题结果",
      "io.history": "提交记录",
      "io.custom.ph": "测试数据 → 点「运行」查看输出",

      // 工作台 · 右
      "team.title": "智能体团队",
      "team.strip.title": "点击展开/收起智能体职责",
      "tutor.title": "苏格拉底导师",
      "tutor.hint": "💡 请求下一层提示",
      "review.title": "导师审阅",
      "review.btn": "🔎 请导师审阅并给修改建议",
      "review.btn.title": "导师通读你的代码，在出问题的行打批注，并可给出修订版",
      "chat.title": "导师对话",
      "chat.ph": "向导师提问，他能看到你的代码…",
      "chat.quote.title": "引用编辑器中选中的代码",

      // 仪表盘
      "dash.title": "学习数据 · LEARNING TELEMETRY",
      "dash.report": "🧾 AI 学习日报",
      "dash.genReport": "生成今日报告",
      "dash.shareImg": "📤 生成分享图",
      "dash.dlPdf": "⬇ 下载 PDF",
      "dash.report.empty": "点「生成今日报告」，AI 全方位分析你今天的学习并可导出 PDF（Pro）",
      "dash.st.total": "总提交",
      "dash.st.solved": "已攻克",
      "dash.st.rate": "通过率",
      "dash.st.avg": "平均分",
      "dash.cal": "刷题日历",
      "dash.cal.sub": "近一年提交活跃度",
      "dash.cal.less": "少",
      "dash.cal.more": "多",
      "dash.errDist": "判题结果分布",
      "dash.weak": "薄弱题型",
      "dash.growth": "学习成长曲线",
      "dash.growth.sub": "累计攻克题数与每日通过率的成长轨迹",
      "dash.recent": "近期提交",
      // 个性化训练计划（新增）
      "plan.title": "🎯 个性化训练计划",
      "plan.refresh": "↻ 换一批",
      "plan.loading": "正在据你的画像挑题…",
      "dash.col.problem": "题目",
      "dash.col.type": "题型",
      "dash.col.result": "结果",
      "dash.col.score": "得分",
      "dash.col.time": "时间",
      // 用户画像 / 学习投入 / 成就（新增）
      "profile.title": "用户画像 · 因材施教",
      "profile.tier": "当前档位",
      "profile.solveRate": "通过率",
      "profile.strong": "擅长题型",
      "profile.weak": "薄弱题型",
      "profile.errors": "高频失误",
      "profile.mastery": "题型掌握度",
      "profile.empty": "多做几道题，这里会刻画你的水平档位与强弱题型，并据此调整辅导策略。",
      "engage.title": "学习投入 · 行为分析",
      "engage.sub": "只统计专注时长与操作计数，不记录任何按键内容或鼠标轨迹",
      "engage.todayMin": "今日专注(分)",
      "engage.totalMin": "累计专注(分)",
      "engage.keys": "累计击键",
      "engage.perSubmit": "每次提交均用时(分)",
      "ach.title": "成就 · 证书",
      "ach.sub": "刷题里程碑会点亮徽章，达成后可生成结业证书",
      "ach.cert": "🎓 生成结业证书",
      "ach.cert.locked": "再攻克几题即可解锁证书",
      "checkin.btn": "📅 每日签到",
      "checkin.done": "✓ 今日已签到",

      // 算法图解
      "vz.title": "算法图解",
      "vz.sub": "逐帧看清每一步在做什么",
      "vz.pickTitle": "选择一个算法",
      "vz.pickDesc": "从左侧挑一个算法，看它一步步执行。",
      "vz.restart": "回到开头",
      "vz.prev": "上一步",
      "vz.play": "▶ 播放",
      "vz.next": "下一步",
      "vz.input": "输入数据",
      "vz.apply": "应用",
      "vz.random": "🎲 随机",
      "vz.code": "伪代码 · 高亮为当前执行行",

      // 社群
      "cm.title": "社群讨论区",
      "cm.sub": "难题一起啃 · 思路互相点 · 发帖前会经 AI 审核护栏",
      "cm.all": "全部",
      "cm.ask": "求助",
      "cm.solu": "题解",
      "cm.disc": "讨论",
      "cm.fb": "反馈",
      "cm.hot": "🔥 最热",
      "cm.new": "🕒 最新",
      "cm.search.ph": "🔍 搜索标题 / 内容 / 作者",
      "cm.newPost": "✎ 发帖",

      // 登录 / 注册
      "auth.login": "登录",
      "auth.register": "注册",
      "auth.username.ph": "用户名",
      "auth.password.ph": "密码（至少 8 位）",
      "auth.hint": "游客可免费使用判题、智能体分析、导师审阅与算法图解。登录后记录学习历史、按画像因材施教，并可看广告或充值解锁苏格拉底导师 / 导师对话 / 深度分析。",
      "auth.forgot": "忘记密码？向管理员申请重置",
      // 找回密码
      "reset.title": "找回密码",
      "reset.intro": "密码以不可逆方式加密存储，系统无法找回原密码。提交申请后，管理员核实身份会为你重置一个新密码，并通过你留的联系方式告知你。",
      "reset.username.ph": "你的用户名",
      "reset.contact.ph": "联系方式（QQ / 手机后四位，便于核实身份）",
      "reset.note.ph": "补充说明（可选）",
      "reset.submit": "提交申请",
      // 充值
      "rc.title": "充值算力点",
      "rc.hint": "演示用模拟充值，不接真实支付。Pro 不受每日额度限制，每次调用消耗 1 点。",
      "rc.adLink": "或 · 看广告免费得算力点",
      // 解锁
      "unlock.need": "需要算力点",
      "unlock.sub": "导师审阅、普通智能体分析对所有人免费；苏格拉底导师、导师对话、深度分析是 Pro 能力，每次消耗 1 算力点。",
      "unlock.ad": "看广告免费得",
      "unlock.adUnit": "点",
      "unlock.recharge": "直接充值开通 Pro",
      // 广告
      "ad.tag": "赞助内容 · 模拟激励",
      "ad.copy": "让每一次刷题，<br>都有人陪你复盘",
      "ad.sub": "ARENA · 算法竞赛辅导智能体",
      "ad.claim": "领取奖励",
      // 题库抽屉
      "pb.title": "题库",
      "pb.search.ph": "🔍 搜索题名 / 知识点…",
      "pb.all": "全部",
      "pb.intro": "入门",
      "pb.easy": "简单",
      "pb.mid": "中等",
      "pb.hard": "困难",
      "pb.todo": "只看未过",
      "pb.paste": "✎ 粘贴自己的题目",
      // diff
      "diff.reject": "✗ 不采用",
      "diff.apply": "✓ 应用到编辑器（可 Ctrl+Z 撤销）",
      // 分享
      "share.title": "📤 分享学习卡片",
      "share.copy": "⎘ 复制图片",
      "share.download": "⬇ 保存图片",
      "share.hint": "保存后可直接发到微信 / QQ / 朋友圈 — 平台无关，无需任何授权",

      // 顶栏 auth 区（app.js 动态渲染）
      "top.adLink": "看广告得点",
      "top.adLink.title": "看广告免费得算力点",
      "top.recharge": "充值",
      "top.logout": "退出",
    },
    en: {
      "brand.sub": "Competitive Programming Tutor Agent",
      "tab.workspace": "[ Workbench ]",
      "tab.visualizer": "[ Visualizer ]",
      "tab.community": "[ Community ]",
      "tab.dashboard": "[ Dashboard ]",
      "status.online": "MODEL ONLINE",
      "lang.toggle": "中",
      "lang.toggle.title": "切换到中文",

      "ws.problem": "Problem",
      "ws.bank": "Problems",
      "ws.bank.title": "Open problem set",
      "ws.problem.ph": "Paste the problem (with I/O format and samples), or pick one from “Problems” at the top-right.",
      "ws.analyze": "▶ Run agent analysis",
      "ws.deep": "🧠 Deep analysis",
      "ws.dissect": "Problem Breakdown",
      "ws.askTutor": "💬 Ask the tutor",
      "ws.complexity": "Target complexity",
      "ws.insight": "Key insight",
      "ws.deepdive": "🧠 Solution walkthrough · PRO",
      "ws.pitfalls": "Pitfalls",
      "ws.knowledge": "Concepts",
      "ws.similar": "Similar problems",
      "ws.strategies": "Strategy spectrum",

      "ed.title": "⌗ Code workspace",
      "ed.copy": "⎘ Copy",
      "ed.copy.title": "Copy code",
      "ed.run": "▷ Run",
      "ed.run.title": "Run (Ctrl+Enter)",
      "ed.submit": "⏍ Submit",
      "ed.submit.title": "Submit for judging (Ctrl+S)",
      "io.custom": "Custom input",
      "io.result": "Judge result",
      "io.history": "Submissions",
      "io.custom.ph": "Test data → click “Run” to see output",

      "team.title": "Agent team",
      "team.strip.title": "Click to expand/collapse agent roles",
      "tutor.title": "Socratic tutor",
      "tutor.hint": "💡 Request next hint level",
      "review.title": "Tutor review",
      "review.btn": "🔎 Ask the tutor to review & suggest fixes",
      "review.btn.title": "The tutor reads your code, annotates problem lines, and may offer a revision",
      "chat.title": "Tutor chat",
      "chat.ph": "Ask the tutor — they can see your code…",
      "chat.quote.title": "Quote the selected code in the editor",

      "dash.title": "Learning Data · TELEMETRY",
      "dash.report": "🧾 AI daily report",
      "dash.genReport": "Generate today's report",
      "dash.shareImg": "📤 Share image",
      "dash.dlPdf": "⬇ Download PDF",
      "dash.report.empty": "Click “Generate today's report” — AI reviews your day and can export a PDF (Pro).",
      "dash.st.total": "Submissions",
      "dash.st.solved": "Solved",
      "dash.st.rate": "Pass rate",
      "dash.st.avg": "Avg score",
      "dash.cal": "Practice calendar",
      "dash.cal.sub": "Submission activity over the past year",
      "dash.cal.less": "Less",
      "dash.cal.more": "More",
      "dash.errDist": "Verdict distribution",
      "dash.weak": "Weak types",
      "dash.growth": "Learning growth curve",
      "dash.growth.sub": "Cumulative solved and daily pass-rate over time",
      "dash.recent": "Recent submissions",
      "plan.title": "🎯 Personalized Training Plan",
      "plan.refresh": "↻ Reshuffle",
      "plan.loading": "Picking problems from your profile…",
      "dash.col.problem": "Problem",
      "dash.col.type": "Type",
      "dash.col.result": "Result",
      "dash.col.score": "Score",
      "dash.col.time": "Time",
      "profile.title": "Learner Profile · Adaptive Tutoring",
      "profile.tier": "Current tier",
      "profile.solveRate": "Pass rate",
      "profile.strong": "Strong types",
      "profile.weak": "Weak types",
      "profile.errors": "Frequent mistakes",
      "profile.mastery": "Type mastery",
      "profile.empty": "Solve a few more problems and we'll profile your tier and strengths, then adapt the tutoring.",
      "engage.title": "Engagement · Behavior Analytics",
      "engage.sub": "Counts focus time and action counts only — no keystroke content or mouse tracking is stored",
      "engage.todayMin": "Focus today (min)",
      "engage.totalMin": "Focus total (min)",
      "engage.keys": "Total keystrokes",
      "engage.perSubmit": "Avg min per submit",
      "ach.title": "Achievements · Certificate",
      "ach.sub": "Milestones light up badges; once earned you can generate a certificate",
      "ach.cert": "🎓 Generate certificate",
      "ach.cert.locked": "Solve a few more to unlock the certificate",
      "checkin.btn": "📅 Daily check-in",
      "checkin.done": "✓ Checked in today",

      "vz.title": "Algorithm Visualizer",
      "vz.sub": "See exactly what each step does, frame by frame",
      "vz.pickTitle": "Pick an algorithm",
      "vz.pickDesc": "Choose an algorithm on the left and watch it run step by step.",
      "vz.restart": "Back to start",
      "vz.prev": "Previous step",
      "vz.play": "▶ Play",
      "vz.next": "Next step",
      "vz.input": "Input data",
      "vz.apply": "Apply",
      "vz.random": "🎲 Random",
      "vz.code": "Pseudocode · current line highlighted",

      "cm.title": "Community",
      "cm.sub": "Crack hard problems together · trade ideas · posts pass an AI moderation guard",
      "cm.all": "All",
      "cm.ask": "Help",
      "cm.solu": "Solution",
      "cm.disc": "Discuss",
      "cm.fb": "Feedback",
      "cm.hot": "🔥 Hot",
      "cm.new": "🕒 New",
      "cm.search.ph": "🔍 Search title / content / author",
      "cm.newPost": "✎ New post",

      "auth.login": "Sign in",
      "auth.register": "Sign up",
      "auth.username.ph": "Username",
      "auth.password.ph": "Password (min 8 chars)",
      "auth.hint": "Guests can freely use judging, agent analysis, tutor review and the visualizer. Sign in to keep history, get adaptive tutoring by profile, and unlock the Socratic tutor / tutor chat / deep analysis via ads or top-up.",
      "auth.forgot": "Forgot password? Request an admin reset",
      "reset.title": "Recover password",
      "reset.intro": "Passwords are stored one-way encrypted, so the original cannot be recovered. After you submit, an admin verifies your identity, resets your password, and notifies you via the contact you provide.",
      "reset.username.ph": "Your username",
      "reset.contact.ph": "Contact (QQ / last 4 digits of phone, to verify identity)",
      "reset.note.ph": "Note (optional)",
      "reset.submit": "Submit request",
      "rc.title": "Top up credits",
      "rc.hint": "Simulated top-up for demo, no real payment. Pro has no daily quota; each call costs 1 credit.",
      "rc.adLink": "Or · watch an ad for free credits",
      "unlock.need": "needs credits",
      "unlock.sub": "Tutor review and basic agent analysis are free for everyone; the Socratic tutor, tutor chat and deep analysis are Pro features, costing 1 credit each.",
      "unlock.ad": "Watch an ad for",
      "unlock.adUnit": "credits",
      "unlock.recharge": "Top up to go Pro",
      "ad.tag": "Sponsored · simulated reward",
      "ad.copy": "Every practice session,<br>someone reviews it with you",
      "ad.sub": "ARENA · CP Tutor Agent",
      "ad.claim": "Claim reward",
      "pb.title": "Problems",
      "pb.search.ph": "🔍 Search name / concept…",
      "pb.all": "All",
      "pb.intro": "Intro",
      "pb.easy": "Easy",
      "pb.mid": "Medium",
      "pb.hard": "Hard",
      "pb.todo": "Unsolved only",
      "pb.paste": "✎ Paste your own problem",
      "diff.reject": "✗ Discard",
      "diff.apply": "✓ Apply to editor (Ctrl+Z to undo)",
      "share.title": "📤 Share learning card",
      "share.copy": "⎘ Copy image",
      "share.download": "⬇ Save image",
      "share.hint": "Save it and send to WeChat / QQ / Moments — platform-agnostic, no authorization needed",

      "top.adLink": "Watch ad",
      "top.adLink.title": "Watch an ad for free credits",
      "top.recharge": "Top up",
      "top.logout": "Sign out",
    },
  };

  let LANG = localStorage.getItem("cp_lang") || "zh";

  function t(key) {
    const d = DICT[LANG] || DICT.zh;
    return (key in d) ? d[key] : (DICT.zh[key] != null ? DICT.zh[key] : key);
  }

  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const v = t(el.getAttribute("data-i18n"));
      if (el.hasAttribute("data-i18n-html")) el.innerHTML = v; else el.textContent = v;
    });
    scope.querySelectorAll("[data-i18n-ph]").forEach((el) => {
      el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
    });
    scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
    });
    document.documentElement.lang = LANG === "en" ? "en" : "zh-CN";
  }

  function setLang(lang) {
    LANG = lang === "en" ? "en" : "zh";
    localStorage.setItem("cp_lang", LANG);
    apply();
    // 通知动态渲染的模块（app.js / community.js）重绘各自界面文案
    window.dispatchEvent(new CustomEvent("langchange", { detail: { lang: LANG } }));
  }

  function toggle() { setLang(LANG === "en" ? "zh" : "en"); }
  function get() { return LANG; }

  window.I18N = { t, apply, setLang, toggle, get, DICT };
  window.t = t;   // 便捷别名，供各 JS 直接调用

  // DOM 就绪即应用一次（脚本在 <body> 末尾加载，DOM 多已可用）
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", () => apply());
  else apply();
})();
