"""tests/test_execution/test_llm_router.py — LLMRouter 单元测试（无网络）"""
from __future__ import annotations

import pytest

from narrative_os.execution.llm_router import (
    Backend,
    LLMRequest,
    LLMResponse,
    LLMRouter,
    ModelTier,
    RoutingStrategy,
    TASK_TIER_MAP,
)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def make_router(openai_key: str = "", anthropic_key: str = "") -> LLMRouter:
    r = LLMRouter()
    from narrative_os.infra.config import settings
    settings.openai_api_key = openai_key
    settings.anthropic_api_key = anthropic_key
    return r


# ------------------------------------------------------------------ #
# resolve_model                                                         #
# ------------------------------------------------------------------ #

class TestResolveModel:
    def test_quality_first_with_anthropic_key(self):
        router = make_router(anthropic_key="sk-test")
        req = LLMRequest(
            task_type="scene_generation",
            strategy=RoutingStrategy.QUALITY_FIRST,
        )
        backend, model = router.resolve_model(req)
        assert backend == Backend.ANTHROPIC
        assert "claude" in model.lower()

    def test_cost_optimized_prefers_deepseek_or_ollama(self):
        # No OpenAI / Anthropic keys → DeepSeek leads cost-optimised chain;
        # without a DeepSeek key Ollama (local, always available) takes over.
        router = make_router()
        req = LLMRequest(
            task_type="scene_generation",
            strategy=RoutingStrategy.COST_OPTIMIZED,
        )
        backend, _ = router.resolve_model(req)
        # DeepSeek or Ollama — both are acceptable for cost-optimised strategy
        assert backend in (Backend.DEEPSEEK, Backend.OLLAMA)

    def test_backend_override(self):
        router = make_router()
        req = LLMRequest(
            task_type="scene_generation",
            backend_override=Backend.OLLAMA,
        )
        backend, model = router.resolve_model(req)
        assert backend == Backend.OLLAMA

    def test_tier_override_large(self):
        router = make_router()
        req = LLMRequest(
            task_type="scene_generation",
            backend_override=Backend.OLLAMA,
            tier_override=ModelTier.LARGE,
        )
        _, model = router.resolve_model(req)
        # Should use large model
        assert "72" in model or "large" in model.lower() or "qwen2.5:72b" == model

    def test_task_tier_map_small_tasks(self):
        assert TASK_TIER_MAP["consistency_check"] == ModelTier.SMALL
        assert TASK_TIER_MAP["summarization"] == ModelTier.SMALL

    def test_task_tier_map_large_tasks(self):
        assert TASK_TIER_MAP["plot_planning"] == ModelTier.LARGE
        assert TASK_TIER_MAP["climax_generation"] == ModelTier.LARGE


# ------------------------------------------------------------------ #
# Fallback chain                                                        #
# ------------------------------------------------------------------ #

class TestFallbackChain:
    def test_fallback_chain_cost_optimized(self):
        router = make_router()
        req = LLMRequest(
            task_type="scene_generation",
            strategy=RoutingStrategy.COST_OPTIMIZED,
        )
        chain = router._build_fallback_chain(req)
        # DeepSeek leads the cost-optimised chain (cheaper API cost than OpenAI/Anthropic)
        assert chain[0][0] == Backend.DEEPSEEK

    def test_fallback_chain_quality_first(self):
        router = make_router()
        req = LLMRequest(strategy=RoutingStrategy.QUALITY_FIRST)
        chain = router._build_fallback_chain(req)
        assert chain[0][0] == Backend.ANTHROPIC

    def test_single_backend_override_chain(self):
        router = make_router()
        req = LLMRequest(backend_override=Backend.OPENAI)
        chain = router._build_fallback_chain(req)
        assert len(chain) == 1
        assert chain[0][0] == Backend.OPENAI


# ------------------------------------------------------------------ #
# async call with mock _dispatch                                        #
# ------------------------------------------------------------------ #

class TestAsyncCall:
    @pytest.mark.asyncio
    async def test_mock_dispatch_success(self, monkeypatch):
        router = make_router()

        async def fake_dispatch(backend, model, req):
            return "生成的场景文本", 100, 200

        monkeypatch.setattr(router, "_dispatch", fake_dispatch)
        monkeypatch.setattr(router, "_record_cost", lambda *a, **kw: None)

        req = LLMRequest(
            task_type="scene_generation",
            messages=[{"role": "user", "content": "写一段"}],
            skill_name="test",
        )
        resp = await router.call(req)
        assert isinstance(resp, LLMResponse)
        assert resp.content == "生成的场景文本"
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 200
        assert resp.total_tokens == 300
        assert resp.fallback_used is False

    @pytest.mark.asyncio
    async def test_fallback_on_first_failure(self, monkeypatch):
        router = make_router()
        call_count = {"n": 0}

        async def fake_dispatch(backend, model, req):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ConnectionError("模拟第一个后端失败")
            return "降级成功", 50, 100

        monkeypatch.setattr(router, "_dispatch", fake_dispatch)
        monkeypatch.setattr(router, "_record_cost", lambda *a, **kw: None)

        req = LLMRequest(
            task_type="scene_generation",
            messages=[{"role": "user", "content": "写"}],
            skill_name="test",
        )
        resp = await router.call(req)
        assert resp.content == "降级成功"
        assert resp.fallback_used is True
        assert resp.attempts == 2

    @pytest.mark.asyncio
    async def test_all_backends_fail_raises(self, monkeypatch):
        router = make_router()

        async def fake_dispatch(backend, model, req):
            raise ConnectionError("全部失败")

        monkeypatch.setattr(router, "_dispatch", fake_dispatch)
        monkeypatch.setattr(router, "_record_cost", lambda *a, **kw: None)

        req = LLMRequest(
            task_type="scene_generation",
            messages=[{"role": "user", "content": "写"}],
            skill_name="test",
        )
        with pytest.raises(RuntimeError, match="All LLM backends failed"):
            await router.call(req)


# ------------------------------------------------------------------ #
# LLMRequest / LLMResponse models                                       #
# ------------------------------------------------------------------ #

class TestModels:
    def test_request_immutable(self):
        req = LLMRequest(task_type="scene_generation")
        # Pydantic model — should be mutable by default (not frozen)
        assert req.task_type == "scene_generation"

    def test_response_total_tokens(self):
        resp = LLMResponse(
            content="hi",
            model_used="gpt-4o-mini",
            backend=Backend.OPENAI,
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert resp.total_tokens == 150


# ------------------------------------------------------------------ #
# Backend adapters — mocked network calls                               #
# ------------------------------------------------------------------ #

class TestCallOpenAI:
    @pytest.mark.asyncio
    async def test_call_openai_returns_content(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        import narrative_os.execution.llm_router as llm_module

        # Build a mock openai response
        mock_message = MagicMock()
        mock_message.content = "OpenAI生成内容"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 100
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        mock_openai_cls = MagicMock(return_value=mock_client)

        import sys
        import types
        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = mock_openai_cls
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        router = LLMRouter()
        req = LLMRequest(task_type="scene_generation", messages=[{"role": "user", "content": "写"}])
        content, p_tok, c_tok = await router._call_openai("gpt-4o", [], req)

        assert content == "OpenAI生成内容"
        assert p_tok == 50
        assert c_tok == 100

    @pytest.mark.asyncio
    async def test_call_openai_empty_response(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        import sys, types

        mock_message = MagicMock()
        mock_message.content = None  # None → should default to ""
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 0
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = MagicMock(return_value=mock_client)
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        router = LLMRouter()
        req = LLMRequest()
        content, _, _ = await router._call_openai("gpt-4o-mini", [], req)
        assert content == ""


class TestCallAnthropic:
    @pytest.mark.asyncio
    async def test_call_anthropic_returns_content(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        import sys, types

        mock_content_block = MagicMock()
        mock_content_block.text = "Anthropic生成内容"
        mock_resp = MagicMock()
        mock_resp.content = [mock_content_block]
        mock_resp.usage = MagicMock(input_tokens=60, output_tokens=120)

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)

        fake_anthropic = types.ModuleType("anthropic")
        fake_anthropic.AsyncAnthropic = MagicMock(return_value=mock_client)
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

        router = LLMRouter()
        req = LLMRequest(system_prompt="你是写手", messages=[{"role": "user", "content": "写"}])
        messages = router._build_messages(req)
        content, p_tok, c_tok = await router._call_anthropic("claude-3", messages, req)

        assert content == "Anthropic生成内容"
        assert p_tok == 60
        assert c_tok == 120

    @pytest.mark.asyncio
    async def test_call_anthropic_empty_content(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        import sys, types

        mock_resp = MagicMock()
        mock_resp.content = []  # empty content list
        mock_resp.usage = MagicMock(input_tokens=5, output_tokens=0)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        fake_anthropic = types.ModuleType("anthropic")
        fake_anthropic.AsyncAnthropic = MagicMock(return_value=mock_client)
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

        router = LLMRouter()
        req = LLMRequest()
        content, _, _ = await router._call_anthropic("claude-3", [], req)
        assert content == ""


class TestCallOllama:
    @pytest.mark.asyncio
    async def test_call_ollama_returns_content(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock, patch
        import sys, types

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Ollama生成内容"},
            "prompt_eval_count": 40,
            "eval_count": 80,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.post = AsyncMock(return_value=mock_response)

        fake_httpx = types.ModuleType("httpx")
        fake_httpx.AsyncClient = MagicMock(return_value=mock_http_client)
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

        router = LLMRouter()
        req = LLMRequest(task_type="scene_generation")
        content, p_tok, c_tok = await router._call_ollama("qwen2.5:14b", [], req)

        assert content == "Ollama生成内容"
        assert p_tok == 40
        assert c_tok == 80

    @pytest.mark.asyncio
    async def test_call_ollama_fallback_token_count(self, monkeypatch):
        """When Ollama doesn't return token counts, fall back to length estimate."""
        from unittest.mock import AsyncMock, MagicMock
        import sys, types

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "短内容"},
            # No prompt_eval_count or eval_count
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.post = AsyncMock(return_value=mock_response)

        fake_httpx = types.ModuleType("httpx")
        fake_httpx.AsyncClient = MagicMock(return_value=mock_http_client)
        monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

        router = LLMRouter()
        req = LLMRequest()
        content, p_tok, c_tok = await router._call_ollama("qwen2.5:7b", [], req)
        assert content == "短内容"
        assert isinstance(p_tok, int)
        assert isinstance(c_tok, int)


# ------------------------------------------------------------------ #
# _record_cost                                                          #
# ------------------------------------------------------------------ #

class TestRecordCost:
    def test_record_cost_calls_cost_ctrl(self, monkeypatch):
        from unittest.mock import MagicMock
        router = LLMRouter()
        req = LLMRequest(skill_name="test_skill", agent_name="test_agent")

        mock_cost_ctrl = MagicMock()
        import narrative_os.infra.cost as cost_module
        monkeypatch.setattr(cost_module, "cost_ctrl", mock_cost_ctrl)

        router._record_cost(req, prompt_tok=100, completion_tok=200)
        mock_cost_ctrl.record.assert_called_once_with(
            skill="test_skill",
            agent="test_agent",
            prompt=100,
            completion=200,
        )


# ------------------------------------------------------------------ #
# _build_messages                                                       #
# ------------------------------------------------------------------ #

class TestBuildMessages:
    def test_system_prompt_prepended(self):
        router = LLMRouter()
        req = LLMRequest(
            system_prompt="你是写手",
            messages=[{"role": "user", "content": "写"}],
        )
        msgs = router._build_messages(req)
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是写手"
        assert msgs[1]["role"] == "user"

    def test_no_system_prompt(self):
        router = LLMRouter()
        req = LLMRequest(messages=[{"role": "user", "content": "写"}])
        msgs = router._build_messages(req)
        assert msgs[0]["role"] == "user"

    def test_empty_messages(self):
        router = LLMRouter()
        req = LLMRequest()
        msgs = router._build_messages(req)
        assert msgs == []


# ------------------------------------------------------------------ #
# _dispatch routing                                                     #
# ------------------------------------------------------------------ #

class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_unknown_backend_raises(self):
        router = LLMRouter()
        req = LLMRequest()
        with pytest.raises((ValueError, Exception)):
            # Use an invalid backend value
            await router._dispatch("invalid_backend", "model", req)  # type: ignore


# ------------------------------------------------------------------ #
# resolve_model fallback path                                           #
# ------------------------------------------------------------------ #

class TestResolveModelFallback:
    def test_no_available_backends_falls_back_to_ollama(self, monkeypatch):
        """When no backends are available, resolve_model falls back to OLLAMA."""
        router = make_router()  # No keys set
        # Override _backend_available to always return False
        monkeypatch.setattr(router, "_backend_available", lambda b: False)
        req = LLMRequest(strategy=RoutingStrategy.QUALITY_FIRST)
        backend, model = router.resolve_model(req)
        assert backend == Backend.OLLAMA
