// mock.js —— 前端写死数据，后续通过 api.js 替换为真实接口
export const mockData = {
  // ---------- 离线开发模式的角色元数据 ----------
  login: {
    roles: {
      ANALYST: { label: "数据分析员", scopes: ["授权数据查询"], budget: 20 },
      DATA_OWNER: { label: "园区管理员", scopes: ["本园区数据"], budget: 8 },
      AUDITOR: { label: "审计员", scopes: ["审计记录"], budget: 50 },
      ADMIN: { label: "系统管理员", scopes: ["系统管理"], budget: 4 },
    },
  },

  // ---------- 全局 ----------
  notifications: [
    { title: "重复查询风险", desc: "华东电网对相同指标重复查询次数较高", time: "10:23:11", unread: true, type: "warn" },
    { title: "预算消耗过快", desc: "新能源集团今日隐私预算消耗速度超过阈值", time: "09:47:35", unread: true, type: "danger" },
    { title: "节点S1-S2同步完成", desc: "计算节点状态与时间同步正常", time: "09:12:07", unread: true, type: "ok" },
    { title: "策略已发布", desc: "默认隐私预算 ε 调整为 1.00", time: "昨天 18:21", unread: false, type: "info" },
    { title: "备份成功", desc: "定时配置与数据备份完成", time: "昨天 03:00", unread: false, type: "info" },
  ],

  // ---------- 系统总览 ----------
  overview: {
    parties: 12,
    partiesDelta: 1,
    queries: 86,
    queriesDelta: 18,
    budget: 43.7,
    budgetDelta: "-2.8",
    alerts: 2,
    flow: [
      { title: "数据源接入", desc: "多源异构数据安全接入", icon: "data", color: "blue" },
      { title: "可信身份验证", desc: "后端会话与角色权限控制", icon: "audit", color: "purple" },
      { title: "权限与隐私预算校验", desc: "权限识别与预算充足性检查", icon: "shield", color: "green" },
      { title: "分布式差分隐私计算", desc: "多方安全协同计算", icon: "compute", color: "blue" },
      { title: "大模型解释与报告", desc: "结果释义与可视化报告", icon: "query", color: "purple" },
      { title: "区块链审计存证", desc: "全过程存证不可篡改", icon: "lock", color: "green" },
    ],
    trendLabels: ["05-12", "05-13", "05-14", "05-15", "05-16", "05-17", "05-18"],
    trendValues: [32, 45, 66, 58, 72, 78, 86],
    donut: {
      total: 126,
      data: [
        { label: "电网公司 - 发电企业", value: 42, pct: 33.33 },
        { label: "电网公司 - 售电公司", value: 28, pct: 22.22 },
        { label: "发电企业 - 设备厂商", value: 24, pct: 19.05 },
        { label: "电网公司 - 政府部门", value: 18, pct: 14.29 },
        { label: "其它组合", value: 14, pct: 11.11 },
      ],
    },
    health: [
      { name: "计算节点S1", score: "98%", meta: "CPU 32%　内存 48%", status: "正常", detail: "节点运行稳定，无异常事件。" },
      { name: "计算节点S2", score: "95%", meta: "CPU 36%　内存 52%", status: "正常", detail: "节点运行稳定，通信延迟正常。" },
      { name: "Agent服务", score: "92%", meta: "QPS 1,256　延迟 45ms", status: "正常", detail: "智能体服务响应正常。" },
      { name: "审计链", score: "99%", meta: "区块高度 12,856,231", status: "正常", detail: "区块链同步正常，上链成功率 99.82%。" },
    ],
    tasks: [
      ["TASK-20250518-00086", "华东电网-数据分析员", "负荷预测查询", "华东电网、国能发电、浙江售电", `<span class="tag ok">已完成</span>`, "2025-05-18　10:28:56"],
      ["TASK-20250518-00085", "新能源集团-算法工程师", "风电功率评估", "新能源集团、设备厂商A、气象中心", `<span class="tag run">运行中</span>`, "2025-05-18　10:21:33"],
      ["TASK-20250518-00084", "政府能源局-审计员", "碳排放核算查询", "华东电网、多家发电企业", `<span class="tag wait">排队中</span>`, "2025-05-18　10:12:07"],
      ["TASK-20250518-00083", "华南电网-数据分析员", "用电异常检测", "华南电网、南网能源、售电公司B", `<span class="tag ok">已完成</span>`, "2025-05-18　09:58:41"],
      ["TASK-20250518-00082", "设备厂商A-研发工程师", "设备健康度分析", "设备厂商A、发电企业X、运维公司", `<span class="tag ok">已完成</span>`, "2025-05-18　09:41:19"],
    ],
    risks: [
      { title: "重复查询风险", level: "中风险", levelTag: "mid", cls: "warn", time: "05-18 10:23:11", desc: "检测到主体「华东电网」对相同指标的重复查询次数较高" },
      { title: "预算消耗过快", level: "高风险", levelTag: "bad", cls: "danger", time: "05-18 09:47:35", desc: "主体「新能源集团」今日隐私预算消耗速度超过阈值" },
    ],
  },

  // ---------- 智能查询工作台 ----------
  query: {
    userQuestion: "请分析明天下午 14:00–17:00 三个园区的总负荷、可调节负荷和储能可用容量，并判断是否存在削峰潜力。",
    steps: [
      { title: "识别业务意图", desc: "识别为负荷与灵活性评估，时间粒度为小时级。" },
      { title: "匹配隐私查询模板", desc: "匹配模板：VPP_FLEXIBILITY_ANALYSIS。" },
      { title: "权限与预算校验", desc: "校验各园区A/B/C的查询权限与预算，预算 ε=0.8，可用 ε=2.7，满足要求。" },
      { title: "生成分布式计算任务", desc: "基于模板与参数，生成计算任务并下发至各数据方。" },
      { title: "汇总结果并生成解释", desc: "汇总差分隐私结果，生成图表与建议。" },
    ],
    params: {
      parties: ["园区A", "园区B", "园区C"],
      timeRange: "2025-05-19 14:00 ～ 2025-05-19 17:00",
      metrics: ["总负荷（kW）", "可调节负荷（kW）", "储能可用容量（kWh）"],
      granularity: "园区级（按园区汇总）",
      budget: "0.8（本次）",
      template: "VPP_FLEXIBILITY_ANALYSIS",
      resultGran: "小时级",
      mechanism: "拉普拉斯机制",
      timeout: "60 秒",
    },
    plan: {
      task_id: "TASK-20250519-00123",
      template: "VPP_FLEXIBILITY_ANALYSIS",
      parties: ["园区A", "园区B", "园区C"],
      metrics: ["总负荷", "可调节负荷", "储能可用容量"],
      privacy: { epsilon: 0.8, mechanism: "laplace" },
      status: "READY",
      timeout_sec: 60,
    },
    resultTable: [
      ["14:00–15:00", "12,480", "2,860", "4,250", "±8.2%"],
      ["15:00–16:00", "12,920", "2,940", "4,180", "±8.0%"],
      ["16:00–17:00", "13,210", "3,120", "4,070", "±8.1%"],
      ["合计/平均", "38,610", "8,920", "12,500", "—"],
    ],
    resultLabels: ["14:00", "15:00", "16:00", "17:00"],
    resultValues: [12480, 12920, 13210, 12480],
    explain: "在明天下午 14:00–17:00 时段内，三区总负荷呈平稳上升趋势，16:00–17:00 达到峰值。可调节负荷占总负荷比例约 22%–24%，储能可用容量整体充足，可覆盖约 97–106% 的当小时峰值负荷。",
    suggestions: [
      "优先使用储能削峰：在 16:00–17:00 时段优先释放储能，预计可削减负荷约 4.07 MWh、覆盖当小时峰值的 31% 左右。",
      "其次调用可中断负荷：当储能不足时，建议启用可中断负荷（约 3.12 MW），按毫秒分轮次下发指令，保障供电可靠性。",
      "持续优化调度策略：建议结合实时级监测结果动态调整储能 SOC 目标与可中断负荷阈值，提升削峰效果。",
    ],
    conclusion: "存在明显削峰潜力，建议优先使用储能，其次调用可中断负荷。",
  },

  // ---------- 分布式隐私计算 ----------
  compute: {
    parties: 3,
    partiesDelta: 1,
    nodes: 2,
    tasks: 6,
    tasksDelta: 2,
    latency: "58ms",
    latencyDelta: "-6ms",
    steps: [
      { name: "本地裁剪", status: "done", desc: "限制单用户贡献，裁剪负荷上限" },
      { name: "本地统计", status: "done", desc: "各数据方本地求和/计数" },
      { name: "秘密份额", status: "done", desc: "Shamir 秘密共享分片分发" },
      { name: "分布式噪声", status: "run", desc: "各方生成部分拉普拉斯噪声份额" },
      { name: "S1/S2聚合", status: "wait", desc: "非串通节点安全聚合" },
      { name: "返回结果", status: "wait", desc: "结果解密并返回 Agent" },
    ],
    providers: ["园区A", "园区B", "园区C"],
    computeNodes: [{ name: "计算节点S1", desc: "Non-colluding" }, { name: "计算节点S2", desc: "Non-colluding" }],
    timeline: [
      { name: "数据预处理", status: "已完成", desc: "数据清洗、标准化、特征提取" },
      { name: "秘密共享", status: "已完成", desc: "Shamir 秘密共享分片分发" },
      { name: "分布式噪声生成", status: "进行中", desc: "各节点生成并提交噪声份额" },
      { name: "聚合计算", status: "待开始", desc: "安全聚合与噪声叠加" },
      { name: "结果返回", status: "待开始", desc: "结果解密与返回 Agent" },
    ],
    metrics: {
      comm: "12.4 MB",
      computeTime: "2.18 s",
      rounds: 4,
      shares: 6,
    },
    resources: [
      { name: "计算节点S1", cpu: 32, mem: 48, qps: 126 },
      { name: "计算节点S2", cpu: 28, mem: 46, qps: 118 },
    ],
    budget: [
      { id: "TASK-20250518-00065", budget: "10.00", used: "2.38", pct: 23.8 },
      { id: "TASK-20250518-00066", budget: "8.00", used: "3.10", pct: 38.8 },
      { id: "TASK-20250518-00067", budget: "6.00", used: "2.20", pct: 36.7 },
      { id: "TASK-20250518-00068", budget: "12.00", used: "5.44", pct: 45.3 },
      { id: "TASK-20250518-00069", budget: "14.00", used: "6.28", pct: 44.9 },
    ],
    events: [
      { type: "ok", title: "S1–S2同步完成", desc: "计算节点S1与S2时间与状态同步完成" },
      { type: "info", title: "园区B噪声份额已提交", desc: "园区B已成功提交噪声份额，共1份" },
      { type: "ok", title: "未发现异常串通行为", desc: "当前轮次未检测到异常通信或串通行为" },
    ],
    recentTasks: [
      ["TASK-20250518-00065", "园区A、园区B、园区C", "园区用电负荷统计（按日）", "10.00", `<span class="tag run">进行中</span>`, "00:02:18"],
      ["TASK-20250518-00064", "园区A、园区B、园区C", "能耗碳排相关性分析", "8.00", `<span class="tag ok">已完成</span>`, "00:01:47"],
      ["TASK-20250518-00063", "园区A、园区B", "设备运行时长分布查询", "6.00", `<span class="tag ok">已完成</span>`, "00:01:12"],
      ["TASK-20250518-00062", "园区B、园区C", "分时电价成本估算", "12.00", `<span class="tag ok">已完成</span>`, "00:02:06"],
      ["TASK-20250518-00061", "园区A、园区C", "碳排放强度趋势分析", "14.00", `<span class="tag ok">已完成</span>`, "00:02:31"],
    ],
  },

};
