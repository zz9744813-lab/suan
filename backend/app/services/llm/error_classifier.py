"""P1-Model-Failover: LLM 错误分类器.

将 LLM 调用异常标准化为 failure_type 字符串,
供熔断器和调用记录使用.
"""
from __future__ import annotations


def classify_llm_exception(exc: Exception) -> str:
    """将异常分类为标准 failure_type.

    返回值:
        auth_error / rate_limited / timeout / connection_error /
        server_error / empty_response / json_parse_failed /
        model_not_found / budget_exhausted / unknown
    """
    text = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # 优先匹配 HTTP 状态码
    if "401" in text or "unauthorized" in text or "auth" in exc_type:
        return "auth_error"
    if "403" in text or "forbidden" in text:
        return "auth_error"
    if "429" in text or "rate limit" in text:
        return "rate_limited"
    if "404" in text or "model not found" in text:
        return "model_not_found"
    if "500" in text or "502" in text or "503" in text:
        return "server_error"

    # 异常类型匹配
    if "timeout" in text or "readtimeout" in text or "timeout" in exc_type:
        return "timeout"
    if "connection" in text or "connect" in exc_type or "无法连接" in text:
        return "connection_error"

    # 语义匹配
    if "empty" in text or "空内容" in text or "空响应" in text:
        return "empty_response"
    if "json" in text or "无法解析" in text or "parse" in exc_type:
        return "json_parse_failed"
    if "budget" in text or "预算" in text:
        return "budget_exhausted"

    return "unknown"
