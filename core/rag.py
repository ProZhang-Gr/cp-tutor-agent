# -*- coding: utf-8 -*-
"""RAG 题库：基于 LangChain 的检索增强。

用 langchain_community 的 TFIDFRetriever 建立题库索引，无需下载向量模型，
开箱即用。中文用字符级 n-gram（char_wb）做特征，规避中文分词依赖。
检索给定题面，返回最相似的若干道历史题，供"举一反三"参考。
"""
import json

from langchain_community.retrievers import TFIDFRetriever
from langchain_core.documents import Document

from config import settings


class ProblemBank:
    def __init__(self, path=None):
        self.path = path or settings.PROBLEM_BANK
        with open(self.path, "r", encoding="utf-8") as f:
            self.problems = json.load(f)
        self._by_id = {p["id"]: p for p in self.problems}
        self.retriever = self._build_retriever()

    def _build_retriever(self):
        docs = []
        for p in self.problems:
            # 把标题、类型、标签、题面拼成可检索文本
            text = "%s 类型:%s 标签:%s %s" % (
                p["title"], p["type"], " ".join(p.get("tags", [])),
                p["description"],
            )
            docs.append(Document(page_content=text, metadata={"id": p["id"]}))
        # 字符级 n-gram，适配中文；同时保留对英文标签的匹配
        return TFIDFRetriever.from_documents(
            docs,
            tfidf_params={"analyzer": "char_wb", "ngram_range": (1, 2)},
            k=4,
        )

    def list_all(self):
        return self.problems

    def get(self, pid):
        return self._by_id.get(pid)

    def search(self, query, k=3):
        """检索相似题，返回精简信息列表。"""
        self.retriever.k = k + 1  # 多取一个，便于过滤掉查询本身
        docs = self.retriever.invoke(query)
        out = []
        for d in docs:
            p = self._by_id.get(d.metadata.get("id"))
            if not p:
                continue
            # 题面高度重合（同一题）时跳过
            if query.strip() and p["description"][:30] in query:
                continue
            out.append({
                "id": p["id"], "title": p["title"], "type": p["type"],
                "difficulty": p["difficulty"], "tags": p.get("tags", []),
            })
            if len(out) >= k:
                break
        return out


# 单例
_bank = None


def get_bank():
    global _bank
    if _bank is None:
        _bank = ProblemBank()
    return _bank
