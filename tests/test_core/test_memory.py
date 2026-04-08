"""
tests/test_core/test_memory.py — MemorySystem 单元测试

ChromaDB 使用 PersistentClient + tmp_path 实现每测试真正隔离。
"""
import pytest

# Skip entire module if chromadb is not installed
chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from narrative_os.core.memory import MemoryRecord, MemorySystem


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def mem(tmp_path) -> MemorySystem:
    """PersistentClient + tmp_path，每个测试函数都得到全新隔离数据库。"""
    ms = MemorySystem(project_id="test_project", db_path=str(tmp_path / "chroma"))
    return ms


# ------------------------------------------------------------------ #
# Write & Retrieve                                                      #
# ------------------------------------------------------------------ #

class TestWriteRetrieve:
    def test_write_and_retrieve_short(self, mem: MemorySystem):
        mem.write_memory(
            content="林风在峰顶打坐修炼",
            memory_type="event",
            layer="short",
            chapter=1,
            importance=0.7,
        )
        results = mem.retrieve_memory("修炼", top_k=5, layer="short")
        assert len(results) >= 1
        assert "修炼" in results[0].content

    def test_retrieve_returns_similarity(self, mem: MemorySystem):
        mem.write_memory(
            content="林风拔出了古剑",
            memory_type="event",
            layer="short",
            chapter=2,
            importance=0.8,
        )
        results = mem.retrieve_memory("古剑", top_k=3, layer="short")
        assert results[0].similarity >= 0.0
        assert results[0].similarity <= 1.0

    def test_retrieve_cross_layer(self, mem: MemorySystem):
        mem.write_memory(
            content="门派秘技传承",
            memory_type="semantic",
            layer="mid",
            chapter=5,
            importance=0.9,
        )
        results = mem.retrieve_memory("秘技", top_k=5)  # no layer filter
        assert len(results) >= 1

    def test_importance_filter(self, mem: MemorySystem):
        mem.write_memory(
            content="路边小事",
            memory_type="event",
            layer="short",
            chapter=1,
            importance=0.1,
        )
        results = mem.retrieve_memory("小事", top_k=5, min_importance=0.5)
        # importance=0.1 should be filtered out
        assert all(r.metadata.get("importance", 0) >= 0.5 for r in results)

    def test_chapter_range_filter(self, mem: MemorySystem):
        mem.write_memory(
            content="第一章事件",
            memory_type="event",
            layer="short",
            chapter=1,
            importance=0.6,
        )
        mem.write_memory(
            content="第十章事件",
            memory_type="event",
            layer="short",
            chapter=10,
            importance=0.6,
        )
        results = mem.retrieve_memory(
            "事件", top_k=10, chapter_range=(1, 3)
        )
        for r in results:
            ch = r.metadata.get("chapter", 0)
            assert 1 <= ch <= 3


# ------------------------------------------------------------------ #
# Chapter Anchor                                                        #
# ------------------------------------------------------------------ #

class TestAnchor:
    def test_write_and_get_anchor(self, mem: MemorySystem):
        mem.write_anchor(
            chapter=3,
            key_pivot="林风得到古剑",
            burning_question="古剑是否有秘密？",
            protagonist_emotion="惊喜",
            next_chapter_debt="必须揭开古剑之谜",
        )
        anchors = mem.get_recent_anchors(last_n=3)
        assert len(anchors) == 1
        assert "chapter_3" in anchors[0].record_id

    def test_multiple_anchors_ordered(self, mem: MemorySystem):
        for i in range(1, 5):
            mem.write_anchor(
                chapter=i,
                key_pivot=f"第{i}章关键转折",
                burning_question=f"悬念{i}",
                protagonist_emotion="平静",
                next_chapter_debt=f"债{i}",
            )
        anchors = mem.get_recent_anchors(last_n=3)
        assert len(anchors) == 3
        # Should be the most recent 3: chapters 2,3,4
        chapters = [a.metadata.get("chapter") for a in anchors]
        assert 4 in chapters
        assert 3 in chapters


# ------------------------------------------------------------------ #
# summarize_and_compress                                                #
# ------------------------------------------------------------------ #

class TestSummarizeAndCompress:
    def test_compress_returns_summary_string(self, mem: MemorySystem):
        mem.write_memory(
            content="林风踏入古庙，发现一把遗落的古剑。",
            memory_type="event",
            layer="short",
            chapter=2,
            importance=0.7,
        )
        result = mem.summarize_and_compress(chapter=2)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_compress_writes_to_mid_layer(self, mem: MemorySystem):
        mem.write_memory(
            content="古庙内机关重重，林风经过一番斗争找到出口。",
            memory_type="event",
            layer="short",
            chapter=3,
            importance=0.8,
        )
        mem.summarize_and_compress(chapter=3)
        # A summary should now appear in the mid layer
        mid_results = mem.retrieve_memory("古庙", top_k=5, layer="mid")
        assert len(mid_results) >= 1

    def test_compress_empty_chapter_returns_empty_string(self, mem: MemorySystem):
        # No memories for chapter 99 → should return empty string
        result = mem.summarize_and_compress(chapter=99)
        assert result == ""


# ------------------------------------------------------------------ #
# archive                                                               #
# ------------------------------------------------------------------ #

class TestArchive:
    def test_archive_writes_to_long_layer(self, mem: MemorySystem):
        # Write mid-layer content first
        mem.write_memory(
            content="卷一摘要：林风踏入永夜山脉，完成了初步探索。",
            memory_type="event",
            layer="mid",
            chapter=5,
            importance=0.7,
        )
        result = mem.archive(volume=1, chapters=[5])
        assert isinstance(result, str)

    def test_archive_empty_mid_returns_empty(self, mem: MemorySystem):
        # No mid-layer content → archive should return empty
        result = mem.archive(volume=888)
        assert result == ""


# ------------------------------------------------------------------ #
# collection_counts                                                     #
# ------------------------------------------------------------------ #

class TestCollectionCounts:
    def test_counts_initially_zero(self, mem: MemorySystem):
        counts = mem.collection_counts()
        for layer in ("short", "mid", "long"):
            assert counts[layer] == 0

    def test_count_after_write(self, mem: MemorySystem):
        mem.write_memory(
            content="测试记忆条目",
            memory_type="event",
            layer="short",
            chapter=1,
            importance=0.5,
        )
        counts = mem.collection_counts()
        assert counts["short"] == 1


# ------------------------------------------------------------------ #
# repr                                                                   #
# ------------------------------------------------------------------ #

class TestRepr:
    def test_repr_contains_project_id(self, mem: MemorySystem):
        r = repr(mem)
        assert "test_project" in r
