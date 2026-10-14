const ALL_ROLES = ["ANALYST", "DATA_OWNER", "AUDITOR", "ADMIN"];

export const PAGE_REGISTRY = [
  { id: "overview", title: "系统总览", icon: "home", roles: ALL_ROLES, description: "平台运行与业务概览", keywords: ["首页", "概览", "dashboard"] },
  { id: "catalog", title: "数据目录", icon: "data", roles: ["ANALYST"], common: true, description: "可申请的数据资产", keywords: ["数据资产", "数据集", "dataset"] },
  { id: "my-requests", title: "我的申请", icon: "audit", roles: ["ANALYST"], description: "数据使用申请记录", keywords: ["申请记录", "申请进度"] },
  { id: "new-request", title: "新建申请", icon: "report", roles: ["ANALYST"], common: true, description: "创建数据使用申请", keywords: ["申请授权", "创建申请"] },
  { id: "my-grants", title: "我的授权", icon: "shield", roles: ["ANALYST"], description: "已获得的数据授权", keywords: ["grant", "授权范围", "授权额度"] },
  { id: "query", title: "授权查询", icon: "query", roles: ["ANALYST"], description: "自然语言与授权约束查询", keywords: ["智能查询", "查询工作台", "自然语言查询"] },
  { id: "compute", title: "任务与计算", icon: "compute", roles: ["ANALYST"], common: true, description: "多方安全协同计算任务", keywords: ["计算任务", "任务状态", "秘密共享", "安全聚合"] },
  { id: "report", title: "报表中心", icon: "report", roles: ["ANALYST"], description: "查询与预算统计报告", keywords: ["报表", "报告", "统计"] },
  { id: "performance", title: "性能测试", icon: "performance", roles: ["ANALYST"], common: true, description: "隐私计算 · 通信开销与时延", keywords: ["性能", "benchmark", "通信开销", "通信量", "时延", "plain", "secret_share", "distributed_dp", "分布式隐私计算", "分布式差分隐私", "差分隐私"] },
  { id: "pending-approvals", title: "待我审批", icon: "audit", roles: ["DATA_OWNER"], common: true, description: "本园区待处理申请", keywords: ["待审批", "审批申请"] },
  { id: "approval-history", title: "审批历史", icon: "report", roles: ["DATA_OWNER"], description: "本园区审批记录", keywords: ["历史审批", "审批记录"] },
  { id: "owner-grants", title: "本园区授权", icon: "shield", roles: ["DATA_OWNER"], common: true, description: "本园区生效授权", keywords: ["grant", "园区授权", "有效授权"] },
  { id: "data", title: "数据接入", icon: "data", roles: ["DATA_OWNER"], common: true, description: "园区数据导入与版本", keywords: ["csv", "数据导入", "数据版本"] },
  { id: "policy", title: "安全策略中心", icon: "shield", roles: ["DATA_OWNER"], common: true, description: "园区安全策略与约束", keywords: ["安全策略", "隐私策略", "策略"] },
  { id: "request-audit", title: "申请审计", icon: "audit", roles: ["AUDITOR"], common: true, description: "数据使用申请审计", keywords: ["申请追溯", "申请记录"] },
  { id: "approval-audit", title: "审批审计", icon: "report", roles: ["AUDITOR"], common: true, description: "多方审批过程审计", keywords: ["审批追溯", "审批记录"] },
  { id: "grant-audit", title: "授权审计", icon: "shield", roles: ["AUDITOR"], common: true, description: "授权范围与状态审计", keywords: ["grant", "授权追溯"] },
  { id: "audit", title: "查询和预算审计", icon: "audit", roles: ["AUDITOR"], common: true, description: "任务、查询与隐私预算追溯", keywords: ["审计追溯", "任务审计", "预算审计", "查询审计"] },
  { id: "admin-requests", title: "全部申请", icon: "audit", roles: ["ADMIN"], common: true, description: "全局数据使用申请", keywords: ["申请管理", "所有申请"] },
  { id: "admin-grants", title: "全部授权", icon: "shield", roles: ["ADMIN"], common: true, description: "全局授权状态", keywords: ["grant", "授权管理", "所有授权"] },
  { id: "admin-users", title: "账号与权限", icon: "user", roles: ["ADMIN"], description: "平台账号、角色与访问权限管理", keywords: ["账号", "用户", "角色", "权限", "停用", "密码", "管理员"] },
  { id: "security-audit", title: "安全审计", icon: "report", roles: ["ADMIN"], common: true, description: "登录与安全事件审计", keywords: ["安全事件", "登录审计", "操作日志"] },
  { id: "settings", title: "系统设置", icon: "settings", roles: ["ADMIN"], common: true, description: "运行依赖与安全基线", keywords: ["系统信息", "运行状态", "安全基线"] },
];

export const ROLE_NAV_ITEMS = Object.fromEntries(ALL_ROLES.map((role) => [
  role,
  PAGE_REGISTRY.filter((feature) => feature.roles.includes(role))
    .map((feature) => [feature.id, feature.title, feature.icon]),
]));

export function navItemsForRole(role, fallback = []) {
  return ROLE_NAV_ITEMS[role] || fallback;
}

export function searchableFeaturesForRole(role) {
  return PAGE_REGISTRY.filter((feature) => feature.roles.includes(role));
}

export function featureForRoleById(role, id) {
  return searchableFeaturesForRole(role).find((feature) => feature.id === id) || null;
}

export function isRegisteredPageForRole(role, pageId) {
  return Boolean(featureForRoleById(role, pageId));
}

export function grantConflicts(form, grants) {
  const grant = grants.find((item) => item.grant_id === form.grant_id);
  if (!grant) return ["请选择当前用户的有效授权"];
  const conflicts = [];
  const grantParties = Array.isArray(grant.parties) ? grant.parties : [];
  const allowedQueryTypes = Array.isArray(grant.allowed_query_types) ? grant.allowed_query_types : [];
  const allowedGroupBy = Array.isArray(grant.allowed_group_by) ? grant.allowed_group_by : [];
  const groupByLabels = { "30m": "30 分钟", "1h": "1 小时", "1d": "1 天" };
  const disallowedParties = (Array.isArray(form.parties) ? form.parties : [])
    .filter((party) => !grantParties.includes(party));
  if (disallowedParties.length) {
    conflicts.push(`当前授权不包含园区 ${disallowedParties.join("、")}；可选园区：${grantParties.join("、") || "无"}`);
  }
  if (!allowedQueryTypes.includes(form.query_type)) {
    conflicts.push(`当前授权不支持查询类型 ${form.query_type || "未选择"}；可选类型：${allowedQueryTypes.join("、") || "无"}`);
  }
  if (new Date(form.start_time) < new Date(grant.allowed_start_time) || new Date(form.end_time) > new Date(grant.allowed_end_time)) conflicts.push("查询时间超出授权范围");
  if (form.query_type === "TIME_SERIES" && form.group_by && !allowedGroupBy.includes(form.group_by)) {
    const requested = groupByLabels[form.group_by] || form.group_by;
    const allowed = allowedGroupBy.map((value) => groupByLabels[value] || value);
    conflicts.push(`当前授权不支持 ${requested}时间粒度；可选时间粒度：${allowed.join("、") || "无"}`);
  }
  if (Number(form.epsilon) > Number(grant.max_epsilon_per_query) || Number(form.epsilon) > Number(grant.epsilon_remaining)) conflicts.push("epsilon 超出授权可用额度");
  return conflicts;
}

export function validateAccessRequest(payload) {
  if (payload.purpose.trim().length < 5 || !payload.requested_parties.length || !payload.requested_query_types.length) {
    return "请完整填写用途，并至少选择一个园区和一种查询类型";
  }
  if (!payload.requested_start_time || !payload.requested_end_time || new Date(payload.requested_start_time) >= new Date(payload.requested_end_time)) {
    return "申请开始时间必须早于结束时间";
  }
  if (!(payload.requested_max_epsilon_per_query > 0) || payload.requested_max_epsilon_per_query > 5) {
    return "单次 epsilon 必须大于 0 且不超过 5";
  }
  if (payload.requested_total_epsilon < payload.requested_max_epsilon_per_query) {
    return "累计 epsilon 不能小于单次 epsilon 上限";
  }
  if (payload.requested_query_types.includes("TIME_SERIES") && !payload.requested_group_by.length) {
    return "申请 TIME_SERIES 时必须选择时序粒度";
  }
  if (!payload.requested_expires_at || new Date(payload.requested_expires_at) <= new Date()) {
    return "授权到期时间必须晚于当前时间";
  }
  return null;
}
