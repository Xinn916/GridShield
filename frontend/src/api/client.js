import { getApiBaseUrl, isMockEnabled } from "../config.js";
import { formatApiError } from "../utils/errors.js";

export class ApiError extends Error {
  constructor(message, { status = null, code = null, detail = null, timedOut = false, networkError = false } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.timedOut = timedOut;
    this.networkError = networkError;
  }
}

/**
 * 统一请求层。
 * - 统一 baseURL（API_BASE_URL）
 * - 超时控制 + AbortController（支持外部取消）
 * - JSON 序列化/解析
 * - HTTP 错误、网络错误、超时分别解析为 ApiError
 * - mock 未显式开启时绝不回退到假数据
 */
export async function request(path, { method = "GET", body = null, timeout = 10000, signal = null, headers = {} } = {}) {
  if (isMockEnabled()) {
    throw new ApiError("mock 模式已显式开启（VITE_USE_MOCK=true），统一 API 客户端已禁用", { code: "MOCK_ENABLED" });
  }

  const controller = new AbortController();
  const baseUrl = getApiBaseUrl();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout);
  const onOuterAbort = () => controller.abort();

  if (signal) {
    if (signal.aborted) {
      clearTimeout(timer);
      throw new ApiError("请求已取消", { code: "ABORTED" });
    }
    signal.addEventListener("abort", onOuterAbort, { once: true });
  }

  try {
    // 支持 VITE_API_BASE_URL=/api 的反代模式：path 已带 base 前缀时不再拼接。
    const url = baseUrl && path.startsWith(baseUrl) ? path : `${baseUrl}${path}`;
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    const response = await fetch(url, {
      method,
      credentials: "include",
      headers: isFormData ? { ...headers } : { "Content-Type": "application/json", ...headers },
      body: body === null || body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!response.ok) {
      throw new ApiError(formatApiError(data, `HTTP ${response.status} ${response.statusText}`.trim()), {
        status: response.status,
        detail: data,
      });
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error && (error.name === "AbortError" || error.name === "TimeoutError")) {
      if (timedOut) {
        throw new ApiError(`请求超时（${timeout}ms）：${path}`, { code: "TIMEOUT", timedOut: true });
      }
      throw new ApiError("请求已取消", { code: "ABORTED" });
    }
    if (error instanceof TypeError) {
      throw new ApiError(`网络错误：无法连接后端服务 ${baseUrl}（${path}）`, {
        code: "NETWORK",
        networkError: true,
      });
    }
    throw new ApiError(formatApiError(error), { code: "UNKNOWN" });
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onOuterAbort);
  }
}
