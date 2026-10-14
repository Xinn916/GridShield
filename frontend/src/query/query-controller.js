import { QUERY_MAX_WAIT_MS, QUERY_POLL_INTERVAL_MS } from "../config.js";
import { getBudget } from "../api/privacy.js";
import { createTask, getTask, getTaskResult } from "../api/tasks.js";
import { createTaskPoller } from "../utils/polling.js";
import { formatApiError } from "../utils/errors.js";

export const QUERY_TYPES = ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"];
export const PARTY_IDS = ["ORG_A", "ORG_B", "ORG_C"];
export const GROUP_BYS = ["30m", "1h", "1d"];

// 非 TIME_SERIES 查询时 group_by 必须为空；TIME_SERIES 必须使用用户选择的时间粒度。
export function resolveGroupBy(queryType, value) {
  return queryType === "TIME_SERIES" ? value : null;
}

function toIsoLocal(value) {
  if (!value) return null;
  const text = String(value);
  return /:\d{2}:\d{2}$/.test(text) ? text : `${text}:00`;
}

export function toTaskPayload(form) {
  const payload = {
    query_type: form.query_type,
    parties: Array.isArray(form.parties) ? [...form.parties] : [],
    start_time: toIsoLocal(form.start_time),
    end_time: toIsoLocal(form.end_time),
    epsilon: Number(form.epsilon),
  };
  if (form.grant_id) {
    payload.grant_id = form.grant_id;
  }
  // 只有 TIME_SERIES 才携带 group_by，SUM/COUNT/AVERAGE 的请求 JSON 中不出现该字段。
  if (form.query_type === "TIME_SERIES") {
    payload.group_by = form.group_by;
  }
  return payload;
}

export function validateQueryForm(form) {
  const errors = [];
  const queryType = form.query_type;
  if (!QUERY_TYPES.includes(queryType)) {
    errors.push("查询类型必须是 SUM / COUNT / AVERAGE / TIME_SERIES");
  }
  const parties = Array.isArray(form.parties) ? form.parties : [];
  if (parties.length === 0) {
    errors.push("请至少选择一个园区");
  }
  if (!form.start_time || !form.end_time) {
    errors.push("请填写开始时间和结束时间");
  } else if (new Date(toIsoLocal(form.start_time)).getTime() >= new Date(toIsoLocal(form.end_time)).getTime()) {
    errors.push("结束时间必须晚于开始时间");
  }
  const epsilon = Number(form.epsilon);
  if (!Number.isFinite(epsilon) || epsilon <= 0 || epsilon > 5) {
    errors.push("隐私预算 ε 必须在 (0, 5] 范围内");
  }
  if (queryType === "TIME_SERIES" && !GROUP_BYS.includes(form.group_by)) {
    errors.push("TIME_SERIES 必须选择时间粒度 group_by（30m / 1h / 1d）");
  }
  if (queryType !== "TIME_SERIES" && form.group_by) {
    errors.push("非 TIME_SERIES 查询时 group_by 必须为空");
  }
  return { ok: errors.length === 0, errors };
}

export class QueryController {
  constructor({
    onCreateTask = createTask,
    onGetTask = getTask,
    onGetResult = getTaskResult,
    onGetBudget = getBudget,
    pollIntervalMs = QUERY_POLL_INTERVAL_MS,
    maxWaitMs = QUERY_MAX_WAIT_MS,
  } = {}) {
    this._createTask = onCreateTask;
    this._getTask = onGetTask;
    this._getResult = onGetResult;
    this._getBudget = onGetBudget;
    this._pollIntervalMs = pollIntervalMs;
    this._maxWaitMs = maxWaitMs;

    this._abort = new AbortController();
    this._poller = null;
    this._submitting = false;
    this._phase = "idle";
    this._task = null;
    this._result = null;
    this._budget = null;
    this._error = null;
    this._lastPayload = null;
  }

  get phase() {
    return this._phase;
  }

  get task() {
    return this._task;
  }

  get result() {
    return this._result;
  }

  get budget() {
    return this._budget;
  }

  get error() {
    return this._error;
  }

  get lastPayload() {
    return this._lastPayload;
  }

  isBusy() {
    return this._submitting || this._phase === "polling";
  }

  async submit(form, handlers = {}) {
    if (this._submitting) {
      return { ok: false, reason: "BUSY" };
    }
    const validation = validateQueryForm(form);
    if (!validation.ok) {
      this._phase = "validation_error";
      this._error = { type: "VALIDATION", messages: validation.errors };
      handlers.onState?.({ phase: this._phase, errors: validation.errors });
      return { ok: false, reason: "VALIDATION", errors: validation.errors };
    }

    this._poller?.stop();
    this._abort.abort();
    this._abort = new AbortController();
    this._submitting = true;
    this._phase = "submitting";
    this._task = null;
    this._result = null;
    this._error = null;
    this._lastPayload = toTaskPayload(form);
    handlers.onState?.({ phase: "submitting" });

    try {
      const task = await this._createTask(this._lastPayload);
      this._task = task;
      this._phase = "polling";
      handlers.onState?.({ phase: "polling", task });

      this._poller = createTaskPoller({
        taskId: task.task_id,
        fetchTask: (taskId) => this._getTask(taskId, { signal: this._abort.signal }),
        onUpdate: (updated) => {
          this._task = updated;
          handlers.onState?.({ phase: "polling", task: updated });
        },
        onComplete: async (completed) => {
          this._phase = "completed";
          this._task = completed;
          try {
            this._result = await this._getResult(completed.task_id, { signal: this._abort.signal });
          } catch (error) {
            this._error = { type: "RESULT_FETCH", detail: formatApiError(error) };
          }
          await this.refreshBudget();
          this._submitting = false;
          handlers.onState?.({
            phase: "completed",
            task: completed,
            result: this._result,
            budget: this._budget,
            error: this._error,
          });
        },
        onFailed: async (failed) => {
          this._phase = "failed";
          this._task = failed;
          this._error = { type: "TASK_FAILED", detail: failed.error || "任务执行失败" };
          await this.refreshBudget();
          this._submitting = false;
          handlers.onState?.({ phase: "failed", task: failed, error: this._error });
        },
        onTimeout: (last) => {
          this._phase = "timeout";
          this._task = last || this._task;
          this._error = {
            type: "TIMEOUT",
            detail: `等待任务结果超过 ${Math.round(this._maxWaitMs / 1000)} 秒，已停止轮询；任务可能仍在后台执行，系统不会自动重复创建任务。`,
          };
          this._submitting = false;
          handlers.onState?.({ phase: "timeout", task: this._task, error: this._error });
        },
        onError: async (error) => {
          this._phase = "error";
          this._error = { type: "NETWORK", detail: formatApiError(error) };
          await this.refreshBudget();
          this._submitting = false;
          handlers.onState?.({ phase: "error", error: this._error });
        },
        intervalMs: this._pollIntervalMs,
        maxWaitMs: this._maxWaitMs,
      });
      this._poller.start();
      return { ok: true, taskId: task.task_id };
    } catch (error) {
      this._submitting = false;
      this._phase = error && error.status === 409 ? "budget_insufficient" : "error";
      this._error = {
        type: this._phase === "budget_insufficient" ? "BUDGET_INSUFFICIENT" : "REQUEST",
        detail: formatApiError(error, "任务创建失败"),
        status: error?.status || null,
      };
      if (this._phase === "budget_insufficient") {
        await this.refreshBudget();
      }
      handlers.onState?.({ phase: this._phase, error: this._error });
      return { ok: false, reason: this._phase };
    }
  }

  async refreshBudget() {
    try {
      this._budget = await this._getBudget("demo-analyst", "GLOBAL", { signal: this._abort.signal });
    } catch {
      // 预算刷新失败不覆盖已有错误状态，页面保留上次预算或显示加载失败。
    }
    return this._budget;
  }

  dispose() {
    this._poller?.stop();
    this._poller = null;
    this._abort.abort();
  }
}
