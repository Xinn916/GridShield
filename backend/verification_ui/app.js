"use strict";

const $ = (id) => document.getElementById(id);
const TERMINAL = new Set(["COMPLETED", "FAILED"]);
const PROGRESS = {
  CREATED: 5,
  DISPATCHING: 18,
  LOCAL_COMPUTING: 35,
  SHARING: 52,
  AGGREGATING: 70,
  RECONSTRUCTING: 88,
  COMPLETED: 100,
  FAILED: 100,
};

const state = {
  budget: null,
  currentTask: null,
  pendingPayload: null,
  polling: false,
  pollCancelled: false,
  pageClosing: false,
};

class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function createElement(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function appendDetail(container, label, value) {
  const item = createElement("div");
  item.append(createElement("dt", label), createElement("dd", displayValue(value)));
  container.append(item);
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatNumber(value, digits = 6) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function errorDetail(payload) {
  if (!payload) return "请求失败";
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => `${(item.loc || []).join(".")}: ${item.msg || "参数错误"}`).join("；");
  }
  return payload.message || JSON.stringify(payload);
}

async function apiRequest(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
      signal: controller.signal,
    });
    const text = await response.text();
    let payload = null;
    if (text) {
      try { payload = JSON.parse(text); } catch { payload = { detail: text }; }
    }
    if (!response.ok) throw new ApiError(errorDetail(payload), response.status);
    return { data: payload, status: response.status };
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError("请求超时，请检查后端服务。", 0);
    if (error instanceof ApiError) throw error;
    throw new ApiError(`网络错误：${error.message}`, 0);
  } finally {
    window.clearTimeout(timer);
  }
}

function showMessage(message, type = "info") {
  const node = $("global-message");
  node.textContent = message;
  node.className = `message ${type}`;
  node.hidden = false;
}

function hideMessage() {
  $("global-message").hidden = true;
}

function setButtonBusy(button, busy, busyText) {
  if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.originalText;
}

function selectedParties() {
  return Array.from(document.querySelectorAll('input[name="party"]:checked')).map((item) => item.value);
}

function isoSeconds(value) {
  if (!value) return value;
  return value.length === 16 ? `${value}:00` : value;
}

function readBasePayload(queryType = $("query-type").value, epsilon = Number($("epsilon").value)) {
  const parties = selectedParties();
  const startTime = isoSeconds($("start-time").value);
  const endTime = isoSeconds($("end-time").value);
  if (!parties.length) throw new Error("请至少选择一个园区。 ");
  if (!startTime || !endTime) throw new Error("请选择完整的开始和结束时间。 ");
  if (new Date(startTime) >= new Date(endTime)) throw new Error("结束时间必须晚于开始时间。 ");
  if (!Number.isFinite(epsilon) || epsilon <= 0 || epsilon > 5) throw new Error("epsilon 必须大于 0 且不超过 5。 ");
  const groupBy = queryType === "TIME_SERIES" ? $("group-by").value : "";
  if (queryType === "TIME_SERIES" && !groupBy) throw new Error("TIME_SERIES 必须选择 group_by。 ");
  return {
    query_type: queryType,
    parties,
    start_time: startTime,
    end_time: endTime,
    group_by: groupBy || null,
    epsilon,
  };
}

async function refreshBudget() {
  const { data } = await apiRequest("/api/v1/privacy/budgets?subject_id=demo-analyst&data_scope=GLOBAL");
  state.budget = data;
  $("remaining-epsilon").textContent = formatNumber(data.remaining_epsilon, 3);
  $("budget-subject").textContent = data.subject_id;
  $("budget-scope").textContent = data.data_scope;
  $("budget-total").textContent = `${formatNumber(data.total_epsilon, 3)} ε`;
  $("budget-used").textContent = `${formatNumber(data.used_epsilon, 3)} ε`;
  $("budget-reserved").textContent = `${formatNumber(data.reserved_epsilon, 3)} ε`;
  $("budget-updated").textContent = formatDate(data.updated_at);
  return data;
}

async function refreshHealth() {
  const button = $("check-services");
  setButtonBusy(button, true, "检查中...");
  try {
    const { data } = await apiRequest("/api/v1/system/health", {}, 30000);
    const grid = $("health-grid");
    clearNode(grid);
    data.services.forEach((service) => {
      const card = createElement("article", null, "health-item");
      card.append(createElement("h3", service.name));
      const status = createElement("span", service.online ? "在线" : "离线", `status ${service.online ? "online" : "offline"}`);
      card.append(status);
      card.append(createElement("p", `端口：${new URL(service.endpoint).port || "80"}`));
      card.append(createElement("p", `响应：${formatNumber(service.latency_ms, 2)} ms`));
      card.append(createElement("p", `检查：${formatDate(data.checked_at)}`));
      if (service.error) card.title = service.error;
      grid.append(card);
    });
  } finally {
    setButtonBusy(button, false, "检查中...");
  }
}

function renderTask(task) {
  state.currentTask = task;
  const details = $("task-details");
  clearNode(details);
  const progress = PROGRESS[task.status] ?? 0;
  $("task-progress").style.width = `${progress}%`;
  const mechanism = task.calculation_mode === "DISTRIBUTED_DP" ? "distributed_laplace" : "none";
  [
    ["task_id", task.task_id],
    ["query_type", task.query_type],
    ["calculation_mode", task.calculation_mode],
    ["status", task.status],
    ["current_stage", task.status],
    ["progress", `${progress}%`],
    ["parties", task.parties?.join(", ")],
    ["epsilon", task.epsilon],
    ["sensitivity", task.sensitivity],
    ["mechanism", mechanism],
    ["privacy_unit", task.privacy_unit],
    ["created_at", formatDate(task.created_at)],
    ["execution_time_ms", task.duration_ms],
    ["error_message", task.error],
  ].forEach(([label, value]) => appendDetail(details, label, value));
}

function renderResult(response, task) {
  const result = response.result || {};
  const rawValue = Number(result.value);
  const valueNode = $("result-value");
  if (response.query_type === "SUM") {
    valueNode.textContent = `${formatNumber(rawValue)} kWh`;
  } else if (response.query_type === "COUNT") {
    valueNode.textContent = `原始带噪值 ${formatNumber(rawValue)}；约 ${Math.max(0, Math.round(rawValue))} 户`;
  } else if (response.query_type === "AVERAGE") {
    valueNode.textContent = `${formatNumber(rawValue)} kWh / 户`;
  } else {
    valueNode.textContent = `TIME_SERIES ${result.bucket_count || 0} buckets`;
  }
  const details = $("result-details");
  clearNode(details);
  const privacy = response.privacy || {};
  [
    ["query_type", response.query_type],
    ["calculation_mode", response.calculation_mode],
    ["epsilon", privacy.epsilon ?? task?.epsilon],
    ["sensitivity", privacy.sensitivity ?? task?.sensitivity],
    ["mechanism", privacy.mechanism],
    ["privacy_unit", privacy.privacy_unit],
    ["parties", task?.parties?.join(", ")],
    ["execution_time_ms", task?.duration_ms],
  ].forEach(([label, value]) => appendDetail(details, label, value));
  renderTimeSeries(response.query_type === "TIME_SERIES" ? result : null);
}

function renderTimeSeries(result) {
  const output = $("time-series-output");
  output.hidden = !result;
  if (!result) return;
  const buckets = result.buckets || [];
  const body = $("series-body");
  clearNode(body);
  buckets.forEach((bucket) => appendTableRow(body, [formatDate(bucket.timestamp), formatNumber(bucket.value)]));

  const metrics = $("series-metrics");
  clearNode(metrics);
  Object.entries(result.metrics || {}).forEach(([key, value]) => {
    appendDetail(metrics, key, key.endsWith("timestamp") ? formatDate(value) : formatNumber(value));
  });

  const values = buckets.map((bucket) => Number(bucket.value));
  const maximum = Math.max(...values, 1);
  const width = 888;
  const points = values.map((value, index) => {
    const x = 56 + (values.length <= 1 ? 0 : index * width / (values.length - 1));
    const y = 244 - Math.max(0, value) / maximum * 220;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  $("series-line").setAttribute("points", points.join(" "));
}

async function waitForTask(task, display = true) {
  const started = Date.now();
  if (display) {
    state.pollCancelled = false;
    state.polling = true;
    $("stop-polling").disabled = false;
  }
  let current = task;
  try {
    while (!TERMINAL.has(current.status)) {
      if (state.pageClosing || (display && state.pollCancelled)) throw new ApiError("轮询已停止。", 0);
      if (Date.now() - started >= 60000) throw new ApiError("等待任务完成超时，请检查后端日志。", 0);
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      current = (await apiRequest(`/api/v1/tasks/${encodeURIComponent(current.task_id)}`)).data;
      if (display) renderTask(current);
    }
    return current;
  } finally {
    if (display) {
      state.polling = false;
      $("stop-polling").disabled = true;
    }
  }
}

async function executeTask(payload, display = false) {
  const { data: created } = await apiRequest("/api/v1/tasks", { method: "POST", body: JSON.stringify(payload) }, 65000);
  if (display) renderTask(created);
  const task = await waitForTask(created, display);
  await refreshBudget();
  if (task.status === "FAILED") throw new ApiError(task.error || "任务执行失败。", 500);
  const { data: result } = await apiRequest(`/api/v1/tasks/${encodeURIComponent(task.task_id)}/result`);
  if (display) {
    renderResult(result, task);
    await loadAudit(task.task_id);
  }
  return { task, result };
}

async function submitMainTask(payload) {
  const button = $("submit-query");
  setButtonBusy(button, true, "执行中...");
  $("query-loading").hidden = false;
  hideMessage();
  try {
    const { task } = await executeTask(payload, true);
    showMessage(`任务 ${task.task_id} 已完成。`, "success");
  } catch (error) {
    showMessage(`提交失败${error.status ? `（HTTP ${error.status}）` : ""}：${error.message}`, "error");
  } finally {
    setButtonBusy(button, false, "执行中...");
    $("query-loading").hidden = true;
    await Promise.allSettled([refreshBudget(), refreshRecentTasks()]);
  }
}

function showConfirmation(payload) {
  state.pendingPayload = payload;
  const details = $("confirm-details");
  clearNode(details);
  [
    ["查询类型", payload.query_type],
    ["参与园区", payload.parties.join(", ")],
    ["时间范围", `${payload.start_time} 至 ${payload.end_time}`],
    ["epsilon", payload.epsilon],
    ["预计消耗预算", `${payload.epsilon} ε`],
  ].forEach(([label, value]) => appendDetail(details, label, value));
  $("confirm-dialog").showModal();
}

function appendTableRow(body, values, className) {
  const row = createElement("tr", null, className);
  values.forEach((value) => row.append(createElement("td", displayValue(value))));
  body.append(row);
  return row;
}

function repeatCost() {
  const epsilon = Number($("repeat-epsilon").value);
  const repeats = Number($("repeat-count").value);
  $("repeat-cost").textContent = `预计消耗：${formatNumber(epsilon * repeats, 2)} ε`;
}

async function runRepeatExperiment() {
  const button = $("run-repeat");
  let payload;
  const epsilon = Number($("repeat-epsilon").value);
  const repeats = Number($("repeat-count").value);
  try {
    if (!Number.isInteger(repeats) || repeats < 2 || repeats > 10) throw new Error("重复次数必须为 2 到 10。 ");
    payload = readBasePayload($("repeat-type").value, epsilon);
    await refreshBudget();
    const cost = epsilon * repeats;
    if (state.budget.remaining_epsilon < cost) throw new Error(`剩余预算不足，需要 ${formatNumber(cost, 2)} ε。`);
  } catch (error) {
    showMessage(error.message, "error");
    return;
  }
  setButtonBusy(button, true, "实验运行中...");
  const values = [];
  try {
    for (let index = 1; index <= repeats; index += 1) {
      try {
        const { task, result } = await executeTask(payload, false);
        const value = Number(result.result.value);
        values.push(value);
        appendTableRow($("repeat-body"), [index, task.task_id, epsilon, formatNumber(value), `${task.duration_ms} ms`, task.status]);
      } catch (error) {
        appendTableRow($("repeat-body"), [index, "--", epsilon, "--", "--", `失败：${error.message}`]);
        break;
      }
    }
    renderRepeatStats(values);
    await refreshRecentTasks();
  } finally {
    setButtonBusy(button, false, "实验运行中...");
    await refreshBudget();
  }
}

function renderRepeatStats(values) {
  const node = $("repeat-stats");
  clearNode(node);
  if (!values.length) return;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.length > 1
    ? values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1)
    : 0;
  [["平均值", mean], ["最小值", Math.min(...values)], ["最大值", Math.max(...values)], ["样本标准差", Math.sqrt(variance)]]
    .forEach(([label, value]) => appendDetail(node, label, formatNumber(value)));
}

async function runEpsilonComparison() {
  const button = $("run-epsilon");
  const epsilons = [0.5, 1, 2, 4];
  try {
    await refreshBudget();
    if (state.budget.remaining_epsilon < 15) throw new Error("剩余预算不足，epsilon 对比需要 15.0 ε。 ");
    readBasePayload($("repeat-type").value, 1);
  } catch (error) {
    showMessage(error.message, "error");
    return;
  }
  setButtonBusy(button, true, "对比运行中...");
  clearNode($("epsilon-body"));
  try {
    for (const epsilon of epsilons) {
      const results = [];
      const times = [];
      for (let run = 0; run < 2; run += 1) {
        const payload = readBasePayload($("repeat-type").value, epsilon);
        const { task, result } = await executeTask(payload, false);
        results.push(Number(result.result.value));
        times.push(Number(task.duration_ms || 0));
      }
      appendTableRow($("epsilon-body"), [epsilon, formatNumber(results[0]), formatNumber(results[1]), formatNumber(Math.abs(results[0] - results[1])), `${formatNumber((times[0] + times[1]) / 2, 1)} ms`]);
    }
    await refreshRecentTasks();
  } catch (error) {
    showMessage(`epsilon 对比中止：${error.message}`, "error");
  } finally {
    setButtonBusy(button, false, "对比运行中...");
    await refreshBudget();
  }
}

async function runInvalidTest(testName, button) {
  setButtonBusy(button, true, "请求中...");
  let before = null;
  let after = null;
  let status = 0;
  let message = "请求意外成功";
  const labels = {
    "epsilon-zero": "epsilon = 0",
    "epsilon-high": "epsilon = 6",
    "no-parties": "不选择园区",
    "bad-time": "结束时间早于开始时间",
  };
  const payload = {
    query_type: "SUM",
    parties: ["ORG_A", "ORG_B", "ORG_C"],
    start_time: "2012-11-11T00:00:00",
    end_time: "2012-11-12T00:00:00",
    group_by: null,
    epsilon: 1.0,
  };
  if (testName === "epsilon-zero") payload.epsilon = 0;
  if (testName === "epsilon-high") payload.epsilon = 6;
  if (testName === "no-parties") payload.parties = [];
  if (testName === "bad-time") payload.end_time = "2012-11-10T00:00:00";
  try {
    before = (await refreshBudget()).remaining_epsilon;
    const response = await apiRequest("/api/v1/tasks", { method: "POST", body: JSON.stringify(payload) }, 65000);
    status = response.status;
  } catch (error) {
    status = error.status;
    message = error.message;
  } finally {
    try { after = (await refreshBudget()).remaining_epsilon; } catch { after = "读取失败"; }
    appendTableRow($("invalid-body"), [labels[testName], status || "网络错误", message, before, after]);
    setButtonBusy(button, false, "请求中...");
  }
}

async function refreshRecentTasks() {
  const { data } = await apiRequest("/api/v1/tasks?limit=10");
  const body = $("recent-body");
  clearNode(body);
  data.forEach((task) => {
    const row = appendTableRow(body, [task.task_id, task.query_type, task.status, task.calculation_mode, task.epsilon, displayValue(task.sensitivity), formatDate(task.created_at), task.duration_ms ? `${task.duration_ms} ms` : "--"], "clickable");
    row.tabIndex = 0;
    row.addEventListener("click", () => loadExistingTask(task.task_id));
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") loadExistingTask(task.task_id); });
  });
}

async function loadExistingTask(taskId) {
  try {
    const { data: task } = await apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
    renderTask(task);
    if (task.status === "COMPLETED") {
      const { data: result } = await apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}/result`);
      renderResult(result, task);
    }
    await loadAudit(taskId);
  } catch (error) {
    showMessage(`加载任务失败：${error.message}`, "error");
  }
}

async function loadAudit(taskId) {
  const details = $("audit-details");
  clearNode(details);
  try {
    const { data } = await apiRequest(`/api/v1/audit/events/${encodeURIComponent(taskId)}`);
    Object.entries(data).forEach(([label, value]) => appendDetail(details, label, label === "created_at" ? formatDate(value) : value));
  } catch (error) {
    appendDetail(details, "状态", `审计记录不可用：${error.message}`);
  }
}

async function refreshAll() {
  const button = $("refresh-all");
  setButtonBusy(button, true, "刷新中...");
  hideMessage();
  const results = await Promise.allSettled([refreshHealth(), refreshBudget(), refreshRecentTasks()]);
  const failures = results.filter((item) => item.status === "rejected");
  if (failures.length) showMessage(`部分状态刷新失败：${failures.map((item) => item.reason.message).join("；")}`, "error");
  setButtonBusy(button, false, "刷新中...");
}

function bindEvents() {
  $("query-type").addEventListener("change", () => {
    const isSeries = $("query-type").value === "TIME_SERIES";
    $("group-by").disabled = !isSeries;
    if (!isSeries) $("group-by").value = "";
  });
  $("query-form").addEventListener("submit", (event) => {
    event.preventDefault();
    try { showConfirmation(readBasePayload()); } catch (error) { showMessage(error.message, "error"); }
  });
  $("confirm-dialog").addEventListener("close", () => {
    if ($("confirm-dialog").returnValue === "confirm" && state.pendingPayload) submitMainTask(state.pendingPayload);
    state.pendingPayload = null;
  });
  $("stop-polling").addEventListener("click", () => { state.pollCancelled = true; });
  $("refresh-all").addEventListener("click", refreshAll);
  $("refresh-budget").addEventListener("click", () => refreshBudget().catch((error) => showMessage(error.message, "error")));
  $("check-services").addEventListener("click", () => refreshHealth().catch((error) => showMessage(error.message, "error")));
  $("refresh-tasks").addEventListener("click", () => refreshRecentTasks().catch((error) => showMessage(error.message, "error")));
  $("repeat-epsilon").addEventListener("input", repeatCost);
  $("repeat-count").addEventListener("input", repeatCost);
  $("run-repeat").addEventListener("click", runRepeatExperiment);
  $("clear-repeat").addEventListener("click", () => { clearNode($("repeat-body")); clearNode($("repeat-stats")); });
  $("run-epsilon").addEventListener("click", runEpsilonComparison);
  document.querySelectorAll(".invalid-test").forEach((button) => button.addEventListener("click", () => runInvalidTest(button.dataset.test, button)));
  window.addEventListener("beforeunload", () => { state.pageClosing = true; state.pollCancelled = true; });
}

function startClock() {
  const update = () => { $("current-time").textContent = new Date().toLocaleString("zh-CN", { hour12: false }); };
  update();
  window.setInterval(update, 1000);
  $("backend-address").textContent = `后端：${window.location.origin}`;
}

async function initialize() {
  startClock();
  bindEvents();
  repeatCost();
  await refreshAll();
}

initialize().catch((error) => showMessage(`页面初始化失败：${error.message}`, "error"));
