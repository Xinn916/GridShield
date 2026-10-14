// 统一前端运行配置：Vite 注入 import.meta.env；Node 测试环境回退到 process.env。
const viteEnv = typeof import.meta !== "undefined" && import.meta.env ? import.meta.env : {};
const nodeEnv = typeof process !== "undefined" && process.env ? process.env : {};

function str(name, fallback) {
  const value = viteEnv[name] ?? nodeEnv[name];
  return value === undefined || value === "" ? fallback : String(value);
}

export function getApiBaseUrl() {
  return str("VITE_API_BASE_URL", "http://127.0.0.1:8000").replace(/\/+$/, "");
}

// mock 必须显式开启（VITE_USE_MOCK=true），默认关闭。
export function isMockEnabled() {
  return str("VITE_USE_MOCK", "false") === "true";
}

export function getPollIntervalMs() {
  return Number(str("VITE_QUERY_POLL_INTERVAL_MS", "1000"));
}

export function getMaxWaitMs() {
  return Number(str("VITE_QUERY_MAX_WAIT_MS", "60000"));
}

// 应用启动时的固定值（页面渲染使用）
export const API_BASE_URL = getApiBaseUrl();
export const USE_MOCK = isMockEnabled();

export const QUERY_POLL_INTERVAL_MS = Number(str("VITE_QUERY_POLL_INTERVAL_MS", "1000"));
export const QUERY_MAX_WAIT_MS = Number(str("VITE_QUERY_MAX_WAIT_MS", "60000"));
