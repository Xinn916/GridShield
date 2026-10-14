// Agent 草案应用逻辑：纯函数，不依赖 DOM，便于测试。

export const AGENT_FIELDS = ["query_type", "parties", "start_time", "end_time", "epsilon", "group_by"];

const MISSING_FIELD_LABELS = {
  query_type: "查询类型",
  parties: "数据方",
  start_time: "开始时间",
  end_time: "结束时间",
  epsilon: "隐私预算",
  group_by: "时间粒度",
};

function sameParties(left, right) {
  const a = Array.isArray(left) ? [...left].sort() : [];
  const b = Array.isArray(right) ? [...right].sort() : [];
  return JSON.stringify(a) === JSON.stringify(b);
}

function sameValue(left, right) {
  if (left === null || left === undefined) left = "";
  if (right === null || right === undefined) right = "";
  return String(left) === String(right);
}

/**
 * 将后端 Agent 草案应用到当前表单。
 * - TIME_SERIES：group_by 取解析值；缺失时保留用户当前选择。
 * - SUM/COUNT/AVERAGE：group_by 强制清空。
 * - 缺失字段不覆盖当前表单，交由用户确认。
 * 返回 { form, changed }，changed 为本次被修改的字段名。
 */
export function applyDraft(current, draft) {
  const form = { ...current };
  const changed = [];
  const queryType = draft?.query_type || current?.query_type;

  if (draft?.query_type) {
    form.query_type = draft.query_type;
    changed.push("query_type");
  }
  if (Array.isArray(draft?.parties) && draft.parties.length > 0 && !sameParties(current?.parties, draft.parties)) {
    form.parties = [...draft.parties];
    changed.push("parties");
  }
  for (const field of ["start_time", "end_time", "epsilon"]) {
    const value = draft?.[field];
    if (value !== null && value !== undefined && value !== "" && !sameValue(current?.[field], value)) {
      form[field] = value;
      changed.push(field);
    }
  }
  if (queryType === "TIME_SERIES") {
    const groupBy = draft?.group_by;
    if (groupBy && !sameValue(current?.group_by, groupBy)) {
      form.group_by = groupBy;
      changed.push("group_by");
    }
  } else if (current?.group_by) {
    form.group_by = null;
    changed.push("group_by");
  } else {
    form.group_by = null;
  }
  return { form, changed };
}

export function draftSummary(draft, response) {
  const rows = [];
  if (draft?.query_type) rows.push(`查询类型：${draft.query_type}`);
  if (Array.isArray(draft?.parties) && draft.parties.length) rows.push(`园区：${draft.parties.join("、")}`);
  if (draft?.start_time) rows.push(`开始时间：${String(draft.start_time).slice(0, 16)}`);
  if (draft?.end_time) rows.push(`结束时间：${String(draft.end_time).slice(0, 16)}`);
  if (draft?.group_by) rows.push(`时间粒度：${draft.group_by}`);
  if (draft?.epsilon != null) rows.push(`隐私预算 ε：${draft.epsilon}`);
  const missing = Array.isArray(response?.missing_fields) ? response.missing_fields : [];
  const warnings = Array.isArray(response?.warnings) ? response.warnings : [];
  return {
    rows,
    missing: missing.map((field) => MISSING_FIELD_LABELS[field] || field),
    warnings,
  };
}
