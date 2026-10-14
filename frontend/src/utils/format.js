// 展示层格式化：数字、时长、时间、枚举中文映射、图表数据与隐私说明行。

export const PRIVACY_LABELS = {
  DISTRIBUTED_DP: "分布式差分隐私",
  SECRET_SHARE: "秘密共享",
  PLAIN: "明文对照",
  distributed_laplace: "分布式拉普拉斯机制",
  distributed_vector_laplace: "分布式向量拉普拉斯机制",
  household: "家庭级隐私保护",
  non_negative_clamp: "非负后处理",
  load_metrics: "负荷指标后处理",
  none: "无噪声机制",
};

export const STATUS_LABELS = {
  CREATED: "已创建",
  DISPATCHING: "任务分发中",
  LOCAL_COMPUTING: "本地计算中",
  SHARING: "秘密共享中",
  AGGREGATING: "节点聚合中",
  RECONSTRUCTING: "结果重构中",
  COMPLETED: "已完成",
  FAILED: "失败",
};

export const QUERY_TYPE_LABELS = {
  SUM: "求和 SUM",
  COUNT: "计数 COUNT",
  AVERAGE: "均值 AVERAGE",
  TIME_SERIES: "时间序列 TIME_SERIES",
};

export function chineseLabel(key, fallback = "—") {
  if (key === null || key === undefined || key === "") return fallback;
  return PRIVACY_LABELS[key] || String(key);
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || "—";
}

export function queryTypeLabel(queryType) {
  return QUERY_TYPE_LABELS[queryType] || queryType || "—";
}

export function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(Number(value));
}

export function fmtEpsilon(value) {
  return value === null || value === undefined ? "—" : `${fmtNumber(value, 2)} ε`;
}

export function fmtDuration(ms) {
  if (ms === null || ms === undefined) return "—";
  const value = Number(ms);
  if (Number.isNaN(value)) return "—";
  if (value < 1000) return `${value.toFixed(0)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const matched = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (matched) return `${matched[1]}/${matched[2]}/${matched[3]}`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
}

export function fmtShortTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// TIME_SERIES 折线图数据：只取后端返回的带噪 buckets。
export function buildSeriesChartData(buckets) {
  const list = Array.isArray(buckets) ? buckets : [];
  return {
    labels: list.map((item) => fmtShortTime(item.timestamp)),
    values: list.map((item) => Math.max(0, Number(item.value) || 0)),
  };
}

export function formatSensitivity(sensitivity) {
  if (sensitivity === null || sensitivity === undefined) return "—";
  if (typeof sensitivity === "number") return fmtNumber(sensitivity, 2);
  if (typeof sensitivity === "object") {
    return Object.entries(sensitivity)
      .map(([key, value]) => `${key}=${fmtNumber(value, 2)}`)
      .join("，");
  }
  return String(sensitivity);
}

// 隐私说明区域：只展示后端返回的任务与结果元数据。
export function privacyRows(task, result) {
  if (!task) return [];
  const postProcessing =
    result && result.privacy && Array.isArray(result.privacy.post_processing)
      ? result.privacy.post_processing.map((item) => chineseLabel(item)).join("、")
      : "无";
  return [
    { k: "计算模式", v: chineseLabel(task.calculation_mode) },
    { k: "隐私预算 ε", v: fmtEpsilon(task.epsilon) },
    { k: "敏感度", v: formatSensitivity(task.sensitivity) },
    { k: "隐私保护单位", v: chineseLabel(task.privacy_unit) },
    { k: "噪声机制", v: chineseLabel(task.mechanism) },
    { k: "后处理", v: postProcessing },
    { k: "参与园区", v: Array.isArray(task.parties) ? task.parties.join("、") : "—" },
    { k: "执行时间", v: fmtDuration(task.duration_ms) },
  ];
}

export function kvRowsHtml(rows) {
  return `<div class="kv-table">${rows
    .map((row) => `<div class="kv-row"><div class="k">${row.k}</div><div class="v">${row.v}</div></div>`)
    .join("")}</div>`;
}

export function timeSeriesMetrics(metrics) {
  if (!metrics) return [];
  return [
    { name: "峰值负荷 (kWh)", value: fmtNumber(metrics.peak_value) },
    { name: "峰值时间", value: fmtDateTime(metrics.peak_timestamp) },
    { name: "谷值负荷 (kWh)", value: fmtNumber(metrics.valley_value) },
    { name: "谷值时间", value: fmtDateTime(metrics.valley_timestamp) },
    { name: "峰谷差 (kWh)", value: fmtNumber(metrics.peak_valley_difference) },
    { name: "平均负荷 (kWh)", value: fmtNumber(metrics.average_load) },
    { name: "负荷率", value: metrics.load_factor === null || metrics.load_factor === undefined ? "—" : fmtNumber(metrics.load_factor * 100, 1) + "%" },
  ];
}
