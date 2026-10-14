// 兼容层：旧代码从 "./api.js" 导入的 request / endpoints 统一指向新的真实 API 客户端。
export { request, ApiError, isMockEnabled } from "./api/client.js";
export { endpoints } from "./api/endpoints.js";
export { API_BASE_URL, USE_MOCK } from "./config.js";
