"""DeepSeek（OpenAI 兼容）HTTP 客户端。

- 复用项目已声明的 httpx 依赖，不引入第二套 SDK；
- API Key 只从后端配置读取，任何情况下不打印、不记录、不返回；
- 超时与 5xx 最多安全重试一次；4xx（含认证/限流）不重试；
- 只返回解析后的 JSON dict，原始响应体不对外暴露。
"""

import json
from typing import Any

import httpx


class DeepSeekError(RuntimeError):
    """模型服务安全错误基类，message 为可展示的中文文案。"""


class DeepSeekNotConfiguredError(DeepSeekError):
    pass


class DeepSeekAuthError(DeepSeekError):
    pass


class DeepSeekRateLimitError(DeepSeekError):
    pass


class DeepSeekTimeoutError(DeepSeekError):
    pass


class DeepSeekServerError(DeepSeekError):
    pass


class DeepSeekInvalidResponseError(DeepSeekError):
    pass


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout: float = 20.0,
        max_tokens: int = 1200,
        temperature: float = 0.0,
        http_client: httpx.Client | None = None,
    ):
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.model = model or "deepseek-v4-flash"
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = http_client or httpx.Client(timeout=timeout)

    def chat_json(self, system_prompt: str, user_text: str) -> dict[str, Any]:
        if not self.api_key:
            raise DeepSeekNotConfiguredError("DeepSeek API 未配置")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        last_error: DeepSeekError | None = None
        for _attempt in (1, 2):  # 超时/5xx 最多一次重试
            try:
                response = self._client.post(
                    url, json=payload, headers=headers, timeout=self.timeout
                )
            except httpx.TimeoutException:
                last_error = DeepSeekTimeoutError("模型请求超时，请稍后重试")
                continue
            except httpx.HTTPError:
                last_error = DeepSeekError("网络连接失败，无法访问模型服务")
                continue

            if response.status_code in (401, 403):
                raise DeepSeekAuthError("模型认证失败，请检查后端 API Key 配置")
            if response.status_code == 429:
                raise DeepSeekRateLimitError("模型服务繁忙，请稍后重试")
            if response.status_code >= 500:
                last_error = DeepSeekServerError("模型服务异常，请稍后重试")
                continue
            if response.status_code != 200:
                raise DeepSeekError("模型服务返回错误，请稍后重试")

            try:
                data = response.json()
            except ValueError:
                raise DeepSeekInvalidResponseError("模型返回非法 JSON")
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            if not str(content).strip():
                raise DeepSeekInvalidResponseError("模型返回空内容")
            try:
                parsed = json.loads(content)
            except ValueError:
                raise DeepSeekInvalidResponseError("模型返回非法 JSON")
            if not isinstance(parsed, dict):
                raise DeepSeekInvalidResponseError("模型返回非法 JSON")
            return parsed

        raise last_error or DeepSeekError("模型请求失败，请稍后重试")
