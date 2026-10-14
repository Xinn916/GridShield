export const DEFAULT_API_ERROR_MESSAGE = "请求失败，请稍后重试";

function safeText(value) {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || /^(?:undefined|null|nan|\[object Object\])$/i.test(text)) return null;
  if (/<!doctype\s+html|<html\b|<head\b|<body\b|<title\b|<h[1-6]\b|<script\b/i.test(text)) return null;
  return text;
}

function arrayDetail(items) {
  const messages = items.map((item) => {
    const direct = safeText(item);
    if (direct) return direct;
    if (!item || typeof item !== "object") return null;
    const message = safeText(item.msg) || safeText(item.message) || safeText(item.detail);
    if (!message) return null;
    const location = Array.isArray(item.loc)
      ? item.loc.filter((part) => part !== "body" && part !== "query" && part !== "path").join(".")
      : "";
    return location ? `${location}：${message}` : message;
  }).filter(Boolean);
  return messages.length ? messages.join("；") : null;
}

function detailText(value) {
  if (Array.isArray(value)) return arrayDetail(value);
  return safeText(value);
}

export function formatApiError(error, fallback = DEFAULT_API_ERROR_MESSAGE) {
  const safeFallback = safeText(fallback) || DEFAULT_API_ERROR_MESSAGE;
  const responseData = error?.response?.data;
  const responseMessage = detailText(responseData?.detail) || detailText(responseData?.message);
  if (responseMessage) return responseMessage;

  const direct = safeText(error);
  if (direct) return direct;

  const message = detailText(error?.message);
  if (message) return message;

  const detail = detailText(error?.detail);
  if (detail) return detail;

  return safeFallback;
}
