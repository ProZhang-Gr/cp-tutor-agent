# -*- coding: utf-8 -*-
"""LLM 工厂：基于 langchain-openai 接入 DeepSeek。

提供两种实例：
  - get_llm()        普通文本/流式输出（导师对话、提示）
  - get_json_llm()   强制 JSON 输出（结构化智能体：分析/规划/审查/测试）
以及一个鲁棒的 JSON 解析器，兼容模型偶尔输出的 ```json 代码块。
"""
import json
import re

from langchain_openai import ChatOpenAI

from config import settings


def get_llm(temperature=0.3, model=None, streaming=False, max_tokens=2048):
    """普通对话 LLM。带网络重试与超时，避免抖动直接打断。"""
    return ChatOpenAI(
        model=model or settings.MODEL_CHAT,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.BASE_URL,
        temperature=temperature,
        streaming=streaming,
        max_tokens=max_tokens,
        max_retries=settings.LLM_MAX_RETRIES,
        timeout=settings.LLM_TIMEOUT,
    )


def get_json_llm(temperature=0.2, model=None, max_tokens=2048):
    """强制 JSON 输出的 LLM（DeepSeek 支持 response_format=json_object）。带重试与超时。"""
    return ChatOpenAI(
        model=model or settings.MODEL_CHAT,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=settings.LLM_MAX_RETRIES,
        timeout=settings.LLM_TIMEOUT,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.S)


def parse_json(text):
    """从 LLM 输出中稳健地提取 JSON 对象。"""
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_BLOCK.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 兜底：截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {}
