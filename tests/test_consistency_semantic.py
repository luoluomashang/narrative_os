"""
tests/test_consistency_semantic.py — Phase 6: ConsistencyChecker 语义升级测试
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from narrative_os.skills.consistency import (
    ConsistencyChecker,
    ConsistencyIssue,
    ConsistencyReport,
    _CACHE_MAXSIZE,
    _cache_key,
    _consistency_cache,
)


# ------------------------------------------------------------------ #
# 固定装置：每次测试前清空缓存                                           #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def clear_cache():
    _consistency_cache.clear()
    yield
    _consistency_cache.clear()


# ------------------------------------------------------------------ #
# confidence 字段 + 降级逻辑                                             #
# ------------------------------------------------------------------ #

def test_confidence_field_defaults_to_1():
    """ConsistencyIssue.confidence 应默认为 1.0（向后兼容）。"""
    issue = ConsistencyIssue(dimension="plot", severity="hard", description="测试")
    assert issue.confidence == 1.0


def test_low_confidence_issue_becomes_info_via_parse():
    """_parse_llm_response 中 confidence<0.7 的 hard issue 应降级为 info。"""
    checker = ConsistencyChecker()
    raw = json.dumps([
        {"description": "严重冲突", "severity": "hard", "confidence": 0.4, "suggestion": ""}
    ])
    issues = checker._parse_llm_response(raw, "plot")
    assert len(issues) == 1
    assert issues[0].severity == "info"
    assert issues[0].confidence == pytest.approx(0.4)


def test_high_confidence_hard_remains_hard():
    """confidence >= 0.7 的 hard issue 不应降级。"""
    checker = ConsistencyChecker()
    raw = json.dumps([
        {"description": "明确冲突", "severity": "hard", "confidence": 0.9, "suggestion": ""}
    ])
    issues = checker._parse_llm_response(raw, "plot")
    assert issues[0].severity == "hard"


def test_low_confidence_issue_excluded_from_score():
    """低置信度问题不计入 score 扣分（即使是 hard）。"""
    checker = ConsistencyChecker(
        llm_call=lambda _: json.dumps([
            {"description": "不确定的问题", "severity": "hard", "confidence": 0.3, "suggestion": ""}
        ])
    )
    # 构造一个有 completed node 的 plot_graph 触发 LLM 调用
    mock_graph = MagicMock()
    mock_node = MagicMock()
    mock_node.status = "completed"
    mock_node.summary = "主角飞翔"
    mock_graph._nodes = {"node1": mock_node}

    report = checker.check(text="主角没有飞翔，他在奔跑。", plot_graph=mock_graph)
    # confidence=0.3 → 降级为 info，不计入 hard_n，score 应为 1.0
    assert report.score == pytest.approx(1.0)


# ------------------------------------------------------------------ #
# LRU 缓存                                                              #
# ------------------------------------------------------------------ #

def test_cache_returns_same_object():
    """相同输入第二次调用应返回缓存对象，不调用 LLM。"""
    call_count = [0]

    def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        return "[]"

    checker = ConsistencyChecker(llm_call=mock_llm)

    # 构造触发 LLM 的条件
    mock_graph = MagicMock()
    mock_node = MagicMock()
    mock_node.status = "completed"
    mock_node.summary = "主角 飞翔 升空"
    mock_graph._nodes = {"n1": mock_node}

    text = "主角没有飞翔，他在奔跑。"

    report1 = checker.check(text=text, plot_graph=mock_graph)
    first_call_count = call_count[0]
    report2 = checker.check(text=text, plot_graph=mock_graph)

    assert report1 is report2  # 同一对象
    assert call_count[0] == first_call_count  # 无额外 LLM 调用


def test_cache_size_does_not_exceed_max():
    """缓存超过 maxsize 时应移除最旧记录。"""
    checker = ConsistencyChecker()

    # 写入 maxsize+1 个不同缓存条目
    for i in range(_CACHE_MAXSIZE + 1):
        text = f"测试文本 {i} " * 10  # 确保不同的 cache key
        checker.check(text=text, chapter=i)

    assert len(_consistency_cache) <= _CACHE_MAXSIZE


def test_cache_key_differs_by_chapter():
    """不同 chapter 应产生不同 cache key。"""
    key1 = _cache_key("同一文本", 1, ["角色A"])
    key2 = _cache_key("同一文本", 2, ["角色A"])
    assert key1 != key2


def test_cache_key_differs_by_char_names():
    """不同角色名列表应产生不同 cache key。"""
    key1 = _cache_key("同一文本", 1, ["角色A"])
    key2 = _cache_key("同一文本", 1, ["角色B"])
    assert key1 != key2


# ------------------------------------------------------------------ #
# plot check — no completed nodes                                        #
# ------------------------------------------------------------------ #

def test_plot_check_with_no_completed_nodes_skips_llm():
    """completed_nodes 为空时应跳过 LLM 调用。"""
    call_count = [0]

    def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        return "[]"

    checker = ConsistencyChecker(llm_call=mock_llm)

    # 所有节点均为 pending
    mock_graph = MagicMock()
    mock_node = MagicMock()
    mock_node.status = "pending"
    mock_node.summary = "主角 没有 飞翔"
    mock_graph._nodes = {"n1": mock_node}

    checker.check(text="主角没有飞翔", plot_graph=mock_graph)
    assert call_count[0] == 0  # LLM 未被调用


# ------------------------------------------------------------------ #
# timeline check — no markers                                           #
# ------------------------------------------------------------------ #

def test_timeline_check_no_time_markers_skips_llm():
    """无时间标记时应跳过 LLM，退化为关键词检查。"""
    call_count = [0]

    def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        return "[]"

    checker = ConsistencyChecker(llm_call=mock_llm)
    # 文本无时间标记
    checker.check(text="林枫走进了宗门大殿，向长老行礼。", chapter=3)
    assert call_count[0] == 0


def test_timeline_check_with_time_markers_calls_llm():
    """有时间标记时应调用 LLM。"""
    call_count = [0]

    def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        return "[]"

    checker = ConsistencyChecker(llm_call=mock_llm)
    # 文本含时间标记"3天前"
    checker.check(text="他3天前离开了宗门，今天才回来。", chapter=5)
    assert call_count[0] >= 1


# ------------------------------------------------------------------ #
# LLM JSON 解析失败回退                                                  #
# ------------------------------------------------------------------ #

def test_llm_json_parse_error_falls_back_to_empty():
    """LLM 返回非 JSON 字符串时应返回空问题列表，不抛异常。"""
    checker = ConsistencyChecker(llm_call=lambda _: "这不是 JSON 格式的响应")

    mock_graph = MagicMock()
    mock_node = MagicMock()
    mock_node.status = "completed"
    mock_node.summary = "主角 飞翔 升空"
    mock_graph._nodes = {"n1": mock_node}

    # 触发 LLM 调用（关键词预筛命中 + 有已完成节点）
    text = "主角没有飞翔"
    report = checker.check(text=text, plot_graph=mock_graph)

    # LLM 返回非 JSON → parse 失败 → 退回关键词 quick_hits（soft issue）
    # 无论如何不应抛出异常
    assert isinstance(report, ConsistencyReport)


def test_llm_empty_response_returns_empty_issues():
    """LLM 返回空字符串时 _parse_llm_response 应返回空列表。"""
    checker = ConsistencyChecker()
    issues = checker._parse_llm_response("", "plot")
    assert issues == []


def test_llm_valid_json_array_parsed_correctly():
    """有效 JSON 数组应正确解析为 ConsistencyIssue 列表。"""
    checker = ConsistencyChecker()
    raw = json.dumps([
        {
            "description": "时序矛盾",
            "severity": "soft",
            "confidence": 0.85,
            "suggestion": "修改时间描述",
        }
    ])
    issues = checker._parse_llm_response(raw, "timeline")
    assert len(issues) == 1
    assert issues[0].severity == "soft"
    assert issues[0].confidence == pytest.approx(0.85)
    assert issues[0].dimension == "timeline"
