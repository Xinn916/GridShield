import { test } from "node:test";
import assert from "node:assert/strict";

const {
  buildSeriesChartData,
  chineseLabel,
  fmtDate,
  fmtEpsilon,
  fmtDuration,
  privacyRows,
  timeSeriesMetrics,
} = await import("../src/utils/format.js");

test("buildSeriesChartData only uses backend noisy buckets", () => {
  const buckets = [
    { timestamp: "2012-11-11T00:00:00", value: 12.5 },
    { timestamp: "2012-11-11T01:00:00", value: 18.2 },
  ];
  const chart = buildSeriesChartData(buckets);
  assert.equal(chart.labels.length, 2);
  assert.deepEqual(chart.values, [12.5, 18.2]);
  assert.deepEqual(buildSeriesChartData(null), { labels: [], values: [] });
});

test("privacy enum values map to Chinese labels", () => {
  assert.equal(chineseLabel("DISTRIBUTED_DP"), "分布式差分隐私");
  assert.equal(chineseLabel("distributed_laplace"), "分布式拉普拉斯机制");
  assert.equal(chineseLabel("distributed_vector_laplace"), "分布式向量拉普拉斯机制");
  assert.equal(chineseLabel("household"), "家庭级隐私保护");
  assert.equal(chineseLabel("non_negative_clamp"), "非负后处理");
  assert.equal(chineseLabel("load_metrics"), "负荷指标后处理");
});

test("privacyRows exposes only safe metadata", () => {
  const task = {
    task_id: "TASK-1",
    status: "COMPLETED",
    query_type: "SUM",
    parties: ["ORG_A", "ORG_B"],
    calculation_mode: "DISTRIBUTED_DP",
    epsilon: 1.0,
    sensitivity: 240,
    privacy_unit: "household",
    mechanism: "distributed_laplace",
    duration_ms: 812,
  };
  const result = {
    privacy: { post_processing: ["non_negative_clamp"] },
    result: { value: 123.4 },
  };
  const rows = privacyRows(task, result);
  const text = JSON.stringify(rows);
  assert.equal(rows.find((r) => r.k === "计算模式").v, "分布式差分隐私");
  assert.equal(rows.find((r) => r.k === "噪声机制").v, "分布式拉普拉斯机制");
  assert.equal(rows.find((r) => r.k === "后处理").v, "非负后处理");
  assert.equal(rows.find((r) => r.k === "参与园区").v, "ORG_A、ORG_B");
  assert.equal(rows.find((r) => r.k === "执行时间").v, "812 ms");
  assert.ok(!text.includes("share"));
  assert.ok(!text.includes("noise_partial"));
});

test("timeSeriesMetrics formats backend metrics", () => {
  const metrics = {
    peak_value: 20,
    peak_timestamp: "2012-11-11T18:00:00",
    valley_value: 5,
    valley_timestamp: "2012-11-11T03:00:00",
    peak_valley_difference: 15,
    average_load: 12,
    load_factor: 0.6,
  };
  const rows = timeSeriesMetrics(metrics);
  assert.equal(rows[0].value, "20");
  assert.equal(rows[5].value, "12");
  assert.equal(rows[6].value, "60%");
  assert.equal(timeSeriesMetrics(null).length, 0);
});

test("number and duration formatting helpers", () => {
  assert.equal(fmtEpsilon(1), "1 ε");
  assert.equal(fmtEpsilon(0.123), "0.12 ε");
  assert.equal(fmtDuration(812), "812 ms");
  assert.equal(fmtDuration(2180), "2.18 s");
  assert.equal(fmtDuration(null), "—");
});

test("catalog dates omit time without changing the source value", () => {
  const source = "2012-11-11T00:00:00";
  assert.equal(fmtDate(source), "2012/11/11");
  assert.equal(source, "2012-11-11T00:00:00");
  assert.equal(fmtDate(null), "—");
});
