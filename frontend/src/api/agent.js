import { request } from "./client.js";

// Agent 接口只调用本项目 control-plane；浏览器中不出现任何 DeepSeek URL / Key / 模型名。

function nullableText(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

export function normalizeAgentCurrentForm(currentForm) {
  if (!currentForm || typeof currentForm !== "object") return null;
  const epsilon = currentForm.epsilon;
  const numericEpsilon = epsilon === "" || epsilon === null || epsilon === undefined
    ? null
    : Number(epsilon);

  return {
    query_type: nullableText(currentForm.query_type),
    parties: Array.isArray(currentForm.parties)
      ? currentForm.parties.map((party) => nullableText(party)).filter(Boolean)
      : [],
    start_time: nullableText(currentForm.start_time),
    end_time: nullableText(currentForm.end_time),
    epsilon: Number.isFinite(numericEpsilon) ? numericEpsilon : null,
    group_by: nullableText(currentForm.group_by),
  };
}

export function parseNaturalLanguageQuery(text, currentForm, signal, context = {}) {
  return request("/api/v1/agent/parse-query", {
    method: "POST",
    body: {
      text,
      current_form: normalizeAgentCurrentForm(currentForm),
      grant_id: context.grantId || null,
      has_current_task: Boolean(context.hasCurrentTask),
      conversation_id: context.conversationId || null,
    },
    timeout: 30000,
    signal,
  });
}

export function listAgentConversations(limit = 50) {
  return request(`/api/v1/agent/conversations?limit=${Number(limit) || 50}`, { timeout: 10000 });
}

export function createAgentConversation() {
  return request("/api/v1/agent/conversations", { method: "POST", timeout: 10000 });
}

export function getAgentConversation(conversationId, { signal } = {}) {
  return request(`/api/v1/agent/conversations/${encodeURIComponent(conversationId)}`, {
    timeout: 10000,
    signal,
  });
}

export function linkAgentConversationTask(conversationId, taskId) {
  return request(`/api/v1/agent/conversations/${encodeURIComponent(conversationId)}/tasks/${encodeURIComponent(taskId)}`, {
    method: "POST",
    timeout: 10000,
  });
}

export function explainResult(payload, signal) {
  return request("/api/v1/agent/explain-result", {
    method: "POST",
    body: payload,
    timeout: 30000,
    signal,
  });
}

export function governanceAdvice(taskId, signal) {
  return request("/api/v1/agent/governance-advice", {
    method: "POST",
    body: { task_id: taskId },
    timeout: 30000,
    signal,
  });
}
