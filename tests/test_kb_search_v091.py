"""知识库多词搜索 —— V0.9.1 回归

## 用户实测报的现象

「搜多个词搜不到东西」。

根因: `search()` 原来只 `q.split()` —— **按空格切**, 于是:

| 输入            | 切出来什么          | 结果 |
|-----------------|---------------------|------|
| `基础训练`       | `['基础训练']`       | ✅ 2 条 |
| `基础 训练`      | `['基础','训练']`    | ✅ 有结果 |
| `基础、训练`     | `['基础、训练']`     | ❌ **0 条** |
| `训练 强度 区间`  | 3 词全 AND           | ❌ **0 条** |

两个独立的毛病:
1. **中文标点不算分隔符** —— `基础、训练` 被当成一个完整词条,
   而 FTS 索引里根本没有这个词条, 所以必然 0 条;
2. **多词是 AND 语义** —— 三四个词同时出现在同一段落里的概率很低,
   于是搜得越具体结果越少, 最多到 0 条。

外加第三个: FTS 抛异常时 `return {"results": [], ...}` 静默返回空,
用户分不清"没搜到"和"搜索崩了"。

## 为什么"搜不到"和"搜崩了"必须分开

这是本项目的核心原则(宁可说算不出来, 也不要给错答案)在搜索上的体现:
**空结果本身是一个断言** —— 它在说"这个内容不在库里"。
如果它其实来自异常, 那就是在**编造一个结论**。

## 用真实导入的知识库测, 不造假数据

`use_temp_db` 之外还要真导一份知识库, 因为这里验的是
"分词 → FTS 语法 → 命中"这条链路, 假 chunk 测不出 FTS 的分词行为。
"""
from __future__ import annotations

import pytest


@pytest.fixture
def kb_client(tmp_path, monkeypatch):
    """真建库 + 真导入一份知识库, 返回 (client, KBService)。"""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))

    from cycling_coach.data.sqlite.database import init_db, SessionLocal
    init_db()

    from cycling_coach.core.kb_importer import import_knowledge_base
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app

    # 造一份小型"知识库"目录
    # import_knowledge_base 的签名是 (kb_root, attach_dir) —— 位置参数,
    # 分类/标题从目录结构里推, 不接受 kwargs。别猜签名, 去读实现。
    #
    # ⚠️ 文档文件名必须是 **`_content.md`** —— 导入器认的是这个约定,
    #    不是任意 .md。我第一版用了 `基础.md`, 结果 documents=0,
    #    于是"搜不到"变成了 fixture 的问题而不是被测代码的问题。
    #    **测试测不到东西时, 先确认被测对象存在。**
    kb_dir = tmp_path / "kb"
    cat_dir = kb_dir / "训练理论"
    cat_dir.mkdir(parents=True)
    (cat_dir / "_content.md").write_text(
        "# 基础理论\n\n"
        "公路车训练的基础理论包括训练强度、训练量、恢复三个维度。\n"
        "训练强度区间通常用 FTP 划分, 强度太低没有刺激, 太高影响恢复。\n"
        "恢复和训练同样重要, 睡眠、营养、休息日都算恢复的一部分。\n"
        "## 强度区间\n\n"
        "强度区间从低到高分别是恢复、耐力、节奏、阈值、极限。\n"
        "阈值训练对乳酸阈心率有要求, 需要通过测试确定。\n"
        "极限区间强度高, 时间短, 恢复要求高。\n",
        encoding="utf-8",
    )

    result = import_knowledge_base(kb_dir, tmp_path / "_attach")
    # fixture 的自检: 数据没导进去的话, 下面每个测试都会"因为搜不到"
    # 而失败 —— 看起来像搜索坏了, 其实是 fixture 坏了。
    # 断言在这里失败, 比在 12 个测试里各失败一次清楚得多。
    assert result.get("chunks", 0) > 0, (
        f"知识库没导入成功: {result} —— fixture 建错了, "
        f"不是搜索逻辑的问题"
    )

    db = SessionLocal()
    from cycling_coach.core.services.kb import KBService
    svc = KBService(db)
    return TestClient(app), svc, result


# ═══════════════════════════════════════════════════════════════
# 1. 中文标点必须算分隔符
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sep", [" ", "、", "，", ",", "／", "/", "；", ";"])
def test_chinese_and_english_separators_are_all_split(kb_client, sep):
    """🔴 `基础、训练` 原来 0 条 —— 顿号/逗号/斜杠都没被当分隔符。"""
    _client, svc, _r = kb_client
    hits = svc.search(q=f"基础{sep}训练")
    assert len(hits.get("results", [])) > 0, (
        f"用 {sep!r} 分隔时搜不到 —— "
        f"多词搜索只认空格, 中文标点全被当成词条的一部分了"
    )


def test_multiword_query_returns_results(kb_client):
    """🔴 `训练 强度 区间` 原来 0 条 —— 三词 AND 太严。"""
    _client, svc, _r = kb_client
    hits = svc.search(q="训练 强度 区间")
    assert len(hits.get("results", [])) > 0, (
        "三个词同时出现的段落本来就不多, 搜不到等于功能不可用。"
        "应该从严到宽退让: 全词命中 > 单词命中"
    )


def test_single_word_still_works(kb_client):
    """修多词不能把单词搜坏 —— 这是最基本的。"""
    _client, svc, _r = kb_client
    hits = svc.search(q="训练")
    assert len(hits.get("results", [])) > 0


def test_nonexistent_word_returns_empty_without_error(kb_client):
    """🔴 搜不到 ≠ 搜索崩溃。这两者必须可区分。"""
    _client, svc, _r = kb_client
    hits = svc.search(q="这个词肯定不存在zzzqqq")
    assert hits.get("results") == []
    assert not hits.get("error"), (
        f"搜不到却带了 error: {hits.get('error')} —— "
        f"空结果是一个断言(内容不在库里), 不该和异常混为一谈"
    )


def test_fts_error_is_reported_not_swallowed(kb_client):
    """🔴 FTS 出错时必须说出来, 不能静默返回空。

    否则用户看到"搜不到"会以为知识库里没有, 而真相是搜索坏了。
    """
    client, svc, _r = kb_client

    from sqlalchemy import text as _t

    def boom(*a, **kw):
        raise RuntimeError("模拟 FTS 索引损坏")

    orig = svc.db.execute
    svc.db.execute = boom          # type: ignore[method-assign]
    try:
        hits = svc.search(q="训练")
    finally:
        svc.db.execute = orig      # type: ignore[method-assign]

    assert hits.get("results") == []
    assert hits.get("error"), (
        "FTS 全部失败却返回了干净的空结果 —— "
        "用户在'内容不存在'和'搜索坏了'之间无法分辨"
    )


def test_empty_query_returns_empty_immediately(kb_client):
    _client, svc, _r = kb_client
    assert svc.search(q="   ")["results"] == []


def test_http_layer_search_works(kb_client):
    """端点层也要能用 —— 前端走的是 HTTP。"""
    client, _svc, _r = kb_client
    r = client.get("/api/kb/search", params={"q": "基础、训练"})
    assert r.status_code == 200
    assert len(r.json().get("results", [])) > 0


# ═══════════════════════════════════════════════════════════════
# 变异验证: 把分隔符逻辑改回只有空格, 测试必须失败
# ═══════════════════════════════════════════════════════════════


def test_splitting_regex_actually_covers_the_separators():
    """🔴 直接验分隔符定义本身, 不依赖数据库。

    纯逻辑、无 fixture、跑得快 —— 将来谁把正则改窄了, 这里立刻红。
    """
    from cycling_coach.core.services.kb import _KB_QUERY_SPLIT

    for sep in [" ", "、", "，", ",", "／", "/", "；", ";", "|", "｜", "：", ":"]:
        parts = [t for t in _KB_QUERY_SPLIT.split(f"基础{sep}训练") if t.strip()]
        assert parts == ["基础", "训练"], (
            f"分隔符 {sep!r} 不生效, 切出来是 {parts}。"
            f"用户按 {sep!r} 分词搜索时就是搜不到。"
        )

    # 连续多个分隔符不能产生空词条
    parts = [t for t in _KB_QUERY_SPLIT.split("基础 、， 训练") if t.strip()]
    assert parts == ["基础", "训练"]

    # 前后空白
    parts = [t for t in _KB_QUERY_SPLIT.split("  基础 训练  ") if t.strip()]
    assert parts == ["基础", "训练"]