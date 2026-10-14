import { request } from "./client.js";

// GET /api/v1/parties —— 三个园区节点状态与元数据
export function listParties() {
  return request("/api/v1/parties", { timeout: 10000 });
}
