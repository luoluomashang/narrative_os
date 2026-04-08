"""
execution/llm_router.py — Phase 2: LLM 路由器

功能：
  - 按任务类型自动选择模型（小/中/大）
  - 三大策略：cost_optimized / quality_first / speed_first
  - 支持 OpenAI、Anthropic、Ollama 三条后端
  - 失败时自动降级（fallback chain）
  - 统一通过 CostController 记录 token 消耗

模型分层（来自 project.md §6.2）：
  small  → 检查 / 摘要 / 一致性
  medium → 普通写作 / 对话生成
  large  → 高潮剧情 / 世界构建 / 规划

UI 映射：模型选择策略面板（旁边实时显示预计费用）
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from narrative_os.infra.config import settings
from narrative_os.infra.logging import logger


# ------------------------------------------------------------------ #
# 枚举 & 常量                                                          #
# ------------------------------------------------------------------ #

class ModelTier(str, Enum):
    SMALL  = "small"   # 检查/摘要
    MEDIUM = "medium"  # 普通写作
    LARGE  = "large"   # 高潮/规划


class RoutingStrategy(str, Enum):
    COST_OPTIMIZED = "cost_optimized"
    QUALITY_FIRST  = "quality_first"
    SPEED_FIRST    = "speed_first"


class Backend(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA    = "ollama"
    DEEPSEEK  = "deepseek"   # OpenAI-compatible, api.deepseek.com
    CUSTOM    = "custom"     # 任意 OpenAI-compat 端点（vLLM/LM Studio/Azure 等）


# task_type → 默认 tier（可被策略覆盖）
TASK_TIER_MAP: dict[str, ModelTier] = {
    "scene_generation":    ModelTier.MEDIUM,
    "climax_generation":   ModelTier.LARGE,
    "plot_planning":       ModelTier.LARGE,
    "dialogue_generation": ModelTier.MEDIUM,
    "consistency_check":   ModelTier.SMALL,
    "summarization":       ModelTier.SMALL,
    "humanization":        ModelTier.MEDIUM,
    "world_building":      ModelTier.LARGE,
    "default":             ModelTier.MEDIUM,
}

# 每个后端的模型名（从 Settings / 环境变量可覆盖）
# 注意：Custom 后端不在此处定义，改为在 __init__ 中从 settings 惰性加载
_DEFAULT_MODELS: dict[Backend, dict[ModelTier, str]] = {
    Backend.OPENAI: {
        ModelTier.SMALL:  "gpt-4o-mini",
        ModelTier.MEDIUM: "gpt-4o",
        ModelTier.LARGE:  "gpt-4o",
    },
    Backend.ANTHROPIC: {
        ModelTier.SMALL:  "claude-3-haiku-20240307",
        ModelTier.MEDIUM: "claude-3-5-sonnet-20241022",
        ModelTier.LARGE:  "claude-3-5-sonnet-20241022",
    },
    Backend.OLLAMA: {
        ModelTier.SMALL:  "qwen2.5:7b",
        ModelTier.MEDIUM: "qwen2.5:14b",
        ModelTier.LARGE:  "qwen2.5:72b",
    },
    Backend.DEEPSEEK: {
        ModelTier.SMALL:  "deepseek-chat",
        ModelTier.MEDIUM: "deepseek-chat",
        ModelTier.LARGE:  "deepseek-reasoner",
    },
}

# 策略 → 后端优先顺序（fallback chain）
_STRATEGY_BACKENDS: dict[RoutingStrategy, list[Backend]] = {
    RoutingStrategy.COST_OPTIMIZED: [Backend.DEEPSEEK, Backend.OLLAMA, Backend.OPENAI, Backend.ANTHROPIC],
    RoutingStrategy.QUALITY_FIRST:  [Backend.ANTHROPIC, Backend.OPENAI, Backend.DEEPSEEK, Backend.OLLAMA],
    RoutingStrategy.SPEED_FIRST:    [Backend.OPENAI, Backend.DEEPSEEK, Backend.OLLAMA, Backend.ANTHROPIC],
}


def get_default_routing_strategy() -> RoutingStrategy:
    """从配置读取默认路由策略，兼容 QUALITY_FIRST / quality_first 两种写法。"""
    raw = (settings.llm_strategy or "").strip()
    if raw:
        try:
            return RoutingStrategy[raw.upper()]
        except KeyError:
            try:
                return RoutingStrategy(raw.lower())
            except ValueError:
                pass
    return RoutingStrategy.COST_OPTIMIZED


def _has_real_api_key(value: str) -> bool:
    """判断 API Key 是否像真实值，过滤示例占位符。"""
    key = (value or "").strip()
    if not key:
        return False
    lowered = key.lower()
    placeholders = ("xxxxxxxx", "xxxxx", "your_", "your-", "demo", "example")
    return not any(token in lowered for token in placeholders)


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class LLMRequest(BaseModel):
    """LLM 调用请求。"""
    task_type: str = "default"
    messages: list[dict[str, str]] = Field(default_factory=list)
    system_prompt: str = ""
    strategy: RoutingStrategy = Field(default_factory=get_default_routing_strategy)
    tier_override: ModelTier | None = None
    backend_override: Backend | None = None
    max_tokens: int = 2048
    temperature: float = 0.7
    skill_name: str = "unknown"   # 用于 CostController 记录
    agent_name: str | None = None


class LLMResponse(BaseModel):
    """LLM 调用响应。"""
    content: str
    model_used: str
    backend: Backend
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    attempts: int = 1
    fallback_used: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ------------------------------------------------------------------ #
# LLMRouter                                                             #
# ------------------------------------------------------------------ #

class LLMRouter:
    """
    统一 LLM 路由器。

    用法：
        router = LLMRouter()
        resp = await router.call(req)   # 异步
        resp = router.call_sync(req)    # 同步（用于测试/简单脚本）
    """

    def __init__(self) -> None:
        self._models: dict[Backend, dict[ModelTier, str]] = {k: dict(v) for k, v in _DEFAULT_MODELS.items()}
        # Custom 后端从 settings 惰性加载（避免 import 时读取）
        self._models[Backend.CUSTOM] = {
            ModelTier.SMALL:  settings.custom_llm_model_small,
            ModelTier.MEDIUM: settings.custom_llm_model_medium,
            ModelTier.LARGE:  settings.custom_llm_model_large,
        }
        self._adapters: dict[str, Any] = {}  # lazy-init

    # ---------------------------------------------------------------- #
    # Public                                                            #
    # ---------------------------------------------------------------- #

    def refresh_from_settings(self) -> None:
        """从 Settings 单例重新加载所有可配置的模型名。
        在 Settings 更新后调用，确保 Router 内存与 Settings 一致。"""
        self._models[Backend.CUSTOM] = {
            ModelTier.SMALL:  settings.custom_llm_model_small,
            ModelTier.MEDIUM: settings.custom_llm_model_medium,
            ModelTier.LARGE:  settings.custom_llm_model_large,
        }

    def update_model_config(self, provider: Backend, tier: ModelTier, model_name: str) -> None:
        """运行时修改指定 provider / tier 的模型名。"""
        if provider not in self._models:
            self._models[provider] = {}
        self._models[provider][tier] = model_name

    def get_provider_status(self) -> dict[str, dict[str, Any]]:
        """返回各 provider 的可用状态和当前模型配置。"""
        result = {}
        for backend in Backend:
            available = self._backend_available(backend)
            models = {tier.value: self._models.get(backend, {}).get(tier, "") for tier in ModelTier}
            result[backend.value] = {"available": available, "models": models}
        return result

    def resolve_model(self, req: LLMRequest) -> tuple[Backend, str]:
        """
        根据任务类型、策略、覆盖参数，解析出 (后端, 模型名)。
        不发起任何网络请求。
        """
        tier = req.tier_override or TASK_TIER_MAP.get(req.task_type, ModelTier.MEDIUM)

        if req.backend_override:
            backend = req.backend_override
            model = self._models[backend][tier]
            return backend, model

        # 策略决定后端顺序
        chain = _STRATEGY_BACKENDS[req.strategy]

        # 优先使用有 API key / 有本地服务的后端
        for backend in chain:
            if self._backend_available(backend):
                model = self._models[backend][tier]
                return backend, model

        # 没有任何后端可用时，退化到 ollama（本地优先）
        return Backend.OLLAMA, self._models[Backend.OLLAMA][tier]

    async def call(self, req: LLMRequest) -> LLMResponse:
        """
        异步调用 LLM，带自动降级。
        """
        chain = self._build_fallback_chain(req)
        last_error: Exception | None = None

        for attempt_idx, (backend, model) in enumerate(chain):
            t0 = time.monotonic()
            try:
                content, prompt_tok, completion_tok = await self._dispatch(
                    backend, model, req
                )
                latency = (time.monotonic() - t0) * 1000
                self._record_cost(req, prompt_tok, completion_tok)
                logger.llm_call(
                    model=model,
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                    latency_ms=latency,
                    skill=req.skill_name,
                    success=True,
                )
                return LLMResponse(
                    content=content,
                    model_used=model,
                    backend=backend,
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                    latency_ms=latency,
                    attempts=attempt_idx + 1,
                    fallback_used=attempt_idx > 0,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.error(f"[LLMRouter] {backend.value}/{model} failed: {exc}")
                continue

        raise RuntimeError(
            f"All LLM backends failed for task '{req.task_type}'"
        ) from last_error

    def call_sync(self, req: LLMRequest) -> LLMResponse:
        """
        同步包装器（测试 / CLI 使用）。
        注意：不要在已有事件循环的协程中调用。
        """
        import asyncio
        return asyncio.run(self.call(req))

    async def call_stream(self, req: LLMRequest) -> AsyncIterator[str]:
        """
        流式调用 LLM，逐块 yield 文本。
        支持自动降级：当前后端不支持流式时退化为完整调用。
        """
        backend, model = self.resolve_model(req)
        messages = self._build_messages(req)
        try:
            async for chunk in self._dispatch_stream(backend, model, messages, req):
                yield chunk
        except Exception as exc:
            logger.error(f"[LLMRouter] stream {backend.value}/{model} failed: {exc}")
            # 退化为非流式
            resp = await self.call(req)
            yield resp.content

    # ---------------------------------------------------------------- #
    # Private helpers                                                    #
    # ---------------------------------------------------------------- #

    def _backend_available(self, backend: Backend) -> bool:
        if backend == Backend.OPENAI:
            return _has_real_api_key(settings.openai_api_key)
        if backend == Backend.ANTHROPIC:
            return _has_real_api_key(settings.anthropic_api_key)
        if backend == Backend.DEEPSEEK:
            return _has_real_api_key(settings.deepseek_api_key)
        if backend == Backend.CUSTOM:
            return bool(settings.custom_llm_base_url)
        if backend == Backend.OLLAMA:
            return True  # 乐观假设本地有 Ollama
        return False

    def _build_fallback_chain(
        self, req: LLMRequest
    ) -> list[tuple[Backend, str]]:
        """返回按优先级排序的 (backend, model) 列表。"""
        tier = req.tier_override or TASK_TIER_MAP.get(req.task_type, ModelTier.MEDIUM)

        if req.backend_override:
            return [(req.backend_override, self._models[req.backend_override][tier])]

        chain = _STRATEGY_BACKENDS[req.strategy]
        return [(b, self._models[b][tier]) for b in chain]

    async def _dispatch_stream(
        self,
        backend: Backend,
        model: str,
        messages: list[dict[str, str]],
        req: LLMRequest,
    ) -> AsyncIterator[str]:
        """流式派发：逐块 yield 文本。支持 OpenAI-compat 和 Anthropic。"""
        if backend in (Backend.OPENAI, Backend.DEEPSEEK, Backend.CUSTOM):
            # OpenAI-compatible streaming
            from openai import AsyncOpenAI
            if backend == Backend.OPENAI:
                client = AsyncOpenAI(api_key=settings.openai_api_key)
            elif backend == Backend.DEEPSEEK:
                client = AsyncOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url="https://api.deepseek.com/v1",
                )
            else:
                client = AsyncOpenAI(
                    api_key=settings.custom_llm_api_key or "not-needed",
                    base_url=settings.custom_llm_base_url,
                )
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        elif backend == Backend.ANTHROPIC:
            import anthropic
            system = ""
            chat_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    chat_msgs.append(m)
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            async with client.messages.stream(
                model=model,
                max_tokens=req.max_tokens,
                system=system,
                messages=chat_msgs,  # type: ignore[arg-type]
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        elif backend == Backend.OLLAMA:
            import httpx
            url = f"{settings.ollama_base_url}/api/chat"
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
            }
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                async with http_client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    import json as _json
                    async for line in resp.aiter_lines():
                        if line.strip():
                            data = _json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
        else:
            raise ValueError(f"Streaming not supported for backend: {backend}")

    async def _dispatch(
        self, backend: Backend, model: str, req: LLMRequest
    ) -> tuple[str, int, int]:
        """
        派发给对应后端的驱动，返回 (content, prompt_tokens, completion_tokens)。

        真实驱动（openai / anthropic / httpx-ollama）在 CostController 记录后延迟导入，
        测试时可通过 monkey-patch _dispatch 跳过网络。
        """
        messages = self._build_messages(req)

        if backend == Backend.OPENAI:
            return await self._call_openai(model, messages, req)
        if backend == Backend.ANTHROPIC:
            return await self._call_anthropic(model, messages, req)
        if backend == Backend.OLLAMA:
            return await self._call_ollama(model, messages, req)
        if backend == Backend.DEEPSEEK:
            return await self._call_deepseek(model, messages, req)
        if backend == Backend.CUSTOM:
            return await self._call_custom(model, messages, req)
        raise ValueError(f"Unknown backend: {backend}")

    def _build_messages(self, req: LLMRequest) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if req.system_prompt:
            msgs.append({"role": "system", "content": req.system_prompt})
        msgs.extend(req.messages)
        return msgs

    # ---- Backend adapters ------------------------------------------ #

    async def _call_openai(
        self, model: str, messages: list[dict], req: LLMRequest
    ) -> tuple[str, int, int]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return content, usage.prompt_tokens, usage.completion_tokens

    async def _call_anthropic(
        self, model: str, messages: list[dict], req: LLMRequest
    ) -> tuple[str, int, int]:
        import anthropic
        # Anthropic 需要把 system 分离
        system = ""
        chat_msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_msgs.append(m)
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=req.max_tokens,
            system=system,
            messages=chat_msgs,  # type: ignore[arg-type]
        )
        content = resp.content[0].text if resp.content else ""
        return content, resp.usage.input_tokens, resp.usage.output_tokens

    async def _call_ollama(
        self, model: str, messages: list[dict], req: LLMRequest
    ) -> tuple[str, int, int]:
        import httpx
        url = f"{settings.ollama_base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data.get("message", {}).get("content", "")
        # Ollama 返回 prompt_eval_count / eval_count
        p_tok = data.get("prompt_eval_count", len(str(messages)) // 4)
        c_tok = data.get("eval_count", len(content) // 4)
        return content, p_tok, c_tok

    async def _call_deepseek(
        self, model: str, messages: list[dict], req: LLMRequest
    ) -> tuple[str, int, int]:
        """DeepSeek — 使用 OpenAI SDK，指向 api.deepseek.com。"""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return content, usage.prompt_tokens, usage.completion_tokens

    async def _call_custom(
        self, model: str, messages: list[dict], req: LLMRequest
    ) -> tuple[str, int, int]:
        """自定义 OpenAI-compat 端点（vLLM / LM Studio / Azure 等）。"""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.custom_llm_api_key or "not-needed",
            base_url=settings.custom_llm_base_url,
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return content, usage.prompt_tokens, usage.completion_tokens

    def _record_cost(
        self, req: LLMRequest, prompt_tok: int, completion_tok: int
    ) -> None:
        from narrative_os.infra.cost import cost_ctrl
        cost_ctrl.record(
            skill=req.skill_name,
            agent=req.agent_name,
            prompt=prompt_tok,
            completion=completion_tok,
        )


# ------------------------------------------------------------------ #
# 进程级单例                                                            #
# ------------------------------------------------------------------ #
router = LLMRouter()
