import { mockData } from "./mock.js";
import { installLocalization, languageControl, translate } from "./i18n/index.js";
import { USE_MOCK } from "./config.js";
import {
  QueryController,
  PARTY_IDS,
  QUERY_TYPES,
  resolveGroupBy,
  validateQueryForm,
} from "./query/query-controller.js";
import { listParties } from "./api/parties.js";
import { getTask, getTaskMonitor, getTaskResult, listTasks } from "./api/tasks.js";
import { getBudget } from "./api/privacy.js";
import { listAuditEvents } from "./api/audit.js";
import {
  auditRecordSearchText,
  normalizeAuditRecord,
  normalizeTaskAudit,
  safeAuditValue,
} from "./audit/audit-adapter.js";
import { getSystemHealth, getSystemPolicySummary } from "./api/system.js";
import {
  createAgentConversation,
  explainResult,
  getAgentConversation,
  linkAgentConversationTask,
  listAgentConversations,
  parseNaturalLanguageQuery,
} from "./api/agent.js";
import { getCurrentUser, login, logout } from "./api/auth.js";
import { listCatalogAssets, listOwnerCatalogAssets } from "./api/catalog.js";
import {
  activateDataImport,
  getActiveDataVersion,
  getDataImportConfig,
  listMyDataImports,
  rollbackDataImport,
  uploadDataImport,
} from "./api/data-imports.js";
import {
  createAccessRequest,
  getAccessRequest,
  listMyAccessRequests,
  submitAccessRequest,
  withdrawAccessRequest,
} from "./api/access-requests.js";
import {
  decideApproval,
  getApproval,
  listApprovalHistory,
  listPendingApprovals,
} from "./api/approvals.js";
import { getGrant, listMyGrants, listOwnerGrants } from "./api/grants.js";
import { getMyAnalystReport } from "./api/reports.js";
import {
  getAdminSystemOverview,
  listAllAccessRequests,
  listAllGrants,
  listAdminUsers,
  createAdminUser,
  updateAdminUser,
  resetAdminUserPassword,
  revokeAdminUserSessions,
  listSecurityAudit,
  setAdminUserStatus,
} from "./api/admin.js";
import { applyDraft, draftSummary } from "./agent/agent-controller.js";
import { createSpeechRecognitionController } from "./agent/speech-recognition.js";
import {
  PAGE_REGISTRY,
  featureForRoleById,
  grantConflicts,
  isRegisteredPageForRole,
  navItemsForRole,
  searchableFeaturesForRole,
  validateAccessRequest,
} from "./access/access-control-ui.js";
import { normalizeApprovalRequest } from "./access/approval-adapter.js";
import {
  buildSeriesChartData,
  chineseLabel,
  fmtDate,
  fmtDateTime,
  fmtDuration,
  fmtEpsilon,
  fmtNumber,
  kvRowsHtml,
  privacyRows,
  queryTypeLabel,
  statusLabel,
  timeSeriesMetrics,
} from "./utils/format.js";
import { formatApiError } from "./utils/errors.js";
import { performanceApi } from "./api/performance.js";
import { grantBudgetSnapshot } from "./query/grant-budget.js";

function currentNavItems() {
  return navItemsForRole(state.user?.role);
}

function searchFeatureById(id) {
  return featureForRoleById(state.user?.role, id);
}

function currentSearchFeatures() {
  return searchableFeaturesForRole(state.user?.role);
}

function searchFeatureForQuery(query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return null;
  return currentSearchFeatures().find((feature) =>
    translate(feature.title).toLowerCase().includes(normalized)
    || translate(feature.description).toLowerCase().includes(normalized)
    || feature.title.toLowerCase().includes(normalized)
    || normalized.includes(feature.title.toLowerCase())
    || feature.description.toLowerCase().includes(normalized)
    || feature.keywords.some((keyword) => normalized.includes(keyword) || keyword.includes(normalized))
  ) || null;
}

const RECENT_SEARCH_LIMIT = 5;

function recentSearchStorageKey() {
  return `privgrid.recent-searches.${state.user?.user_id || "anonymous"}`;
}

function loadRecentSearches() {
  try {
    const values = JSON.parse(localStorage.getItem(recentSearchStorageKey()) || "[]");
    return Array.isArray(values)
      ? values.filter((value) => typeof value === "string" && value.trim()).slice(0, RECENT_SEARCH_LIMIT)
      : [];
  } catch {
    return [];
  }
}

function rememberRecentSearch(query) {
  const value = String(query || "").trim();
  if (!value) return;
  const values = [value, ...loadRecentSearches().filter((item) => item !== value)]
    .slice(0, RECENT_SEARCH_LIMIT);
  try {
    localStorage.setItem(recentSearchStorageKey(), JSON.stringify(values));
  } catch {
    // Search history is optional when browser storage is unavailable.
  }
}

const icons = {
  home: '<path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z"/>',
  query: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  compute: '<circle cx="6" cy="18" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M7 16 11 8m2 0 4 8M8 18h8"/>',
  data: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v14c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
  shield: '<path d="M12 3 5 6v6c0 4.5 2.9 7.8 7 9 4.1-1.2 7-4.5 7-9V6z"/><path d="m9 12 2 2 4-5"/>',
  audit: '<path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  report: '<path d="M4 20h16M7 17V9m5 8V5m5 12v-6"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21h-4v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1L7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V3h4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
  performance: '<path d="M13 2 5 14h6l-1 8 8-12h-6z"/><path d="M4 20h4M16 20h4"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  send: '<path d="m22 2-7 20-4-9-9-4 20-7z"/><path d="M22 2 11 13"/>',
  microphone: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  cloud: '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
  db: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v14c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/>',
  wifi: '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="12" x2="12.01" y2="12"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  mail: '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
  msg: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
  eyeOff: '<path d="m3 3 18 18"/><path d="M10.6 6.2A9.8 9.8 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-2.2 3"/><path d="M6.6 6.6C3.6 8.5 2 12 2 12s3.5 6 10 6c1.7 0 3.1-.4 4.4-1"/>',
};

const icon = (name) => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icons[name] || icons.home}</svg>`;

let state = {
  page: "overview",
  loggedIn: false,
  collapsed: false,
  user: null,
  searchOpen: false,
  searchSelection: -1,
  notifyOpen: false,
  userOpen: false,
  modal: null,
  loginBusy: false,
  loginError: null,
  loginUsername: "",
  passwordVisible: false,
  activePage: null,
  query: {
    controller: null,
    budgetLoaded: false,
    phase: "idle",
    task: null,
    result: null,
    budget: null,
    error: null,
    lastPayload: null,
    chartZoom: 1,
  },
  agent: {
    busy: false,
    abort: null,
    typingTimer: null,
    typingMessageId: null,
    phase: "idle",
    last: null,
    error: null,
    changed: [],
    lastUserText: "",
    messages: [],
    hasCurrentTask: false,
    conversationId: null,
    conversations: [],
    conversationsInitialized: false,
    historyOpen: false,
    historySearch: "",
    historyLoading: false,
    detailLoading: false,
    lastLinkedTaskId: null,
  },
  overview: { loading: false, loaded: false, data: null, ownerSummary: null, error: null },
  compute: { loading: false, loaded: false, data: null, error: null, selectedTaskId: null },
  performance: {
    loading: false,
    loaded: false,
    status: "idle",
    testId: null,
    error: null,
    config: {
      benchmarkId: "ENERGY_BENCHMARK_V1",
      queryType: "SUM",
      interval: "30m",
      parties: [...PARTY_IDS],
      mode: "DISTRIBUTED_DP",
      epsilon: 1,
    },
    summary: { totalDurationMs: null, communicationBytes: null, nodeCount: null, averageLatencyMs: null },
    phases: [
      ["authentication", "身份认证"],
      ["parameter_validation", "参数与模式校验"],
      ["secret_sharing", "秘密共享传输"],
      ["secure_aggregation", "安全聚合计算"],
      ["result_return", "结果返回"],
    ].map(([key, label]) => ({ key, label, durationMs: null })),
    links: [],
    nodes: ["control", "party-a", "party-b", "party-c", "compute-s1", "compute-s2"].map((id) => ({
      id, status: null, cpuPercent: null, memoryPercent: null, latencyMs: null, txBytesPerSecond: null, rxBytesPerSecond: null,
    })),
    history: [],
    historyState: "empty",
  },
  audit: {
    loading: false,
    loaded: false,
    records: null,
    taskAudits: null,
    filtered: null,
    error: null,
    selectedAuditId: null,
  },
  access: {
    loading: false,
    loaded: {},
    error: null,
    assets: [],
    requests: [],
    approvals: [],
    approvalHistory: [],
    selectedApproval: null,
    grants: [],
    ownerGrants: [],
    ownerAssets: [],
    policySummary: null,
    allRequests: [],
    allGrants: [],
    users: [],
    userFilters: { query: "", role: "", status: "" },
    securityAudit: [],
    loadErrors: {},
    loadingKeys: {},
    adminOverview: null,
    analystReport: null,
    ownerData: { assets: [], imports: [], active: null, config: null },
    importPhase: "idle",
    selectedDataImport: null,
  },
};

const speechInput = createSpeechRecognitionController({
  environment: globalThis.window,
  readInput: () => document.querySelector("#query-input")?.value || "",
  writeInput: (value) => {
    const input = document.querySelector("#query-input");
    if (input) input.value = value;
  },
  onStateChange: () => updateSpeechInputUi(),
  onError: (message) => toast(message, "warn"),
});

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function toast(msg, type = "ok") {
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `${icon(type === "ok" ? "check" : type === "error" ? "alert" : "alert")}<span>${escapeHtml(formatApiError(msg))}</span>`;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

function closeOverlays() {
  state.searchOpen = false;
  state.searchSelection = -1;
  state.notifyOpen = false;
  state.userOpen = false;
  state.modal = null;
}

function initialPageForRole(role) {
  return ({ AUDITOR: "audit", ADMIN: "settings" })[role] || "overview";
}

function topbar() {
  const userName = state.user?.username || state.user?.name?.split(" - ")[0] || "当前用户";
  return `<header class="topbar">
    <div class="brand">
      <div class="logo"><span></span><span></span><span></span><span></span></div>
      <h1>面向能源可信数据空间的多方安全协同与隐私保护平台</h1>
    </div>
    <div class="top-actions">
      ${languageControl()}
      <div class="search" data-action="open-search">${icon("search")}<span>搜索功能...</span><kbd>/</kbd></div>
      <div class="bell-wrap">
        <div class="bell" data-action="toggle-notify">${icon("bell")}<b>3</b></div>
        ${state.notifyOpen ? notificationDrawer() : ""}
      </div>
      <div class="user-wrap">
        <div class="user" data-action="toggle-user">
          <div class="avatar"></div>
          <strong>${escapeHtml(userName)}</strong>
          <span class="chev">⌄</span>
        </div>
        ${state.userOpen ? userMenu() : ""}
      </div>
    </div>
  </header>`;
}

function sidebar() {
  return `<aside class="sidebar ${state.collapsed ? "collapsed" : ""}">
    <nav>${currentNavItems().map(([id, text, ic]) =>
      `<button data-page="${id}" class="${state.page === id ? "active" : ""}">${icon(ic)}<span>${text}</span></button>`
    ).join("")}</nav>
    <button class="collapse" data-action="toggle-collapse">${icon("report")}<span>${state.collapsed ? "展开导航" : "收起导航"}</span></button>
  </aside>`;
}

function notificationDrawer() {
  const items = mockData.notifications;
  return `<div class="overlay drawer-open" data-action="close-overlay">
    <div class="drawer" data-stop>
      <div class="drawer-head"><h3>通知中心</h3><button class="close" data-action="close-overlay">✕</button></div>
      <div class="drawer-body">
        ${items.map(n => `
          <div class="risk ${n.type === "danger" ? "danger" : n.type === "warn" ? "warn" : ""}" style="margin-bottom:10px">
            <div class="risk-header"><b>${icon("alert")}${escapeHtml(n.title)}</b><span>${n.time}</span></div>
            <p>${escapeHtml(n.desc)}</p>
          </div>
        `).join("")}
        <button class="primary wide" data-action="mark-read">全部标记为已读</button>
      </div>
    </div>
  </div>`;
}

function userMenu() {
  const role = ({ ANALYST: "数据分析员", DATA_OWNER: "园区管理员", AUDITOR: "审计员", ADMIN: "系统管理员" })[state.user?.role]
    || mockData.login.roles[state.user?.role]?.label
    || "当前用户";
  return `<div class="popover" style="top:50px;min-width:180px">
    <div class="popover-title">${escapeHtml(role)}${state.user?.party_id ? ` · ${escapeHtml(state.user.party_id)}` : ""}</div>
    <div class="popover-item" data-action="go-settings">${icon("settings")}个人设置</div>
    <div class="popover-item" data-action="go-audit">${icon("audit")}我的审计</div>
    <div class="popover-divider"></div>
    <div class="popover-item" data-action="logout">${icon("logout")}退出登录</div>
  </div>`;
}

function searchOverlay() {
  const features = currentSearchFeatures();
  const commonFeatures = features.filter((feature) => feature.common);
  const recentSearches = loadRecentSearches();
  return `<div class="overlay" data-action="close-overlay">
    <div class="modal search-modal" data-stop role="dialog" aria-modal="true" aria-labelledby="global-search-title">
      <div class="modal-head"><h3 id="global-search-title">全局搜索</h3><button class="close" type="button" data-action="close-overlay" aria-label="关闭全局搜索">✕</button></div>
      <div class="modal-body">
        <div class="query-input" style="margin-bottom:16px">
          <input id="global-search-input" placeholder="搜索功能..." autocomplete="off" autofocus>
          <button type="button" data-action="do-search" aria-label="搜索">${icon("search")}</button>
        </div>
        <div id="global-search-results" class="search-results" hidden>
          <h4>搜索结果 <span id="global-search-count">0 项</span></h4>
          <div class="search-result-list">
            ${features.map((feature) => `<button type="button" class="search-result" data-action="go-function" data-source="result" data-feature="${feature.id}" data-search-text="${escapeHtml([feature.title, feature.description, ...feature.keywords].join(" ").toLowerCase())}" aria-selected="false">${icon(feature.icon)}<span><b>${feature.title}</b><small>${feature.description}</small></span><i class="search-result-arrow" aria-hidden="true">›</i></button>`).join("")}
          </div>
          <div class="search-empty" hidden>未找到相关功能<span>尝试使用其他关键词</span></div>
        </div>
        <div class="search-idle-content">
          <h4>最近搜索</h4>
          <div class="chips search-recent-list">
            ${recentSearches.length
              ? recentSearches.map((value) => `<button type="button" class="chip search-chip" data-action="search-chip" data-q="${escapeHtml(value)}">${escapeHtml(value)}</button>`).join("")
              : `<span class="search-empty recent-search-empty">暂无最近搜索</span>`}
          </div>
          <h4>常用功能</h4>
          <div class="method-grid search-common-grid" style="grid-template-columns:repeat(2,1fr)">
            ${commonFeatures.map(feature => `
              <button type="button" class="method search-function" data-action="go-function" data-source="common" data-feature="${feature.id}">
                <span class="round blue">${icon(feature.icon)}</span>
                <span><b>${feature.title}</b><small>${feature.description}</small></span>
                <i class="search-result-arrow" aria-hidden="true">›</i>
              </button>
            `).join("")}
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

function modalHtml(title, body) {
  return `<div class="overlay" data-action="close-overlay">
    <div class="modal" data-stop>
      <div class="modal-head"><h3>${escapeHtml(title)}</h3><button class="close" data-action="close-overlay">✕</button></div>
      <div class="modal-body">${body}</div>
    </div>
  </div>`;
}

function statCard({ label, value, sub, type = "blue", ic = "home", up }) {
  const arrow = up === "up" ? "↑" : up === "down" ? "↓" : "－";
  const cls = up === "up" ? "up" : up === "down" ? "down" : "flat";
  return `<div class="card stat">
    <div class="round ${type}">${icon(ic)}</div>
    <div>
      <p>${label}</p>
      <h2>${value}</h2>
      <small>${sub} <span class="${cls}">${arrow}</span></small>
    </div>
  </div>`;
}

function panel(title, body, extra = "", className = "") {
  return `<section class="card panel${className ? ` ${className}` : ""}">
    ${title ? `<div class="panel-head"><h3>${title}</h3>${extra ? `<div class="extra">${extra}</div>` : ""}</div>` : ""}
    <div class="panel-body">${body}</div>
  </section>`;
}

function table(headers, rows, cls = "") {
  return `<table class="${cls}"><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
  <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function tag(t, cls = "ok") { return `<span class="tag ${cls}">${t}</span>`; }

function spark(c = "blue") {
  const stroke = c === "green" ? "#10b981" : c === "red" ? "#ff4d5e" : "#1677ff";
  return `<svg class="spark" viewBox="0 0 100 28"><polyline points="0,18 10,12 20,15 30,8 40,17 50,10 60,13 70,6 80,14 90,9 100,12" fill="none" stroke="${stroke}" stroke-width="2"/></svg>`;
}

function lineChart(labels, values, opts = {}) {
  if (!Array.isArray(values) || values.length === 0) {
    return `<div class="chart"><div class="api-state">暂无图表数据</div></div>`;
  }
  const width = opts.width || 560;
  const height = opts.height || 180;
  const padL = 36, padR = 20, padT = 25, padB = 28;
  if (values.length === 1) {
    values = [values[0], values[0]];
    labels = [labels[0] || "", labels[0] ? `${labels[0]} ` : ""];
  }
  const max = Math.max(...values) * 1.15;
  const x = i => padL + i * ((width - padL - padR) / (values.length - 1));
  const y = v => padT + (height - padT - padB) * (1 - v / max);
  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `${pts} ${x(values.length - 1)},${height - padB} ${x(0)},${height - padB}`;
  const gridLines = [0, 0.33, 0.66, 1].map(p => `<line class="grid" x1="${padL}" x2="${width - padR}" y1="${padT + p * (height - padT - padB)}" y2="${padT + p * (height - padT - padB)}"/>`).join("");
  return `<div class="chart"><svg viewBox="0 0 ${width} ${height}">${gridLines}<polygon points="${area}" fill="rgba(22,119,255,.08)"/><polyline points="${pts}" fill="none" stroke="#1677ff" stroke-width="2.8"/>${values.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}"/><text x="${x(i) - 6}" y="${y(v) - 10}">${v}</text>`).join("")}${labels.map((l, i) => `<text class="axis" x="${x(i) - 16}" y="${height - 8}">${l}</text>`).join("")}</svg></div>`;
}

const TIME_SERIES_ZOOM_LEVELS = [0.75, 1, 1.25, 1.5, 2];

function normalizedTimeSeriesZoom(value) {
  const requested = Number(value);
  if (!Number.isFinite(requested)) return 1;
  return TIME_SERIES_ZOOM_LEVELS.reduce((closest, level) => (
    Math.abs(level - requested) < Math.abs(closest - requested) ? level : closest
  ), 1);
}

function queryTimeSeriesChart(labels, values, zoomValue = 1) {
  if (!Array.isArray(values) || values.length === 0) {
    return `<div class="api-state">暂无时间序列图表数据</div>`;
  }

  const sourceLabels = Array.isArray(labels) ? labels : [];
  const sourceValues = values.map((value) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.max(0, numeric) : 0;
  });
  const zoom = normalizedTimeSeriesZoom(zoomValue);
  const height = 340;
  const padL = 70;
  const padR = 28;
  const padT = 28;
  const padB = 52;
  // The canvas follows the real bucket count. Dense results become horizontally
  // scrollable instead of squeezing every timestamp into a fixed 640px viewBox.
  const baseWidth = Math.max(1200, padL + padR + Math.max(1, sourceValues.length - 1) * 42);
  const width = Math.round(baseWidth * zoom);
  const plotHeight = height - padT - padB;
  const scaleMax = Math.max(1, Math.max(...sourceValues) * 1.12);
  const x = (index) => sourceValues.length === 1
    ? padL + (width - padL - padR) / 2
    : padL + index * ((width - padL - padR) / (sourceValues.length - 1));
  const y = (value) => padT + plotHeight * (1 - value / scaleMax);
  const points = sourceValues.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const area = `${points} ${x(sourceValues.length - 1)},${height - padB} ${x(0)},${height - padB}`;

  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const grid = yTicks.map((ratio) => {
    const gridY = padT + ratio * plotHeight;
    const tickValue = scaleMax * (1 - ratio);
    return `<g class="grid"><line x1="${padL}" x2="${width - padR}" y1="${gridY}" y2="${gridY}"/><text class="axis time-series-y-label" x="${padL - 10}" y="${gridY + 4}" text-anchor="end">${escapeHtml(fmtNumber(tickValue, tickValue >= 100 ? 0 : 1))}</text></g>`;
  }).join("");

  const tickTarget = Math.min(18, Math.max(6, Math.floor(width / 150)));
  const tickStep = Math.max(1, Math.ceil(sourceValues.length / tickTarget));
  const tickIndexes = sourceValues
    .map((_, index) => index)
    .filter((index) => index % tickStep === 0);
  const finalIndex = sourceValues.length - 1;
  if (!tickIndexes.includes(finalIndex)) {
    const previousIndex = tickIndexes.at(-1);
    if (previousIndex !== undefined && x(finalIndex) - x(previousIndex) < 110) {
      tickIndexes[tickIndexes.length - 1] = finalIndex;
    } else {
      tickIndexes.push(finalIndex);
    }
  }
  const xTicks = tickIndexes.map((index) => {
    const label = sourceLabels[index] || `#${index + 1}`;
    return `<text class="axis time-series-x-label" x="${x(index)}" y="${height - 17}" text-anchor="middle"><title>${escapeHtml(label)}</title>${escapeHtml(label)}</text>`;
  }).join("");
  const dots = sourceValues.map((value, index) => {
    const label = sourceLabels[index] || `时间桶 ${index + 1}`;
    return `<circle cx="${x(index)}" cy="${y(value)}"><title>${escapeHtml(label)}：${escapeHtml(fmtNumber(value, 2))} kWh</title></circle>`;
  }).join("");

  const zoomIndex = TIME_SERIES_ZOOM_LEVELS.indexOf(zoom);
  return `<section class="time-series-chart" aria-label="负荷时间序列图">
    <div class="time-series-chart-toolbar">
      <span>${sourceValues.length} 个时间桶 · 横向滚动浏览，悬停数据点查看精确值</span>
      <div class="time-series-chart-actions" aria-label="图表缩放控制">
        <button type="button" data-action="chart-zoom-out" aria-label="缩小图表" ${zoomIndex === 0 ? "disabled" : ""}>−</button>
        <output class="time-series-chart-zoom" aria-label="当前缩放比例">${Math.round(zoom * 100)}%</output>
        <button type="button" data-action="chart-zoom-in" aria-label="放大图表" ${zoomIndex === TIME_SERIES_ZOOM_LEVELS.length - 1 ? "disabled" : ""}>＋</button>
        <button type="button" data-action="chart-zoom-reset" aria-label="重置图表缩放">重置</button>
      </div>
    </div>
    <div class="time-series-chart-scroll" data-zoom="${zoom}" role="region" tabindex="0" aria-label="可横向滚动的时间序列图">
      <div class="chart time-series-chart-canvas" style="--time-series-chart-width:${width}px;width:${width}px">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${sourceValues.length} 个后端带噪时间桶的负荷折线图">
          ${grid}
          <polygon points="${area}" fill="rgba(22,119,255,.08)"/>
          <polyline points="${points}" fill="none" stroke="#1677ff" stroke-width="2.8"/>
          ${dots}
          ${xTicks}
        </svg>
      </div>
    </div>
  </section>`;
}

function donutChart({ total, data }) {
  const colors = ["#1677ff", "#10b981", "#ffbd4a", "#9b73ff", "#c7d2e5"];
  let acc = 0;
  const segs = data.map(d => { const s = acc; acc += d.pct; return { ...d, start: s, end: acc }; });
  const conic = segs.map((s, i) => `${colors[i]} ${s.start}% ${s.end}%`).join(",");
  return `<div class="donut-wrap">
    <div class="donut" style="background:conic-gradient(${conic})">
      <div class="inner"><b>总任务数</b><strong>${total}</strong></div>
    </div>
    <ul class="legend">${data.map((d, i) => `<li><i style="background:${colors[i]}"></i>${d.label} <b>${d.value}（${d.pct.toFixed(2)}%）</b></li>`).join("")}</ul>
  </div>`;
}

function flowSteps(items) {
  return `<div class="flow">${items.map((it, i) =>
    `<div class="flow-step">
      <div class="round ${it.color}">${icon(it.icon)}</div>
      <h4>${it.title}</h4>
      <p>${it.desc}</p>
      <span class="num">0${i + 1}</span>
    </div>${i < items.length - 1 ? `<div class="flow-arr">→</div>` : ""}`
  ).join("")}</div>`;
}

function pagination(page = 1, total = 13) {
  return `<div class="pagination">共 ${total} 条　10条/页　<button>‹</button><button class="active">1</button><button>2</button><button>3</button><button>4</button><button>5</button><span>...</span><button>${total}</button><button>›</button>　前往 <input style="width:40px" value="1"></div>`;
}

function computeProgress(steps) {
  let html = '<div class="compute-progress">';
  steps.forEach((st, i) => {
    html += `<div class="step ${st.status}"><div class="dot">${st.status === "done" ? "✓" : st.status === "run" ? "●" : i + 1}</div><b>${st.name}</b><small>${st.desc}</small></div>`;
    if (i < steps.length - 1) {
      const lineCls = st.status === "done" ? "done" : st.status === "run" ? "run" : "";
      html += `<div class="line ${lineCls}"></div>`;
    }
  });
  html += "</div>";
  return html;
}

function statusTag(taskStatus) {
  if (taskStatus === "COMPLETED") return tag("已完成", "ok");
  if (taskStatus === "FAILED") return tag("失败", "bad");
  return tag(statusLabel(taskStatus), taskStatus ? "run" : "wait");
}

function errorBox(error, fallback) {
  return `<div class="api-state error">${escapeHtml(formatApiError(error, fallback))}</div>`;
}

function queryStagesHtml(phase, task) {
  const stages = [
    ["权限与预算校验", "核验 Grant 与预算"],
    ["园区本地统计", "本地裁剪与聚合"],
    ["秘密份额生成", "生成并传输份额"],
    ["安全聚合", "非串通节点聚合"],
    ["结果重构", "总控重构与定点解码"],
    ["完成", "返回带噪统计结果"],
  ];
  const status = task?.status;
  const failed = ["validation_error", "error", "budget_insufficient", "failed"].includes(phase)
    || status === "FAILED";
  if (failed && !task?.task_id) {
    return `<div class="query-progress-step failed"><div class="query-progress-marker">!</div><b>创建失败</b><small>权限与预算校验未通过，未启动后续计算</small></div>`;
  }
  const current = phase === "submitting" ? 0
    : ["CREATED", "DISPATCHING"].includes(status) ? 0
    : status === "LOCAL_COMPUTING" ? 1
    : status === "SHARING" ? 2
    : status === "AGGREGATING" ? 3
    : status === "RECONSTRUCTING" ? 4
    : status === "COMPLETED" ? 5
    : -1;
  return stages.map(([title, desc], i) => {
    const cls = failed && i === 0 ? "failed" : current === i ? "current" : current > i ? "done" : "wait";
    const marker = cls === "done" ? "✓" : cls === "failed" ? "!" : i + 1;
    return `<div class="query-progress-step ${cls}"><div class="query-progress-marker">${marker}</div><b>${title}</b><small>${desc}</small></div>`;
  }).join("");
}

function queryResultBodyHtml(task, result) {
  const queryType = task?.query_type || result?.query_type;
  const resultData = result?.result || {};
  if (queryType === "SUM") {
    return `<div class="big-result">${fmtNumber(resultData.value, 2)} <small>kWh（带噪总用电量）</small></div>`;
  }
  if (queryType === "COUNT") {
    const raw = fmtNumber(resultData.value, 2);
    const approx = fmtNumber(resultData.value, 0);
    return `<div class="big-result">${raw} <small>约 ${approx} 户</small></div>`;
  }
  if (queryType === "AVERAGE") {
    return `<div class="big-result">${fmtNumber(resultData.value, 2)} <small>kWh（带噪平均用电量）</small></div>`;
  }
  if (queryType === "TIME_SERIES") {
    const buckets = Array.isArray(resultData.buckets) ? resultData.buckets : [];
    const chart = buildSeriesChartData(buckets);
    const metrics = timeSeriesMetrics(resultData.metrics || {});
    return `
      <div class="kv-table">
        <div class="kv-row"><div class="k">时间桶数量</div><div class="v">${resultData.bucket_count ?? buckets.length}</div></div>
        ${metrics.map((m) => `<div class="kv-row"><div class="k">${m.name}</div><div class="v">${m.value}</div></div>`).join("")}
      </div>
      ${buckets.length ? queryTimeSeriesChart(chart.labels, chart.values, state.query.chartZoom) : `<div class="api-state">后端未返回带噪时间桶数据</div>`}
      <div class="notice" style="margin-top:10px">ⓘ 图表仅使用后端返回的带噪 buckets，不请求真实未加噪结果。</div>
    `;
  }
  return `<div class="api-state">后端返回结果为空或查询类型未知</div>`;
}

function queryResultHtml(q) {
  switch (q.phase) {
    case "idle":
      return `<div class="api-state">尚未提交查询任务。请填写查询参数后点击「提交隐私查询」。</div>`;
    case "submitting":
      return `<div class="api-state">正在创建任务并校验隐私预算…</div>`;
    case "polling":
      return `<div class="api-state">任务执行中：${statusLabel(q.task?.status)}<br><small>任务ID：${escapeHtml(q.task?.task_id || "")}</small></div>`;
    case "validation_error":
    case "budget_insufficient":
    case "failed":
    case "timeout":
    case "error":
      return errorBox(q.error);
    case "completed":
      if (!q.result) return errorBox(q.error || { detail: "任务已完成，但获取结果失败" });
      return queryResultBodyHtml(q.task, q.result);
    default:
      return `<div class="api-state">未知状态</div>`;
  }
}

function queryPrivacyHtml(q) {
  if (!q.task || q.phase !== "completed") {
    return `<div class="api-state">任务执行完成后展示隐私保护说明与执行元数据。</div>`;
  }
  const rows = privacyRows(q.task, q.result);
  const queryType = q.task.query_type || q.result?.query_type;
  let conclusion = "";
  if (queryType === "TIME_SERIES" && q.result?.result?.metrics) {
    const m = q.result.result.metrics;
    conclusion = `
      <div class="advice-box"><b>结论：</b>峰值 ${fmtNumber(m.peak_value)} kWh（${fmtDateTime(m.peak_timestamp)}），
      谷值 ${fmtNumber(m.valley_value)} kWh（${fmtDateTime(m.valley_timestamp)}），
      峰谷差 ${fmtNumber(m.peak_valley_difference)} kWh，平均负荷 ${fmtNumber(m.average_load)} kWh，
      负荷率 ${m.load_factor == null ? "—" : `${fmtNumber(m.load_factor * 100, 1)}%`}。</div>`;
  } else {
    conclusion = `<div class="advice-box"><b>说明：</b>本结果已通过 ${chineseLabel(q.task.mechanism)} 发布，只返回带噪统计值，不包含任何园区局部明文或秘密份额。</div>`;
  }
  return `${kvRowsHtml(rows)}${conclusion}`;
}

function queryResultMetricsHtml(q) {
  const duration = q.task?.duration_ms ?? q.result?.duration_ms;
  const epsilon = q.task?.epsilon ?? q.lastPayload?.epsilon;
  const status = q.task?.status ? statusLabel(q.task.status) : q.phase === "idle" ? "待执行" : "处理中";
  return `<div class="query-result-metrics">
    <div><span>任务状态</span><strong>${escapeHtml(status)}</strong></div>
    <div><span>响应时间</span><strong>${duration == null ? "—" : `${fmtNumber(duration, 0)} ms`}</strong></div>
    <div><span>消耗预算</span><strong>${epsilon == null ? "—" : fmtEpsilon(epsilon)}</strong></div>
  </div>`;
}

function updateCurrentTaskSummary() {
  const root = document.querySelector("#q-current-task");
  if (!root) return;
  const form = readQueryForm();
  const selectedGrant = state.access.grants.find((grant) => grant.grant_id === form.grant_id);
  const budgetRemaining = state.query.budget?.remaining_epsilon ?? selectedGrant?.epsilon_remaining;
  const setText = (id, value) => {
    const node = document.querySelector(id);
    if (node) node.textContent = value == null || value === "" ? "—" : String(value);
  };
  setText("#q-current-grant", form.grant_id || "暂无可用授权");
  if (!state.agent.hasCurrentTask) {
    setText("#q-current-type", "待生成");
    setText("#q-current-parties", "待生成");
    setText("#q-current-range", "待生成");
    setText("#q-current-epsilon", "待生成");
    setText("#q-current-budget", budgetRemaining == null ? "加载中…" : fmtEpsilon(budgetRemaining));
    const emptyMetrics = document.querySelector("#q-result-metrics");
    if (emptyMetrics) emptyMetrics.innerHTML = queryResultMetricsHtml(state.query);
    return;
  }
  setText("#q-current-type", chineseLabel(form.query_type));
  setText("#q-current-parties", form.parties.length ? form.parties.join(" / ") : "未选择");
  setText("#q-current-range", form.start_time && form.end_time
    ? `${form.start_time.replace("T", " ")} — ${form.end_time.replace("T", " ")}`
    : "待补充");
  setText("#q-current-epsilon", form.epsilon == null ? "待补充" : fmtEpsilon(form.epsilon));
  setText("#q-current-budget", budgetRemaining == null ? "加载中…" : fmtEpsilon(budgetRemaining));
  const resultMetrics = document.querySelector("#q-result-metrics");
  if (resultMetrics) resultMetrics.innerHTML = queryResultMetricsHtml(state.query);
}

function readQueryForm() {
  const queryType = document.querySelector("#q-type")?.value || "SUM";
  const rawGroupBy = document.querySelector("#q-group")?.value || "";
  return {
    grant_id: document.querySelector("#q-grant")?.value || null,
    query_type: queryType,
    parties: Array.from(document.querySelectorAll("#q-parties input:checked")).map((cb) => cb.value),
    start_time: document.querySelector("#q-start")?.value || "",
    end_time: document.querySelector("#q-end")?.value || "",
    epsilon: document.querySelector("#q-epsilon")?.value === ""
      ? null
      : Number(document.querySelector("#q-epsilon")?.value),
    group_by: resolveGroupBy(queryType, rawGroupBy),
  };
}

function grantAllowedGroupBys(grant) {
  return Array.isArray(grant?.allowed_group_by) ? grant.allowed_group_by : [];
}

function selectedQueryGrant() {
  const grantId = document.querySelector("#q-grant")?.value || state.access.selectedGrantId;
  return state.access.grants.find((grant) => grant.grant_id === grantId) || null;
}

function preferredGroupByForGrant(grant) {
  const allowed = grantAllowedGroupBys(grant);
  return allowed.includes("1h") ? "1h" : (allowed[0] || "");
}

function persistCurrentQueryDraft() {
  if (!document.querySelector("#q-grant")) return null;
  const form = readQueryForm();
  state.query.lastPayload = { ...form };
  return form;
}

function updateGroupByAuthorizationHint(grant) {
  const hint = document.querySelector("#q-group-scope");
  if (!hint) return;
  const allowed = grantAllowedGroupBys(grant);
  hint.textContent = allowed.length
    ? `当前授权可选：${allowed.map(queryGroupLabel).join(" / ")}`
    : "当前授权未开放时间粒度";
}

// 非 TIME_SERIES：隐藏并禁用时间粒度控件、清空残留值；
// 切回 TIME_SERIES：仅从当前 Grant 的授权范围内选择默认粒度。
function syncGroupByControl({ defaultIfEmpty = true } = {}) {
  const type = document.querySelector("#q-type")?.value;
  const wrap = document.querySelector("#q-group-wrap");
  const select = document.querySelector("#q-group");
  if (!wrap || !select) return;
  const isTimeSeries = type === "TIME_SERIES";
  wrap.style.display = isTimeSeries ? "" : "none";
  select.disabled = !isTimeSeries;
  if (isTimeSeries) {
    if (!select.value && defaultIfEmpty) select.value = preferredGroupByForGrant(selectedQueryGrant());
  } else {
    select.value = "";
  }
}

function mergeGrant(grant) {
  if (!grant?.grant_id) return;
  const index = state.access.grants.findIndex((item) => item.grant_id === grant.grant_id);
  if (index < 0) state.access.grants = [...state.access.grants, grant];
  else state.access.grants[index] = grant;
}

function syncGrantSelectorRuntime() {
  const select = document.querySelector("#q-grant");
  if (!select) return;
  for (const option of Array.from(select.options)) {
    const grant = state.access.grants.find((item) => item.grant_id === option.value);
    if (!grant) continue;
    option.textContent = `${grant.grant_id} · 剩余 ε ${fmtEpsilon(grant.epsilon_remaining)}`;
    option.disabled = grant.status !== "ACTIVE" || Number(grant.epsilon_remaining) <= 0;
  }
}

async function refreshSelectedGrantBudget({ signal } = {}) {
  const grantId = state.access.selectedGrantId;
  if (!grantId) return null;
  const grant = await getGrant(grantId, { signal });
  mergeGrant(grant);
  const budget = grantBudgetSnapshot(grant);
  state.query.budget = budget;
  state.query.budgetLoaded = true;
  syncGrantSelectorRuntime();
  return budget;
}

async function selectGrantForQuery(grantId) {
  const grant = state.access.grants.find((item) => item.grant_id === grantId);
  if (!grant) return;
  state.access.selectedGrantId = grantId;
  // Apply the list snapshot immediately so scope controls never retain the
  // previous Grant while the authoritative detail request is in flight.
  applyGrantToQuery(grantId, { resetScope: true });
  persistCurrentQueryDraft();
  try {
    const freshGrant = await getGrant(grantId);
    if (state.access.selectedGrantId !== grantId) return;
    mergeGrant(freshGrant);
    // A late detail response may tighten authorization constraints, but it
    // must not reset valid edits made while the request was in flight.
    applyGrantToQuery(grantId, { resetScope: false });
    persistCurrentQueryDraft();
    state.query.budgetLoaded = true;
    updateQueryRuntime();
  } catch (error) {
    // Keep the last server snapshot visible; never decrement or synthesize a
    // browser-side balance when the refresh cannot be completed.
    toast(formatApiError(error, "授权预算刷新失败"), "error");
  }
}

function applyGrantToQuery(grantId, { resetScope = true } = {}) {
  const grant = state.access.grants.find((item) => item.grant_id === grantId);
  if (!grant) return;
  state.access.selectedGrantId = grant.grant_id;
  state.query.budget = grantBudgetSnapshot(grant);
  state.query.budgetLoaded = true;
  const typeSelect = document.querySelector("#q-type");
  if (typeSelect) {
    Array.from(typeSelect.options).forEach((option) => {
      option.disabled = !grant.allowed_query_types.includes(option.value);
    });
    if (!grant.allowed_query_types.includes(typeSelect.value)) {
      typeSelect.value = grant.allowed_query_types[0] || "";
    }
  }
  document.querySelectorAll("#q-parties input").forEach((checkbox) => {
    const allowed = grant.parties.includes(checkbox.value);
    checkbox.disabled = !allowed;
    if (resetScope) checkbox.checked = allowed;
    else if (!allowed) checkbox.checked = false;
  });
  const start = document.querySelector("#q-start");
  const end = document.querySelector("#q-end");
  const startValue = toDateTimeLocal(grant.allowed_start_time);
  const endValue = toDateTimeLocal(grant.allowed_end_time);
  if (start) {
    start.min = startValue;
    start.max = endValue;
    if (resetScope) start.value = startValue;
    else if (start.value && startValue && start.value < startValue) start.value = startValue;
    else if (start.value && endValue && start.value > endValue) start.value = endValue;
  }
  if (end) {
    end.min = startValue;
    end.max = endValue;
    if (resetScope) end.value = endValue;
    else if (end.value && startValue && end.value < startValue) end.value = startValue;
    else if (end.value && endValue && end.value > endValue) end.value = endValue;
  }
  const epsilon = document.querySelector("#q-epsilon");
  if (epsilon) {
    epsilon.max = String(grant.max_epsilon_per_query);
    if (resetScope) {
      epsilon.value = String(Math.min(1, grant.max_epsilon_per_query));
    } else if (epsilon.value !== "") {
      epsilon.value = String(Math.min(Number(epsilon.value), grant.max_epsilon_per_query));
    }
  }
  const group = document.querySelector("#q-group");
  const allowedGroupBys = grantAllowedGroupBys(grant);
  if (group) {
    Array.from(group.options).forEach((option) => {
      option.disabled = !allowedGroupBys.includes(option.value);
    });
    if (typeSelect?.value === "TIME_SERIES" && !allowedGroupBys.includes(group.value)) {
      group.value = resetScope ? preferredGroupByForGrant(grant) : "";
    }
  }
  updateGroupByAuthorizationHint(grant);
  syncGroupByControl({ defaultIfEmpty: resetScope });
  updateQueryRuntime();
}

function queryGrantConflicts(form) {
  return grantConflicts(form, state.access.grants.map((grant) => ({
    ...grant,
    allowed_group_by: grantAllowedGroupBys(grant),
  })));
}

const QUERY_GROUP_LABELS = { "30m": "30 分钟", "1h": "1 小时", "1d": "1 天" };

function queryGroupLabel(value) {
  return QUERY_GROUP_LABELS[value] || value || "未选择";
}

function querySubmissionBlockers(form, {
  isBusy = false,
  selectedGrant = null,
  hasCurrentTask = state.agent.hasCurrentTask,
} = {}) {
  if (isBusy) return ["任务正在执行，请稍候"];
  if (!selectedGrant) return ["当前没有可用授权，请先完成数据使用申请与审批"];
  if (selectedGrant.status !== "ACTIVE") return ["当前授权未生效，请选择状态为 ACTIVE 的授权"];
  if (Number(selectedGrant.epsilon_remaining) <= 0) return ["当前授权的隐私预算已耗尽，请选择其他有效授权"];
  if (!hasCurrentTask) return ["请先在左侧描述查询需求，或展开参数设置当前任务"];

  const allowedGroupBys = grantAllowedGroupBys(selectedGrant);
  const validation = validateQueryForm(form).errors.map((message) => {
    if (message === "请至少选择一个园区") {
      const allowedParties = Array.isArray(selectedGrant.parties) ? selectedGrant.parties : [];
      return `请至少选择一个园区；当前授权可选：${allowedParties.join("、") || "无"}`;
    }
    if (message.startsWith("TIME_SERIES 必须选择时间粒度")) {
      return `请选择时间粒度；当前授权可选：${allowedGroupBys.map(queryGroupLabel).join("、") || "无"}`;
    }
    return message;
  });
  return [...new Set([...validation, ...queryGrantConflicts(form)])];
}

function querySubmitHintHtml(blockers) {
  if (!blockers.length) return "";
  return `<span class="query-submit-hint-icon" aria-hidden="true">!</span>
    <span><b>暂不能提交</b><span>${blockers.map(escapeHtml).join("；")}。请修改后重试。</span></span>`;
}

function setQueryEditorExpanded(expanded, { focus = false } = {}) {
  const editor = document.querySelector("#q-param-editor");
  if (!editor) return;
  editor.hidden = !expanded;
  const trigger = document.querySelector('[data-action="edit-params"][aria-controls="q-param-editor"]');
  if (trigger) {
    trigger.setAttribute("aria-expanded", String(expanded));
    trigger.textContent = expanded ? "收起参数" : "编辑参数";
  }
  if (expanded && focus) queueMicrotask(() => document.querySelector("#q-grant")?.focus());
}

function focusFirstQueryCorrection(form, selectedGrant) {
  let target = null;
  if (!state.agent.hasCurrentTask) target = document.querySelector("#query-input");
  else if (!selectedGrant) target = document.querySelector("#q-grant");
  else if (!QUERY_TYPES.includes(form.query_type)) target = document.querySelector("#q-type");
  else if (!Array.isArray(form.parties) || form.parties.length === 0) {
    target = document.querySelector('#q-parties input:not([disabled])');
  } else if (!form.start_time) target = document.querySelector("#q-start");
  else if (!form.end_time) target = document.querySelector("#q-end");
  else if (!Number.isFinite(Number(form.epsilon)) || Number(form.epsilon) <= 0) {
    target = document.querySelector("#q-epsilon");
  } else if (form.query_type === "TIME_SERIES"
    && (!form.group_by || !grantAllowedGroupBys(selectedGrant).includes(form.group_by))) {
    target = document.querySelector("#q-group");
  }
  target?.focus();
}

function toDateTimeLocal(value) {
  const text = String(value || "");
  return text.slice(0, 16);
}

function applyAgentDraftToForm(draft, { replace = false } = {}) {
  const existing = readQueryForm();
  const selectedGrant = state.access.grants.find((grant) => grant.grant_id === existing.grant_id);
  const maxEpsilon = Number(selectedGrant?.max_epsilon_per_query);
  const remainingEpsilon = Number(selectedGrant?.epsilon_remaining);
  const grantDefaultEpsilon = selectedGrant
    && Number.isFinite(maxEpsilon) && maxEpsilon > 0
    && Number.isFinite(remainingEpsilon) && remainingEpsilon > 0
      ? Math.min(1, maxEpsilon, remainingEpsilon)
      : null;
  const base = replace
    ? {
        ...existing,
        query_type: null,
        parties: [],
        // A new Agent task must not inherit stale values from an older task.
        // These three defaults come from the currently selected, authoritative
        // Grant rather than from model-generated values.
        start_time: selectedGrant ? toDateTimeLocal(selectedGrant.allowed_start_time) : "",
        end_time: selectedGrant ? toDateTimeLocal(selectedGrant.allowed_end_time) : "",
        epsilon: grantDefaultEpsilon,
        group_by: null,
      }
    : existing;
  const result = applyDraft(base, draft);
  const controlMap = {
    query_type: "#q-type",
    parties: "#q-parties",
    start_time: "#q-start",
    end_time: "#q-end",
    epsilon: "#q-epsilon",
    group_by: "#q-group",
  };
  const set = (selector, value) => {
    const el = document.querySelector(selector);
    if (el) el.value = value;
  };
  set("#q-type", result.form.query_type || "");
  document.querySelectorAll("#q-parties input").forEach((cb) => {
    cb.checked = (result.form.parties || []).includes(cb.value);
  });
  set("#q-start", result.form.start_time ? toDateTimeLocal(result.form.start_time) : "");
  set("#q-end", result.form.end_time ? toDateTimeLocal(result.form.end_time) : "");
  set("#q-epsilon", result.form.epsilon == null ? "" : String(result.form.epsilon));
  set("#q-group", result.form.group_by || "");
  syncGroupByControl({ defaultIfEmpty: false });

  document.querySelectorAll(".agent-changed").forEach((el) => el.classList.remove("agent-changed"));
  result.changed.forEach((field) => {
    const selector = controlMap[field];
    const el = selector ? document.querySelector(selector) : null;
    const label = el ? el.closest("label") : null;
    if (label) label.classList.add("agent-changed");
  });
  state.agent.changed = result.changed;
  updateCurrentTaskSummary();
  return result;
}

function unresolvedAgentFields(response, form) {
  const missing = Array.isArray(response?.missing_fields) ? response.missing_fields : [];
  return missing.filter((field) => {
    if (field === "parties") return !Array.isArray(form?.parties) || form.parties.length === 0;
    if (field === "epsilon") return !Number.isFinite(Number(form?.epsilon)) || Number(form.epsilon) <= 0;
    if (field === "group_by") return form?.query_type === "TIME_SERIES" && !form?.group_by;
    return !form?.[field];
  });
}

function isAgentTaskIntent(intent) {
  return ["QUERY", "TASK_UPDATE", "CREATE_PRIVACY_QUERY"].includes(intent);
}

const AGENT_TYPE_INTERVAL_MS = 18;
const AGENT_RUNTIME_ID = `agent-runtime-${Date.now()}-${Math.random().toString(36).slice(2)}`;
let agentMessageSequence = 0;

function agentReplyText(response) {
  return String(response?.reply || response?.explanation || "");
}

function prefersReducedMotion() {
  return typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function finishAgentTyping({ update = true } = {}) {
  const agent = state.agent;
  if (agent.typingTimer !== null) {
    clearTimeout(agent.typingTimer);
    agent.typingTimer = null;
  }
  const message = agent.messages.find((item) => item.id === agent.typingMessageId);
  if (message?.typing) {
    message.visibleReply = agentReplyText(message.response);
    message.typing = false;
  }
  agent.typingMessageId = null;
  if (update) updateAgentRuntime();
}

function startAgentTyping(message) {
  const fullReply = agentReplyText(message.response);
  const characters = Array.from(fullReply);
  if (!characters.length || prefersReducedMotion()) {
    message.visibleReply = fullReply;
    message.typing = false;
    updateAgentRuntime();
    return;
  }

  finishAgentTyping({ update: false });
  message.visibleReply = "";
  message.typing = true;
  state.agent.typingMessageId = message.id;
  let index = 0;

  const revealNextCharacter = () => {
    if (state.agent.typingMessageId !== message.id || !message.typing) return;
    message.visibleReply += characters[index];
    index += 1;
    if (index >= characters.length) {
      message.typing = false;
      state.agent.typingMessageId = null;
      state.agent.typingTimer = null;
      updateAgentRuntime();
      return;
    }
    updateAgentRuntime();
    state.agent.typingTimer = setTimeout(revealNextCharacter, AGENT_TYPE_INTERVAL_MS);
  };

  updateAgentRuntime();
  state.agent.typingTimer = setTimeout(revealNextCharacter, AGENT_TYPE_INTERVAL_MS);
}

function agentResponseHtml(message) {
  const response = message.response || {};
  const fullReply = agentReplyText(response);
  const reply = message.typing ? message.visibleReply || "" : fullReply;
  const replyHtml = `<p class="agent-typewriter" data-agent-typing="${message.typing ? "true" : "false"}">${escapeHtml(reply)}${message.typing ? `<span class="agent-typing-cursor" aria-hidden="true"></span>` : ""}</p>`;
  if (response.intent === "REFUSED") {
    return `<div class="advice-box agent-refusal">
      <h4>请求已拒绝</h4>
      ${replyHtml}
      ${(response.warnings || []).length ? `<ul>${response.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : ""}
      <b>未生成任何查询参数，未创建任务，隐私预算未变化。</b>
    </div>`;
  }
  if (!isAgentTaskIntent(response.intent)) {
    return `${replyHtml}
      ${(response.warnings || []).length ? `<div class="agent-draft-warning">${response.warnings.map(escapeHtml).join("；")}</div>` : ""}
      ${message.confirmReady ? `<div class="agent-draft-status ready">当前任务可进入提交确认</div>` : ""}`;
  }
  const summary = draftSummary(message.resolvedForm || response.task_draft, {
    ...response,
    missing_fields: message.unresolvedMissingFields ?? response.missing_fields,
  });
  const title = response.intent === "TASK_UPDATE" ? "已更新任务" : "已识别任务";
  const changedText = message.changed?.length
    ? `已更新字段：${message.changed.join("、")}`
    : response.task_draft ? "当前任务已按本轮明确参数核对" : "未修改当前任务参数";
  const confirmationText = message.canExecute
    ? `${changedText}。参数已同步至当前任务，请确认后点击「提交隐私查询」。`
    : `${changedText}。当前任务尚不能提交，请按上方提示修改参数。`;
  return `
    ${fullReply ? replyHtml : `<p>已生成查询参数草案</p>`}
    <div class="agent-task-draft">
      <b>${title}</b>
      ${summary.rows.length ? `<ul>${summary.rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>` : ""}
      ${summary.missing.length ? `<div class="agent-draft-warning">缺少参数：${summary.missing.map(escapeHtml).join("、")}</div>` : ""}
      ${summary.warnings.length ? `<div class="agent-draft-warning">安全提醒：${summary.warnings.map(escapeHtml).join("；")}</div>` : ""}
      ${message.conflicts?.length ? `<div class="agent-authorization-warning"><b>授权提示：当前授权不满足此任务</b><span>${message.conflicts.map(escapeHtml).join("；")}</span></div>` : ""}
      <div class="agent-draft-status ${message.canExecute ? "ready" : "review"}">${message.canExecute ? "当前授权可执行" : "需要补充或调整参数"}</div>
    </div>
    ${response.task_draft ? `<p class="agent-confirmation ${message.canExecute ? "" : "blocked"}">${confirmationText}</p>` : ""}
  `;
}

function agentHistoryHtml(agentState) {
  if (agentState.detailLoading) {
    return `<div class="agent-conversation-loading" aria-label="正在加载会话">
      <span></span><span></span><span></span><span></span>
    </div>`;
  }
  const welcome = `<div class="agent-message agent-message-agent">
    <div class="agent-message-avatar">A</div>
    <div class="agent-message-content"><b>Agent</b><p>你好，请描述需要分析的能源数据任务。我会将自然语言需求转换为受授权和隐私预算约束的计算任务。</p></div>
  </div>`;
  const messages = agentState.messages.map((message) => {
    if (message.role === "user") {
      return `<div class="agent-message agent-message-user">
        <div class="agent-message-content"><p>${escapeHtml(message.text)}</p></div>
        <div class="agent-message-avatar" aria-label="用户">您</div>
      </div>`;
    }
    if (message.error) {
      return `<div class="agent-message agent-message-agent">
        <div class="agent-message-avatar">A</div>
        <div class="agent-message-content"><b>Agent</b><div class="agent-response-error">${escapeHtml(message.error)}</div></div>
      </div>`;
    }
    return `<div class="agent-message agent-message-agent">
      <div class="agent-message-avatar">A</div>
      <div class="agent-message-content"><b>Agent</b>${agentResponseHtml(message)}</div>
    </div>`;
  }).join("");
  const thinking = agentState.busy || agentState.phase === "loading"
    ? `<div class="agent-message agent-message-agent"><div class="agent-message-avatar">A</div><div class="agent-message-content"><div class="agent-thinking"><span></span><span></span><span></span>正在解析查询意图并核验任务约束…</div></div></div>`
    : "";
  return `${welcome}${messages}${thinking}`;
}

function updateAgentRuntime() {
  const a = state.agent;
  const area = document.querySelector(`#q-agent-area[data-agent-runtime="${AGENT_RUNTIME_ID}"]`);
  const sendBtn = document.querySelector('[data-action="send-query"]');
  if (sendBtn) {
    sendBtn.disabled = a.busy;
    sendBtn.style.opacity = a.busy ? "0.55" : "1";
  }
  if (!area) return;
  area.innerHTML = agentHistoryHtml(a);
  area.scrollTop = area.scrollHeight;
}

function speechInputButtonHtml() {
  const { supported, listening, unavailableReason } = speechInput.getState();
  const label = listening ? "停止语音输入" : "开始语音输入";
  const title = supported
    ? (listening ? "停止语音输入" : "语音输入")
    : unavailableReason;
  return `<span class="speech-listening-status" aria-live="polite" ${listening ? "" : "hidden"}>正在聆听…</span>
    <button type="button" class="speech-input-button ${listening ? "listening" : ""}" data-action="toggle-speech-input" aria-label="${label}" aria-pressed="${listening}" title="${title}" ${supported ? "" : "disabled"}>${icon("microphone")}</button>`;
}

function updateSpeechInputUi() {
  const { supported, listening, unavailableReason } = speechInput.getState();
  const button = document.querySelector('[data-action="toggle-speech-input"]');
  const status = document.querySelector(".speech-listening-status");
  if (!button) return;
  const label = listening ? "停止语音输入" : "开始语音输入";
  button.disabled = !supported;
  button.classList.toggle("listening", listening);
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-pressed", String(listening));
  button.title = supported
    ? (listening ? "停止语音输入" : "语音输入")
    : unavailableReason;
  if (status) status.hidden = !listening;
}

function conversationSummaryFromDetail(detail) {
  return {
    conversation_id: detail.conversation_id,
    title: detail.title,
    query_type: detail.query_type || null,
    parties: detail.parties || [],
    task_status: detail.task_status || null,
    last_task_id: detail.last_task_id || null,
    has_current_task: Boolean(detail.has_current_task),
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

function mergeConversationSummary(detail) {
  const summary = conversationSummaryFromDetail(detail);
  const others = state.agent.conversations.filter(
    (item) => item.conversation_id !== summary.conversation_id
  );
  state.agent.conversations = [summary, ...others].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );
}

function resetConversationTaskState() {
  state.query.controller?.dispose();
  state.query.controller = null;
  Object.assign(state.query, {
    budgetLoaded: false,
    phase: "idle",
    task: null,
    result: null,
    budget: null,
    error: null,
    lastPayload: null,
  });
  state.agent.hasCurrentTask = false;
  state.agent.lastLinkedTaskId = null;
}

function resetConversationMessages() {
  finishAgentTyping({ update: false });
  state.agent.messages = [];
  state.agent.last = null;
  state.agent.error = null;
  state.agent.changed = [];
  state.agent.lastUserText = "";
  state.agent.phase = "idle";
}

function restoreConversationMessages(messages) {
  state.agent.messages = (messages || []).map((message) => {
    if (message.role === "USER") {
      return { id: message.message_id, role: "user", text: message.content };
    }
    return {
      id: message.message_id,
      role: "agent",
      response: {
        intent: message.intent || "OTHER",
        reply: message.content,
        task_draft: message.task_update || null,
        missing_fields: [],
        warnings: [],
      },
      visibleReply: message.content,
      typing: false,
      changed: [],
      conflicts: [],
      canExecute: false,
    };
  });
}

async function restoreLinkedConversationTask(detail) {
  if (!detail.last_task_id) return;
  try {
    const task = await getTask(detail.last_task_id);
    state.query.task = task;
    state.agent.lastLinkedTaskId = task.task_id;
    state.query.phase = task.status === "COMPLETED"
      ? "completed"
      : task.status === "FAILED" ? "failed" : "polling";
    if (task.status === "COMPLETED") {
      try {
        state.query.result = await getTaskResult(task.task_id);
      } catch (error) {
        state.query.error = { type: "RESULT_FETCH", detail: formatApiError(error) };
      }
    } else if (task.status === "FAILED") {
      state.query.error = { type: "TASK_FAILED", detail: task.error || "任务执行失败" };
    }
  } catch (error) {
    state.query.error = { type: "TASK_RESTORE", detail: formatApiError(error, "历史任务状态加载失败") };
  }
}

async function openAgentConversation(conversationId, { closeDrawer = true } = {}) {
  speechInput.cancel({ abort: true, discardInterim: true });
  if (!conversationId || state.agent.detailLoading) return;
  finishAgentTyping({ update: false });
  state.agent.detailLoading = true;
  if (closeDrawer) state.agent.historyOpen = false;
  render();
  try {
    const detail = await getAgentConversation(conversationId);
    resetConversationTaskState();
    resetConversationMessages();
    state.agent.conversationId = detail.conversation_id;
    restoreConversationMessages(detail.messages);
    if (detail.current_task_snapshot) {
      state.agent.hasCurrentTask = true;
      state.query.lastPayload = { ...detail.current_task_snapshot };
      state.access.selectedGrantId = detail.current_task_snapshot.grant_id || state.access.selectedGrantId;
      // The selected Grant snapshot already contains the authoritative remaining budget.
      state.query.budgetLoaded = true;
    }
    await restoreLinkedConversationTask(detail);
    mergeConversationSummary(detail);
  } catch (error) {
    toast(formatApiError(error, "历史会话加载失败"), "error");
  } finally {
    state.agent.detailLoading = false;
    render();
  }
}

async function refreshAgentConversations() {
  const conversations = await listAgentConversations();
  state.agent.conversations = Array.isArray(conversations) ? conversations : [];
  return state.agent.conversations;
}

async function ensureAgentConversation() {
  if (state.agent.conversationId) return state.agent.conversationId;
  try {
    const detail = await createAgentConversation();
    state.agent.conversationId = detail.conversation_id;
    mergeConversationSummary(detail);
    return detail.conversation_id;
  } catch (error) {
    // Parsing remains available for a transient persistence outage; no fake history is created.
    toast(formatApiError(error, "会话暂时无法持久化"), "warn");
    return null;
  }
}

async function mountAgentConversations() {
  if (state.agent.conversationsInitialized || state.agent.historyLoading) return;
  state.agent.historyLoading = true;
  try {
    const conversations = await refreshAgentConversations();
    state.agent.conversationsInitialized = true;
    if (conversations.length) {
      await openAgentConversation(conversations[0].conversation_id, { closeDrawer: false });
    }
  } catch {
    // Keep the workbench usable when the history endpoint is temporarily unavailable.
    state.agent.conversationsInitialized = true;
  } finally {
    state.agent.historyLoading = false;
  }
}

async function startNewAgentConversation() {
  speechInput.cancel({ abort: true, discardInterim: true });
  if (state.agent.busy || state.agent.detailLoading) return;
  state.agent.detailLoading = true;
  render();
  try {
    const detail = await createAgentConversation();
    resetConversationTaskState();
    resetConversationMessages();
    state.agent.conversationId = detail.conversation_id;
    state.agent.historyOpen = false;
    mergeConversationSummary(detail);
  } catch (error) {
    toast(formatApiError(error, "新建会话失败"), "error");
  } finally {
    state.agent.detailLoading = false;
    render();
  }
}

async function linkCurrentConversationTask(taskId) {
  if (!taskId || !state.agent.conversationId || state.agent.lastLinkedTaskId === taskId) return;
  state.agent.lastLinkedTaskId = taskId;
  try {
    const detail = await linkAgentConversationTask(state.agent.conversationId, taskId);
    mergeConversationSummary(detail);
  } catch (error) {
    state.agent.lastLinkedTaskId = null;
    toast(formatApiError(error, "任务会话关联失败"), "warn");
  }
}

async function runAgentParse(text) {
  if (state.agent.busy) return;
  finishAgentTyping();
  state.agent.abort?.abort();
  state.agent.abort = new AbortController();
  state.agent.busy = true;
  state.agent.phase = "loading";
  state.agent.error = null;
  state.agent.changed = [];
  state.agent.lastUserText = text;
  state.agent.messages.push({ role: "user", text });
  const input = document.querySelector("#query-input");
  if (input) input.value = "";
  updateAgentRuntime();
  try {
    const conversationId = await ensureAgentConversation();
    const currentForm = readQueryForm();
    const response = await parseNaturalLanguageQuery(text, currentForm, state.agent.abort.signal, {
      grantId: currentForm.grant_id,
      hasCurrentTask: state.agent.hasCurrentTask,
      conversationId,
    });
    state.agent.last = response;
    let applied = { changed: [], form: null };
    if (isAgentTaskIntent(response.intent)) {
      if ((response.intent === "QUERY" || response.intent === "CREATE_PRIVACY_QUERY") && response.task_draft) {
        // Mark the task before synchronizing controls so the right-hand summary
        // is refreshed immediately instead of remaining in its "待生成" state.
        state.agent.hasCurrentTask = true;
        applied = applyAgentDraftToForm(response.task_draft || {}, { replace: true });
      } else if (response.intent === "TASK_UPDATE" && state.agent.hasCurrentTask && response.task_draft) {
        applied = applyAgentDraftToForm(response.task_draft);
      }
    }
    state.agent.changed = applied.changed || [];
    const resolvedForm = readQueryForm();
    const currentTaskValidation = validateQueryForm(resolvedForm);
    const conflicts = queryGrantConflicts(resolvedForm);
    const canExecute = state.agent.hasCurrentTask && currentTaskValidation.ok && conflicts.length === 0;
    const unresolvedMissingFields = applied.form
      ? unresolvedAgentFields(response, resolvedForm)
      : (Array.isArray(response.missing_fields) ? response.missing_fields : []);
    if (applied.form) state.query.lastPayload = { ...resolvedForm };
    const displayResponse = conflicts.length && isAgentTaskIntent(response.intent)
      ? {
          ...response,
          reply: `已识别本轮参数，但${conflicts.join("；")}。当前任务暂不能提交，请按授权范围调整参数或选择符合条件的授权。`,
        }
      : response;
    const agentMessage = {
      id: `agent-${++agentMessageSequence}`,
      role: "agent",
      response: displayResponse,
      visibleReply: "",
      typing: false,
      changed: [...state.agent.changed],
      conflicts,
      canExecute,
      resolvedForm: applied.form ? { ...resolvedForm } : null,
      unresolvedMissingFields,
      confirmReady: response.intent === "TASK_CONFIRM" && canExecute,
    };
    state.agent.messages.push(agentMessage);
    state.agent.phase = "done";
    // Agent parsing updates more than the chat stream: it also changes the
    // current-task summary and the real disabled state of the submit button.
    updateQueryRuntime();
    updateAgentRuntime();
    startAgentTyping(agentMessage);
    if (isAgentTaskIntent(response.intent)) toast("Agent 已更新当前任务，请确认后提交", "ok");
    if (response.intent === "TASK_CONFIRM" && canExecute) toast("当前任务可提交，请进行最终确认", "ok");
    if (conversationId) void refreshAgentConversations();
  } catch (error) {
    if (error && error.code === "ABORTED") return;
    state.agent.error = error;
    state.agent.phase = "error";
    state.agent.messages.push({
      role: "agent",
      error: "智能解析暂不可用，请稍后重试或使用右侧参数编辑功能。当前任务未发生改变。",
    });
    updateAgentRuntime();
    toast("智能解析暂不可用，请稍后重试或使用右侧参数编辑功能", "error");
  } finally {
    state.agent.busy = false;
    updateAgentRuntime();
  }
}

function buildExplainPayload() {
  const q = state.query;
  if (q.phase !== "completed" || !q.result || !q.task) return null;
  const task = q.task;
  const resultData = q.result.result || {};
  const payload = {
    query_type: task.query_type || q.result.query_type,
    epsilon: task.epsilon,
    sensitivity: task.sensitivity,
    parties: task.parties || [],
    execution_time_ms: task.duration_ms,
  };
  if (payload.query_type === "TIME_SERIES") {
    const m = resultData.metrics || {};
    payload.bucket_count = resultData.bucket_count;
    payload.peak_value = m.peak_value;
    payload.peak_timestamp = m.peak_timestamp;
    payload.valley_value = m.valley_value;
    payload.valley_timestamp = m.valley_timestamp;
    payload.peak_valley_difference = m.peak_valley_difference;
    payload.average_load = m.average_load;
    payload.load_factor = m.load_factor;
  } else {
    payload.noisy_value = resultData.value;
  }
  return payload;
}

async function runAgentExplain() {
  const payload = buildExplainPayload();
  if (!payload) {
    toast("请先完成一次查询", "error");
    return;
  }
  if (state.agent.busy) return;
  state.agent.abort?.abort();
  state.agent.abort = new AbortController();
  state.agent.busy = true;
  const box = document.querySelector("#q-explanation");
  const btn = document.querySelector('[data-action="explain-result"]');
  if (btn) {
    btn.disabled = true;
    btn.textContent = "生成中…";
  }
  if (box) box.innerHTML = `<div class="api-state">正在生成智能解读…</div>`;
  try {
    const response = await explainResult(payload, state.agent.abort.signal);
    if (box) {
      box.innerHTML = `<div class="advice-box"><h4>智能解读</h4><p>${escapeHtml(response.explanation || "")}</p></div>`;
    }
    toast("智能解读已生成", "ok");
  } catch (error) {
    if (error && error.code === "ABORTED") return;
    if (box) {
      box.innerHTML = `<div class="api-state error">解读生成失败：${escapeHtml(formatApiError(error, "模型服务不可用"))}</div>`;
    }
  } finally {
    state.agent.busy = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = "生成智能解读";
    }
  }
}

function ensureQueryController() {
  if (!state.query.controller) {
    state.query.controller = new QueryController({
      // The query page is Grant-scoped.  Refreshing after completion/failure
      // must read the selected Grant, never the legacy GLOBAL budget endpoint.
      onGetBudget: (_subjectId, _dataScope, options) => refreshSelectedGrantBudget(options),
    });
  }
  return state.query.controller;
}

// 把控制器的实时状态同步到页面级 state.query，供渲染与跨页面保留结果使用。
function syncQueryState(partial) {
  const controller = state.query.controller;
  state.query.phase = partial?.phase || (controller ? controller.phase : state.query.phase);
  state.query.task = partial?.task || (controller ? controller.task : state.query.task);
  state.query.result = partial?.result || (controller ? controller.result : state.query.result);
  state.query.budget = partial?.budget || (controller ? controller.budget : state.query.budget);
  state.query.error = partial?.error || (controller ? controller.error : state.query.error);
  // Refreshing budget/task state before submission must not erase an Agent
  // draft that still needs to survive a normal page re-render.
  if (controller?.lastPayload) state.query.lastPayload = controller.lastPayload;
}

function updateQueryRuntime() {
  const q = state.query;
  const isBusy = q.controller ? q.controller.isBusy() : false;
  const currentForm = readQueryForm();
  const selectedGrant = state.access.grants.find(
    (grant) => grant.grant_id === currentForm.grant_id
  );
  const blockers = querySubmissionBlockers(currentForm, { isBusy, selectedGrant });
  const submit = document.querySelector("#q-submit");
  if (submit) {
    const isBlocked = blockers.length > 0;
    // Keep validation-blocked actions focusable/clickable so the user can ask
    // why submission is unavailable. Only an in-flight request is truly disabled.
    submit.disabled = isBusy;
    submit.classList.toggle("is-blocked", !isBusy && isBlocked);
    submit.setAttribute("aria-disabled", String(isBlocked));
    if (isBlocked) {
      submit.setAttribute("aria-describedby", "q-submit-hint");
      submit.title = blockers[0];
    } else {
      submit.removeAttribute("aria-describedby");
      submit.removeAttribute("title");
    }
    submit.textContent = isBusy ? "任务执行中…" : "提交隐私查询";
  }
  const submitHint = document.querySelector("#q-submit-hint");
  if (submitHint) {
    submitHint.innerHTML = querySubmitHintHtml(blockers);
    submitHint.hidden = blockers.length === 0;
  }
  const status = document.querySelector("#q-status");
  if (status) {
    if (q.error && ["validation_error", "error", "budget_insufficient"].includes(q.phase)) {
      status.innerHTML = `创建失败：${escapeHtml(formatApiError(q.error, "未知错误"))}`;
    } else if (q.task) {
      status.innerHTML = `任务ID：${escapeHtml(q.task.task_id)}　状态：${statusLabel(q.task.status)}`;
    } else {
      status.innerHTML = "尚未提交任务";
    }
  }
  const steps = document.querySelector("#q-steps");
  if (steps) steps.innerHTML = queryStagesHtml(q.phase, q.task);
  const result = document.querySelector("#q-result");
  if (result) {
    result.innerHTML = queryResultHtml(q);
    bindTimeSeriesChartActions(result);
  }
  const privacy = document.querySelector("#q-privacy");
  if (privacy) privacy.innerHTML = queryPrivacyHtml(q);
  const plan = document.querySelector("#q-plan");
  if (plan) {
    plan.toggleAttribute('data-i18n-ignore', Boolean(q.lastPayload));
    plan.textContent = q.lastPayload ? JSON.stringify(q.lastPayload, null, 2) : "提交任务后将在此展示实际请求参数";
  }
  const formError = document.querySelector("#q-form-error");
  if (formError) {
    const error = q.error;
    if (error && ["validation_error", "budget_insufficient", "error"].includes(q.phase)) {
      formError.textContent = formatApiError(error);
      formError.style.display = "block";
    } else {
      formError.textContent = "";
      formError.style.display = "none";
    }
  }
  syncGrantSelectorRuntime();
  const budgetBox = document.querySelector("#q-budget");
  if (budgetBox && q.budget) {
    budgetBox.innerHTML = `
      <div class="kv-row"><div class="k">剩余预算</div><div class="v">${fmtEpsilon(q.budget.remaining_epsilon)}</div></div>
      <div class="kv-row"><div class="k">本次预计消耗</div><div class="v">${fmtEpsilon(Number(document.querySelector("#q-epsilon")?.value || 0))}</div></div>
    `;
  }
  // Runtime refreshes must not invent a TIME_SERIES granularity that the
  // Agent explicitly left unresolved. Direct user/type changes initialize it
  // in their own event path.
  syncGroupByControl({ defaultIfEmpty: false });
  updateCurrentTaskSummary();
}

async function loadQueryBudget() {
  const controller = ensureQueryController();
  await controller.refreshBudget();
  syncQueryState();
  updateQueryRuntime();
}

function mountQuery() {
  if (state.query.budgetLoaded) return;
  state.query.budgetLoaded = true;
  void loadQueryBudget();
}

function conversationTimeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function conversationDayGroup(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更早";
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  if (startDate === startToday) return "今天";
  if (startDate === startToday - 86400000) return "昨天";
  return "更早";
}

function conversationMeta(item) {
  if (!item.has_current_task) return "普通对话";
  const parties = item.parties?.length === 3 ? "3方" : (item.parties || []).join(" / ");
  return `${item.query_type || "查询"} · ${parties || "待补充"}`;
}

function agentHistoryDrawerHtml() {
  if (!state.agent.historyOpen) return "";
  const query = state.agent.historySearch.trim().toLowerCase();
  const items = state.agent.conversations.filter((item) => !query
    || item.title.toLowerCase().includes(query)
    || conversationMeta(item).toLowerCase().includes(query));
  const groups = ["今天", "昨天", "更早"].map((group) => {
    const groupItems = items.filter((item) => conversationDayGroup(item.updated_at) === group);
    if (!groupItems.length) return "";
    return `<section class="agent-history-group"><h4>${group}</h4>${groupItems.map((item) => `
      <button class="agent-history-item ${item.conversation_id === state.agent.conversationId ? "active" : ""}" data-action="open-agent-conversation" data-id="${escapeHtml(item.conversation_id)}">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(conversationMeta(item))}</span>
        <small><time>${conversationTimeLabel(item.updated_at)}</time>${item.task_status ? `<b class="pill ${String(item.task_status).toLowerCase()}">${escapeHtml(statusLabel(item.task_status))}</b>` : ""}</small>
      </button>`).join("")}</section>`;
  }).join("");
  const content = state.agent.historyLoading
    ? `<div class="agent-history-skeleton"><span></span><span></span><span></span></div>`
    : groups || `<div class="agent-history-empty"><b>${query ? "没有匹配的会话" : "暂无历史会话"}</b><p>${query ? "请尝试其他关键词。" : "你可以通过自然语言创建第一个隐私查询任务。"}</p></div>`;
  return `<div class="agent-history-backdrop" data-action="close-agent-history">
    <aside class="agent-history-drawer" role="dialog" aria-modal="true" aria-label="历史会话" onclick="event.stopPropagation()">
      <div class="agent-history-head"><h3>历史会话</h3><button data-action="close-agent-history" aria-label="关闭历史会话">×</button></div>
      <div class="agent-history-search">${icon("search")}<input id="agent-history-search" value="${escapeHtml(state.agent.historySearch)}" placeholder="搜索会话"></div>
      <div class="agent-history-list">${content}</div>
    </aside>
  </div>`;
}

function queryPage() {
  if (USE_MOCK) return queryPageMock();
  const q = state.query;
  const isBusy = q.controller ? q.controller.isBusy() : false;
  const budget = q.budget;
  const activeGrants = state.access.grants.filter((grant) => grant.status === "ACTIVE" && grant.epsilon_remaining > 0);
  const selectedGrant = activeGrants.find((grant) => grant.grant_id === state.access.selectedGrantId) || activeGrants[0] || null;
  if (selectedGrant) state.access.selectedGrantId = selectedGrant.grant_id;
  const initialType = q.lastPayload?.query_type || q.task?.query_type || selectedGrant?.allowed_query_types?.[0] || "SUM";
  const initialParties = q.lastPayload?.parties || q.task?.parties || selectedGrant?.parties || [];
  const initialStart = q.lastPayload?.start_time || selectedGrant?.allowed_start_time || "2012-11-11T00:00";
  const initialEnd = q.lastPayload?.end_time || selectedGrant?.allowed_end_time || "2012-11-12T00:00";
  const initialEpsilon = q.lastPayload?.epsilon ?? Math.min(1, selectedGrant?.max_epsilon_per_query || 1);
  const hasPersistedGroupBy = Boolean(q.lastPayload)
    && Object.prototype.hasOwnProperty.call(q.lastPayload, "group_by");
  const initialGroupBy = hasPersistedGroupBy
    ? (q.lastPayload.group_by || "")
    : (initialType === "TIME_SERIES" ? preferredGroupByForGrant(selectedGrant) : "");
  const initialForm = {
    grant_id: selectedGrant?.grant_id || "",
    query_type: initialType,
    parties: initialParties,
    start_time: initialStart,
    end_time: initialEnd,
    epsilon: initialEpsilon,
    group_by: initialType === "TIME_SERIES" ? initialGroupBy : null,
  };
  const initialBlockers = querySubmissionBlockers(initialForm, {
    isBusy,
    selectedGrant,
    hasCurrentTask: state.agent.hasCurrentTask,
  });
  const remainingBudget = budget?.remaining_epsilon ?? selectedGrant?.epsilon_remaining;
  const budgetRows = budget
    ? [
        ["剩余预算 ε", fmtEpsilon(budget.remaining_epsilon)],
        ["总预算 ε", fmtEpsilon(budget.total_epsilon)],
        ["已用 ε", fmtEpsilon(budget.used_epsilon)],
        ["预留 ε", fmtEpsilon(budget.reserved_epsilon)],
      ]
    : [["剩余预算 ε", "加载中…"]];
  const partyChecks = PARTY_IDS.map(
    (party) => `<label class="chip-check access-option"><input type="checkbox" value="${party}" ${initialParties.includes(party) ? "checked" : ""} ${selectedGrant?.parties.includes(party) ? "" : "disabled"}><span>${party}</span></label>`
  ).join("");
  return `<main class="content query-workspace-page">
    <div class="query-page-heading">
      <h2>智能隐私查询</h2>
    </div>

    ${panel("Agent 工作台", `
        <div class="agent-workbench">
          <section class="agent-main-column" aria-label="Agent 对话工作区">
          <div class="agent-conversation" id="q-agent-area" data-agent-runtime="${AGENT_RUNTIME_ID}" aria-live="polite">${agentHistoryHtml(state.agent)}</div>
          <div class="agent-quick-actions" aria-label="Agent 快捷操作">
            <button data-action="edit-params">修改查询范围</button>
            <button data-action="query-prompt" data-prompt="请解释当前任务的隐私预算和预计消耗">解释预算</button>
            <button data-action="query-prompt" data-prompt="请解释当前授权可使用的数据方、查询类型和时间范围">查看授权范围</button>
            <button data-action="query-prompt" data-prompt="分析小时负荷趋势">生成趋势分析</button>
          </div>
          <div class="agent-composer">
            <div class="agent-suggestions"><span>推荐问题</span>
              <button data-action="query-prompt" data-prompt="查询三园区总负荷">查询三园区总负荷</button>
              <button data-action="query-prompt" data-prompt="分析小时负荷趋势">分析小时负荷趋势</button>
              <button data-action="query-prompt" data-prompt="查看当前隐私预算">查看当前隐私预算</button>
              <button data-action="query-prompt" data-prompt="解释上一次查询">解释上一次查询</button>
            </div>
            <div class="query-input"><input id="query-input" maxlength="500" placeholder="请输入您的问题...">${speechInputButtonHtml()}<button class="agent-send-button" data-action="send-query" aria-label="发送问题">${icon("send")}</button></div>
          </div>
          </section>

          <aside class="current-task-column" aria-labelledby="current-task-title">
            <div class="current-task-column-head"><h3 id="current-task-title">当前任务</h3></div>
            <div class="current-task-column-body">
              <div id="q-current-task" class="current-task-card">
          <div class="current-task-summary">
            <div><span>授权</span><strong id="q-current-grant">${escapeHtml(selectedGrant?.grant_id || "暂无可用授权")}</strong></div>
            <div><span>查询类型</span><strong id="q-current-type">${state.agent.hasCurrentTask ? escapeHtml(chineseLabel(initialType)) : "待生成"}</strong></div>
            <div><span>参与方</span><strong id="q-current-parties">${state.agent.hasCurrentTask ? escapeHtml(initialParties.length ? initialParties.join(" / ") : "未选择") : "待生成"}</strong></div>
            <div><span>时间范围</span><strong id="q-current-range">${state.agent.hasCurrentTask ? escapeHtml(`${toDateTimeLocal(initialStart).replace("T", " ")} — ${toDateTimeLocal(initialEnd).replace("T", " ")}`) : "待生成"}</strong></div>
            <div><span>隐私预算</span><strong id="q-current-epsilon">${state.agent.hasCurrentTask ? fmtEpsilon(initialEpsilon) : "待生成"}</strong></div>
            <div><span>剩余预算</span><strong id="q-current-budget">${remainingBudget == null ? "加载中…" : fmtEpsilon(remainingBudget)}</strong></div>
            <div><span>安全模式</span><strong>分布式差分隐私</strong></div>
          </div>

          <div class="task-editor" id="q-param-editor" hidden>
            <div class="form2 query-editor-form">
              <label><span class="k">有效授权</span>
                <select id="q-grant">
                  ${activeGrants.map((grant) => `<option value="${escapeHtml(grant.grant_id)}" ${grant.grant_id === selectedGrant?.grant_id ? "selected" : ""}>${escapeHtml(grant.grant_id)} · 剩余 ε ${fmtEpsilon(grant.epsilon_remaining)}</option>`).join("")}
                </select>
              </label>
              ${activeGrants.length ? "" : `<div class="api-state error">当前没有可用授权，请先完成数据使用申请与多方审批。</div>`}
              <label><span class="k">查询类型</span>
                <select id="q-type">
                  ${[["SUM", "求和 SUM"], ["COUNT", "计数 COUNT"], ["AVERAGE", "均值 AVERAGE"], ["TIME_SERIES", "时间序列 TIME_SERIES"]].map(([value, label]) => `<option value="${value}" ${value === initialType ? "selected" : ""}>${label}</option>`).join("")}
                </select>
              </label>
              <label><span class="k">数据方</span><span id="q-parties" class="chips access-options">${partyChecks}</span></label>
              <label><span class="k">开始时间</span><input id="q-start" type="datetime-local" value="${toDateTimeLocal(initialStart)}"></label>
              <label><span class="k">结束时间</span><input id="q-end" type="datetime-local" value="${toDateTimeLocal(initialEnd)}"></label>
              <label><span class="k">隐私预算 ε</span><input id="q-epsilon" type="number" min="0.1" max="${selectedGrant?.max_epsilon_per_query || 5}" step="0.1" value="${initialEpsilon}"><small>授权单次上限：${selectedGrant ? fmtEpsilon(selectedGrant.max_epsilon_per_query) : "--"}</small></label>
              <label id="q-group-wrap"><span class="k">时间粒度</span>
                <select id="q-group">
                  <option value="30m" ${initialGroupBy === "30m" ? "selected" : ""}>30分钟</option>
                  <option value="1h" ${initialGroupBy === "1h" ? "selected" : ""}>1小时</option>
                  <option value="1d" ${initialGroupBy === "1d" ? "selected" : ""}>1天</option>
                </select>
                <small id="q-group-scope">${grantAllowedGroupBys(selectedGrant).length ? `当前授权可选：${grantAllowedGroupBys(selectedGrant).map(queryGroupLabel).join(" / ")}` : "当前授权未开放时间粒度"}</small>
              </label>
            </div>
            <div class="kv-table" id="q-budget">${budgetRows.map(([k, v]) => `<div class="kv-row"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
          </div>

          <div class="notice" id="q-form-error" style="display:none"></div>
          <div class="query-submit-hint" id="q-submit-hint" role="status" aria-live="polite" ${initialBlockers.length ? "" : "hidden"}>${querySubmitHintHtml(initialBlockers)}</div>
          <div class="current-task-actions">
            <button data-action="edit-params" aria-controls="q-param-editor" aria-expanded="false">编辑参数</button>
            <button class="primary ${!isBusy && initialBlockers.length ? "is-blocked" : ""}" data-action="submit-query" id="q-submit" aria-disabled="${initialBlockers.length > 0}" ${initialBlockers.length ? 'aria-describedby="q-submit-hint"' : ""} ${isBusy ? "disabled" : ""}>${isBusy ? "任务执行中…" : "提交隐私查询"}</button>
          </div>
              </div>
            </div>
          </aside>
        </div>
      `, `<div class="agent-workbench-head-actions"><span class="agent-online"><i></i>Agent 在线</span><button data-action="new-agent-conversation">+ 新建会话</button><button class="text" data-action="open-agent-history">${icon("clock")}历史会话</button></div>`, "agent-workbench-card")}

    ${panel("任务执行状态", `
      <div class="query-lifecycle-head"><span id="q-status">${q.task ? `任务ID：${escapeHtml(q.task.task_id)}　状态：${statusLabel(q.task.status)}` : "尚未提交任务"}</span><small>执行阶段由后端任务状态实时驱动</small></div>
      <div class="query-progress" id="q-steps">${queryStagesHtml(q.phase, q.task)}</div>
    `, "", "query-lifecycle-card")}

    <section class="card panel query-results-card">
      <div class="panel-head"><h3>任务结果</h3></div>
      <div class="panel-body">
        <div class="query-result-tabs" role="tablist" aria-label="任务结果视图">
          <button class="active" role="tab" aria-selected="true" data-action="query-tab" data-tab="result">查询结果</button>
          <button role="tab" aria-selected="false" data-action="query-tab" data-tab="insight">智能解读</button>
          <button role="tab" aria-selected="false" data-action="query-tab" data-tab="logs">执行日志</button>
        </div>
        <div class="query-tab-panel" id="q-tab-result" data-tab-panel="result">
          <div id="q-result-metrics">${queryResultMetricsHtml(q)}</div>
          <div id="q-result">${queryResultHtml(q)}</div>
        </div>
        <div class="query-tab-panel" id="q-tab-insight" data-tab-panel="insight" hidden>
          <div id="q-privacy">${queryPrivacyHtml(q)}</div>
          <div id="q-explanation"></div>
          <div class="query-tab-actions"><button data-action="copy-explain">复制</button><button class="primary" data-action="explain-result">生成智能解读</button></div>
        </div>
        <div class="query-tab-panel" id="q-tab-logs" data-tab-panel="logs" hidden>
          <div class="code-block" id="q-plan" ${q.lastPayload ? 'data-i18n-ignore' : ''}>${escapeHtml(q.lastPayload ? JSON.stringify(q.lastPayload, null, 2) : "提交任务后将在此展示实际请求参数")}</div>
          <div class="query-tab-actions"><button data-action="view-logs">查看执行日志</button><button data-action="copy-plan">复制计划</button></div>
        </div>
      </div>
    </section>
  </main>${agentHistoryDrawerHtml()}`;
}

function mockSessionUser(username) {
  return { user_id: username, username, role: "ANALYST", party_id: null, is_active: true };
}

async function submitLogin() {
  const username = document.querySelector("#login-username")?.value.trim() || "";
  const password = document.querySelector("#login-password")?.value || "";
  state.loginUsername = username;
  if (!username || !password) {
    state.loginError = "请输入用户名和密码";
    render();
    return;
  }
  state.loginBusy = true;
  state.loginError = null;
  render();
  try {
    let user;
    if (USE_MOCK) {
      user = mockSessionUser(username);
    } else {
      await login(username, password);
      user = await getCurrentUser();
    }
    state.user = user;
    state.loggedIn = true;
    state.page = initialPageForRole(user.role);
    state.loginError = null;
    toast(`身份验证通过，欢迎 ${user.username}`, "ok");
  } catch (error) {
    state.loginError = formatApiError(error, "身份验证失败");
  } finally {
    state.loginBusy = false;
    render();
  }
}

async function performLogout() {
  speechInput.cancel({ abort: true, discardInterim: true });
  try {
    if (!USE_MOCK) await logout();
  } catch (error) {
    toast(formatApiError(error, "退出请求失败，本地界面已清理"), "error");
  } finally {
    state.loggedIn = false;
    state.user = null;
    state.loginUsername = "";
    state.passwordVisible = false;
    state.userOpen = false;
    Object.assign(state.overview, { loading: false, loaded: false, data: null, ownerSummary: null, error: null });
    Object.assign(state.access, {
      loading: false,
      loaded: {},
      error: null,
      assets: [],
      ownerAssets: [],
      requests: [],
      approvals: [],
      approvalHistory: [],
      selectedApproval: null,
      grants: [],
      ownerGrants: [],
      allRequests: [],
      allGrants: [],
      users: [],
      securityAudit: [],
      adminOverview: null,
      analystReport: null,
      policySummary: null,
      loadErrors: {},
      loadingKeys: {},
      ownerData: { assets: [], imports: [], active: null, config: null },
      importPhase: "idle",
      selectedDataImport: null,
    });
    resetConversationTaskState();
    resetConversationMessages();
    Object.assign(state.agent, {
      conversationId: null,
      conversations: [],
      conversationsInitialized: false,
      historyOpen: false,
      historySearch: "",
      historyLoading: false,
      detailLoading: false,
      lastLinkedTaskId: null,
    });
    render();
  }
}

async function restoreSession() {
  if (USE_MOCK) return;
  try {
    const user = await getCurrentUser();
    state.user = user;
    state.loggedIn = true;
    state.page = initialPageForRole(user.role);
    render();
  } catch {
    // 401 表示没有有效会话，保留现有登录页。
  }
}

function loginPage() {
  return `<div class="login-page">
    <div class="login-language">${languageControl()}</div>
    <div class="login-left">
      <div class="brand"><div class="logo"><span></span><span></span><span></span><span></span></div><h2>PrivGrid-Agent</h2></div>
      <h1>面向能源可信数据空间的<br>多方安全协同与隐私保护平台</h1>
      <p class="login-tagline">跨域协同 · 隐私计算 · 全程可审计</p>
      <div class="login-features">
        <div class="login-feature"><div class="round">${icon("data")}</div><b>数据不出域</b></div>
        <div class="login-feature"><div class="round">${icon("compute")}</div><b>多方安全计算</b></div>
        <div class="login-feature"><div class="round">${icon("query")}</div><b>智能可信交互</b></div>
      </div>
    </div>
    <div class="login-right">
      <div class="login-card">
        <h2>身份认证</h2>
        <div class="sub">登录平台以访问已授权的数据空间</div>
        <form id="login-form" class="login-form">
          <label for="login-username">用户名</label>
          <input id="login-username" name="username" value="${escapeHtml(state.loginUsername)}" autocomplete="username" maxlength="64" autofocus>
          <label for="login-password">密码</label>
          <div class="password-field">
            <input id="login-password" name="password" type="${state.passwordVisible ? "text" : "password"}" autocomplete="current-password" maxlength="256">
            <button type="button" class="password-toggle" data-action="toggle-password" aria-label="${state.passwordVisible ? "隐藏密码" : "显示密码"}" title="${state.passwordVisible ? "隐藏密码" : "显示密码"}">${icon(state.passwordVisible ? "eyeOff" : "eye")}</button>
          </div>
          ${state.loginError ? `<div class="login-error" role="alert">${escapeHtml(state.loginError)}</div>` : ""}
          <button class="primary wide login-submit" type="submit" ${state.loginBusy ? "disabled" : ""}>${state.loginBusy ? "正在登录..." : "登录"}</button>
        </form>
        <div class="login-footnote">账号角色与园区权限由平台统一管理</div>
      </div>
    </div>
  </div>`;
}

function taskStatusTag(status) {
  if (status === "COMPLETED") return tag("已完成", "ok");
  if (status === "FAILED") return tag("失败", "bad");
  return tag(statusLabel(status), "run");
}

function overviewHealthList(services) {
  return `<div class="health-list">${services.map((item) =>
    `<div class="health-item" data-action="health-detail" data-i="${escapeHtml(item.service_id || "")}">
      <span class="health-dot ${item.online ? "online" : "offline"}" aria-hidden="true"></span>
      <strong>${escapeHtml(item.name || item.service_id || "未命名节点")}<small>延迟 ${fmtNumber(item.latency_ms, 1)} ms · 版本 ${escapeHtml(item.version || "—")}</small></strong>
      <em class="${item.online ? "online" : "offline"}">${item.online ? "ONLINE" : "OFFLINE"}</em>
    </div>`).join("")}</div>`;
}

function latestBy(items, field) {
  return [...items].filter(Boolean).sort((a, b) => new Date(b?.[field] || 0) - new Date(a?.[field] || 0))[0] || null;
}

function ownerBusinessOverview(summary, tasks) {
  if (state.user?.role !== "DATA_OWNER") return "";
  const cards = [];
  const hasPending = Array.isArray(summary?.pendingApprovals);
  const hasHistory = Array.isArray(summary?.approvalHistory);
  if (hasPending || hasHistory) {
    const pending = hasPending ? summary.pendingApprovals.length : null;
    const completed = hasHistory ? summary.approvalHistory.length : null;
    const latestApproval = hasHistory ? latestBy(summary.approvalHistory, "decided_at") : null;
    const meta = [
      completed !== null ? `已完成 ${completed}` : null,
      latestApproval?.decided_at ? `最近 ${fmtDateTime(latestApproval.decided_at)}` : null,
    ].filter(Boolean).join(" · ") || (hasPending ? "来自待审批列表" : "来自审批历史");
    cards.push({
      label: hasPending ? "待处理审批" : "已完成审批",
      value: hasPending ? pending : completed,
      meta,
      page: hasPending ? "pending-approvals" : "approval-history",
      action: "查看审批",
    });
  }
  if (Array.isArray(summary?.ownerGrants)) {
    cards.push({
      label: "本园区有效授权",
      value: summary.ownerGrants.filter((grant) => grant.status === "ACTIVE").length,
      meta: `授权记录 ${summary.ownerGrants.length} 条`,
      page: "owner-grants",
      action: "查看授权",
    });
  }
  const latestImport = Array.isArray(summary?.dataImports) ? latestBy(summary.dataImports, "created_at") : null;
  if (summary?.activeDataVersion?.dataset_version || latestImport) {
    const hasActiveVersion = Boolean(summary?.activeDataVersion?.dataset_version);
    cards.push({
      label: hasActiveVersion ? "当前数据版本" : "最近数据导入",
      value: hasActiveVersion ? summary.activeDataVersion.dataset_version : latestImport.import_id,
      meta: latestImport ? `最近导入 ${latestImport.status || "—"}` : `状态 ${summary.activeDataVersion.status || "—"}`,
      page: "data",
      action: "数据接入",
    });
  }
  cards.push({
    label: "最近任务",
    value: Array.isArray(tasks) ? tasks.length : 0,
    meta: "最近返回记录，最多 50 条",
    page: "overview",
    action: "查看详情",
  });
  if (!cards.length) return "";
  return panel("园区业务概览", `<div class="business-summary-grid">${cards.map((card) => `
    <article class="business-summary-card">
      <span>${escapeHtml(card.label)}</span>
      <strong title="${escapeHtml(card.value)}">${escapeHtml(card.value)}</strong>
      <small>${escapeHtml(card.meta)}</small>
      <button type="button" data-page="${card.page}">${escapeHtml(card.action)} ›</button>
    </article>`).join("")}</div>`, "", "business-overview-panel");
}

function overviewRecentTasks(tasks) {
  if (!tasks.length) return `<div class="api-state">暂无任务记录</div>`;
  return `<div class="overview-table-scroll">${table(["任务ID", "数据方", "查询类型", "计算模式", "状态", "时间"],
    tasks.slice(0, 6).map((t) => [
      t.task_id,
      (t.parties || []).join("、"),
      queryTypeLabel(t.query_type),
      chineseLabel(t.calculation_mode),
      taskStatusTag(t.status),
      fmtDateTime(t.created_at),
    ]))}</div><div class="panel-foot"><button data-action="view-all-tasks">查看全部任务 ›</button></div>`;
}

function overview() {
  if (USE_MOCK) return overviewMock();
  const view = state.overview;
  if (view.error) {
    return `<main class="content overview">
      <div class="api-state error">总览数据加载失败：${escapeHtml(formatApiError(view.error))}<br>
        <button class="primary" data-action="retry-overview" style="margin-top:12px">重新加载</button>
      </div>
    </main>`;
  }
  if (!view.data) {
    return `<main class="content overview"><div class="api-state">正在加载系统总览…</div></main>`;
  }
  const { health, parties, tasks, budget } = view.data;
  const services = health?.services || [];
  const onlineServices = services.filter((s) => s.online).length;
  const onlineParties = (parties || []).filter((p) => p.status === "ok" || p.status === "online").length;
  const successCount = tasks.filter((t) => t.status === "COMPLETED").length;
  const failedCount = tasks.filter((t) => t.status === "FAILED").length;
  const durations = tasks.map((t) => t.duration_ms).filter((v) => v !== null && v !== undefined);
  const avgDuration = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;

  const dayCounts = new Map();
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    dayCounts.set(`${d.getMonth() + 1}-${String(d.getDate()).padStart(2, "0")}`, 0);
  }
  tasks.forEach((t) => {
    const d = new Date(t.created_at);
    if (Number.isNaN(d.getTime())) return;
    const key = `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, "0")}`;
    if (dayCounts.has(key)) dayCounts.set(key, dayCounts.get(key) + 1);
  });
  const trendLabels = [...dayCounts.keys()];
  const trendValues = [...dayCounts.values()];

  const typeCounts = {};
  tasks.forEach((t) => { typeCounts[t.query_type] = (typeCounts[t.query_type] || 0) + 1; });
  const typeEntries = Object.entries(typeCounts);
  const donutData = typeEntries.length
    ? typeEntries.map(([type, value]) => ({
        label: queryTypeLabel(type),
        value,
        pct: (value / tasks.length) * 100,
      }))
    : [];

  return `<main class="content overview">
    <div class="stat-grid">
      ${statCard({ label: "在线服务", value: `${onlineServices} / ${services.length}`, sub: "总控 / 园区 / 计算节点", type: "blue", ic: "compute" })}
      ${statCard({ label: "在线园区", value: `${onlineParties} / ${parties.length}`, sub: "数据提供方", type: "green", ic: "data" })}
      ${statCard({ label: "剩余总隐私预算 ε", value: fmtEpsilon(budget?.remaining_epsilon), sub: `总 ${fmtEpsilon(budget?.total_epsilon)}`, type: "purple", ic: "shield" })}
      ${statCard({ label: "任务统计", value: `${successCount} / ${failedCount}`, sub: `成功 / 失败 · 平均 ${fmtDuration(avgDuration)}`, type: "red", ic: "audit" })}
    </div>
    ${panel("全链路业务流程", flowSteps(mockData.overview.flow))}
    <div class="overview-dashboard">
      <div class="dashboard-left">
        <div class="overview-charts">
          ${panel("近7日隐私查询趋势 ⓘ", trendValues.some((v) => v > 0) ? lineChart(trendLabels, trendValues) : `<div class="api-state">近 7 日暂无任务数据</div>`, `<button data-action="period">近7日 ⌄</button>`, "overview-chart-card")}
          ${panel("跨主体协同任务分布 ⓘ", donutData.length ? donutChart({ total: tasks.length, data: donutData }) : `<div class="api-state">暂无任务分布数据</div>`, `<button data-action="period">近7日 ⌄</button>`, "overview-chart-card")}
        </div>
        ${ownerBusinessOverview(view.ownerSummary, tasks)}
        ${panel("最近任务", overviewRecentTasks(tasks), "", "recent-tasks-panel")}
      </div>
      <div class="dashboard-right">
        ${panel("系统健康度", overviewHealthList(services), `<button data-action="health-detail" data-i="control">详情 ›</button>`, "overview-health-panel")}
        ${panel("风险预警", `<div class="api-state">后端暂未提供风险预警接口；预算不足或任务失败会在智能查询工作台直接提示。</div>`, "", "overview-risk-panel")}
      </div>
    </div>
  </main>`;
}

async function loadOwnerOverviewSummary() {
  const entries = [
    ["pendingApprovals", listPendingApprovals()],
    ["approvalHistory", listApprovalHistory()],
    ["ownerGrants", listOwnerGrants()],
    ["activeDataVersion", getActiveDataVersion()],
    ["dataImports", listMyDataImports()],
  ];
  const results = await Promise.allSettled(entries.map(([, promise]) => promise));
  return results.reduce((summary, result, index) => {
    if (result.status === "fulfilled") summary[entries[index][0]] = result.value;
    return summary;
  }, {});
}

async function mountOverview() {
  if (state.overview.loading || state.overview.loaded) return;
  state.overview.loading = true;
  try {
    const [health, parties, tasks, budget] = await Promise.all([
      getSystemHealth(),
      listParties(),
      listTasks(50),
      getBudget("demo-analyst", "GLOBAL"),
    ]);
    state.overview.data = {
      health: health || { services: [] },
      parties: Array.isArray(parties) ? parties : [],
      tasks: Array.isArray(tasks) ? tasks : [],
      budget: budget || null,
    };
    state.overview.error = null;
    state.overview.loaded = true;
    if (state.user?.role === "DATA_OWNER") {
      const ownerUserId = state.user.user_id;
      void loadOwnerOverviewSummary().then((summary) => {
        if (state.user?.user_id !== ownerUserId) return;
        state.overview.ownerSummary = summary;
        if (state.page === "overview") render();
      });
    }
  } catch (error) {
    state.overview.error = formatApiError(error, "网络错误");
  } finally {
    state.overview.loading = false;
  }
  render();
}

function overviewMock() {
  const d = mockData.overview;
  return `<main class="content overview">
    <div class="stat-grid">
      ${statCard({ label: "接入数据方", value: d.parties, sub: `较昨日　+${d.partiesDelta}`, type: "blue", ic: "compute", up: "up" })}
      ${statCard({ label: "今日隐私查询", value: d.queries, sub: `较昨日　+${d.queriesDelta}`, type: "green", ic: "audit", up: "up" })}
      ${statCard({ label: "剩余总隐私预算 ε", value: d.budget, sub: `较昨日　${d.budgetDelta}`, type: "purple", ic: "shield", up: "down" })}
      ${statCard({ label: "告警事件", value: d.alerts, sub: "较昨日　±0", type: "red", ic: "bell", up: "flat" })}
    </div>
    ${panel("全链路业务流程", flowSteps(d.flow))}
    <div class="overview-dashboard">
      <div class="dashboard-left">
        <div class="overview-charts">
          ${panel("近7日隐私查询趋势 ⓘ", lineChart(d.trendLabels, d.trendValues), `<button data-action="period">近7日 ⌄</button>`, "overview-chart-card")}
          ${panel("跨主体协同任务分布 ⓘ", donutChart(d.donut), `<button data-action="period">近7日 ⌄</button>`, "overview-chart-card")}
        </div>
        ${panel("最近任务", `<div class="overview-table-scroll">${table(["任务ID", "发起人", "查询类型", "数据方", "状态", "时间"], d.tasks)}</div><div class="panel-foot"><button data-action="view-all-tasks">查看全部任务 ›</button></div>`, "", "recent-tasks-panel")}
      </div>
      <div class="dashboard-right">
        ${panel("系统健康度", `<div class="health-list">${d.health.map((h, i) =>
          `<div class="health-item" data-action="health-detail" data-i="${i}"><span class="ring">${h.score}</span><strong>${h.name}<small>${h.meta}</small></strong><em>${h.status} ⌄</em></div>`
        ).join("")}</div>`, `<button data-action="health-detail" data-i="-1">详情 ›</button>`, "overview-health-panel")}
        ${panel("风险预警", `<div class="risk-list">${d.risks.map(r =>
          `<div class="risk ${r.cls}">
            <div class="risk-header"><b>${icon("alert")}${r.title} ${tag(r.level, r.levelTag)}</b><span>${r.time}</span></div>
            <p>${r.desc}</p>
          </div>`
        ).join("")}</div><div class="panel-foot"><button data-action="view-all-alerts">查看全部预警记录 ›</button></div>`, "", "overview-risk-panel")}
      </div>
    </div>
  </main>`;
}

function dataPage() {
  const ownerData = state.access.ownerData || { assets: [], imports: [], active: null, config: null };
  const assets = ownerData.assets || [];
  const imports = ownerData.imports || [];
  const active = ownerData.active;
  const config = ownerData.config;
  const safe = (value) => value === null || value === undefined || value === "" ? "—" : escapeHtml(value);
  const cards = assets.map((asset) => {
    const queryTypes = Array.isArray(asset.supported_query_types) ? asset.supported_query_types : [];
    return `<article class="card asset-card catalog-asset-card owner-asset-card">
    <div class="asset-head">
      <div class="round blue">${icon("db")}</div>
      <div class="asset-title"><h3>${safe(asset.name)}</h3><span>${safe(asset.asset_id)}</span></div>
      ${accessStatusTag(asset.status)}
    </div>
    <div class="asset-meta">
      <span><b>所属园区</b>${safe(asset.owner_party)}</span>
      <span><b>时间范围</b>${safe(fmtDate(asset.time_start))} — ${safe(fmtDate(asset.time_end))}</span>
      <span><b>数据粒度</b>${safe(asset.source_granularity)}</span>
      <span class="catalog-query-row"><b>支持查询</b><span class="asset-query-tags">${queryTypes.length ? queryTypes.map((type) => `<span class="asset-query-tag">${safe(type)}</span>`).join("") : "—"}</span></span>
    </div>
    <div class="catalog-card-actions"><button data-action="view-catalog-asset" data-id="${safe(asset.asset_id)}">查看详情</button></div>
  </article>`;
  }).join("");
  const empty = state.access.loading
    ? "正在加载本园区数据资产..."
    : `暂无 ${escapeHtml(state.user?.party_id || "当前园区")} 数据资产`;
  const phaseText = {
    idle: "等待选择 CSV",
    uploading: "上传中，随后将由本园区 Party 校验并转换…",
    success: "上传、校验与转换已完成",
    failed: "导入失败，请查看安全错误摘要",
  }[state.access.importPhase] || "等待选择 CSV";
  const selected = state.access.selectedDataImport || imports[0] || null;
  const validation = selected?.validation_summary || {};
  const validationErrors = Array.isArray(validation.errors) ? validation.errors : [];
  const report = selected ? `<div class="import-report">
    ${kvRowsHtml([
      { k: "导入编号", v: safe(selected.import_id) },
      { k: "Schema 匹配", v: validation.schema_matches ? "是" : "否" },
      { k: "总行数", v: fmtNumber(selected.row_count || 0) },
      { k: "有效行", v: fmtNumber(selected.valid_row_count || 0) },
      { k: "错误行", v: fmtNumber(selected.invalid_row_count || 0) },
      { k: "重复记录", v: fmtNumber(selected.duplicate_count || 0) },
      { k: "时间范围", v: `${fmtDateTime(selected.time_start)} — ${fmtDateTime(selected.time_end)}` },
      { k: "源文件 SHA-256", v: safe(selected.source_sha256) },
      { k: "Parquet SHA-256", v: safe(selected.parquet_sha256) },
    ])}
    <div class="notice">${validationErrors.length ? validationErrors.map((item) => `${safe(item.error_type)} · 行 ${safe(item.row_number)} · ${safe(item.field)} · ${safe(item.message)}`).join("<br>") : selected.error_message ? safe(selected.error_message) : "未记录校验错误"}</div>
  </div>` : `<div class="api-state">暂无校验报告</div>`;
  const historyRows = imports.map((item) => {
    const actions = item.status === "VALID"
      ? `<button data-action="activate-data-import" data-id="${escapeHtml(item.import_id)}">启用</button>`
      : item.status === "ACTIVE"
        ? `<span class="muted">当前使用</span>`
        : item.status === "ARCHIVED"
          ? `<button data-action="rollback-data-import" data-id="${escapeHtml(item.import_id)}">回滚至此</button>`
          : `<button data-action="view-data-import" data-id="${escapeHtml(item.import_id)}">查看错误</button>`;
    return [
      safe(item.import_id), safe(item.original_filename), fmtNumber(item.row_count || 0),
      `${fmtDateTime(item.time_start)} — ${fmtDateTime(item.time_end)}`,
      accessStatusTag(item.status), fmtDateTime(item.created_at), safe(item.uploader_user_id),
      fmtDateTime(item.activated_at), actions,
    ];
  });
  const activePanel = active ? `<div class="asset-meta active-version">
    <span><b>版本</b>${safe(active.dataset_version)}</span>
    <span><b>行数</b>${fmtNumber(active.row_count || 0)}</span>
    <span><b>时间范围</b>${fmtDateTime(active.time_start)} — ${fmtDateTime(active.time_end)}</span>
    <span><b>启用时间</b>${fmtDateTime(active.activated_at)}</span>
    <span><b>状态</b>${accessStatusTag(active.status || "ACTIVE")}</span>
    ${active.fallback_warning ? `<span class="notice">${safe(active.fallback_warning)}</span>` : ""}
    ${active.dataset_version !== "BASELINE" ? `<button data-action="rollback-data-import" data-id="BASELINE">回滚到基线</button>` : ""}
  </div>` : `<div class="api-state">${state.access.loading ? "正在读取活动版本…" : "活动版本加载失败"}</div>`;
  const upload = `<div class="import-upload">
    <div class="notice"><b>完整快照导入</b>：CSV 必须包含 household_id、organization_id、timestamp、energy_kwh；唯一键为 household_id + timestamp。文件不会自动启用。</div>
    <label class="file-picker"><span>选择 CSV 文件</span><input id="csv-import-file" type="file" accept=".csv,text/csv"></label>
    <div class="muted">上限 ${config ? fmtNumber(config.max_bytes / 1024 / 1024, 0) : 50} MB / ${config ? fmtNumber(config.max_rows) : "500,000"} 行；UTF-8 或 UTF-8-SIG。</div>
    <button class="primary" data-action="upload-data-import" ${state.access.importPhase === "uploading" || config?.enabled === false ? "disabled" : ""}>上传并校验</button>
    <span class="import-phase">${phaseText}</span>
  </div>`;
  const planned = `<div class="method-grid planned-methods">
    ${["MQTT 接入", "数据库直连", "API/HTTPS 接入", "新增外部数据源"].map((name) => `<button class="method" disabled><b>${name}</b><p>规划功能，当前版本未开放</p></button>`).join("")}
  </div>`;
  return accessPage(
    "本园区数据资产",
    "",
    `${panel("当前活动数据版本", activePanel)}${panel("CSV 安全导入", upload)}${panel("最近校验报告", report)}${panel("数据版本历史", historyRows.length ? table(["导入编号", "安全文件名", "行数", "时间范围", "状态", "上传时间", "上传人", "启用时间", "操作"], historyRows) : `<div class="api-state">暂无导入版本，查询继续使用 BASELINE。</div>`)}${panel("资产目录", `<div class="asset-grid">${cards || `<div class="api-state">${empty}</div>`}</div>`)}${panel("规划中的接入能力", planned)}`,
  );
}
function queryPageMock() {
  const d = mockData.query;
  return `<main class="content query-workspace-page">
    <div class="query-page-heading"><h2>智能隐私查询</h2></div>
    ${panel("Agent 工作台", `
        <div class="agent-workbench">
          <section class="agent-main-column" aria-label="Agent 对话工作区">
          <div class="agent-conversation">
            <div class="agent-message agent-message-agent"><div class="agent-message-avatar">A</div><div class="agent-message-content"><b>Agent</b><p>你好，请描述需要分析的能源数据任务。</p></div></div>
            <div class="agent-message agent-message-user"><div class="agent-message-content"><p>${escapeHtml(d.userQuestion)}</p></div><div class="agent-message-avatar" aria-label="用户">您</div></div>
            <div class="agent-message agent-message-agent"><div class="agent-message-avatar">A</div><div class="agent-message-content"><b>Agent</b><p>已生成结构化查询任务，请确认后提交。</p></div></div>
          </div>
          <div class="agent-quick-actions"><button data-action="edit-params">修改查询范围</button><button data-action="query-prompt" data-prompt="请解释当前任务的隐私预算和预计消耗">解释预算</button><button data-action="query-prompt" data-prompt="请解释当前授权范围">查看授权范围</button><button data-action="query-prompt" data-prompt="分析小时负荷趋势">生成趋势分析</button></div>
          <div class="agent-composer"><div class="agent-suggestions"><span>推荐问题</span><button data-action="query-prompt" data-prompt="查询三园区总负荷">查询三园区总负荷</button><button data-action="query-prompt" data-prompt="分析小时负荷趋势">分析小时负荷趋势</button></div><div class="query-input"><input id="query-input" placeholder="请输入您的问题...">${speechInputButtonHtml()}<button class="agent-send-button" data-action="send-query" aria-label="发送问题">${icon("send")}</button></div></div>
          </section>
          <aside class="current-task-column" aria-labelledby="mock-current-task-title">
            <div class="current-task-column-head"><h3 id="mock-current-task-title">当前任务</h3></div>
            <div class="current-task-column-body">
              <div id="q-current-task" class="current-task-card">
          <div class="current-task-summary"><div><span>授权</span><strong>演示授权</strong></div><div><span>查询类型</span><strong>${escapeHtml(d.params.metrics.join(" / "))}</strong></div><div><span>参与方</span><strong>${escapeHtml(d.params.parties.join(" / "))}</strong></div><div><span>时间范围</span><strong>${escapeHtml(d.params.timeRange)}</strong></div><div><span>隐私预算</span><strong>${escapeHtml(d.params.budget)}</strong></div><div><span>安全模式</span><strong>分布式差分隐私</strong></div></div>
          <div class="task-editor" id="q-param-editor" hidden><div class="api-state">演示模式仅展示任务结构</div></div>
          <div class="current-task-actions"><button data-action="edit-params" aria-controls="q-param-editor" aria-expanded="false">编辑参数</button><button class="primary" data-action="submit-query">提交隐私查询</button></div>
              </div>
            </div>
          </aside>
        </div>
      `, `<span class="agent-online"><i></i>Agent 在线</span>`, "agent-workbench-card")}
    ${panel("任务执行状态", `<div class="query-lifecycle-head"><span>演示任务状态</span><small>执行阶段由后端任务状态实时驱动</small></div><div class="query-progress">${d.steps.slice(0, 6).map((s, i) => `<div class="query-progress-step ${i === 0 ? "current" : "wait"}"><div class="query-progress-marker">${i + 1}</div><b>${escapeHtml(s.title)}</b><small>${escapeHtml(s.desc)}</small></div>`).join("")}</div>`, "", "query-lifecycle-card")}
    <section class="card panel query-results-card"><div class="panel-head"><h3>任务结果</h3></div><div class="panel-body">
      <div class="query-result-tabs" role="tablist"><button class="active" aria-selected="true" data-action="query-tab" data-tab="result">查询结果</button><button aria-selected="false" data-action="query-tab" data-tab="insight">智能解读</button><button aria-selected="false" data-action="query-tab" data-tab="logs">执行日志</button></div>
      <div class="query-tab-panel" data-tab-panel="result">${table(["时间", "总负荷(kW)", "可调节负荷(kW)", "储能可用容量(kWh)", "误差区间"], d.resultTable)}${lineChart(d.resultLabels, d.resultValues)}</div>
      <div class="query-tab-panel" data-tab-panel="insight" hidden><div class="advice-box"><h4>解释</h4><p>${escapeHtml(d.explain)}</p></div><div class="advice-box"><b>结论：${escapeHtml(d.conclusion)}</b></div></div>
      <div class="query-tab-panel" data-tab-panel="logs" hidden><div class="code-block">${escapeHtml(JSON.stringify(d.plan, null, 2))}</div></div>
    </div></section>
  </main>`;
}

function computeStepsFromMonitor(monitor) {
  const order = ["CREATED", "DISPATCHING", "LOCAL_COMPUTING", "SHARING", "AGGREGATING", "RECONSTRUCTING", "COMPLETED"];
  const index = order.indexOf(monitor?.current_stage);
  const failed = monitor?.status === "FAILED";
  const statusAt = (threshold) => {
    if (failed) return "wait";
    if (index < 0) return "wait";
    if (index > threshold) return "done";
    if (index === threshold) return "run";
    return "wait";
  };
  return [
    { name: "创建与分发", status: statusAt(0), desc: "任务注册到 S1/S2 并下发园区" },
    { name: "园区本地计算", status: statusAt(1), desc: "贡献度裁剪与本地统计" },
    { name: "秘密共享提交", status: statusAt(2), desc: "份额提交至 S1/S2" },
    { name: "S1/S2 聚合", status: statusAt(3), desc: "非串通节点安全聚合" },
    { name: "结果重构", status: statusAt(4), desc: "总控重构与定点解码" },
    { name: "完成", status: statusAt(5), desc: "返回带噪结果" },
  ];
}

function monitorKvRows(monitor) {
  const safe = (value) => {
    if (value === null || value === undefined || value === "") return "—";
    if (["string", "number", "boolean"].includes(typeof value)) return escapeHtml(String(value));
    return "—";
  };
  const partyStatus = Object.entries(monitor?.party_statuses || {})
    .map(([party, value]) => `${safe(party)}: ${safe(value)}`)
    .join("　") || "—";
  const computeStatus = Object.entries(monitor?.compute_node_statuses || {})
    .map(([node, value]) => `${safe(node)}: ${safe(value)}`)
    .join("　") || "—";
  const progress = Number(monitor?.progress);
  const expectedParties = Array.isArray(monitor?.expected_parties)
    ? monitor.expected_parties.map(safe).join("、") || "—"
    : "—";
  return [
    { k: "任务ID", v: safe(monitor?.task_id) },
    { k: "当前阶段", v: safe(statusLabel(monitor?.current_stage)) },
    { k: "进度", v: monitor?.progress !== null && monitor?.progress !== undefined && Number.isFinite(progress) ? `${progress}%` : "—" },
    { k: "园区状态", v: partyStatus },
    { k: "计算节点状态", v: computeStatus },
    { k: "预计参与方", v: expectedParties },
    { k: "已提交份额数", v: safe(monitor?.submitted_share_count) },
    { k: "开始时间", v: safe(fmtDateTime(monitor?.started_at)) },
    { k: "更新时间", v: safe(fmtDateTime(monitor?.updated_at)) },
    { k: "执行时间", v: safe(fmtDuration(monitor?.execution_time_ms)) },
  ];
}

function computeTopology(parties, nodes, monitor = {}) {
  const safeParties = Array.isArray(parties) ? parties.filter(Boolean) : [];
  const safeNodes = Array.isArray(nodes) ? nodes.filter((item) => item?.name) : [];
  const resultStatus = monitor.status || monitor.current_stage || "—";
  const resultType = resultStatus === "FAILED" ? "failed" : resultStatus === "COMPLETED" ? "complete" : "running";
  const members = (items, empty) => items.length
    ? items.map((item) => `<span class="topology-member"><i class="topology-status-dot ${item.online === false ? "offline" : ""}"></i><span><b>${escapeHtml(item.name)}</b>${item.meta ? `<small>${escapeHtml(item.meta)}</small>` : ""}</span></span>`).join("")
    : `<span class="topology-empty">${empty}</span>`;
  return `<div class="task-topology" aria-label="当前任务执行拓扑">
    <section class="topology-stage topology-providers">
      <div class="topology-stage-head"><span class="round blue">${icon("data")}</span><span><b>参与园区</b><small>${safeParties.length ? `${safeParties.length} 个数据提供方` : "暂无参与方"}</small></span></div>
      <div class="topology-members">${members(safeParties.map((name) => ({ name, meta: "本地受控统计" })), "暂无参与园区")}</div>
    </section>
    <div class="topology-connector"><span>秘密份额</span><i aria-hidden="true"></i></div>
    <section class="topology-stage topology-compute">
      <div class="topology-stage-head"><span class="round purple">${icon("compute")}</span><span><b>安全计算节点</b><small>非串通聚合</small></span></div>
      <div class="topology-members">${members(safeNodes, "暂无节点状态")}</div>
    </section>
    <div class="topology-connector"><span>带噪聚合</span><i aria-hidden="true"></i></div>
    <section class="topology-stage topology-result ${resultType}">
      <div class="topology-result-icon">${icon(resultType === "failed" ? "alert" : "check")}</div>
      <b>${resultType === "failed" ? "执行失败" : resultType === "complete" ? "结果已返回" : "结果处理中"}</b>
      <small>${escapeHtml(statusLabel(resultStatus))}</small>
      ${monitor.task_id ? `<span>${escapeHtml(monitor.task_id)}</span>` : ""}
    </section>
  </div>`;
}

function computePage() {
  if (USE_MOCK) return computePageMock();
  const view = state.compute;
  if (view.error) {
    return `<main class="content">
      <h2>分布式隐私计算监控</h2>
      <div class="api-state error">监控数据加载失败：${escapeHtml(formatApiError(view.error))}<br>
        <button class="primary" data-action="retry-compute" style="margin-top:12px">重新加载</button>
      </div>
    </main>`;
  }
  if (!view.data) {
    return `<main class="content"><h2>分布式隐私计算监控</h2><div class="api-state">正在加载监控数据…</div></main>`;
  }
  const { tasks, parties, health, budgets, monitor } = view.data;
  const monitorError = view.monitorError;
  const services = health?.services || [];
  const onlineParties = (parties || []).filter((p) => p.status === "ok" || p.status === "online").length;
  const computeServices = services.filter((s) => s.service_id === "compute-s1" || s.service_id === "compute-s2");
  const onlineCompute = computeServices.filter((s) => s.online).length;
  const runningTasks = tasks.filter((t) => !["COMPLETED", "FAILED"].includes(t.status)).length;
  const durations = tasks.map((t) => t.duration_ms).filter((v) => v != null);
  const avgDuration = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;
  const taskOptions = tasks.length
    ? `<option value="">请选择任务</option>` + tasks.map((t) => `<option value="${escapeHtml(t.task_id)}" ${t.task_id === view.selectedTaskId ? "selected" : ""}>${escapeHtml(t.task_id)} · ${queryTypeLabel(t.query_type)}</option>`).join("")
    : `<option value="">暂无任务</option>`;
  const budgetRows = Object.entries(budgets || {})
    .filter(([scope, row]) => row)
    .map(([scope, row]) => {
      const pct = row.total_epsilon > 0 ? Math.min(100, (row.used_epsilon / row.total_epsilon) * 100) : 0;
      return [scope, fmtEpsilon(row.total_epsilon), fmtEpsilon(row.used_epsilon), fmtEpsilon(row.remaining_epsilon),
        `<div class="budget-bar"><div class="bar"><i style="width:${pct.toFixed(1)}%"></i></div><span>${pct.toFixed(1)}%</span></div>`];
    });
  const resourceRows = services.map((s) => [
    `${escapeHtml(s.name)} ${s.online ? tag("正常") : tag("离线", "bad")}`,
    `${s.online ? "在线" : "离线"}`,
    fmtNumber(s.latency_ms, 1),
  ]);
  const steps = monitor ? computeStepsFromMonitor(monitor) : [];
  const selectedTask = tasks.find((task) => task.task_id === view.selectedTaskId) || null;
  const topologyParties = Array.isArray(monitor?.expected_parties) && monitor.expected_parties.length
    ? monitor.expected_parties
    : selectedTask?.parties || [];
  const monitoredNodes = Object.entries(monitor?.compute_node_statuses || {}).map(([name, status]) => ({
    name,
    meta: status || "—",
    online: !["OFFLINE", "FAILED", "ERROR"].includes(String(status || "").toUpperCase()),
  }));
  const topologyNodes = monitoredNodes.length ? monitoredNodes : computeServices.map((service) => ({
    name: service.name || service.service_id,
    meta: service.online ? "ONLINE" : "OFFLINE",
    online: Boolean(service.online),
  }));

  return `<main class="content task-compute-page">
    <div class="title-row">
      <h2>分布式隐私计算监控</h2>
      <div class="actions">
        <label style="display:flex;align-items:center;gap:8px;color:#5a6a85;font-size:13px">监控任务
          <select id="monitor-task-select" style="min-width:280px">${taskOptions}</select>
        </label>
        <button class="primary" data-action="refresh-monitor">${icon("clock")} 刷新监控</button>
      </div>
    </div>
    <div class="stat-grid">
      ${statCard({ label: "在线数据方", value: `${onlineParties} / ${parties.length}`, sub: "数据提供方", type: "blue", ic: "compute" })}
      ${statCard({ label: "计算节点在线", value: `${onlineCompute} / ${computeServices.length}`, sub: "S1 / S2", type: "green", ic: "data" })}
      ${statCard({ label: "执行中任务", value: runningTasks, sub: `最近 ${tasks.length} 条记录`, type: "purple", ic: "audit" })}
      ${statCard({ label: "平均执行时间", value: fmtDuration(avgDuration), sub: "最近任务", type: "green", ic: "settings" })}
    </div>
    ${panel("分布式隐私计算执行流程", monitor
      ? computeProgress(steps)
        + (monitor.status === "FAILED" ? errorBox({ detail: `任务执行失败：${monitor.error || "未知原因"}` }) : "")
        + (monitorError ? errorBox({ detail: monitorError }) : "")
      : monitorError
        ? errorBox({ detail: monitorError })
        : `<div class="api-state">请选择一个任务查看执行流程</div>`)}
    <div class="metric-pills compute-summary-grid">
      <div class="metric-pill"><b>${monitor?.submitted_share_count ?? "—"}</b><span>秘密份额数</span></div>
      <div class="metric-pill"><b>${fmtDuration(monitor?.execution_time_ms)}</b><span>计算时间</span></div>
      <div class="metric-pill"><b>${monitor?.progress != null ? monitor.progress + "%" : "—"}</b><span>整体进度</span></div>
      <div class="metric-pill"><b>${(monitor?.expected_parties || []).length || "—"}</b><span>参与方</span></div>
    </div>
    <div class="task-compute-main">
      <div class="task-main-column">
        ${panel("当前任务执行拓扑 ⓘ", monitor
          ? computeTopology(topologyParties, topologyNodes, monitor)
          : `<div class="api-state">请选择一个任务查看执行拓扑</div>`, "", "task-topology-panel")}
        <div class="node-budget-grid">
          ${panel("节点资源监控", resourceRows.length ? `<div class="resource-list">${resourceRows.map(([name, status, latency]) =>
            `<div class="resource-item"><b>${name}</b>
              <div class="resource-metrics"><span>状态 ${status}</span><span>延迟 ${latency} ms ${spark(status === "在线" ? "green" : "red")}</span></div>
            </div>`).join("")}</div>` : `<div class="api-state">暂无节点数据</div>`, "", "node-resources-panel")}
          ${panel("隐私预算消耗 ⓘ", budgetRows.length ? table(["数据范围", "总预算 ε", "已用 ε", "剩余 ε", "消耗占比"], budgetRows) : `<div class="api-state">暂无预算数据</div>`, "", "privacy-budget-panel")}
        </div>
      </div>
      <div class="task-side-column">
        ${panel("任务状态", monitor ? kvRowsHtml(monitorKvRows(monitor)) : `<div class="api-state">请选择一个任务查看状态</div>`, "", "task-status-panel")}
        ${panel("通信与安全事件", `<div class="api-state">后端暂未提供通信量统计与安全事件接口；本阶段仅展示任务阶段与计数。</div>`, "", "communication-events-panel")}
      </div>
    </div>
    ${panel("最近计算任务", tasks.length ? table(["任务ID", "数据方", "查询类型", "预算 ε", "状态", "用时"], tasks.map((t) => [
      t.task_id,
      (t.parties || []).join("、"),
      queryTypeLabel(t.query_type),
      fmtEpsilon(t.epsilon),
      taskStatusTag(t.status),
      fmtDuration(t.duration_ms),
    ])) : `<div class="api-state">暂无任务记录</div>`)}
  </main>`;
}

async function mountCompute() {
  if (state.compute.loading || state.compute.loaded) return;
  state.compute.loading = true;
  try {
    const [tasks, parties, health, globalBudget, orgABudget, orgBBudget, orgCBudget] = await Promise.all([
      listTasks(10),
      listParties(),
      getSystemHealth(),
      getBudget("demo-analyst", "GLOBAL"),
      getBudget("demo-analyst", "ORG_A"),
      getBudget("demo-analyst", "ORG_B"),
      getBudget("demo-analyst", "ORG_C"),
    ]);
    state.compute.data = {
      tasks: Array.isArray(tasks) ? tasks : [],
      parties: Array.isArray(parties) ? parties : [],
      health: health || { services: [] },
      budgets: { GLOBAL: globalBudget, ORG_A: orgABudget, ORG_B: orgBBudget, ORG_C: orgCBudget },
      monitor: null,
    };
    state.compute.error = null;
    state.compute.loaded = true;
    if (!state.compute.selectedTaskId && state.compute.data.tasks.length) {
      state.compute.selectedTaskId = state.compute.data.tasks[0].task_id;
    }
  } catch (error) {
    state.compute.error = formatApiError(error, "网络错误");
  } finally {
    state.compute.loading = false;
  }
  render();
  if (state.compute.selectedTaskId) {
    await refreshMonitor();
  }
}

async function refreshMonitor() {
  if (!state.compute.data) return;
  const select = document.querySelector("#monitor-task-select");
  const taskId = select?.value || state.compute.selectedTaskId;
  if (!taskId) return;
  state.compute.selectedTaskId = taskId;
  try {
    state.compute.data.monitor = await getTaskMonitor(taskId);
    state.compute.monitorError = null;
  } catch (error) {
    state.compute.monitorError = formatApiError(error, "监控加载失败");
    state.compute.data.monitor = null;
  }
  render();
}

function computePageMock() {
  const d = mockData.compute;
  return `<main class="content task-compute-page">
    <h2>分布式隐私计算监控</h2>
    <div class="stat-grid">
      ${statCard({ label: "在线数据方", value: d.parties, sub: `较昨日　+${d.partiesDelta}`, type: "blue", ic: "compute", up: "up" })}
      ${statCard({ label: "计算节点", value: d.nodes, sub: "较昨日　±0", type: "green", ic: "data", up: "flat" })}
      ${statCard({ label: "执行中任务", value: d.tasks, sub: `较昨日　+${d.tasksDelta}`, type: "purple", ic: "audit", up: "up" })}
      ${statCard({ label: "平均延迟", value: d.latency, sub: `较昨日　${d.latencyDelta}`, type: "green", ic: "settings", up: "up" })}
    </div>
    ${panel("分布式隐私计算执行流程", computeProgress(d.steps))}
    <div class="metric-pills compute-summary-grid">
      <div class="metric-pill"><b>${d.metrics.comm}</b><span>通信量</span></div>
      <div class="metric-pill"><b>${d.metrics.computeTime}</b><span>计算时间</span></div>
      <div class="metric-pill"><b>${d.metrics.rounds}</b><span>交互轮次</span></div>
      <div class="metric-pill"><b>${d.metrics.shares}</b><span>秘密份额</span></div>
    </div>
    <div class="task-compute-main">
      <div class="task-main-column">
        ${panel("当前任务执行拓扑 ⓘ", computeTopology(
          d.providers,
          d.computeNodes.map((node) => ({ name: node.name, meta: node.desc, online: true })),
          { status: "COMPLETED", current_stage: "COMPLETED" },
        ), "", "task-topology-panel")}
        <div class="node-budget-grid">
          ${panel("节点资源监控", `<div class="resource-list">${d.resources.map(r =>
            `<div class="resource-item"><b>${r.name} ${tag("正常")}</b>
              <div class="resource-metrics">
                <span>CPU ${r.cpu}% ${spark("blue")}</span>
                <span>内存 ${r.mem}% ${spark("green")}</span>
                <span>QPS ${r.qps} ${spark("purple")}</span>
              </div>
            </div>`
          ).join("")}</div>`, "", "node-resources-panel")}
          ${panel("隐私预算消耗 ⓘ", table(["任务ID", "预算 ε", "已消耗 ε", "消耗占比"], d.budget.map(b => [b.id, b.budget, b.used, `<div class="budget-bar"><div class="bar"><i style="width:${b.pct}%"></i></div><span>${b.pct}%</span></div>`])), "", "privacy-budget-panel")}
        </div>
      </div>
      <div class="task-side-column">
        ${panel("任务状态", `<div class="timeline">${d.timeline.map(t =>
          `<div class="timeline-item ${t.status === "已完成" ? "done" : t.status === "进行中" ? "run" : ""}">
            <b>${t.name}</b><em>${t.status}</em><p>${t.desc}</p>
          </div>`
        ).join("")}</div>`, "", "task-status-panel")}
        ${panel("通信与安全事件", `<div class="event-list">${d.events.map(e =>
          `<div><b>${tag("✓", e.type === "info" ? "info" : "ok")} ${e.title}</b><p>${e.desc}</p></div>`
        ).join("")}</div><div class="panel-foot"><button data-action="view-all-events">查看全部事件记录 ›</button></div>`, "", "communication-events-panel")}
      </div>
    </div>
    ${panel("最近计算任务", table(["任务ID", "数据方", "查询类型", "预算 ε", "状态", "用时"], d.recentTasks) + `<div class="panel-foot"><button data-action="view-all-tasks">查看全部任务 ›</button></div>`)}
  </main>`;
}
function policyPage() {
  const policy = state.access.policySummary;
  if (!policy) {
    return accessPage(
      "安全策略中心",
      "",
      `<div class="api-state">${state.access.loading ? "正在加载安全策略..." : "暂无安全策略摘要"}</div>`,
    );
  }
  const configRows = [
    ["授权强制校验", policy.authorization_enforcement_enabled ? accessStatusTag("ENABLED") : accessStatusTag("DISABLED")],
    ["原始数据下载", policy.raw_download_allowed ? accessStatusTag("ENABLED") : accessStatusTag("DISABLED")],
    ["当前计算模式", escapeHtml(policy.calculation_mode)],
    ["支持查询类型", policy.supported_query_types.map(queryTypeLabel).join(" / ")],
    ["支持时间粒度", policy.supported_group_by.join(" / ")],
    ["默认隐私预算 ε", fmtEpsilon(policy.default_total_epsilon)],
    ["会话 TTL", `${fmtNumber(policy.session_ttl_seconds)} 秒`],
    ["审计功能", policy.audit_enabled ? accessStatusTag("ENABLED") : accessStatusTag("DISABLED")],
  ];
  const nodeRows = [...policy.party_nodes, ...policy.compute_nodes].map((node) => [
    escapeHtml(node.name),
    escapeHtml(node.service_id),
    node.online ? accessStatusTag("ONLINE") : accessStatusTag("OFFLINE"),
    `${fmtNumber(node.latency_ms, 2)} ms`,
    escapeHtml(node.version || "--"),
  ]);
  return accessPage(
    "安全策略中心",
    "",
    `<div class="grid-half">
      ${panel("当前生效配置", `<div class="kv-table">${configRows.map(([key, value]) => `<div class="kv-row"><div class="k">${key}</div><div class="v">${value}</div></div>`).join("")}</div>`)}
      ${panel("Party 与 Compute 节点状态", nodeRows.length ? table(["节点", "服务标识", "状态", "检查延迟", "版本"], nodeRows) : `<div class="api-state">暂无节点状态</div>`)}
    </div>
    ${panel("策略变更记录", `<div class="api-state">暂无策略变更记录</div>`)}`,
  );
}

function auditResultTag(result) {
  const value = safeAuditValue(result);
  const type = ["DENIED", "FAILED", "REJECTED"].includes(value)
    ? "bad"
    : ["ALLOWED", "COMPLETED", "CREATED", "APPROVED"].includes(value)
      ? "ok"
      : "mid";
  return tag(escapeHtml(chineseLabel(value)), type);
}

function auditRowsFromRecords(records) {
  return records.map((record) => [
    `<span class="audit-cell-text" title="${escapeHtml(record.eventType)}">${escapeHtml(record.eventType)}</span>`,
    escapeHtml(fmtDateTime(record.timestamp)),
    `<span class="audit-cell-text" title="${escapeHtml(record.actor)}">${escapeHtml(record.actor)}</span>`,
    `<span class="audit-cell-text audit-task-id" title="${escapeHtml(record.taskId)}">${escapeHtml(record.taskId)}</span>`,
    auditResultTag(record.result),
    `<span class="actions-cell"><span data-action="audit-detail" data-id="${escapeHtml(record.auditId)}">详情</span></span>`,
  ]);
}

function auditDetailRows(record) {
  if (!record) return [];
  return [
    { k: "事件类型", v: escapeHtml(record.eventType) },
    { k: "时间", v: escapeHtml(fmtDateTime(record.timestamp)) },
    { k: "操作用户或主体", v: escapeHtml(record.actor) },
    { k: "主体角色", v: escapeHtml(record.actorRole) },
    { k: "所属园区", v: escapeHtml(record.partyId) },
    { k: "任务 ID", v: escapeHtml(record.taskId) },
    { k: "授权 ID", v: escapeHtml(record.grantId) },
    { k: "申请 ID", v: escapeHtml(record.requestId) },
    { k: "结果或状态", v: auditResultTag(record.result) },
    { k: "简短说明", v: escapeHtml(record.description) },
  ];
}

function taskAuditReport(taskAudit, securityRecord) {
  if (!taskAudit) {
    return `<div class="api-state">所选记录未关联可用的任务和预算审计数据</div>`;
  }
  const parties = taskAudit.parties.length ? taskAudit.parties.join("、") : "—";
  return `<div class="report-card audit-report-card">
    <div class="paper"></div>
    <table class="kv">
      <tr><th>任务概述</th><td>${escapeHtml(taskAudit.taskId)} · ${escapeHtml(queryTypeLabel(taskAudit.queryType))}</td></tr>
      <tr><th>参与数据方</th><td>${escapeHtml(parties)}</td></tr>
      <tr><th>隐私预算使用情况</th><td>${escapeHtml(fmtEpsilon(taskAudit.budgetBefore))} → ${escapeHtml(fmtEpsilon(taskAudit.budgetAfter))}</td></tr>
      <tr><th>查询状态</th><td>${taskStatusTag(taskAudit.status)}</td></tr>
      <tr><th>计算模式</th><td>${escapeHtml(chineseLabel(taskAudit.calculationMode))}</td></tr>
      <tr><th>关联授权</th><td>${escapeHtml(securityRecord?.grantId || "—")}</td></tr>
      <tr><th>风险结论</th><td>未记录（当前后端未提供风险评估字段）</td></tr>
      <tr><th>审计说明</th><td>${escapeHtml(securityRecord?.description || "未记录")}</td></tr>
    </table>
    <button class="primary wide" disabled aria-disabled="true">${icon("report")} PDF 报告功能开发中</button>
  </div>`;
}

function auditPage() {
  if (USE_MOCK) {
    return `<main class="content audit-page"><h2>审计追溯与报告中心</h2><div class="api-state">离线开发模式不提供审计记录，请连接后端审计接口</div></main>`;
  }
  const view = state.audit;
  if (view.error) {
    return `<main class="content audit-page">
      <h2>审计追溯与报告中心</h2>
      <div class="api-state error">审计记录加载失败：${escapeHtml(formatApiError(view.error))}<br>
        <button class="primary" data-action="retry-audit" style="margin-top:12px">重新加载</button>
      </div>
    </main>`;
  }
  if (!view.records || !view.taskAudits) {
    return `<main class="content audit-page"><h2>审计追溯与报告中心</h2><div class="api-state">正在加载审计记录…</div></main>`;
  }
  const records = view.filtered || view.records;
  const selected = view.records.find((record) => record.auditId === view.selectedAuditId) || records[0] || null;
  const selectedTask = selected
    ? view.taskAudits.find((taskAudit) => taskAudit.taskId === selected.taskId) || null
    : null;
  const allowedCount = view.records.filter((record) => ["ALLOWED", "APPROVED", "CREATED", "COMPLETED"].includes(record.result)).length;
  const deniedCount = view.records.filter((record) => ["DENIED", "REJECTED", "FAILED"].includes(record.result)).length;
  const chainBlocks = records.slice(0, 6).map((record, index) =>
    `<div class="audit-timeline-item ${index === 0 ? "current" : ""}"><span class="audit-timeline-dot" aria-hidden="true"></span><div><b>#${escapeHtml(record.auditId)} · ${escapeHtml(record.eventType)}</b><small>${escapeHtml(fmtDateTime(record.timestamp))}</small></div></div>`
  ).join("");

  return `<main class="content audit-page">
    <h2>审计追溯与报告中心</h2>
    ${panel("", `
      <div class="filters audit-filters">
        <label><span>审计关键词</span><input id="audit-task-input" placeholder="任务、授权、申请、事件或主体"></label>
        <button class="primary" data-action="audit-search">搜索</button>
        <button disabled aria-disabled="true">${icon("report")} 导出功能开发中</button>
      </div>
    `)}
    <div class="audit-primary-grid">
      ${panel("查询和预算审计记录", records.length
        ? `<div class="audit-table-scroll">${table(["事件类型", "时间", "操作主体", "任务 ID", "结果", "操作"], auditRowsFromRecords(records), "audit-records-table")}</div><div class="panel-foot">共 ${records.length} 条安全审计记录</div>`
        : `<div class="api-state">暂无查询和预算审计记录</div>`)}
      ${panel("审计记录摘要 ⓘ", `
        <div class="audit-kpis">
          ${statCard({ label: "审计记录数", value: records.length, sub: "当前查询范围", type: "blue", ic: "audit" })}
          ${statCard({ label: "允许或完成", value: allowedCount, sub: "真实 decision/status", type: "green", ic: "shield" })}
          ${statCard({ label: "拒绝或失败", value: deniedCount, sub: "真实 decision/status", type: "purple", ic: "data" })}
        </div>
        <div class="notice" style="margin-bottom:12px">ⓘ 以下内容来自本地安全审计表，不声称已接入区块链存证。</div>
        <div class="audit-timeline">${chainBlocks || `<div class="api-state">暂无记录</div>`}</div>
      `)}
    </div>
    <div class="audit-detail-grid">
      ${panel(`任务追溯详情　${selected ? auditResultTag(selected.result) : ""}`,
        selected ? kvRowsHtml(auditDetailRows(selected)) : `<div class="api-state">暂无查询和预算审计记录</div>`)}
      ${panel("任务与预算审计报告", taskAuditReport(selectedTask, selected))}
    </div>
  </main>`;
}

async function mountAudit() {
  if (state.audit.loading || state.audit.loaded) return;
  state.audit.loading = true;
  try {
    const [securityRecords, taskAudits] = await Promise.all([
      listSecurityAudit(),
      listAuditEvents(100),
    ]);
    state.audit.records = Array.isArray(securityRecords)
      ? securityRecords.map(normalizeAuditRecord)
      : [];
    state.audit.taskAudits = Array.isArray(taskAudits)
      ? taskAudits.map(normalizeTaskAudit)
      : [];
    state.audit.filtered = null;
    const linkedRecord = state.audit.records.find((record) =>
      state.audit.taskAudits.some((taskAudit) => taskAudit.taskId === record.taskId)
    );
    state.audit.selectedAuditId = linkedRecord?.auditId || state.audit.records[0]?.auditId || null;
    state.audit.error = null;
    state.audit.loaded = true;
  } catch (error) {
    state.audit.error = formatApiError(error, "网络错误");
  } finally {
    state.audit.loading = false;
  }
  render();
}
function reportPage() {
  if (USE_MOCK) {
    return accessPage("报表中心", "", `<div class="api-state">离线开发模式不生成业务报表</div>`);
  }
  const report = state.access.analystReport;
  if (!report) {
    return accessPage("报表中心", "", `<div class="api-state">${state.access.loading ? "正在加载真实报表…" : "暂无报表数据"}</div>`);
  }
  const queryRows = Object.entries(report.query_type_counts).map(([queryType, count]) => [
    escapeHtml(queryTypeLabel(queryType)), fmtNumber(count, 0),
  ]);
  const partyRows = Object.entries(report.party_participation_counts).map(([party, count]) => [
    escapeHtml(party), fmtNumber(count, 0),
  ]);
  const taskRows = report.recent_tasks.map((task) => [
    escapeHtml(task.task_id),
    escapeHtml(queryTypeLabel(task.query_type)),
    escapeHtml((task.parties || []).join(" / ") || "—"),
    taskStatusTag(task.status),
    fmtEpsilon(task.epsilon),
    fmtDateTime(task.created_at),
    fmtDateTime(task.completed_at),
    escapeHtml(task.grant_id || "—"),
    task.query_type === "TIME_SERIES" ? fmtNumber(task.bucket_count, 0) : "—",
  ]);
  const usageRows = report.recent_grant_usage.map((usage) => [
    escapeHtml(usage.task_id),
    escapeHtml(usage.grant_id),
    fmtEpsilon(usage.epsilon),
    accessStatusTag(usage.status),
    fmtEpsilon(usage.remaining_before),
    fmtEpsilon(usage.remaining_after),
    fmtDateTime(usage.updated_at),
  ]);
  const methodRows = [
    ["无隐私聚合", "直接聚合", "依赖可信执行方", "不增加隐私扰动", "方法学说明"],
    ["本地差分隐私", "数据方本地加噪", "不依赖中心查看原值", "本地扰动", "方法学说明"],
    ["中心差分隐私", "聚合后统一加噪", "依赖可信聚合方", "中心扰动", "方法学说明"],
    ["分布式差分隐私", "多方共同贡献噪声", "结合多方安全计算", "分布式扰动", "当前系统采用的设计"],
  ];

  return accessPage(
    "报表中心",
    "",
    `<div class="stat-grid">
      ${statCard({ label: "总任务数", value: fmtNumber(report.total_tasks, 0), sub: "当前用户", type: "blue", ic: "report" })}
      ${statCard({ label: "COMPLETED", value: fmtNumber(report.completed_tasks, 0), sub: "真实任务状态", type: "green", ic: "check" })}
      ${statCard({ label: "FAILED", value: fmtNumber(report.failed_tasks, 0), sub: "真实任务状态", type: "purple", ic: "alert" })}
      ${statCard({ label: "任务成功率", value: `${fmtNumber(report.success_rate, 2)}%`, sub: "COMPLETED / 总任务数", type: "green", ic: "audit" })}
    </div>
    <div class="stat-grid">
      ${statCard({ label: "平均任务耗时", value: fmtDuration(report.average_task_duration_ms), sub: "created_at → completed_at", type: "blue", ic: "compute" })}
      ${statCard({ label: "累计 epsilon 消耗", value: fmtEpsilon(report.epsilon_consumed), sub: "已消费授权记录", type: "orange", ic: "shield" })}
      ${statCard({ label: "剩余隐私预算", value: fmtEpsilon(report.remaining_privacy_budget), sub: "各 Grant 剩余余额合计", type: "green", ic: "data" })}
      ${statCard({ label: "TIME_SERIES 桶数", value: fmtNumber(report.time_series_bucket_count, 0), sub: "真实 task_audits.bucket_count", type: "purple", ic: "report" })}
    </div>
    <div class="grid-half">
      ${panel("各查询类型任务数量", queryRows.length ? table(["查询类型", "任务数"], queryRows) : `<div class="api-state">暂无数据</div>`)}
      ${panel("各园区参与次数", partyRows.length ? table(["园区", "参与次数"], partyRows) : `<div class="api-state">暂无数据</div>`)}
    </div>
    ${panel("最近真实任务", taskRows.length ? table(["task_id", "query_type", "parties", "status", "epsilon", "created_at", "completed_at", "grant_id", "bucket_count"], taskRows) : `<div class="api-state">暂无真实任务</div>`) }
    ${panel("最近真实授权使用记录", usageRows.length ? table(["task_id", "grant_id", "epsilon", "状态", "使用前剩余", "使用后剩余", "更新时间"], usageRows) : `<div class="api-state">暂无授权使用记录</div>`) }
    ${panel("报告导出", `<button disabled aria-disabled="true">PDF 下载当前版本未开放</button>`)}
    ${panel("隐私保护方法原理对比", `${table(["方法", "核心机制", "信任假设", "隐私处理", "说明"], methodRows)}<div class="notice" style="margin-top:12px">该表为方法学说明，不代表当前在线实验测量结果。隐私效用及攻击实验指标由离线实验脚本生成，不属于在线业务统计。</div>`)} `,
  );
}

function performanceMetric(value, unit = "", digits = 0) {
  return value === null || value === undefined || !Number.isFinite(Number(value))
    ? `<strong>--</strong>${unit ? `<em>${unit}</em>` : ""}`
    : `<strong>${performanceFixedNumber(value, digits)}</strong>${unit ? `<em>${unit}</em>` : ""}`;
}

function performanceFixedNumber(value, digits = 2) {
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function displayedPerformancePhases(phases) {
  return Array.isArray(phases)
    ? phases.filter((phase) => phase?.key !== "local_statistics")
    : [];
}

function displayedPhaseTotal(phases) {
  const values = displayedPerformancePhases(phases)
    .map((phase) => Number(phase?.duration_ms ?? phase?.durationMs))
    .filter(Number.isFinite);
  return values.length ? values.reduce((total, value) => total + value, 0) : null;
}

function performanceStatusLabel(status) {
  if (status === "running") return { text: "测试中", cls: "run" };
  if (status === "completed") return { text: "已完成", cls: "ok" };
  if (status === "failed") return { text: "失败", cls: "bad" };
  return { text: "待测试", cls: "mid" };
}

function performanceControl() {
  const view = state.performance;
  const config = view.config;
  const segment = (name, values, selected, disabled = false) => `<div class="performance-segment" role="group">${values.map(([value, label]) => `
    <label class="${value === selected ? "selected" : ""}"><input type="radio" name="${name}" value="${value}" ${value === selected ? "checked" : ""} ${disabled ? "disabled" : ""}><span>${label}</span></label>`).join("")}</div>`;
  const intervalControl = config.queryType === "TIME_SERIES"
    ? segment("performance-interval", [["30m", "30m"], ["1h", "1h"], ["1d", "1d"]], config.interval)
    : `<div class="performance-not-applicable" aria-disabled="true">仅 TIME_SERIES 可设置</div>`;
  return `<section class="card performance-controls" aria-label="性能测试参数">
    <label class="performance-field dataset-field"><span>基准数据</span><select id="performance-benchmark"><option value="ENERGY_BENCHMARK_V1" selected>标准三方能源数据基准集</option></select><small>合成能源负荷数据</small></label>
    <div class="performance-field"><span>查询类型</span>${segment("performance-query-type", [["SUM", "SUM"], ["COUNT", "COUNT"], ["AVERAGE", "AVERAGE"], ["TIME_SERIES", "TIME_SERIES"]], config.queryType)}</div>
    <div class="performance-field"><span>时间粒度</span>${intervalControl}</div>
    <div class="performance-field parties-field"><span>参与方 <b>${config.parties.length}</b></span><div class="performance-party-list">${PARTY_IDS.map((party) =>
      `<label class="${config.parties.includes(party) ? "selected" : ""}" title="Benchmark Party，不代表业务数据授权"><input type="checkbox" name="performance-party" value="${party}" ${config.parties.includes(party) ? "checked" : ""}><span>${party}</span></label>`
    ).join("")}</div></div>
    <div class="performance-field mode-field"><span>隐私计算模式</span>${segment("performance-mode", [["PLAIN", "PLAIN"], ["SECRET_SHARE", "SECRET_SHARE"], ["DISTRIBUTED_DP", "DISTRIBUTED_DP"]], config.mode)}</div>
    <label class="performance-field epsilon-field"><span>ε 预算</span><input id="performance-epsilon" type="number" min="0.1" max="5" step="0.1" value="${escapeHtml(config.epsilon)}" ${config.mode === "DISTRIBUTED_DP" ? "" : "disabled"}><small>基准测试预算独立于业务隐私预算</small></label>
    <div class="performance-actions"><button class="primary" type="button" data-action="start-performance" ${view.loading ? "disabled" : ""}>${icon("performance")} ${view.loading ? "准备中…" : "开始测试"}</button><button type="button" data-action="export-performance" disabled>导出结果</button></div>
  </section>`;
}

function performanceKpis() {
  const view = state.performance;
  const nodeCount = view.summary.nodeCount;
  const status = performanceStatusLabel(view.status);
  const items = [
    ["clock", "blue", "阶段总耗时", performanceMetric(view.summary.totalDurationMs, "ms", 2), "下方阶段耗时合计"],
    ["compute", "green", "通信总量", performanceMetric(view.summary.communicationBytes === null || view.summary.communicationBytes === undefined ? null : Number(view.summary.communicationBytes) / 1024, "KB", 2), "跨节点通信字节"],
    ["user", "purple", "参与节点", `<strong>${nodeCount ? `${nodeCount.participating} / ${nodeCount.total}` : "-- / 6"}</strong>`, "本次涉及 / 核心总数"],
    ["report", "cyan", "平均响应", performanceMetric(view.summary.averageLatencyMs, "ms"), "平均节点响应"],
    ["check", "green", "测试状态", `<strong class="status-${status.cls}">${status.text}</strong>`, view.status === "running" ? "正在执行真实协议" : view.status === "completed" ? "指标已更新" : view.status === "failed" ? "请查看错误提示" : "尚未执行"],
  ];
  return `<div class="performance-kpis">${items.map(([ic, color, label, value, sub]) => `<article class="card performance-kpi"><span class="round ${color}">${icon(ic)}</span><div><p>${label}</p><div class="performance-kpi-value">${value}</div><small>${sub}</small></div></article>`).join("")}</div>`;
}

function performancePhases() {
  const hasDuration = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
  const hasData = state.performance.phases.some((phase) => hasDuration(phase.durationMs));
  const max = Math.max(1, ...state.performance.phases.map((phase) => Number(phase.durationMs) || 0));
  return `<div class="performance-phase-chart ${hasData ? "" : "empty"}">${state.performance.phases.map((phase) => {
    const valid = hasDuration(phase.durationMs);
    const width = valid ? Math.max(2, (Number(phase.durationMs) / max) * 100) : 0;
    return `<div class="performance-phase-row"><span>${phase.label}</span><div class="performance-bar-track"><i style="width:${width}%"></i></div><b>${valid ? `${performanceFixedNumber(phase.durationMs, 2)} ms` : "--"}</b></div>`;
  }).join("")}<div class="performance-empty-caption">${hasData ? "" : "暂无性能测试数据"}</div></div>`;
}

function performanceLinks() {
  const links = state.performance.links;
  if (!links.length) return `<div class="performance-communication-empty">${icon("compute")}<b>暂无通信数据</b><span>完成性能测试后展示真实跨节点通信链路</span></div>`;
  const max = Math.max(1, ...links.map((link) => Number(link.totalBytes) || 0));
  return `<div class="performance-link-list">${links.map((link) => `<div class="performance-link-row"><span>${escapeHtml(link.source)} → ${escapeHtml(link.target)}</span><div><i style="width:${Math.max(2, Number(link.totalBytes || 0) / max * 100)}%"></i></div><b>${performanceFixedNumber(Number(link.totalBytes) / 1024, 2)} KB</b></div>`).join("")}</div>`;
}

function performanceHistory() {
  const view = state.performance;
  if (view.historyState === "loading") return `<div class="api-state">正在加载性能测试记录…</div>`;
  if (view.historyState === "error") return `<div class="api-state error">性能测试记录加载失败</div>`;
  if (!view.history.length) return `<div class="performance-table-scroll">${table(["测试 ID", "参与方", "查询类型", "计算模式", "阶段总耗时", "通信量", "ε", "执行时间", "状态"], [])}</div><div class="api-state performance-history-empty">暂无性能测试记录</div><div class="performance-pagination"><span>共 0 条</span><button disabled>‹</button><button disabled>›</button></div>`;
  return `<div class="performance-table-scroll">${table(["测试 ID", "参与方", "查询类型", "计算模式", "阶段总耗时", "通信量", "ε", "执行时间", "状态"], view.history.map((item) => [escapeHtml(item.testId), escapeHtml((item.parties || []).join(" / ")), escapeHtml(item.queryType), escapeHtml(item.mode), item.totalDurationMs == null ? "—" : `${performanceFixedNumber(item.totalDurationMs, 2)} ms`, `${performanceFixedNumber(item.communicationBytes / 1024, 2)} KB`, item.epsilon == null ? "—" : fmtEpsilon(item.epsilon), fmtDateTime(item.executedAt), accessStatusTag(item.status)]))}</div>`;
}

function applyPerformanceResult(result) {
  const view = state.performance;
  view.testId = result?.id || null;
  view.status = String(result?.status || "FAILED").toLowerCase();
  const summary = result?.summary || {};
  const phases = displayedPerformancePhases(result?.phases).map((phase) => ({
    key: phase.key, label: phase.label, durationMs: phase.duration_ms ?? null,
  }));
  view.summary = {
    totalDurationMs: displayedPhaseTotal(phases),
    communicationBytes: summary.communication_bytes ?? null,
    nodeCount: summary.participant_nodes == null ? null : {
      participating: summary.participant_nodes,
      total: summary.total_nodes ?? 6,
    },
    averageLatencyMs: summary.average_response_ms ?? null,
  };
  view.phases = phases;
  view.links = Array.isArray(result?.links) ? result.links.map((link) => ({
    source: link.source_node, target: link.target_node, operation: link.operation,
    requestBytes: link.request_bytes, responseBytes: link.response_bytes,
    totalBytes: link.total_bytes, durationMs: link.duration_ms,
  })) : [];
  view.error = result?.error || null;
}

function performanceHistoryItem(item) {
  return {
    testId: item.id, parties: item.parties || [], queryType: item.query_type,
    mode: item.mode, totalDurationMs: displayedPhaseTotal(item.phases),
    communicationBytes: item.summary?.communication_bytes,
    epsilon: item.epsilon, executedAt: item.created_at, status: item.status,
  };
}

function performanceNodes() {
  return `<div class="performance-node-grid">${state.performance.nodes.map((node) => `<article class="performance-node"><header><span class="round ${node.id.startsWith("party") ? "green" : node.id.startsWith("compute") ? "purple" : "blue"}">${icon(node.id.startsWith("party") ? "data" : "compute")}</span><b>${node.id}</b><em class="${node.status === "ONLINE" ? "online" : node.status === "OFFLINE" ? "offline" : "unknown"}"><i></i>${node.status === "ONLINE" ? "在线" : node.status === "OFFLINE" ? "离线" : "状态未知"}</em></header><dl><div><dt>CPU</dt><dd>--</dd></div><div><dt>内存</dt><dd>--</dd></div><div><dt>延迟</dt><dd>${node.latencyMs === null || node.latencyMs === undefined ? "--" : `${fmtNumber(node.latencyMs, 1)} ms`}</dd></div><div><dt>上传</dt><dd>--</dd></div><div><dt>下载</dt><dd>--</dd></div></dl></article>`).join("")}</div>`;
}

function performancePage() {
  const view = state.performance;
  return `<main class="content performance-page">
    <div class="title-row"><h2>性能测试</h2></div>
    ${view.error ? `<div class="performance-inline-status">${escapeHtml(formatApiError(view.error, "性能测试失败，请稍后重试"))}</div>` : ""}
    ${performanceControl()}
    ${performanceKpis()}
    <div class="performance-layout">
      <div class="performance-column">
        ${panel("阶段耗时拆解 ⓘ", performancePhases(), "", "performance-phase-panel")}
        ${panel("最近测试记录", performanceHistory(), "", "performance-history-panel")}
      </div>
      <div class="performance-column">
        ${panel("通信开销分布 ⓘ", `${performanceLinks()}<div class="notice performance-info">通信开销统计口径：统计 Benchmark 执行期间跨节点业务请求与响应的 UTF-8 字节数，不含 HTTP/TCP/IP 头与浏览器静态资源流量。</div>`, "", "performance-communication-panel")}
        ${panel("节点资源与网络 ⓘ", performanceNodes(), "", "performance-node-panel")}
      </div>
    </div>
  </main>`;
}

async function mountPerformance() {
  const view = state.performance;
  if (view.loading || view.loaded) return;
  view.loading = true;
  view.historyState = "loading";
  const result = await Promise.allSettled([getSystemHealth(), performanceApi.listTests({ limit: 10, offset: 0 })]);
  if (result[0].status === "fulfilled") {
    const services = Array.isArray(result[0].value?.services) ? result[0].value.services : [];
    const aliases = { control: ["control", "control-plane"], "party-a": ["party-a"], "party-b": ["party-b"], "party-c": ["party-c"], "compute-s1": ["compute-s1"], "compute-s2": ["compute-s2"] };
    view.nodes = view.nodes.map((node) => {
      const service = services.find((item) => aliases[node.id].includes(item.service_id));
      return { ...node, status: service ? (service.online ? "ONLINE" : "OFFLINE") : null, latencyMs: service?.latency_ms ?? null };
    });
  }
  if (result[1].status === "fulfilled") {
    view.history = (result[1].value?.items || []).map(performanceHistoryItem);
    view.historyState = view.history.length ? "ready" : "empty";
  } else {
    view.historyState = "error";
  }
  view.loaded = true;
  view.loading = false;
  if (state.page === "performance") render();
}

async function startPerformanceTest() {
  const view = state.performance;
  const epsilon = Number(view.config.epsilon);
  if (!view.config.parties.length) return toast("请至少选择一个 Benchmark Party", "error");
  if (view.config.mode === "DISTRIBUTED_DP" && (!Number.isFinite(epsilon) || epsilon <= 0 || epsilon > 5)) return toast("ε 预算必须大于 0 且不超过 5", "error");
  view.loading = true;
  view.status = "running";
  view.error = null;
  render();
  try {
    const result = await performanceApi.startTest({
      benchmark_id: view.config.benchmarkId,
      parties: [...view.config.parties],
      query_type: view.config.queryType,
      mode: view.config.mode,
      epsilon: view.config.mode === "DISTRIBUTED_DP" ? epsilon : null,
      interval: view.config.queryType === "TIME_SERIES" ? view.config.interval : null,
    });
    applyPerformanceResult(result);
    view.history = [performanceHistoryItem(result), ...view.history.filter((item) => item.testId !== result.id)].slice(0, 10);
    view.historyState = "ready";
    toast(result.status === "COMPLETED" ? "Benchmark 性能测试已完成" : (result.error || "Benchmark 性能测试失败"), result.status === "COMPLETED" ? "ok" : "error");
  } catch (error) {
    view.status = "failed";
    view.error = error;
    toast(error, "error");
  } finally {
    view.loading = false;
    render();
  }
}

function settingsPage() {
  if (USE_MOCK) {
    return accessPage("系统设置", "", `<div class="api-state">离线开发模式不提供系统运行状态</div>`);
  }
  const overview = state.access.adminOverview;
  if (!overview) {
    return accessPage("系统设置", "", `<div class="api-state">${state.access.loading ? "正在加载系统运行状态…" : "暂无系统运行状态"}</div>`);
  }

  const nodes = [overview.frontend_gateway, ...(overview.party_nodes || []), ...(overview.compute_nodes || [])].filter(Boolean);
  const nodeRows = nodes.map((node) => [
    escapeHtml(node.name),
    escapeHtml(node.service_id),
    node.online ? tag("在线", "ok") : tag("离线", "bad"),
    `${fmtNumber(node.latency_ms, 2)} ms`,
  ]);
  const dependencyRows = [
    ["控制数据库", escapeHtml(overview.database.type), overview.database.connected ? tag("已连接", "ok") : tag("连接失败", "bad"), "仅控制平面元数据"],
    ["数据资产存储", "Parquet", tag("只读挂载", "ok"), `${overview.asset_storage.party_count} 个数据方`],
    ["前端网关", "Nginx", overview.frontend_gateway.online ? tag("在线", "ok") : tag("离线", "bad"), `${fmtNumber(overview.frontend_gateway.latency_ms, 2)} ms`],
    ["Agent 模型服务", "外部模型 API", overview.agent_model_configured ? tag("已配置", "ok") : tag("未配置", "wait"), "仅返回 configured 状态"],
  ];
  const security = overview.security_baseline;
  const enabledTag = (value, on = "已启用", off = "未启用") => value ? tag(on, "ok") : tag(off, "wait");
  const securityGroups = [
    {
      title: "访问控制",
      rows: [
        { k: "授权强制校验", v: enabledTag(security.authorization_enforcement_enabled) },
        { k: "原始数据下载", v: security.raw_download_disabled ? tag("已禁用", "ok") : tag("未禁用", "bad") },
        { k: "双因素认证", v: enabledTag(security.mfa_enabled) },
        { k: "IP 白名单", v: enabledTag(security.ip_allowlist_enabled) },
      ],
    },
    {
      title: "会话安全",
      rows: [
        { k: "Cookie HttpOnly", v: enabledTag(security.session_cookie_http_only) },
        { k: "Cookie SameSite", v: escapeHtml(security.cookie_samesite || "—") },
        { k: "会话 TTL", v: `${fmtNumber(security.session_ttl_seconds, 0)} 秒` },
        { k: "Session token", v: security.session_token_hash_storage ? tag("哈希存储", "ok") : tag("未确认", "bad") },
      ],
    },
    {
      title: "平台安全",
      rows: [
        { k: "密码存储", v: security.password_hash_storage ? tag("哈希存储", "ok") : tag("未确认", "bad") },
        { k: "安全审计", v: enabledTag(security.audit_enabled) },
        { k: "计算模式", v: escapeHtml(security.calculation_mode || "—") },
        { k: "账号初始化策略", v: enabledTag(security.demo_identity_mode_enabled) },
        { k: "证书管理", v: tag("由部署环境配置", "mid") },
        { k: "HTTPS 强制", v: enabledTag(security.https_forced) },
      ],
    },
  ];
  const securityGroupsHtml = securityGroups.map((group) => `
    <section class="settings-security-group">
      <h4>${group.title}</h4>
      <div class="kv-table">${group.rows.map((row) => `<div class="kv-row"><div class="k">${row.k}</div><div class="v">${row.v}</div></div>`).join("")}</div>
    </section>`).join("");
  const events = (overview.system_events || []).slice(0, 6);
  const eventItems = events.map((event) => `
    <div class="settings-event-item">
      <div><b>${escapeHtml(event.event_type || "未知事件")}</b>${event.decision ? accessStatusTag(event.decision) : ""}</div>
      <p>${escapeHtml(event.actor_user_id || "—")} · ${escapeHtml(event.actor_role || "—")}</p>
      <time>${fmtDateTime(event.timestamp)}</time>
    </div>`).join("");
  const onlineNodeCount = nodes.filter((node) => node.online).length;
  const runtimeSummaryRows = [
    { k: "状态检查时间", v: fmtDateTime(overview.checked_at) },
    { k: "控制数据库", v: overview.database.connected ? tag("已连接", "ok") : tag("连接失败", "bad") },
    { k: "在线节点", v: `${onlineNodeCount} / ${nodes.length}` },
    { k: "数据方", v: `${fmtNumber(overview.asset_storage.party_count, 0)} 个` },
    { k: "Agent 模型服务", v: overview.agent_model_configured ? tag("已配置", "ok") : tag("未配置", "wait") },
  ];

  return accessPage(
    "系统设置",
    "",
    `<div class="settings-layout">
      <div class="settings-main-column">
        ${panel("当前系统依赖与运行状态", `
          <div class="settings-table-scroll">${table(["组件", "类型", "状态", "安全摘要"], dependencyRows)}</div>
          <div class="notice settings-runtime-note">控制数据库仅保存用户、会话、申请、审批、Grant、预算、任务和审计；园区能源数据保存在只读 Parquet 中。</div>
          <div class="settings-table-scroll settings-node-table">${table(["运行节点", "服务标识", "状态", "延迟"], nodeRows)}</div>
        `, "", "settings-runtime-panel")}
        ${panel("当前生效安全基线", `<div class="settings-security-groups">${securityGroupsHtml}</div><div class="notice">以上状态只读，未实现能力不会显示为已启用。</div>`, "", "settings-security-panel")}
      </div>
      <aside class="settings-side-column">
        ${panel("运行状态摘要", `<div class="kv-table settings-summary">${runtimeSummaryRows.map((row) => `<div class="kv-row"><div class="k">${row.k}</div><div class="v">${row.v}</div></div>`).join("")}</div>`)}
        ${panel("最近安全审计", eventItems ? `<div class="settings-event-list">${eventItems}</div>` : `<div class="api-state">暂无真实系统事件</div>`)}
        ${panel("系统维护记录", (overview.maintenance_records || []).length ? table(["记录"], overview.maintenance_records.map((item) => [escapeHtml(item)])) : `<div class="api-state settings-empty-state">暂无系统维护记录</div>`)}
      </aside>
    </div>`,
  );
}

function accessStatusTag(status) {
  const cls = {
    ACTIVE: "ok", APPROVED: "ok", ENABLED: "ok", ONLINE: "ok",
    VALID: "ok",
    EXPIRED: "mid", CONDITIONALLY_APPROVED: "mid", PARTIALLY_APPROVED: "mid",
    REVOKED: "bad", REJECTED: "bad", OFFLINE: "bad", INVALID: "bad", FAILED: "bad",
    EXHAUSTED: "wait", DISABLED: "wait", UPLOADED: "wait", VALIDATING: "wait", ACTIVATING: "wait", ARCHIVED: "wait",
  }[status] || "wait";
  return tag(status || "--", cls);
}

function accessPage(title, subtitle, body, actions = "") {
  const pageSubtitle = ["new-request", "my-grants", "report"].includes(state.page) ? "" : subtitle;
  const pageBody = state.page === "new-request" ? body.replace(/<div class="notice">[\s\S]*?<\/div>/, "") : body;
  const loadKey = ACCESS_PAGE_LOAD_KEYS[state.page];
  const loadError = loadKey ? state.access.loadErrors[loadKey] : null;
  const loadErrorHtml = loadError
    ? state.page === "approval-history"
      ? `<div class="api-state error">审批历史加载失败，请稍后重试</div>`
      : errorBox(loadError)
    : "";
  return `<main class="content">
    <div class="title-row"><h2>${title}${pageSubtitle ? `<small>${pageSubtitle}</small>` : ""}</h2>${actions ? `<div class="actions">${actions}</div>` : ""}</div>
    ${loadErrorHtml}
    ${state.access.error ? errorBox(state.access.error) : ""}
    ${pageBody}
  </main>`;
}

const accessLoaders = {
  assets: () => listCatalogAssets(),
  ownerAssets: () => listOwnerCatalogAssets(),
  requests: () => listMyAccessRequests(),
  approvals: () => listPendingApprovals(),
  approvalHistory: () => listApprovalHistory(),
  grants: () => listMyGrants(),
  ownerGrants: () => listOwnerGrants(),
  allRequests: () => listAllAccessRequests(),
  allGrants: () => listAllGrants(),
  users: () => listAdminUsers(),
  securityAudit: () => listSecurityAudit(),
  adminOverview: () => getAdminSystemOverview(),
  analystReport: () => getMyAnalystReport(20),
  policySummary: () => getSystemPolicySummary(),
  ownerData: async () => {
    const [assets, imports, active, config] = await Promise.all([
      listOwnerCatalogAssets(),
      listMyDataImports(),
      getActiveDataVersion(),
      getDataImportConfig(),
    ]);
    return { assets, imports, active, config };
  },
};

async function ensureAccessData(key, force = false) {
  if (!accessLoaders[key] || state.access.loadingKeys[key] || (!force && state.access.loaded[key])) return;
  state.access.loadingKeys[key] = true;
  state.access.loading = true;
  delete state.access.loadErrors[key];
  try {
    state.access[key] = await accessLoaders[key]();
    state.access.loaded[key] = true;
  } catch (error) {
    state.access.loadErrors[key] = error;
    // Mark the attempted load as settled so an API error cannot trigger a
    // synchronous render → loader → render loop. A later explicit refresh
    // can call ensureAccessData(key, true).
    state.access.loaded[key] = true;
  } finally {
    delete state.access.loadingKeys[key];
    state.access.loading = Object.keys(state.access.loadingKeys).length > 0;
    render();
  }
}

function catalogPage() {
  const safe = (value) => value === null || value === undefined || value === "" ? "—" : escapeHtml(value);
  const cards = state.access.assets.map((asset) => {
    const queryTypes = Array.isArray(asset.supported_query_types) ? asset.supported_query_types : [];
    return `<article class="card asset-card catalog-asset-card">
    <div class="asset-head"><div class="round blue">${icon("db")}</div><div class="asset-title"><h3>${safe(asset.name)}</h3><span>${safe(asset.asset_id)}</span></div>${accessStatusTag(asset.status)}</div>
    <div class="asset-meta">
      <span><b>提供方</b>${safe(asset.owner_party)}</span>
      <span><b>时间范围</b>${safe(fmtDate(asset.time_start))} — ${safe(fmtDate(asset.time_end))}</span>
      <span><b>数据粒度</b>${safe(asset.source_granularity)}</span>
      <span class="catalog-query-row"><b>支持查询</b><span class="asset-query-tags">${queryTypes.length ? queryTypes.map((type) => `<span class="asset-query-tag">${safe(type)}</span>`).join("") : "—"}</span></span>
    </div>
    <div class="catalog-card-actions"><button data-action="view-catalog-asset" data-id="${safe(asset.asset_id)}">查看详情</button><button class="primary" data-action="apply-asset" data-party="${safe(asset.owner_party)}">申请使用</button></div>
  </article>`;
  }).join("");
  return accessPage("数据目录", "", `<div class="asset-grid catalog-asset-grid">${cards || `<div class="api-state">${state.access.loading ? "正在加载数据目录..." : "暂无数据资产"}</div>`}</div>`);
}

function approvalProgress(request) {
  const approvals = request.approvals || [];
  return `<div class="approval-progress">${request.requested_parties.map((party) => {
    const item = approvals.find((approval) => approval.party_id === party);
    return `<span>${escapeHtml(party)} ${accessStatusTag(item?.decision || "PENDING")}</span>`;
  }).join("")}</div>`;
}

function myRequestsPage() {
  const rows = state.access.requests.map((request) => [
    escapeHtml(request.request_id),
    `<span data-i18n-ignore>${escapeHtml(request.purpose)}</span>`,
    request.requested_parties.join(" / "),
    accessStatusTag(request.status),
    approvalProgress(request),
    `<div class="actions-cell">${request.status === "DRAFT" ? `<span data-action="submit-access-request" data-id="${request.request_id}">提交</span>` : ""}${["DRAFT", "PENDING", "PARTIALLY_APPROVED"].includes(request.status) ? `<span data-action="withdraw-access-request" data-id="${request.request_id}">撤销</span>` : ""}</div>`,
  ]);
  return accessPage("我的申请", "", panel("数据使用申请", rows.length ? table(["申请编号", "用途", "园区", "状态", "审批进度", "操作"], rows) : `<div class="api-state">${state.access.loading ? "正在加载申请..." : "暂无申请"}</div>`), `<button class="primary" data-page="new-request">新建申请</button>`);
}

function newRequestPage() {
  const selected = state.access.prefillParty || "ORG_A";
  const expires = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 16);
  const body = panel("申请范围", `<div class="form2 access-form">
    <label style="grid-column:1/-1"><span class="k">使用目的</span><textarea id="ar-purpose" maxlength="500" placeholder="请说明业务目的，不少于 5 个字符"></textarea></label>
    <label><span class="k">申请园区</span><span id="ar-parties" class="chips access-options">${PARTY_IDS.map((party) => `<label class="chip-check access-option"><input type="checkbox" value="${party}" ${party === selected ? "checked" : ""}><span>${party}</span></label>`).join("")}</span></label>
    <label><span class="k">查询类型</span><span id="ar-types" class="chips access-options">${["SUM", "COUNT", "AVERAGE", "TIME_SERIES"].map((type) => `<label class="chip-check access-option"><input type="checkbox" value="${type}" ${type === "SUM" ? "checked" : ""}><span>${type}</span></label>`).join("")}</span></label>
    <label><span class="k">开始时间</span><input id="ar-start" type="datetime-local" value="2012-11-11T00:00"></label>
    <label><span class="k">结束时间</span><input id="ar-end" type="datetime-local" value="2012-11-12T00:00"></label>
    <label><span class="k">时序粒度</span><span id="ar-groups" class="chips access-options">${["30m", "1h", "1d"].map((value) => `<label class="chip-check access-option"><input type="checkbox" value="${value}" ${value === "1h" ? "checked" : ""}><span>${value}</span></label>`).join("")}</span><small>仅申请 TIME_SERIES 时使用</small></label>
    <label><span class="k">单次 epsilon 上限</span><input id="ar-max-epsilon" type="number" min="0.1" max="5" step="0.1" value="1"></label>
    <label><span class="k">累计 epsilon</span><input id="ar-total-epsilon" type="number" min="0.1" step="0.1" value="4"></label>
    <label><span class="k">授权到期时间</span><input id="ar-expires" type="datetime-local" value="${expires}"></label>
  </div><div class="notice">前端校验用于操作提示；后端会再次校验数据资产范围、审批归属和全部授权条件。</div>
  <div class="form-actions"><button data-action="save-access-request">保存草稿</button><button class="primary" data-action="save-submit-access-request">保存并提交审批</button></div>`);
  return accessPage("新建申请", "选择数据园区、查询类型、时间范围和可接受的隐私预算上限。", body);
}

function readAccessRequestForm() {
  const queryTypes = Array.from(document.querySelectorAll("#ar-types input:checked")).map((item) => item.value);
  return {
    purpose: document.querySelector("#ar-purpose")?.value.trim() || "",
    requested_parties: Array.from(document.querySelectorAll("#ar-parties input:checked")).map((item) => item.value),
    requested_query_types: queryTypes,
    requested_start_time: document.querySelector("#ar-start")?.value || "",
    requested_end_time: document.querySelector("#ar-end")?.value || "",
    requested_group_by: queryTypes.includes("TIME_SERIES") ? Array.from(document.querySelectorAll("#ar-groups input:checked")).map((item) => item.value) : [],
    requested_max_epsilon_per_query: Number(document.querySelector("#ar-max-epsilon")?.value || 0),
    requested_total_epsilon: Number(document.querySelector("#ar-total-epsilon")?.value || 0),
    requested_expires_at: document.querySelector("#ar-expires")?.value || "",
  };
}

function grantsTable(grants = [], { owner = false } = {}) {
  const allowUse = state.user?.role === "ANALYST";
  const rows = grants.map((grant) => [
    escapeHtml(grant.grant_id),
    escapeHtml(grant.grantee_user_id),
    grant.parties.join(" / "),
    grant.allowed_query_types.join(" / "),
    `${fmtDateTime(grant.allowed_start_time)} — ${fmtDateTime(grant.allowed_end_time)}`,
    fmtEpsilon(grant.max_epsilon_per_query),
    `${fmtEpsilon(grant.epsilon_consumed)} / ${fmtEpsilon(grant.total_epsilon_limit)}`,
    fmtEpsilon(grant.epsilon_remaining),
    fmtDateTime(grant.expires_at),
    accessStatusTag(grant.status),
    ...(allowUse ? [grant.status === "ACTIVE" ? `<button class="primary grant-use-button" data-action="use-grant" data-id="${grant.grant_id}">使用此授权查询</button>` : ""] : []),
  ]);
  const columns = ["授权编号", "授权用户", "园区", "查询类型", "时间范围", "单次 ε", "已用/总额", "剩余", "到期", "状态"];
  if (allowUse) columns.push("操作");
  const tableClass = allowUse ? "grants-table grants-table-action" : "grants-table";
  return rows.length ? `<div class="grants-table-wrap">${table(columns, rows, tableClass)}</div>` : `<div class="api-state">${state.access.loading ? "正在加载授权..." : owner ? "暂无本园区相关授权" : "暂无授权"}</div>`;
}

function grantsPage(owner = false) {
  const grants = owner ? state.access.ownerGrants : state.access.grants;
  return accessPage(owner ? "本园区授权" : "我的授权", "", panel("授权列表", grantsTable(grants, { owner })));
}

function approvalsPage(history = false) {
  const approvals = history ? state.access.approvalHistory : state.access.approvals;
  const rows = approvals.map((item) => [
    escapeHtml(item.approval_id),
    escapeHtml(item.request_id),
    escapeHtml(item.party_id),
    accessStatusTag(item.decision),
    item.decided_at ? fmtDateTime(item.decided_at) : "待处理",
    `<button data-action="view-approval" data-id="${item.approval_id}">${history ? "查看" : "审批详情"}</button>`,
  ]);
  return accessPage(history ? "审批历史" : "待我审批", "", panel(history ? "已完成审批" : "待处理审批", rows.length ? table(["审批编号", "申请编号", "园区", "决定", "时间", "操作"], rows) : `<div class="api-state">${state.access.loading ? "正在加载审批..." : "暂无记录"}</div>`));
}

function approvalDetailPage() {
  const selected = state.access.selectedApproval;
  if (!selected) return accessPage("审批详情", "核对申请范围后作出园区独立决定。", `<div class="api-state">正在加载审批详情...</div>`);
  const { approval, request } = selected;
  const content = normalizeApprovalRequest(request);
  const decided = approval.decision !== "PENDING";
  return accessPage("审批详情", `${escapeHtml(approval.approval_id)} · ${escapeHtml(approval.party_id)}`, `
    <div class="grid-half">
      ${panel("申请内容", kvRowsHtml([
        { k: "申请编号", v: escapeHtml(content.requestId) },
        { k: "申请人", v: escapeHtml(content.requesterUserId) },
        { k: "使用目的", v: `<span data-i18n-ignore>${escapeHtml(content.purpose)}</span>` },
        { k: "申请园区", v: escapeHtml(content.requestedParties) },
        { k: "查询类型", v: escapeHtml(content.requestedQueryTypes) },
        { k: "开始时间", v: escapeHtml(fmtDateTime(content.requestedStartTime)) },
        { k: "结束时间", v: escapeHtml(fmtDateTime(content.requestedEndTime)) },
        { k: "group_by", v: escapeHtml(content.requestedGroupBy) },
        { k: "单次 epsilon 上限", v: escapeHtml(content.maxEpsilonPerQuery) },
        { k: "累计 epsilon", v: escapeHtml(content.totalEpsilon) },
        { k: "申请到期时间", v: escapeHtml(fmtDateTime(content.requestedExpiresAt)) },
        { k: "当前申请状态", v: accessStatusTag(content.status) },
      ]))}
      ${panel("审批决定", decided ? `<div class="api-state">该审批已完成：${accessStatusTag(approval.decision)}<br><span ${approval.reason ? 'data-i18n-ignore' : ''}>${escapeHtml(approval.reason || "无附加说明")}</span></div>` : `<div class="form2" style="grid-template-columns:1fr">
        <label><span class="k">决定</span><select id="approval-decision"><option value="APPROVED">批准</option><option value="CONDITIONALLY_APPROVED">附条件批准</option><option value="REJECTED">拒绝</option></select></label>
        <div class="approval-types-field"><span class="k">允许查询类型</span>${approvalQueryTypesControl(request.requested_query_types)}</div>
        <label><span class="k">允许开始时间</span><input id="approval-start" type="datetime-local" value="${toDateTimeLocal(request.requested_start_time)}"></label>
        <label><span class="k">允许结束时间</span><input id="approval-end" type="datetime-local" value="${toDateTimeLocal(request.requested_end_time)}"></label>
        <label><span class="k">单次 epsilon</span><input id="approval-max-epsilon" type="number" value="${request.requested_max_epsilon_per_query}" max="${request.requested_max_epsilon_per_query}" step="0.1"></label>
        <label><span class="k">累计 epsilon</span><input id="approval-total-epsilon" type="number" value="${request.requested_total_epsilon}" max="${request.requested_total_epsilon}" step="0.1"></label>
        <label><span class="k">到期时间</span><input id="approval-expires" type="datetime-local" value="${toDateTimeLocal(request.requested_expires_at)}"></label>
        <label><span class="k">理由/附加条件</span><textarea id="approval-reason" maxlength="500"></textarea></label>
        <button class="primary wide" data-action="submit-approval-decision" data-id="${approval.approval_id}">提交审批决定</button>
      </div>`)}
    </div>`, `<button data-page="pending-approvals">返回审批列表</button>`);
}

function approvalQueryTypesControl(queryTypes = []) {
  const types = [...new Set((Array.isArray(queryTypes) ? queryTypes : []).filter(Boolean))];
  if (types.length === 1) {
    const type = escapeHtml(types[0]);
    return `<span id="approval-types" class="approval-types-readonly"><input type="hidden" value="${type}"><span class="query-type-pill">${type}</span><small>本申请仅包含此查询类型</small></span>`;
  }
  return `<span id="approval-types" class="approval-type-options">${types.map((type) => {
    const safeType = escapeHtml(type);
    return `<label class="query-type-option"><input type="checkbox" value="${safeType}" checked><span>${safeType}</span></label>`;
  }).join("")}<small>可取消查询类型，以收紧本次批准范围</small></span>`;
}

function auditRequestsPage(kind = "request") {
  const requests = state.access.allRequests;
  const rows = requests.map((request) => [
    request.request_id,
    request.requester_user_id,
    request.requested_parties.join(" / "),
    accessStatusTag(request.status),
    kind === "approval" ? approvalProgress(request) : `<span data-i18n-ignore>${escapeHtml(request.purpose)}</span>`,
    fmtDateTime(request.created_at),
  ]);
  return accessPage(kind === "approval" ? "审批审计" : state.user?.role === "ADMIN" ? "全部申请" : "申请审计", "", panel("申请记录", rows.length ? table(["申请编号", "申请人", "园区", "状态", kind === "approval" ? "审批进度" : "用途", "创建时间"], rows) : `<div class="api-state">暂无申请记录</div>`));
}

function auditGrantsPage() {
  return accessPage(state.user?.role === "ADMIN" ? "全部授权" : "授权审计", "", panel("授权记录", grantsTable(state.access.allGrants)));
}

const ADMIN_ROLE_LABELS = {
  ANALYST: "数据分析员",
  DATA_OWNER: "园区管理员",
  AUDITOR: "审计员",
  ADMIN: "系统管理员",
};

function adminRoleLabel(role) {
  return ADMIN_ROLE_LABELS[role] ? `${ADMIN_ROLE_LABELS[role]} (${role})` : (role || "—");
}

function adminUsersPage() {
  const filters = state.access.userFilters || { query: "", role: "", status: "" };
  const query = String(filters.query || "").trim().toLowerCase();
  const users = state.access.users.filter((user) => {
    if (query && !`${user.username || ""} ${user.user_id || ""}`.toLowerCase().includes(query)) return false;
    if (filters.role && user.role !== filters.role) return false;
    if (filters.status && (user.is_active ? "ACTIVE" : "DISABLED") !== filters.status) return false;
    return true;
  });
  const rows = users.map((user) => {
    const self = user.user_id === state.user?.user_id;
    const active = Boolean(user.is_active);
    const actions = `<div class="admin-user-actions">
      <button data-action="edit-admin-user" data-id="${escapeHtml(user.user_id)}">编辑</button>
      <button data-action="reset-admin-password" data-id="${escapeHtml(user.user_id)}">重置密码</button>
      <button data-action="revoke-admin-sessions" data-id="${escapeHtml(user.user_id)}">撤销会话</button>
      <button data-action="toggle-admin-user" data-id="${escapeHtml(user.user_id)}" data-active="${active ? "false" : "true"}" ${self && active ? "disabled title=\"不能停用当前账号\"" : ""}>${active ? "停用" : "启用"}</button>
    </div>`;
    return [
      `<div class="admin-user-identity"><b>${escapeHtml(user.username || "—")}</b></div>`,
      escapeHtml(adminRoleLabel(user.role)),
      user.role === "DATA_OWNER" ? escapeHtml(user.party_id || "未绑定") : "—",
      accessStatusTag(active ? "ACTIVE" : "DISABLED"),
      fmtDateTime(user.last_login_at),
      fmtDateTime(user.created_at),
      actions,
    ];
  });
  const toolbar = `<div class="admin-users-toolbar">
    <label><span>搜索账号</span><input id="admin-user-search" value="${escapeHtml(filters.query)}" placeholder="用户名或账号 ID" autocomplete="off"></label>
    <label><span>角色</span><select id="admin-user-role-filter"><option value="">全部角色</option>${Object.keys(ADMIN_ROLE_LABELS).map((role) => `<option value="${role}" ${filters.role === role ? "selected" : ""}>${ADMIN_ROLE_LABELS[role]}</option>`).join("")}</select></label>
    <label><span>状态</span><select id="admin-user-status-filter"><option value="">全部状态</option><option value="ACTIVE" ${filters.status === "ACTIVE" ? "selected" : ""}>启用</option><option value="DISABLED" ${filters.status === "DISABLED" ? "selected" : ""}>停用</option></select></label>
  </div>`;
  const body = `${toolbar}<div class="admin-users-table-wrap">${rows.length ? table(["账号", "角色", "园区", "状态", "最近登录", "创建时间", "操作"], rows) : `<div class="api-state">${state.access.loading ? "正在加载账号..." : "暂无匹配账号"}</div>`}</div>`;
  return accessPage("账号与权限", "", panel("账号列表", body), `<button class="primary" data-action="create-admin-user">+ 新建账号</button>`);
}

function securityAuditPage() {
  const rows = state.access.securityAudit.map((item) => [
    fmtDateTime(item.timestamp), item.event_type, item.actor_user_id || "--", item.actor_role || "--",
    item.target_user_id || "--", item.operation || "--", item.party_id || "--", item.request_id || item.grant_id || item.task_id || "--", item.decision || "--", `<span data-i18n-ignore>${escapeHtml(item.reason || "--")}</span>`,
  ]);
  return accessPage("安全审计", "", panel("安全事件", rows.length ? table(["时间", "事件", "操作者", "角色", "目标账号", "操作", "园区", "关联对象", "决定", "原因"], rows) : `<div class="api-state">暂无安全审计事件</div>`));
}

const pages = {
  overview,
  query: queryPage,
  data: dataPage,
  compute: computePage,
  policy: policyPage,
  audit: auditPage,
  report: reportPage,
  performance: performancePage,
  settings: settingsPage,
  catalog: catalogPage,
  "my-requests": myRequestsPage,
  "new-request": newRequestPage,
  "my-grants": () => grantsPage(false),
  "pending-approvals": () => approvalsPage(false),
  "approval-history": () => approvalsPage(true),
  "approval-detail": approvalDetailPage,
  "owner-grants": () => grantsPage(true),
  "request-audit": () => auditRequestsPage("request"),
  "approval-audit": () => auditRequestsPage("approval"),
  "grant-audit": auditGrantsPage,
  "admin-requests": () => auditRequestsPage("request"),
  "admin-grants": auditGrantsPage,
  "admin-users": adminUsersPage,
  "security-audit": securityAuditPage,
};

const invalidRegisteredPages = PAGE_REGISTRY.filter((feature) => typeof pages[feature.id] !== "function");
if (invalidRegisteredPages.length) {
  throw new Error(`Feature registry contains unavailable pages: ${invalidRegisteredPages.map((item) => item.id).join(", ")}`);
}

const ACCESS_PAGE_LOAD_KEYS = {
  catalog: "assets",
  data: "ownerData",
  policy: "policySummary",
  "my-requests": "requests",
  "my-grants": "grants",
  "pending-approvals": "approvals",
  "approval-history": "approvalHistory",
  "owner-grants": "ownerGrants",
  "request-audit": "allRequests",
  "approval-audit": "allRequests",
  "admin-requests": "allRequests",
  "grant-audit": "allGrants",
  "admin-grants": "allGrants",
  "admin-users": "users",
  "security-audit": "securityAudit",
  settings: "adminOverview",
  report: "analystReport",
};

function bindNav() {
  document.querySelectorAll("[data-page]").forEach(btn => btn.addEventListener("click", () => {
    state.access.error = null;
    state.page = btn.dataset.page;
    render();
  }));
}

const TIME_SERIES_CHART_ACTIONS = new Set([
  "chart-zoom-in",
  "chart-zoom-out",
  "chart-zoom-reset",
]);

function bindTimeSeriesChartActions(root = document) {
  root.querySelectorAll(".time-series-chart [data-action]").forEach((el) => {
    if (el.dataset.chartActionBound === "true") return;
    el.dataset.chartActionBound = "true";
    el.addEventListener("click", (event) => handleAction(el.dataset.action, el, event));
  });
}

function bindActions() {
  document.querySelectorAll("[data-action]").forEach(el => {
    const action = el.dataset.action;
    if (TIME_SERIES_CHART_ACTIONS.has(action)) return;
    el.addEventListener("click", (e) => handleAction(action, el, e));
  });
  bindTimeSeriesChartActions();
  const loginForm = document.querySelector("#login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!state.loginBusy) void submitLogin();
    });
  }
  const searchInput = document.querySelector("#global-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", () => filterSearchResults(searchInput.value));
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        moveSearchSelection(event.key === "ArrowDown" ? 1 : -1);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const selected = document.querySelector("#global-search-results .search-result.keyboard-selected:not([hidden])");
        if (selected) {
          handleAction("go-function", selected, event);
        } else {
          handleAction("do-search", searchInput, event);
        }
      }
    });
  }
  const queryInput = document.querySelector("#query-input");
  if (queryInput) {
    queryInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      const send = document.querySelector('[data-action="send-query"]');
      if (send && !send.disabled) handleAction("send-query", send, event);
    });
  }
  const historySearch = document.querySelector("#agent-history-search");
  if (historySearch) {
    historySearch.addEventListener("input", () => {
      state.agent.historySearch = historySearch.value;
      const selectionStart = historySearch.selectionStart;
      render();
      queueMicrotask(() => {
        const next = document.querySelector("#agent-history-search");
        next?.focus();
        if (next && selectionStart != null) next.setSelectionRange(selectionStart, selectionStart);
      });
    });
  }
  const adminUserRole = document.querySelector("#admin-user-role");
  if (adminUserRole) {
    adminUserRole.addEventListener("change", syncAdminUserOrgField);
    syncAdminUserOrgField();
  }
  const adminUserSearch = document.querySelector("#admin-user-search");
  if (adminUserSearch) {
    const applySearch = () => {
      state.access.userFilters.query = adminUserSearch.value;
      render();
      queueMicrotask(() => {
        const next = document.querySelector("#admin-user-search");
        next?.focus();
        if (next) next.selectionStart = next.selectionEnd = next.value.length;
      });
    };
    adminUserSearch.addEventListener("change", applySearch);
    adminUserSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applySearch();
      }
    });
  }
  [
    ["#admin-user-role-filter", "role"],
    ["#admin-user-status-filter", "status"],
  ].forEach(([selector, key]) => {
    const select = document.querySelector(selector);
    if (select) select.addEventListener("change", () => {
      state.access.userFilters[key] = select.value;
      render();
    });
  });
}

function filterSearchResults(query) {
  const results = document.querySelector("#global-search-results");
  if (!results) return;
  const normalized = String(query || "").trim().toLowerCase();
  results.hidden = !normalized;
  const idle = document.querySelector(".search-idle-content");
  if (idle) idle.hidden = Boolean(normalized);
  let visible = 0;
  results.querySelectorAll(".search-result").forEach((item) => {
    const matches = Boolean(normalized) && item.dataset.searchText.includes(normalized);
    item.hidden = !matches;
    if (matches) visible += 1;
  });
  const empty = results.querySelector(".search-empty");
  if (empty) empty.hidden = visible > 0;
  const list = results.querySelector(".search-result-list");
  if (list) list.hidden = visible === 0;
  const count = document.querySelector("#global-search-count");
  if (count) count.textContent = `${visible} 项`;
  state.searchSelection = -1;
  updateSearchSelection();
}

function updateSearchSelection() {
  const visible = [...document.querySelectorAll("#global-search-results .search-result:not([hidden])")];
  visible.forEach((item, index) => {
    const selected = index === state.searchSelection;
    item.classList.toggle("keyboard-selected", selected);
    item.setAttribute("aria-selected", String(selected));
  });
}

function moveSearchSelection(direction) {
  const visible = [...document.querySelectorAll("#global-search-results .search-result:not([hidden])")];
  if (!visible.length) return;
  state.searchSelection = (state.searchSelection + direction + visible.length) % visible.length;
  updateSearchSelection();
  visible[state.searchSelection]?.scrollIntoView?.({ block: "nearest" });
}

function goToSearchFeature(feature) {
  const role = state.user?.role;
  if (!feature || !isRegisteredPageForRole(role, feature.id) || typeof pages[feature.id] !== "function") {
    console.error("Global search rejected an unavailable route", { role, featureId: feature?.id });
    toast("该功能暂不可用", "warn");
    return false;
  }
  state.page = feature.id;
  closeOverlays();
  render();
  return true;
}

async function saveAccessRequest(andSubmit = false) {
  const payload = readAccessRequestForm();
  const validationError = validateAccessRequest(payload);
  if (validationError) {
    toast(validationError, "error");
    return;
  }
  state.access.loading = true;
  try {
    const created = await createAccessRequest(payload);
    if (andSubmit) await submitAccessRequest(created.request_id);
    state.access.loaded.requests = false;
    state.access.prefillParty = null;
    state.page = "my-requests";
    toast(andSubmit ? "申请已保存并提交多方审批" : "申请草稿已保存", "ok");
  } catch (error) {
    toast(formatApiError(error, "保存申请失败"), "error");
  } finally {
    state.access.loading = false;
    render();
  }
}

async function changeAccessRequest(requestId, action) {
  try {
    if (action === "submit") await submitAccessRequest(requestId);
    else await withdrawAccessRequest(requestId);
    state.access.loaded.requests = false;
    toast(action === "submit" ? "申请已提交" : "申请已撤销", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "申请操作失败"), "error");
  }
}

async function openApproval(approvalId) {
  state.access.selectedApproval = null;
  state.page = "approval-detail";
  render();
  try {
    const approval = await getApproval(approvalId);
    const request = await getAccessRequest(approval.request_id);
    state.access.selectedApproval = { approval, request };
  } catch (error) {
    state.access.error = error;
  }
  render();
}

async function submitApprovalDecision(approvalId) {
  const decision = document.querySelector("#approval-decision")?.value || "APPROVED";
  const reason = document.querySelector("#approval-reason")?.value.trim() || null;
  const payload = { decision, reason };
  if (decision === "CONDITIONALLY_APPROVED") {
    payload.allowed_query_types = Array.from(document.querySelectorAll("#approval-types input"))
      .filter((item) => item.type === "hidden" || item.checked)
      .map((item) => item.value);
    if (!payload.allowed_query_types.length) {
      toast("至少保留一种允许的查询类型", "error");
      return;
    }
    payload.allowed_start_time = document.querySelector("#approval-start")?.value;
    payload.allowed_end_time = document.querySelector("#approval-end")?.value;
    payload.max_epsilon_per_query = Number(document.querySelector("#approval-max-epsilon")?.value || 0);
    payload.total_epsilon_limit = Number(document.querySelector("#approval-total-epsilon")?.value || 0);
    payload.expires_at = document.querySelector("#approval-expires")?.value;
  }
  if (decision === "REJECTED" && !reason) {
    toast("拒绝申请时必须填写理由", "error");
    return;
  }
  try {
    await decideApproval(approvalId, payload);
    state.access.loaded.approvals = false;
    state.access.loaded.approvalHistory = false;
    state.access.selectedApproval = null;
    state.page = "pending-approvals";
    toast("审批决定已提交", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "提交审批失败"), "error");
  }
}

function adminUserById(userId) {
  return state.access.users.find((user) => user.user_id === userId) || null;
}

function adminUserForm(role = "ANALYST", user = null) {
  const isOwner = role === "DATA_OWNER";
  return `<div class="form2 admin-user-form" style="grid-template-columns:1fr">
    <label><span class="k">账号名</span><input id="admin-user-username" value="${escapeHtml(user?.username || "")}" ${user ? "disabled" : ""} autocomplete="off" maxlength="64" placeholder="3-64 位字母、数字、点、下划线或连字符"></label>
    <label><span class="k">角色</span><select id="admin-user-role">${Object.entries(ADMIN_ROLE_LABELS).map(([value, label]) => `<option value="${value}" ${role === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label id="admin-user-org-wrap" class="${isOwner ? "" : "is-hidden"}"><span class="k">绑定园区</span><select id="admin-user-org"><option value="">请选择园区</option>${["ORG_A", "ORG_B", "ORG_C"].map((org) => `<option value="${org}" ${user?.party_id === org ? "selected" : ""}>${org}</option>`).join("")}</select></label>
    ${user ? "" : `<label><span class="k">初始密码</span><input id="admin-user-password" type="password" minlength="8" maxlength="256" autocomplete="new-password"></label><label><span class="k">确认密码</span><input id="admin-user-password-confirm" type="password" minlength="8" maxlength="256" autocomplete="new-password"></label>`}
  </div>`;
}

function syncAdminUserOrgField() {
  const role = document.querySelector("#admin-user-role")?.value;
  const wrap = document.querySelector("#admin-user-org-wrap");
  const org = document.querySelector("#admin-user-org");
  if (!wrap || !org) return;
  const owner = role === "DATA_OWNER";
  wrap.classList.toggle("is-hidden", !owner);
  org.disabled = !owner;
  org.required = owner;
  if (!owner) org.value = "";
}

function openAdminUserCreate() {
  state.modal = { type: "admin-user-create", title: "新建账号" };
  render();
}

function openAdminUserEdit(userId) {
  const user = adminUserById(userId);
  if (!user) return;
  state.modal = { type: "admin-user-edit", title: "编辑账号", data: user };
  render();
}

function openAdminPasswordReset(userId) {
  const user = adminUserById(userId);
  if (!user) return;
  state.modal = { type: "admin-user-reset", title: `重置密码 · ${user.username}`, data: user };
  render();
}

function readAdminUserRolePayload() {
  const role = document.querySelector("#admin-user-role")?.value || "ANALYST";
  const organization_id = role === "DATA_OWNER" ? document.querySelector("#admin-user-org")?.value || null : null;
  return { role, organization_id };
}

async function submitAdminUserCreate() {
  const username = document.querySelector("#admin-user-username")?.value.trim() || "";
  const password = document.querySelector("#admin-user-password")?.value || "";
  const confirm = document.querySelector("#admin-user-password-confirm")?.value || "";
  const payload = { username, password, ...readAdminUserRolePayload() };
  if (!username || !password || password !== confirm) {
    toast("请填写完整账号信息，并确认两次密码一致", "error");
    return;
  }
  if (payload.role === "DATA_OWNER" && !payload.organization_id) {
    toast("园区管理员必须绑定园区", "error");
    return;
  }
  try {
    await createAdminUser(payload);
    state.access.loaded.users = false;
    state.modal = null;
    toast("账号已创建", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "创建账号失败"), "error");
  }
}

async function submitAdminUserEdit() {
  const user = state.modal?.data;
  if (!user) return;
  const payload = readAdminUserRolePayload();
  if (payload.role === "DATA_OWNER" && !payload.organization_id) {
    toast("园区管理员必须绑定园区", "error");
    return;
  }
  try {
    await updateAdminUser(user.user_id, payload);
    state.access.loaded.users = false;
    state.modal = null;
    toast("账号权限已更新", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "更新账号失败"), "error");
  }
}

async function submitAdminPasswordReset() {
  const user = state.modal?.data;
  const password = document.querySelector("#admin-reset-password")?.value || "";
  const confirm = document.querySelector("#admin-reset-password-confirm")?.value || "";
  if (!user) return;
  if (password.length < 8 || password !== confirm) {
    toast("密码至少 8 位，且两次输入必须一致", "error");
    return;
  }
  try {
    await resetAdminUserPassword(user.user_id, password);
    state.access.loaded.users = false;
    state.modal = null;
    toast("密码已重置，原有会话已撤销", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "重置密码失败"), "error");
  }
}

async function revokeAdminSessions(userId) {
  const user = adminUserById(userId);
  if (!user) return;
  try {
    await revokeAdminUserSessions(userId);
    toast(`${user.username} 的会话已撤销`, "ok");
  } catch (error) {
    toast(formatApiError(error, "撤销会话失败"), "error");
  }
}

async function toggleAdminUser(userId, active) {
  try {
    await setAdminUserStatus(userId, active);
    state.access.loaded.users = false;
    toast(active ? "账号已启用" : "账号已停用，现有会话已撤销", "ok");
    render();
  } catch (error) {
    toast(formatApiError(error, "更新账号状态失败"), "error");
  }
}

async function refreshOwnerData() {
  state.access.loading = true;
  state.access.error = null;
  try {
    state.access.ownerData = await accessLoaders.ownerData();
    state.access.loaded.ownerData = true;
  } catch (error) {
    state.access.error = error;
  } finally {
    state.access.loading = false;
    render();
  }
}

async function submitDataImport() {
  if (state.user?.role !== "DATA_OWNER") {
    toast("仅园区管理员可以导入数据", "error");
    return;
  }
  const input = document.querySelector("#csv-import-file");
  const file = input?.files?.[0];
  const config = state.access.ownerData?.config;
  if (!file) {
    toast("请选择 CSV 文件", "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    toast("仅支持 .csv 文件", "error");
    return;
  }
  if (config?.max_bytes && file.size > config.max_bytes) {
    toast("文件超过导入大小上限", "error");
    return;
  }
  state.access.importPhase = "uploading";
  state.access.error = null;
  render();
  try {
    const result = await uploadDataImport(file);
    state.access.selectedDataImport = result;
    state.access.importPhase = ["VALID", "ACTIVE"].includes(result.status) ? "success" : "failed";
    toast(result.status === "VALID" ? "CSV 校验通过，可确认启用" : "CSV 未通过校验，请查看报告", result.status === "VALID" ? "ok" : "error");
    await refreshOwnerData();
  } catch (error) {
    state.access.importPhase = "failed";
    state.access.error = error;
    render();
  }
}

async function activateImportedVersion(importId) {
  const message = "启用后，该园区后续查询将使用此数据快照。原有版本仍可回滚。";
  if (typeof globalThis.confirm === "function" && !globalThis.confirm(message)) return;
  try {
    state.access.selectedDataImport = await activateDataImport(importId);
    toast("数据版本已启用", "ok");
    await refreshOwnerData();
  } catch (error) {
    state.access.error = error;
    render();
  }
}

async function rollbackImportedVersion(targetVersion) {
  const message = targetVersion === "BASELINE"
    ? "确认回滚到只读基线数据？当前导入版本仍会保留。"
    : `确认回滚到 ${targetVersion}？`;
  if (typeof globalThis.confirm === "function" && !globalThis.confirm(message)) return;
  try {
    await rollbackDataImport(targetVersion);
    state.access.selectedDataImport = targetVersion === "BASELINE"
      ? null
      : state.access.ownerData.imports.find((item) => item.import_id === targetVersion) || null;
    toast("数据版本回滚完成", "ok");
    await refreshOwnerData();
  } catch (error) {
    state.access.error = error;
    render();
  }
}

function updateTimeSeriesChartZoom(action, source) {
  const currentZoom = normalizedTimeSeriesZoom(state.query.chartZoom);
  const currentIndex = TIME_SERIES_ZOOM_LEVELS.indexOf(currentZoom);
  const nextZoom = action === "chart-zoom-reset"
    ? 1
    : action === "chart-zoom-in"
      ? TIME_SERIES_ZOOM_LEVELS[Math.min(TIME_SERIES_ZOOM_LEVELS.length - 1, currentIndex + 1)]
      : TIME_SERIES_ZOOM_LEVELS[Math.max(0, currentIndex - 1)];
  const previousScroll = source.closest(".time-series-chart")?.querySelector(".time-series-chart-scroll");
  const centerRatio = previousScroll?.scrollWidth
    ? (previousScroll.scrollLeft + previousScroll.clientWidth / 2) / previousScroll.scrollWidth
    : 0;

  state.query.chartZoom = nextZoom;
  const result = document.querySelector("#q-result");
  if (!result) return;
  result.innerHTML = queryResultHtml(state.query);
  bindTimeSeriesChartActions(result);

  queueMicrotask(() => {
    const nextScroll = result.querySelector(".time-series-chart-scroll");
    if (!nextScroll) return;
    if (action === "chart-zoom-reset") {
      nextScroll.scrollLeft = 0;
      return;
    }
    nextScroll.scrollLeft = Math.max(0, centerRatio * nextScroll.scrollWidth - nextScroll.clientWidth / 2);
  });
}

function handleAction(action, el, e) {
  if (action === "close-overlay" && el.classList.contains("overlay") && e.target !== el) return;
  switch (action) {
    case "chart-zoom-in":
    case "chart-zoom-out":
    case "chart-zoom-reset":
      updateTimeSeriesChartZoom(action, el);
      break;
    case "toggle-speech-input": speechInput.toggle(); break;
    case "new-agent-conversation": void startNewAgentConversation(); break;
    case "open-agent-history":
      state.agent.historyOpen = true;
      state.agent.historySearch = "";
      render();
      if (!state.agent.conversations.length) {
        state.agent.historyLoading = true;
        void refreshAgentConversations()
          .catch((error) => toast(formatApiError(error, "历史会话加载失败"), "error"))
          .finally(() => { state.agent.historyLoading = false; render(); });
      }
      break;
    case "close-agent-history": state.agent.historyOpen = false; render(); break;
    case "open-agent-conversation": void openAgentConversation(el.dataset.id); break;
    case "upload-data-import": void submitDataImport(); break;
    case "activate-data-import": void activateImportedVersion(el.dataset.id); break;
    case "rollback-data-import": void rollbackImportedVersion(el.dataset.id); break;
    case "view-data-import": {
      state.access.selectedDataImport = state.access.ownerData.imports.find((item) => item.import_id === el.dataset.id) || null;
      render();
      break;
    }
    case "open-search":
      closeOverlays();
      state.searchOpen = true;
      render();
      queueMicrotask(() => document.querySelector("#global-search-input")?.focus());
      break;
    case "close-overlay":
      closeOverlays();
      render();
      queueMicrotask(() => document.querySelector('[data-action="open-search"]')?.focus());
      break;
    case "toggle-notify": state.notifyOpen = !state.notifyOpen; render(); break;
    case "mark-read": toast("全部通知已标记为已读", "ok"); state.notifyOpen = false; render(); break;
    case "toggle-user": state.userOpen = !state.userOpen; render(); break;
    case "go-settings": state.page = "settings"; state.userOpen = false; render(); break;
    case "go-audit": state.page = "audit"; state.userOpen = false; render(); break;
    case "logout": void performLogout(); break;
    case "toggle-collapse": state.collapsed = !state.collapsed; render(); break;
    case "do-search":
    case "search-chip": {
      const q = action === "search-chip" ? el.dataset.q : document.querySelector("#global-search-input")?.value;
      if (action === "search-chip") {
        const input = document.querySelector("#global-search-input");
        if (input) {
          input.value = q || "";
          filterSearchResults(q);
        }
      }
      const feature = searchFeatureForQuery(q);
      if (feature && goToSearchFeature(feature)) rememberRecentSearch(q);
      else if (!feature && q) toast(`未找到与“${q}”匹配的功能页`, "warn");
      break;
    }
    case "go-function": {
      const query = el.dataset.source === "result" ? document.querySelector("#global-search-input")?.value : null;
      if (goToSearchFeature(searchFeatureById(el.dataset.feature)) && query) rememberRecentSearch(query);
      break;
    }
    case "period": toast("时间周期切换（mock）", "ok"); break;
    case "health-detail": {
      if (!USE_MOCK && state.overview.data?.health?.services) {
        const item = state.overview.data.health.services.find((s) => s.service_id === el.dataset.i)
          || state.overview.data.health.services[0];
        if (!item) break;
        state.modal = {
          type: "health",
          data: {
            name: item.name,
            score: item.online ? "在线" : "离线",
            meta: `版本 ${item.version || "—"} · 延迟 ${fmtNumber(item.latency_ms, 1)} ms`,
            status: item.online ? "正常" : "离线",
            detail: item.online ? "节点运行正常，无异常事件。" : `节点当前离线：${item.error || "未知原因"}`,
          },
        };
        render();
        break;
      }
      const i = parseInt(el.dataset.i, 10);
      const h = i >= 0 ? mockData.overview.health[i] : mockData.overview.health[0];
      state.modal = { type: "health", data: h };
      render();
      break;
    }
    case "view-all-tasks": state.page = "report"; render(); break;
    case "view-all-alerts": state.page = "audit"; render(); break;
    case "view-logs": toast("正在打开执行日志...", "ok"); break;
    case "send-query": {
      speechInput.cancel();
      const val = document.querySelector("#query-input")?.value;
      if (USE_MOCK) {
        if (val) toast("Agent 已接收问题，正在生成查询计划...", "ok");
        else toast("请输入问题", "error");
        break;
      }
      if (!val || !val.trim()) {
        toast("请输入问题", "error");
        break;
      }
      void runAgentParse(val.trim());
      break;
    }
    case "query-prompt": {
      speechInput.cancel({ abort: true, discardInterim: true });
      const input = document.querySelector("#query-input");
      if (!input) break;
      const prompt = el.dataset.prompt || "";
      input.value = prompt;
      if (!USE_MOCK && prompt) void runAgentParse(prompt);
      else input.focus();
      break;
    }
    case "query-tab": {
      const selected = el.dataset.tab;
      document.querySelectorAll(".query-result-tabs [data-tab]").forEach((button) => {
        const active = button.dataset.tab === selected;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll("[data-tab-panel]").forEach((tabPanel) => {
        tabPanel.hidden = tabPanel.dataset.tabPanel !== selected;
      });
      break;
    }
    case "explain-result": {
      void runAgentExplain();
      break;
    }
    case "submit-query": {
      state.query.chartZoom = 1;
      const controller = ensureQueryController();
      const form = readQueryForm();
      const selectedGrant = state.access.grants.find((grant) => grant.grant_id === form.grant_id) || null;
      let blockers = querySubmissionBlockers(form, {
        isBusy: controller.isBusy(),
        selectedGrant,
      });
      // A deliberate click is also an explicit confirmation of a fully valid
      // manually edited/default Grant form. This keeps the form usable when
      // Agent parsing is temporarily unavailable without weakening validation.
      if (!state.agent.hasCurrentTask && !controller.isBusy()) {
        const manualBlockers = querySubmissionBlockers(form, {
          isBusy: false,
          selectedGrant,
          hasCurrentTask: true,
        });
        if (!manualBlockers.length) {
          state.agent.hasCurrentTask = true;
          persistCurrentQueryDraft();
          blockers = [];
        }
      }
      if (blockers.length) {
        if (!controller.isBusy()) setQueryEditorExpanded(true);
        updateQueryRuntime();
        toast(blockers[0], "warn");
        queueMicrotask(() => focusFirstQueryCorrection(form, selectedGrant));
        break;
      }
      void controller.submit(form, {
        onState: (s) => {
          syncQueryState(s);
          updateQueryRuntime();
          if (s.phase === "polling" && s.task?.task_id) {
            void linkCurrentConversationTask(s.task.task_id);
          }
        },
      });
      break;
    }
    case "retry-overview": state.overview.error = null; state.overview.loaded = false; render(); break;
    case "retry-compute": state.compute.error = null; state.compute.loaded = false; render(); break;
    case "retry-audit": state.audit.error = null; state.audit.loaded = false; render(); break;
    case "refresh-monitor": void refreshMonitor(); break;
    case "start-performance": void startPerformanceTest(); break;
    case "export-performance": toast("暂无可导出的真实性能测试结果", "warn"); break;
    case "edit-params": {
      const editor = document.querySelector("#q-param-editor");
      if (!editor) break;
      setQueryEditorExpanded(editor.hidden, { focus: true });
      break;
    }
    case "copy-plan": toast("计算计划已复制到剪贴板", "ok"); break;
    case "export-data": toast("数据导出中...", "ok"); break;
    case "view-detail": toast("打开结果明细", "ok"); break;
    case "copy-explain": toast("解释内容已复制", "ok"); break;
    case "export-report": toast("报告导出中...", "ok"); break;
    case "view-all-events": toast("查看全部安全事件", "ok"); break;
    case "audit-search": {
      const keyword = document.querySelector("#audit-task-input")?.value.trim().toLowerCase() || "";
      state.audit.filtered = keyword
        ? state.audit.records.filter((record) => auditRecordSearchText(record).includes(keyword))
        : null;
      state.audit.selectedAuditId = (state.audit.filtered || state.audit.records)[0]?.auditId || null;
      render();
      break;
    }
    case "audit-detail": state.audit.selectedAuditId = el.dataset.id; render(); break;
    case "view-catalog-asset": {
      const asset = state.access.assets.find((item) => item.asset_id === el.dataset.id)
        || state.access.ownerData.assets.find((item) => item.asset_id === el.dataset.id);
      if (!asset) break;
      const safe = (value) => value === null || value === undefined || value === "" ? "—" : escapeHtml(value);
      const queryTypes = Array.isArray(asset.supported_query_types) ? asset.supported_query_types : [];
      const groupBy = Array.isArray(asset.supported_group_by) ? asset.supported_group_by : [];
      state.modal = {
        type: "catalog",
        title: safe(asset.name),
        body: `${kvRowsHtml([
          { k: "资产编号", v: safe(asset.asset_id) },
          { k: "提供方", v: safe(asset.owner_party) },
          { k: "时间范围", v: `${safe(fmtDate(asset.time_start))} — ${safe(fmtDate(asset.time_end))}` },
          { k: "数据粒度", v: safe(asset.source_granularity) },
          { k: "支持查询", v: queryTypes.length ? queryTypes.map(safe).join(" · ") : "—" },
          { k: "时序粒度", v: groupBy.length ? groupBy.map(safe).join(" · ") : "—" },
          { k: "状态", v: accessStatusTag(asset.status) },
          ...(asset.description ? [{ k: "资产说明", v: safe(asset.description) }] : []),
          ...(asset.privacy_protection ? [{ k: "保护机制", v: safe(asset.privacy_protection) }] : []),
        ])}<div class="catalog-detail-notice">原始数据由数据提供方本地保存，平台仅支持授权后的受控统计查询。</div>`,
      };
      render();
      break;
    }
    case "apply-asset": state.access.prefillParty = el.dataset.party; state.page = "new-request"; render(); break;
    case "save-access-request": void saveAccessRequest(false); break;
    case "save-submit-access-request": void saveAccessRequest(true); break;
    case "submit-access-request": void changeAccessRequest(el.dataset.id, "submit"); break;
    case "withdraw-access-request": void changeAccessRequest(el.dataset.id, "withdraw"); break;
    case "view-approval": void openApproval(el.dataset.id); break;
    case "submit-approval-decision": void submitApprovalDecision(el.dataset.id); break;
    case "use-grant": state.access.selectedGrantId = el.dataset.id; state.page = "query"; render(); break;
    case "create-admin-user": openAdminUserCreate(); break;
    case "edit-admin-user": openAdminUserEdit(el.dataset.id); break;
    case "reset-admin-password": openAdminPasswordReset(el.dataset.id); break;
    case "submit-admin-user-create": void submitAdminUserCreate(); break;
    case "submit-admin-user-edit": void submitAdminUserEdit(); break;
    case "submit-admin-password-reset": void submitAdminPasswordReset(); break;
    case "revoke-admin-sessions": void revokeAdminSessions(el.dataset.id); break;
    case "toggle-admin-user": void toggleAdminUser(el.dataset.id, el.dataset.active === "true"); break;
    case "toggle-password": {
      const input = document.querySelector("#login-password");
      if (!input) break;
      state.passwordVisible = input.type === "password";
      input.type = state.passwordVisible ? "text" : "password";
      el.innerHTML = icon(state.passwordVisible ? "eyeOff" : "eye");
      el.setAttribute("aria-label", state.passwordVisible ? "隐藏密码" : "显示密码");
      el.title = state.passwordVisible ? "隐藏密码" : "显示密码";
      input.focus();
      break;
    }
    default: break;
  }
}
function renderModal() {
  if (!state.modal) return "";
  if (state.modal.type === "admin-user-create") {
    return modalHtml("新建账号", `${adminUserForm()}<div class="modal-actions"><button data-action="close-overlay">取消</button><button class="primary" data-action="submit-admin-user-create">创建账号</button></div>`);
  }
  if (state.modal.type === "admin-user-edit") {
    const user = state.modal.data;
    return modalHtml("编辑账号", `${adminUserForm(user.role, user)}<div class="modal-actions"><button data-action="close-overlay">取消</button><button class="primary" data-action="submit-admin-user-edit">保存修改</button></div>`);
  }
  if (state.modal.type === "admin-user-reset") {
    return modalHtml(state.modal.title, `<div class="form2 admin-user-form" style="grid-template-columns:1fr"><p class="form-hint">重置后，该账号的现有登录会话将全部失效。</p><label><span class="k">新密码</span><input id="admin-reset-password" type="password" minlength="8" maxlength="256" autocomplete="new-password"></label><label><span class="k">确认新密码</span><input id="admin-reset-password-confirm" type="password" minlength="8" maxlength="256" autocomplete="new-password"></label></div><div class="modal-actions"><button data-action="close-overlay">取消</button><button class="primary" data-action="submit-admin-password-reset">重置密码</button></div>`);
  }
  if (state.modal.type === "catalog") {
    return modalHtml(state.modal.title, `${state.modal.body}<div class="modal-actions"><button class="primary" data-action="close-overlay">关闭</button></div>`);
  }
  if (state.modal.type === "health") {
    const h = state.modal.data;
    return modalHtml(h.name, `
      <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px">
        <div class="ring" style="width:80px;height:80px;font-size:20px">${h.score}</div>
        <div><b style="font-size:18px">${h.name}</b><p style="color:#6b7a94;margin:6px 0 0">${h.meta}</p></div>
      </div>
      <p>${h.detail}</p>
      <div class="metric-pills" style="margin-top:16px">
        <div class="metric-pill"><b>${h.score}</b><span>健康度</span></div>
        <div class="metric-pill"><b>${h.status}</b><span>运行状态</span></div>
      </div>
    `);
  }
  return modalHtml(state.modal.title, state.modal.body + `<div style="margin-top:18px;text-align:right"><button data-action="close-overlay">取消</button><button class="primary" data-action="close-overlay" style="margin-left:10px">确定</button></div>`);
}

async function render() {
  const app = document.querySelector("#app");
  if (!state.loggedIn) {
    app.innerHTML = loginPage();
    bindActions();
    return;
  }
  if (state.activePage && state.activePage !== state.page) {
    if (state.activePage === "query" && state.query.controller) {
      // 离开智能查询页时停止轮询并取消进行中的请求，避免后台重复请求。
      state.query.controller.dispose();
      state.query.controller = null;
      state.query.budgetLoaded = false;
      state.query.budget = null;
    }
    if (state.activePage === "query" && state.agent.abort) {
      // 页面卸载时取消 Agent 解析/解读请求。
      state.agent.abort.abort();
      state.agent.abort = null;
      state.agent.busy = false;
      state.agent.phase = "idle";
    }
    if (state.activePage === "query" && state.agent.typingMessageId) {
      // 离开页面时立即完成当前文本，避免后台持续刷新已卸载的对话 DOM。
      finishAgentTyping({ update: false });
    }
    if (state.activePage === "query") {
      speechInput.cancel({ abort: true, discardInterim: true });
    }
  }
  state.activePage = state.page;
  const pageRenderer = pages[state.page] || overview;
  app.innerHTML = `${topbar()}<div class="layout">${sidebar()}${pageRenderer()}</div>${state.searchOpen ? searchOverlay() : ""}${renderModal()}`;
  bindNav();
  bindActions();
  if (state.page === "query") updateSpeechInputUi();
  if (!USE_MOCK) {
    if (state.page === "query") {
      void ensureAccessData("grants");
      mountQuery();
      const hasPersistedDraft = Boolean(state.agent.hasCurrentTask && state.query.lastPayload);
      syncGroupByControl({ defaultIfEmpty: !hasPersistedDraft });
      if (hasPersistedDraft) {
        applyAgentDraftToForm(state.query.lastPayload, { replace: true });
      }
      applyGrantToQuery(document.querySelector("#q-grant")?.value, { resetScope: !hasPersistedDraft });
      if (hasPersistedDraft) persistCurrentQueryDraft();
      void mountAgentConversations();
    }
    else if (state.page === "overview" && !state.overview.error) void mountOverview();
    else if (state.page === "compute" && !state.compute.error) void mountCompute();
    else if (state.page === "audit" && !state.audit.error) void mountAudit();
    else if (state.page === "performance") void mountPerformance();
    if (ACCESS_PAGE_LOAD_KEYS[state.page]) void ensureAccessData(ACCESS_PAGE_LOAD_KEYS[state.page]);
  }
}

document.addEventListener("change", (event) => {
  const targetId = event.target && event.target.id;
  if (targetId === "monitor-task-select") {
    void refreshMonitor();
  } else if (targetId === "q-type") {
    state.agent.hasCurrentTask = true;
    syncGroupByControl();
    persistCurrentQueryDraft();
    updateQueryRuntime();
  } else if (targetId === "q-grant") {
    state.agent.hasCurrentTask = true;
    void selectGrantForQuery(event.target.value);
  } else if (["q-start", "q-end", "q-epsilon", "q-group"].includes(targetId)
    || (event.target instanceof Element && event.target.closest("#q-parties"))) {
    state.agent.hasCurrentTask = true;
    persistCurrentQueryDraft();
    updateQueryRuntime();
  } else if (targetId === "performance-epsilon") {
    state.performance.config.epsilon = event.target.value;
  } else if (event.target?.name === "performance-query-type") {
    state.performance.config.queryType = event.target.value;
    render();
  } else if (event.target?.name === "performance-interval") {
    state.performance.config.interval = event.target.value;
  } else if (event.target?.name === "performance-mode") {
    state.performance.config.mode = event.target.value;
    render();
  } else if (event.target?.name === "performance-party") {
    const parties = new Set(state.performance.config.parties);
    event.target.checked ? parties.add(event.target.value) : parties.delete(event.target.value);
    state.performance.config.parties = PARTY_IDS.filter((party) => parties.has(party));
    render();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.agent.historyOpen) {
    state.agent.historyOpen = false;
    render();
  } else if (event.key === "Escape" && (state.searchOpen || state.notifyOpen || state.modal)) {
    closeOverlays();
    render();
    queueMicrotask(() => document.querySelector('[data-action="open-search"]')?.focus());
    return;
  }
  const target = event.target;
  const isTyping = target instanceof HTMLElement && (target.matches("input, textarea, select") || target.isContentEditable);
  if (event.key === "/" && state.loggedIn && !isTyping) {
    event.preventDefault();
    closeOverlays();
    state.searchOpen = true;
    render();
    queueMicrotask(() => document.querySelector("#global-search-input")?.focus());
  }
});

globalThis.window?.addEventListener("beforeunload", () => {
  speechInput.cancel({ abort: true, discardInterim: true });
});

installLocalization();
render();
void restoreSession();
