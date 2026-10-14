"""自然语言查询解析与结果解释编排。

安全边界：
- 模型输出只是“草案”，必须经过白名单二次校验；
- 解析接口不创建任务、不预留/消费预算、不访问园区节点、不写任务审计；
- 日志只记录元数据（字符数、SHA-256、意图、耗时），不记录原文、Key、完整响应。
"""

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable

from common.enums import GroupBy, OrganizationId, QueryType
from common.schemas import (
    AgentExplainRequest,
    AgentExplainResponse,
    AgentParseRequest,
    AgentParseResponse,
    GovernanceAdviceContext,
    GovernanceAdviceResponse,
    TaskDraft,
)
from control_plane.services.agent_prompts import (
    EXPLAIN_SYSTEM_PROMPT,
    GOVERNANCE_SYSTEM_PROMPT,
    PARSE_SYSTEM_PROMPT,
)
from control_plane.services.deepseek_client import (
    DeepSeekClient,
    DeepSeekError,
    DeepSeekInvalidResponseError,
)


logger = logging.getLogger(__name__)

# 数据集可用时间范围（与 data_processed 一致，左闭右开）
DATASET_START = datetime(2012, 11, 11)
DATASET_END = datetime(2012, 12, 11)

# 模型输出中禁止出现的字段（键名匹配，避免模型夹带越权参数）
FORBIDDEN_FIELD_PATTERNS = (
    "sensitivity",
    "window_cap",
    "record_cap",
    "max_records",
    "max_window",
    "budget",
    "share",
    "noise",
    "partial",
    "raw",
    "local",
    "true_value",
    "parquet",
    "secret",
    "sql",
)

INJECTION_PATTERNS = [
    re.compile(r"原始\s*(数据|记录|文件|parquet)", re.I),
    re.compile(r"\bparquet\b", re.I),
    re.compile(r"不要加噪|不加噪声|关闭差分隐私|关闭隐私保护|禁用差分隐私|去掉噪声", re.I),
    re.compile(r"(epsilon|ε)\s*(无限|无限大|∞|不要限制)", re.I),
    re.compile(r"份额|secret\s*share|partial\s*noise|局部(总量|统计|明文)|原始曲线", re.I),
    re.compile(r"window_cap|record_cap|裁剪上限|(敏感度|裁剪|贡献上限)\s*(改|调|设|增加|降低|放开)", re.I),
    re.compile(r"绕过预算|跳过预算|不扣预算|不消费预算|免预算|预算检查.*跳过", re.I),
    re.compile(r"绕过授权|跳过授权|无视授权|未授权.*(?:查询|访问)", re.I),
    re.compile(r"自动提交|直接执行|自动运行|不要确认", re.I),
    re.compile(r"重复执行|循环查询|重复.*直到|直到.*满意", re.I),
    re.compile(r"忽略(之前|所有)?规则|无视规则|越权", re.I),
]

RELATIVE_TIME_PATTERN = re.compile(r"今天|昨天|当天|最近一天|最近几天|本周|本月")
EXPLICIT_DATE_PATTERN = re.compile(r"20\d{2}\s*年|20\d{2}-\d{1,2}")
PARTY_MENTION_PATTERN = re.compile(r"园区\s*([A-Z])|ORG_([ABC])")
ALL_PARTIES_PATTERN = re.compile(r"三(?:个)?园区|所有园区|全部园区|各园区|全部数据方")
DATE_MENTION_PATTERN = re.compile(
    r"20\d{2}\s*年|20\d{2}-\d{1,2}|\d{1,2}\s*月\s*\d{1,2}\s*日|今天|昨天|当天|最近一天|本周|本月"
)
EPSILON_MENTION_PATTERN = re.compile(r"(?:epsilon|ε|隐私预算)\s*(?:为|是|=|改成|改为|调整为|设为|设置为)?\s*\d", re.I)
GROUP_BY_MENTION_PATTERN = re.compile(
    r"(?<!\d)30\s*(?:m|min|分钟)|半小时|(?<!\d)1\s*(?:h|小时)|每小时|按小时|"
    r"(?<!\d)小时(?:级|粒度|趋势|序列)?|(?<!\d)1\s*(?:d|天|日)|一天|按天|每天|日粒度",
    re.I,
)
TASK_UPDATE_PATTERN = re.compile(
    r"改成|改为|调整为|设置为|设为|只查询|仅查询|时间改|范围改|"
    r"把\s*(?:epsilon|ε|隐私预算)|"
    r"(?:修改|更新|调整|设置|设定)\s*(?:查询类型|数据方|参与方|园区|时间粒度|粒度|开始时间|起始时间|结束时间|截止时间|查询时间范围|时间范围)|"
    r"(?:时间粒度|粒度|开始时间|起始时间|结束时间|截止时间|查询时间范围|时间范围)\s*(?:为|是)",
    re.I,
)
START_TIME_UPDATE_PATTERN = re.compile(
    r"(?:开始|起始)(?:日期|时间)?(?=\s*(?:改|调整|设置|设为|为|是|用|到))",
    re.I,
)
END_TIME_UPDATE_PATTERN = re.compile(
    r"(?:结束|截止)(?:日期|时间)?(?=\s*(?:改|调整|设置|设为|为|是|用|到))",
    re.I,
)
TIME_RANGE_UPDATE_PATTERN = re.compile(
    r"(?:查询)?(?:时间|日期)范围|起止(?:日期|时间)|"
    r"(?:从|就用|那就用|用)?\s*20\d{2}.+?(?:到|至|~|～|—)\s*20\d{2}",
    re.I,
)
EXPLICIT_DATETIME_TOKEN_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?P<iso_year>20\d{2})-(?P<iso_month>\d{1,2})-(?P<iso_day>\d{1,2})"
    r"(?:(?:T|\s+)(?P<iso_hour>\d{1,2}):(?P<iso_minute>\d{2})(?::(?P<iso_second>\d{2}))?)?"
    r"|"
    r"(?P<cn_year>20\d{2})\s*年\s*(?P<cn_month>\d{1,2})\s*月\s*(?P<cn_day>\d{1,2})\s*日"
    r"(?:\s*(?P<cn_hour>\d{1,2})(?:\s*时\s*|:)(?P<cn_minute>\d{1,2})(?:\s*分|:(?P<cn_second>\d{1,2}))?)?"
    r")(?!\d)",
    re.I,
)
TASK_CONFIRM_PATTERN = re.compile(r"^(?:提交吧?|确认(?:执行|提交)?|开始(?:查询|执行)|执行吧?)\s*[。！!？?]*$", re.I)
QUERY_SIGNAL_PATTERN = re.compile(r"查询|统计|分析|计算|负荷|用电量|家庭数量|趋势|曲线", re.I)
EXPLANATION_QUESTION_PATTERN = re.compile(
    r"什么|哪些|为何|为什么|怎么|如何|有何区别|什么区别|区别是什么|"
    r"含义|意思|影响|会怎样|是否支持|能不能|可以吗|吗\s*[？?]*$",
    re.I,
)
CONTEXTUAL_UPDATE_CUE_PATTERN = re.compile(
    r"那就|就用|还是|改(?:成|为|用)?|换成|调整(?:成|为)?|设置?(?:成|为)?|用|按|就行|即可|就好",
    re.I,
)

AGENT_INTENTS = {
    "QUERY",
    "TASK_UPDATE",
    "GREETING",
    "IDENTITY",
    "HELP",
    "PRIVACY_EXPLAIN",
    "BUDGET_QUERY",
    "TASK_CONFIRM",
    "OTHER",
    "REFUSED",
}
TASK_INTENTS = {"QUERY", "TASK_UPDATE"}


class AgentRateLimitError(RuntimeError):
    pass


class InMemoryRateLimiter:
    """简单进程内限频：key（IP）每分钟最多 limit 次。"""

    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


class AgentService:
    def __init__(
        self,
        client: DeepSeekClient,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit: int = 10,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.client = client
        self.rate_limiter = rate_limiter or InMemoryRateLimiter(rate_limit, 60)
        self.now_provider = now_provider or (lambda: datetime.now())

    # ---------- 解析 ----------

    def parse_query(
        self,
        request: AgentParseRequest,
        client_key: str = "default",
        budget_context: dict[str, Any] | None = None,
    ) -> AgentParseResponse:
        if not self.rate_limiter.allow(client_key):
            raise AgentRateLimitError("请求过于频繁，请稍后再试（每分钟最多 10 次）")
        text = request.text
        request_id = uuid.uuid4().hex[:12]
        input_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        started = time.perf_counter()

        refused = self._prefilter(text)
        if refused is not None:
            self._log(request_id, text, refused.intent, True, started)
            return refused

        user_payload = {
            "text": text,
            "current_form": self._current_form_dict(request.current_form),
            "has_current_task": request.has_current_task,
            "budget_context": budget_context,
            "now": self.now_provider().isoformat(timespec="seconds"),
            "timezone": request.timezone,
            "dataset_time_range": [
                DATASET_START.isoformat(),
                DATASET_END.isoformat(),
            ],
        }
        try:
            raw = self.client.chat_json(
                PARSE_SYSTEM_PROMPT,
                json.dumps(user_payload, ensure_ascii=False),
            )
            response = self._validate_output(raw, request, budget_context)
            self._log(request_id, text, response.intent, True, started)
            return response
        except DeepSeekError:
            self._log(request_id, text, "ERROR", False, started)
            raise

    # ---------- 解释 ----------

    def explain_result(self, request: AgentExplainRequest, client_key: str = "default") -> AgentExplainResponse:
        if not self.rate_limiter.allow(f"explain:{client_key}"):
            raise AgentRateLimitError("请求过于频繁，请稍后再试（每分钟最多 10 次）")
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        summary = request.model_dump(mode="json")
        try:
            raw = self.client.chat_json(
                EXPLAIN_SYSTEM_PROMPT,
                json.dumps({"result_summary": summary}, ensure_ascii=False),
            )
            explanation = raw.get("explanation") if isinstance(raw, dict) else None
            if not explanation or not str(explanation).strip():
                raise DeepSeekInvalidResponseError("模型返回空内容")
            self._log(request_id, "", "EXPLAIN", True, started)
            return AgentExplainResponse(explanation=str(explanation).strip()[:1000])
        except DeepSeekError:
            self._log(request_id, "", "ERROR", False, started)
            raise

    def governance_advice(
        self, context: GovernanceAdviceContext, client_key: str = "default"
    ) -> GovernanceAdviceResponse:
        """Generate budget governance advice from server-built safe context only."""
        if not self.rate_limiter.allow(f"governance:{client_key}"):
            raise AgentRateLimitError("璇锋眰杩囦簬棰戠箒锛岃绋嶅悗鍐嶈瘯")
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        safe_context = context.model_dump(mode="json")
        try:
            raw = self.client.chat_json(
                GOVERNANCE_SYSTEM_PROMPT,
                json.dumps({"task_context": safe_context}, ensure_ascii=False),
            )
            if not isinstance(raw, dict):
                raise DeepSeekInvalidResponseError("model returned non-object governance advice")
            suggestions_raw = raw.get("suggestions", [])
            if not isinstance(suggestions_raw, list):
                raise DeepSeekInvalidResponseError("model returned invalid governance suggestions")
            try:
                response = GovernanceAdviceResponse(
                    task_id=context.task_id,
                    risk_level=str(raw.get("risk_level", "")).upper(),
                    summary=str(raw.get("summary") or "").strip(),
                    suggestions=[
                        str(item).strip()[:300]
                        for item in suggestions_raw
                        if str(item).strip()
                    ][:4],
                )
            except (TypeError, ValueError) as exc:
                raise DeepSeekInvalidResponseError("model returned invalid governance advice") from exc
            self._log(request_id, context.task_id, "GOVERNANCE", True, started, endpoint="governance-advice")
            return response
        except DeepSeekError:
            self._log(request_id, context.task_id, "GOVERNANCE", False, started, endpoint="governance-advice")
            raise

    # ---------- 安全校验 ----------

    def _prefilter(self, text: str) -> AgentParseResponse | None:
        lowered = text.lower()
        for pattern in INJECTION_PATTERNS:
            if pattern.search(lowered):
                return AgentParseResponse(
                    intent="REFUSED",
                    reply="当前查询必须受到 Grant 和隐私预算约束，无法绕过授权访问未获许可的数据方。",
                    task_draft=None,
                    missing_fields=[],
                    warnings=["该请求试图访问原始数据或绕过隐私保护策略，已拒绝。"],
                    explanation="当前查询必须受到 Grant 和隐私预算约束，无法绕过授权访问未获许可的数据方。",
                    requires_confirmation=True,
                )
        return None

    def _validate_output(
        self,
        raw: Any,
        request: AgentParseRequest,
        budget_context: dict[str, Any] | None,
    ) -> AgentParseResponse:
        if not isinstance(raw, dict):
            return self._refused(["模型输出格式异常，已拒绝。"])

        text = request.text
        warnings = [str(item)[:200] for item in raw.get("warnings") or [] if str(item).strip()][:5]
        model_reply = str(raw.get("reply") or raw.get("explanation") or "").strip()[:1000]
        missing = [str(item)[:100] for item in raw.get("missing_fields") or [] if str(item).strip()][:10]
        raw_intent = str(raw.get("intent") or "OTHER").upper()
        if raw_intent == "CREATE_PRIVACY_QUERY":
            raw_intent = "QUERY"
        intent = self._guard_intent(text, raw_intent, request.has_current_task)
        if intent in TASK_INTENTS and intent != raw_intent:
            # Guard 已纠正模型意图时，模型回复通常仍属于原错误意图，
            # 不得把无关的通用话术继续显示给用户。
            model_reply = ""

        if intent == "REFUSED":
            return self._refused(warnings or ["该请求已被安全策略拒绝。"], model_reply or None)
        if intent not in AGENT_INTENTS:
            return self._refused(["模型返回了未知意图，已拒绝。"])
        if intent not in TASK_INTENTS:
            return self._non_task_response(intent, request, budget_context, model_reply, warnings)
        if intent == "TASK_UPDATE" and not request.has_current_task:
            reply = "当前还没有可修改的查询任务，请先描述查询需求。"
            return AgentParseResponse(
                intent="TASK_UPDATE",
                reply=reply,
                task_draft=None,
                missing_fields=[],
                warnings=[],
                explanation=reply,
                requires_confirmation=True,
            )

        draft_raw = raw.get("task_update", raw.get("task_draft"))
        if draft_raw is None:
            deterministic_query_type = self._explicit_query_type(text)
            deterministic_parties = self._mentioned_parties(text)
            if ALL_PARTIES_PATTERN.search(text):
                deterministic_parties = list(OrganizationId)
            deterministic_group_by = self._explicit_group_by(text)
            deterministic_start_time, deterministic_end_time = self._explicit_time_update(text)
            if (
                deterministic_query_type
                or deterministic_parties
                or deterministic_group_by
                or deterministic_start_time
                or deterministic_end_time
            ):
                # 仅从本轮原文的白名单词汇构造稀疏草案。这样即使模型把
                # 明确的参数修改误判为 OTHER 且返回 null，也不会丢失更新；
                # 时间和 epsilon 仍保持 null，绝不在这里猜测。
                draft_raw = {
                    "query_type": deterministic_query_type.value if deterministic_query_type else None,
                    "parties": [party.value for party in deterministic_parties],
                    "start_time": deterministic_start_time.isoformat() if deterministic_start_time else None,
                    "end_time": deterministic_end_time.isoformat() if deterministic_end_time else None,
                    "epsilon": None,
                    "group_by": deterministic_group_by.value if deterministic_group_by else None,
                }
                model_reply = ""
            else:
                if intent == "QUERY" and "query_type" not in missing:
                    missing.append("query_type")
                reply = model_reply or (
                    "可以，请补充需要查询的园区、时间范围、查询类型和隐私预算。"
                    if intent == "QUERY"
                    else "未识别到明确的参数修改，请说明需要调整的字段。"
                )
                return AgentParseResponse(
                    intent=intent,
                    reply=reply,
                    task_draft=None,
                    missing_fields=list(dict.fromkeys(missing)),
                    warnings=warnings,
                    explanation=reply,
                    requires_confirmation=True,
                )
        if not isinstance(draft_raw, dict) or self._contains_forbidden(draft_raw):
            return self._refused(["模型输出包含越权字段（敏感度/裁剪/预算/份额/原始数据等），已拒绝。"])

        query_type_raw = draft_raw.get("query_type")
        if query_type_raw not in (None, "", "null") and query_type_raw not in {item.value for item in QueryType}:
            return self._refused(["识别结果包含非法查询类型，已拒绝。"])
        query_type = QueryType(query_type_raw) if query_type_raw not in (None, "", "null") else None
        explicit_query_type = self._explicit_query_type(text)
        if explicit_query_type is not None:
            if query_type is not None and query_type != explicit_query_type:
                warnings.append("查询类型已按本轮输入明确表达的值收敛。")
            query_type = explicit_query_type
        elif query_type is not None:
            warnings.append("查询类型未在本轮输入中明确表达，已忽略模型填充值。")
            query_type = None
        if intent == "QUERY" and query_type is None:
            missing.append("query_type")

        model_parties: list[OrganizationId] = []
        for party_raw in draft_raw.get("parties") or []:
            try:
                model_parties.append(OrganizationId(str(party_raw)))
            except ValueError:
                return self._refused(["识别结果包含非法数据方，已拒绝。"])
        mentioned_parties = self._mentioned_parties(text)
        if ALL_PARTIES_PATTERN.search(text):
            mentioned_parties = list(OrganizationId)
        parties = [party for party in model_parties if party in mentioned_parties]
        if mentioned_parties and sorted(p.value for p in model_parties) != sorted(p.value for p in mentioned_parties):
            parties = mentioned_parties
            warnings.append("数据方已按本轮输入明确提到的园区收敛。")
        if not mentioned_parties:
            parties = []
            if model_parties:
                warnings.append("本轮未明确数据方，已忽略模型沿用的园区。")
        if intent == "QUERY" and not parties:
            missing.append("parties")

        group_by: GroupBy | None = None
        group_by_raw = draft_raw.get("group_by")
        explicit_group_by = self._explicit_group_by(text)
        effective_query_type = query_type or (request.current_form.query_type if intent == "TASK_UPDATE" and request.current_form else None)
        if effective_query_type == QueryType.TIME_SERIES:
            if group_by_raw not in (None, "", "null"):
                try:
                    model_group_by = GroupBy(str(group_by_raw))
                except ValueError:
                    return self._refused(["识别结果包含非法时间粒度，已拒绝。"])
                if explicit_group_by is not None:
                    group_by = explicit_group_by
                    if model_group_by != explicit_group_by:
                        warnings.append("时间粒度已按本轮输入明确表达的值收敛。")
                else:
                    warnings.append("时间粒度未在本轮输入中明确修改，已忽略模型填充值。")
            elif explicit_group_by is not None:
                # 中文短句（如“时间粒度为30分钟”）应由确定性解析兜底，
                # 不依赖模型是否恰好返回 group_by。
                group_by = explicit_group_by
            elif intent == "QUERY" or not request.current_form or request.current_form.group_by is None:
                missing.append("group_by")
        elif group_by_raw not in (None, "", "null") or explicit_group_by is not None:
            warnings.append("非 TIME_SERIES 查询的 group_by 已强制置空。")

        epsilon: float | None = None
        epsilon_raw = draft_raw.get("epsilon")
        if epsilon_raw is not None and EPSILON_MENTION_PATTERN.search(text):
            try:
                epsilon = float(epsilon_raw)
            except (TypeError, ValueError):
                return self._refused(["识别结果包含非法隐私预算，已拒绝。"])
            if not (0 < epsilon <= 5):
                return self._refused(["识别结果包含非法隐私预算，已拒绝。"])
        elif epsilon_raw is not None:
            warnings.append("epsilon 未在本轮输入中明确修改，已忽略模型填充值。")
        if intent == "QUERY" and epsilon is None:
            missing.append("epsilon")

        start_time_raw = draft_raw.get("start_time")
        end_time_raw = draft_raw.get("end_time")
        time_explicit = bool(DATE_MENTION_PATTERN.search(text))
        start_time_explicit = time_explicit
        end_time_explicit = time_explicit
        deterministic_start_time, deterministic_end_time = self._explicit_time_update(text)
        if intent == "TASK_UPDATE":
            range_explicit = bool(TIME_RANGE_UPDATE_PATTERN.search(text))
            start_time_explicit = time_explicit and (
                range_explicit or bool(START_TIME_UPDATE_PATTERN.search(text))
            )
            end_time_explicit = time_explicit and (
                range_explicit or bool(END_TIME_UPDATE_PATTERN.search(text))
            )

        if intent == "TASK_UPDATE":
            # 增量修改的日期直接由本轮原文确定性解析，避免模型替换或补齐
            # 用户没有说出的边界。未写时分秒则明确采用 00:00:00。
            start_time = deterministic_start_time if start_time_explicit else None
            end_time = deterministic_end_time if end_time_explicit else None
        else:
            start_time = (
                deterministic_start_time
                or (self._parse_time(start_time_raw) if start_time_explicit else None)
            )
            end_time = (
                deterministic_end_time
                or (self._parse_time(end_time_raw) if end_time_explicit else None)
            )
        if not time_explicit and (start_time_raw or end_time_raw):
            warnings.append("时间范围未在本轮输入中明确表达，已忽略模型沿用的时间。")
        elif intent == "TASK_UPDATE":
            ignored_boundaries: list[str] = []
            if start_time_raw and not start_time_explicit:
                ignored_boundaries.append("开始时间")
            if end_time_raw and not end_time_explicit:
                ignored_boundaries.append("结束时间")
            if ignored_boundaries:
                warnings.append(
                    f"{'、'.join(ignored_boundaries)}未在本轮输入中明确修改，已忽略模型填充值。"
                )
        if RELATIVE_TIME_PATTERN.search(text) and not EXPLICIT_DATE_PATTERN.search(text):
            # “当天/昨天”等相对时间未附明确日期：禁止沿用表单时间或猜测。
            start_time = None
            end_time = None
            warnings.append("当天等相对时间无法确认，请补充具体日期（数据集范围为 2012-11-11 至 2012-12-10）。")
            if (intent == "QUERY" or start_time_explicit) and "start_time" not in missing:
                missing.append("start_time")
            if (intent == "QUERY" or end_time_explicit) and "end_time" not in missing:
                missing.append("end_time")
        if intent == "QUERY" and start_time is None:
            missing.append("start_time")
        if intent == "QUERY" and end_time is None:
            missing.append("end_time")
        if intent == "TASK_UPDATE" and start_time_explicit and start_time is None:
            missing.append("start_time")
        if intent == "TASK_UPDATE" and end_time_explicit and end_time is None:
            missing.append("end_time")
        if start_time is not None and end_time is not None and start_time >= end_time:
            start_time = None
            end_time = None
            warnings.append("识别到的时间范围无效，请补充正确的开始与结束时间。")
        if start_time is not None and not (DATASET_START <= start_time < DATASET_END):
            start_time = None
            warnings.append("开始时间超出数据集可用范围（2012-11-11 至 2012-12-10）。")
            missing.append("start_time")
        if end_time is not None and not (DATASET_START < end_time <= DATASET_END):
            end_time = None
            warnings.append("结束时间超出数据集可用范围（2012-11-11 至 2012-12-10）。")
            missing.append("end_time")

        draft = TaskDraft(
            query_type=query_type,
            parties=parties,
            start_time=start_time,
            end_time=end_time,
            epsilon=epsilon,
            group_by=group_by,
        )
        reply = (
            self._task_update_reply(draft)
            if intent == "TASK_UPDATE"
            else model_reply or "已识别新的查询任务，请确认参数。"
        )
        return AgentParseResponse(
            intent=intent,
            reply=reply,
            task_draft=draft,
            missing_fields=list(dict.fromkeys(missing)),
            warnings=warnings,
            explanation=reply,
            requires_confirmation=True,
        )

    # ---------- 工具 ----------

    @classmethod
    def _guard_intent(cls, text: str, model_intent: str, has_current_task: bool) -> str:
        """Use small deterministic guards to prevent obvious chat from becoming a task.

        The model remains the primary classifier.  These guards only enforce the
        product boundary for unambiguous phrases and unsafe model misclassification.
        """
        compact = re.sub(r"[\s，。！？!?、]", "", text).lower()
        if compact in {"你好", "您好", "在吗", "早上好", "下午好", "晚上好", "嗨", "hello", "hi"}:
            return "GREETING"
        if re.search(r"你是谁|你是什么|你是.*deepseek|你叫什", compact, re.I):
            return "IDENTITY"
        if re.search(r"你能做什么|怎么使用|如何使用|怎么查询数据|如何查询数据|使用帮助|解释上一次查询|查看当前授权", compact):
            return "HELP"
        if re.search(r"还剩多少.*预算|剩余.*预算|还能查询几次|会消耗多少.*(?:epsilon|ε|预算)", compact, re.I):
            return "BUDGET_QUERY"
        if not TASK_UPDATE_PATTERN.search(text) and re.search(
            r"(?:epsilon|ε)是什么|什么是.*(?:差分隐私|秘密共享)|为什么需要秘密共享|查询安全吗|这个查询安全",
            text,
            re.I,
        ):
            return "PRIVACY_EXPLAIN"
        if TASK_CONFIRM_PATTERN.match(text.strip()):
            return "TASK_CONFIRM"
        if EXPLANATION_QUESTION_PATTERN.search(text) and (
            GROUP_BY_MENTION_PATTERN.search(text)
            or re.search(r"时间粒度|查询类型|数据方|参与方|开始时间|结束时间|时间范围", text, re.I)
        ):
            # “30分钟是什么意思”“为什么要用1小时”等是在询问概念，
            # 即使包含“为/改成”等字样也不得修改当前任务。
            return model_intent if model_intent not in TASK_INTENTS else "OTHER"
        explicit_new_query = (
            re.search(r"^\s*(?:请\s*)?(?:查询|统计|分析|计算)", text, re.I)
            and cls._explicit_query_type(text) is not None
            and (
                bool(cls._mentioned_parties(text))
                or bool(ALL_PARTIES_PATTERN.search(text))
            )
        )
        if explicit_new_query:
            return "QUERY"
        if TASK_UPDATE_PATTERN.search(text):
            return "TASK_UPDATE"
        if has_current_task and cls._is_contextual_task_update(text):
            # 已有任务后的“那就30分钟”“三园区就行”等，是对上一轮缺失
            # 参数的回答。即使模型将它识别成 OTHER，也应安全地生成稀疏更新。
            return "TASK_UPDATE"
        if QUERY_SIGNAL_PATTERN.search(text):
            return "QUERY"
        if model_intent == "TASK_UPDATE" and not cls._is_contextual_task_update(text):
            return "OTHER"
        if model_intent == "QUERY" and not QUERY_SIGNAL_PATTERN.search(text):
            return "OTHER"
        return model_intent if model_intent in AGENT_INTENTS else "OTHER"

    @classmethod
    def _is_contextual_task_update(cls, text: str) -> bool:
        """Recognize safe, elliptical replies that modify an existing task.

        This is deliberately limited to allow-listed values that can be parsed
        deterministically from the current turn.  It never fills an omitted
        value from conversational prose, and explicit explanation questions are
        left to the model/non-task intent path.
        """
        stripped = text.strip()
        if EXPLANATION_QUESTION_PATTERN.search(stripped):
            return False

        compact = re.sub(r"[\s，。！!、]", "", stripped)
        has_cue = bool(CONTEXTUAL_UPDATE_CUE_PATTERN.search(compact))

        group_by = cls._explicit_group_by(stripped)
        if group_by is not None:
            names_group_field = bool(re.search(r"(?:时间)?粒度", stripped, re.I))
            is_short_group_answer = bool(
                re.fullmatch(
                    r"(?:那就|就用|还是|改(?:成|为)?|换成|调整(?:成|为)?|用|按)?"
                    r"(?:30(?:m|min|分钟)|半小时|1(?:h|小时|d|天|日)|一天|每小时|按小时|按天|每天)"
                    r"(?:就行|即可|就好|好了?|吧)?[。！!]*",
                    compact,
                    re.I,
                )
            )
            if names_group_field or (has_cue and is_short_group_answer) or is_short_group_answer:
                return True

        # A complete explicit date interval is safe to apply as a sparse update,
        # even when the user omits the words “时间范围”.
        explicit_times = cls._explicit_datetimes(stripped)
        if (
            len(explicit_times) >= 2
            and TIME_RANGE_UPDATE_PATTERN.search(stripped)
            and (has_cue or not QUERY_SIGNAL_PATTERN.search(stripped))
        ):
            return True
        if len(explicit_times) >= 1 and (
            START_TIME_UPDATE_PATTERN.search(stripped)
            or END_TIME_UPDATE_PATTERN.search(stripped)
        ):
            return True

        parties = cls._mentioned_parties(stripped)
        all_parties = bool(ALL_PARTIES_PATTERN.search(stripped))
        if parties or all_parties:
            names_party_field = bool(re.search(r"数据方|参与方", stripped, re.I))
            short_party_answer = bool(
                re.fullmatch(
                    r"(?:那就|就用|还是|改(?:成|为)?|换成|用)?"
                    r"(?:(?:三(?:个)?|所有|全部|各)园区|全部数据方|"
                    r"(?:(?:ORG_)?[ABC](?:[、,/和及与](?:ORG_)?[ABC])*)(?:园区)?)"
                    r"(?:就行|即可|就好|好了?|吧)?[。！!]*",
                    compact,
                    re.I,
                )
            )
            if names_party_field or (has_cue and short_party_answer) or short_party_answer:
                return True

        query_type = cls._explicit_query_type(stripped)
        if query_type is not None:
            names_type_field = bool(re.search(r"查询类型", stripped, re.I))
            short_type_answer = bool(
                re.fullmatch(
                    r"(?:那就|就用|还是|改(?:成|为)?|换成|用)?"
                    r"(?:SUM|COUNT|AVERAGE|TIME_SERIES|求和|计数|均值|平均|时间序列)"
                    r"(?:就行|即可|就好|好了?|吧)?[。！!]*",
                    compact,
                    re.I,
                )
            )
            if names_type_field or (has_cue and short_type_answer) or short_type_answer:
                return True

        if EPSILON_MENTION_PATTERN.search(stripped) and (
            has_cue or bool(re.search(r"epsilon|ε|隐私预算", stripped, re.I))
        ):
            return True
        return False

    @staticmethod
    def _explicit_query_type(text: str) -> QueryType | None:
        patterns = (
            (QueryType.TIME_SERIES, r"TIME_SERIES|时间序列|负荷(?:趋势|曲线)|每小时|按小时|小时负荷"),
            (QueryType.COUNT, r"COUNT|计数|家庭数量|户数|多少户"),
            (QueryType.AVERAGE, r"AVERAGE|平均(?:用电量|负荷)?|均值"),
            (QueryType.SUM, r"SUM|求和|总用电量|总负荷|用电总量"),
        )
        for query_type, pattern in patterns:
            if re.search(pattern, text, re.I):
                return query_type
        return None

    @staticmethod
    def _task_update_reply(draft: TaskDraft) -> str:
        """Describe only the sparse fields that passed deterministic validation."""
        changed: list[str] = []
        if draft.query_type is not None:
            changed.append(f"查询类型更新为 {draft.query_type.value}")
        if draft.parties:
            changed.append(f"数据方更新为 {'、'.join(item.value for item in draft.parties)}")
        if draft.start_time is not None and draft.end_time is not None:
            changed.append(
                "时间范围更新为 "
                f"{draft.start_time.isoformat(timespec='minutes')} 至 "
                f"{draft.end_time.isoformat(timespec='minutes')}"
            )
        else:
            if draft.start_time is not None:
                changed.append(f"开始时间更新为 {draft.start_time.isoformat(timespec='minutes')}")
            if draft.end_time is not None:
                changed.append(f"结束时间更新为 {draft.end_time.isoformat(timespec='minutes')}")
        if draft.epsilon is not None:
            changed.append(f"隐私预算更新为 ε={draft.epsilon:g}")
        if draft.group_by is not None:
            labels = {
                GroupBy.HALF_HOUR: "30 分钟",
                GroupBy.HOUR: "1 小时",
                GroupBy.DAY: "1 天",
            }
            changed.append(f"时间粒度更新为 {labels[draft.group_by]}")
        if not changed:
            return "未识别到明确的参数修改，请说明需要调整的字段。"
        return f"已将当前任务的{'、'.join(changed)}，其余参数保持不变。"

    @staticmethod
    def _explicit_group_by(text: str) -> GroupBy | None:
        """Parse only a time granularity explicitly stated in the current turn."""
        patterns = (
            (GroupBy.HALF_HOUR, r"(?<!\d)30\s*(?:m|min|分钟)|半小时"),
            (GroupBy.HOUR, r"(?<!\d)1\s*(?:h|小时)|每小时|按小时|(?<!\d)小时(?:级|粒度|趋势|序列)?"),
            (GroupBy.DAY, r"(?<!\d)1\s*(?:d|天|日)|一天|按天|每天|日粒度"),
        )
        for group_by, pattern in patterns:
            if re.search(pattern, text, re.I):
                return group_by
        return None

    @staticmethod
    def _explicit_datetimes(text: str) -> list[datetime]:
        """Parse explicit ISO/Chinese calendar dates without resolving relative time."""
        values: list[datetime] = []
        for match in EXPLICIT_DATETIME_TOKEN_PATTERN.finditer(text):
            groups = match.groupdict()
            prefix = "iso" if groups.get("iso_year") else "cn"
            try:
                values.append(
                    datetime(
                        int(groups[f"{prefix}_year"]),
                        int(groups[f"{prefix}_month"]),
                        int(groups[f"{prefix}_day"]),
                        int(groups.get(f"{prefix}_hour") or 0),
                        int(groups.get(f"{prefix}_minute") or 0),
                        int(groups.get(f"{prefix}_second") or 0),
                    )
                )
            except (TypeError, ValueError):
                # 无效日历日期不交给模型猜测，后续按缺失字段处理。
                continue
        return values

    @classmethod
    def _explicit_time_update(cls, text: str) -> tuple[datetime | None, datetime | None]:
        """Return only the explicitly addressed time boundary/boundaries."""
        values = cls._explicit_datetimes(text)
        if not values:
            return None, None
        if TIME_RANGE_UPDATE_PATTERN.search(text):
            return values[0], values[1] if len(values) > 1 else None
        if START_TIME_UPDATE_PATTERN.search(text):
            return values[0], None
        if END_TIME_UPDATE_PATTERN.search(text):
            return None, values[0]
        return None, None

    @staticmethod
    def _mentioned_parties(text: str) -> list[OrganizationId]:
        letters: list[str] = []
        for pattern in (
            r"ORG_([ABC])",
            r"园区\s*([ABC])",
            r"([ABC])\s*园区",
        ):
            letters.extend(re.findall(pattern, text, re.I))
        for sequence in re.findall(r"([ABC](?:\s*[、,/和及与]\s*[ABC])+)(?:\s*园区)?", text, re.I):
            letters.extend(re.findall(r"[ABC]", sequence, re.I))
        result: list[OrganizationId] = []
        for letter in letters:
            party = OrganizationId(f"ORG_{str(letter).upper()}")
            if party not in result:
                result.append(party)
        return sorted(result, key=lambda item: item.value)

    def _non_task_response(
        self,
        intent: str,
        request: AgentParseRequest,
        budget_context: dict[str, Any] | None,
        model_reply: str,
        warnings: list[str],
    ) -> AgentParseResponse:
        if intent == "GREETING":
            reply = (
                "你好，我是 PrivGrid 智能隐私查询 Agent。"
                "你可以直接描述需要分析的能源数据，例如“查询 B、C 园区在指定日期的总用电量”。"
            )
        elif intent == "IDENTITY":
            reply = (
                "我是 PrivGrid 智能隐私查询 Agent，负责将自然语言需求转换为受授权范围和隐私预算约束的计算任务，"
                "并协助解释隐私预算和执行结果。"
            )
        elif intent == "HELP":
            reply = (
                "我可以创建或修改隐私查询任务，查看授权范围与隐私预算，解释查询结果，并生成隐私治理建议。"
                "请直接告诉我需要分析的园区、时间范围和查询类型。"
            )
        elif intent == "PRIVACY_EXPLAIN":
            if re.search(r"epsilon|ε", request.text, re.I):
                reply = (
                    "epsilon（ε）是差分隐私中的隐私预算参数。通常 ε 越小，隐私保护越强，"
                    "但结果扰动可能更明显；这只是概念解释，不会修改当前任务的 ε。"
                )
            else:
                reply = model_reply or (
                    "PrivGrid 通过 Grant 授权、隐私预算、秘密共享和分布式差分隐私约束查询，"
                    "只发布受保护的聚合结果，不返回园区原始记录。"
                )
        elif intent == "BUDGET_QUERY":
            reply = self._budget_reply(budget_context)
        elif intent == "TASK_CONFIRM":
            if request.has_current_task and request.grant_id and self._current_form_complete(request.current_form):
                reply = "当前任务参数完整，请核对右侧任务摘要后点击“提交隐私查询”进行最终确认。"
            else:
                reply = "当前还没有完整、合法且可提交的查询任务，请先描述查询需求或补充缺失参数。"
        else:
            intent = "OTHER"
            reply = (
                "我主要负责能源数据隐私查询、授权范围、隐私预算及计算结果解释。"
                "你可以告诉我需要分析的数据任务。"
            )
        return AgentParseResponse(
            intent=intent,
            reply=reply,
            task_draft=None,
            missing_fields=[],
            warnings=warnings,
            explanation=reply,
            requires_confirmation=intent == "TASK_CONFIRM",
        )

    @staticmethod
    def _current_form_complete(form: TaskDraft | None) -> bool:
        if form is None:
            return False
        if not form.query_type or not form.parties or not form.start_time or not form.end_time or form.epsilon is None:
            return False
        if form.start_time >= form.end_time:
            return False
        return form.query_type != QueryType.TIME_SERIES or form.group_by is not None

    @staticmethod
    def _budget_reply(context: dict[str, Any] | None) -> str:
        if not context:
            return "当前未选择可读取预算状态的有效授权，请先选择 Grant。"

        def fmt(value: Any) -> str:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "—"
            return f"{number:.2f}".rstrip("0").rstrip(".")

        grant_id = str(context.get("grant_id") or "当前 Grant")
        remaining = fmt(context.get("remaining_epsilon"))
        total = fmt(context.get("total_epsilon"))
        used = fmt(context.get("used_epsilon"))
        reserved = fmt(context.get("reserved_epsilon"))
        planned_raw = context.get("planned_epsilon")
        planned = fmt(planned_raw) if planned_raw is not None else "—"
        return (
            f"当前 {grant_id} 的总预算为 {total} ε，已用 {used} ε，预留 {reserved} ε，"
            f"剩余 {remaining} ε；当前任务预计消耗 {planned} ε。最终余额以任务提交时的授权校验结果为准。"
        )

    @staticmethod
    def _refused(warnings: list[str], explanation: str | None = None) -> AgentParseResponse:
        reply = explanation or "平台仅支持受 Grant、隐私预算和隐私策略约束的聚合查询。"
        return AgentParseResponse(
            intent="REFUSED",
            reply=reply,
            task_draft=None,
            missing_fields=[],
            warnings=warnings,
            explanation=reply,
            requires_confirmation=True,
        )

    @staticmethod
    def _contains_forbidden(obj: Any) -> bool:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lowered = str(key).lower()
                if any(pattern in lowered for pattern in FORBIDDEN_FIELD_PATTERNS):
                    return True
                if AgentService._contains_forbidden(value):
                    return True
        elif isinstance(obj, list):
            return any(AgentService._contains_forbidden(item) for item in obj)
        return False

    @staticmethod
    def _current_form_dict(form: TaskDraft | None) -> dict | None:
        return form.model_dump(mode="json") if form is not None else None

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if value is None or value == "" or str(value).lower() == "null":
            return None
        try:
            if isinstance(value, datetime):
                parsed = value
            else:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _reconcile_parties(
        text: str,
        parties: list[OrganizationId],
        missing: list[str],
        warnings: list[str],
    ) -> list[OrganizationId]:
        """文本明确提到部分园区时，以文本为准收敛 parties（三个园区/所有园区等除外）。"""
        if ALL_PARTIES_PATTERN.search(text):
            return parties
        mentioned: list[OrganizationId] = []
        for match in PARTY_MENTION_PATTERN.finditer(text):
            letter = match.group(1) or match.group(2)
            if letter in ("A", "B", "C"):
                party = OrganizationId(f"ORG_{letter}")
                if party not in mentioned:
                    mentioned.append(party)
        if not mentioned:
            return parties
        reconciled = [party for party in parties if party in mentioned]
        if not reconciled:
            missing.append("parties")
            warnings.append("识别到的数据方与文本明确提到的园区不一致，请人工确认。")
            return parties
        if sorted(reconciled) != sorted(parties):
            warnings.append(
                "数据方已按文本明确提到的园区收敛为：" + "、".join(p.value for p in reconciled) + "。"
            )
        return reconciled

    def _log(
        self,
        request_id: str,
        text: str,
        intent: str,
        ok: bool,
        started: float,
        endpoint: str | None = None,
    ) -> None:
        # 安全日志：不记录输入原文、API Key、Authorization 或完整模型响应。
        logger.info(
            "agent request_id=%s endpoint=%s model=%s chars=%d input_sha256=%s intent=%s ok=%s latency_ms=%.1f tokens=%s",
            request_id,
            endpoint or ("parse-query" if intent != "EXPLAIN" else "explain-result"),
            getattr(self.client, "model", "unknown"),
            len(text),
            hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "-",
            intent,
            ok,
            (time.perf_counter() - started) * 1000,
            "not-collected",
        )
