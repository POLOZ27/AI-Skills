"""
title: AI Homework Detector
description: 本地检测作业文本是否可能由 AI 生成（中英文），使用开源 AIGC_text_detector 模型，结果仅供参考
version: 0.2.0
license: Apache-2.0
requirements: transformers, torch
"""

import asyncio
import os
import re
import threading

from pydantic import BaseModel, Field

AI_LABEL_INDEX = 1  # 模型输出 [人类, AI]
MAX_TOKENS = 510

_MODELS = {}
_LOCK = threading.Lock()


def _detect_language(text):
    cjk = len(re.findall(r"[一-鿿]", text))
    letters = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk >= letters * 0.3 and cjk > 0 else "en"


def _split_sentences(paragraph, lang):
    if lang == "zh":
        parts = re.split(r"(?<=[。！？；!?])", paragraph)
    else:
        parts = re.split(r"(?<=[.!?])\s+", paragraph)
    return [p for p in parts if p.strip()]


def _make_chunks(text, lang, count_tokens):
    paragraphs = [p.strip() for p in re.split(r"\n", text) if p.strip()]
    pieces = []
    for para in paragraphs:
        if count_tokens(para) <= MAX_TOKENS:
            pieces.append(para)
        else:
            pieces.extend(_split_sentences(para, lang))
    sep = "\n" if lang == "zh" else " "
    chunks, current = [], ""
    for piece in pieces:
        candidate = (current + sep + piece) if current else piece
        if current and count_tokens(candidate) > MAX_TOKENS:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class Tools:
    class Valves(BaseModel):
        model_zh: str = Field("yuchuantian/AIGC_detector_zhv3", description="中文检测模型")
        model_en: str = Field("yuchuantian/AIGC_detector_env3", description="英文检测模型")
        cache_dir: str = Field(
            "/app/backend/data/cache/aigc_detector",
            description="模型缓存目录，放在数据卷里，容器重建后不会丢",
        )
        high_threshold: float = Field(0.95, description="高于此值为'高'（2026-10-31 校准：英文真人作文约 0.7% 落在此等级）")
        medium_threshold: float = Field(0.80, description="高于此值为'中'（2026-10-31 校准：英文真人作文约 1.6% 达到中或以上）")
        min_chars_zh: int = Field(150, description="中文少于此字数时提示不可靠")
        min_words_en: int = Field(80, description="英文少于此词数时提示不可靠")
        cpu_threads: int = Field(8, description="推理使用的 CPU 线程数")

    def __init__(self):
        self.valves = self.Valves()

    def _load(self, lang):
        name = self.valves.model_zh if lang == "zh" else self.valves.model_en
        with _LOCK:
            if name not in _MODELS:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                torch.set_num_threads(self.valves.cpu_threads)
                os.makedirs(self.valves.cache_dir, exist_ok=True)
                tokenizer = AutoTokenizer.from_pretrained(name, cache_dir=self.valves.cache_dir)
                model = AutoModelForSequenceClassification.from_pretrained(name, cache_dir=self.valves.cache_dir)
                model.eval()
                _MODELS[name] = (tokenizer, model)
            return _MODELS[name]

    def _level(self, p):
        if p >= self.valves.high_threshold:
            return "高"
        if p >= self.valves.medium_threshold:
            return "中"
        return "低"

    def _false_positive_note(self, level, lang):
        """Calibrated 2026-10-31 on 1,000 pre-ChatGPT English student essays (PERSUADE 2.0) at thresholds 0.95 / 0.80."""
        if lang != "en":
            return "误判率参考：中文检测尚未用真实学生作文校准，误判率未知，请格外谨慎。"
        if level == "高":
            return "误判率参考：在 1,000 篇 ChatGPT 出现前的真实中学生英文作文测试中，约 0.7% 的真人作文（约每 150 篇 1 篇）会落在『高』。"
        if level == "中":
            return "误判率参考：同一测试中，约 1.6% 的真人作文会达到『中』或以上。"
        return "误判率参考：『低』不代表一定是学生自己写的，改写过的 AI 文本也可能得低分。"

    def _too_short(self, text, lang):
        if lang == "zh":
            return len(re.findall(r"[一-鿿]", text)) < self.valves.min_chars_zh
        return len(text.split()) < self.valves.min_words_en

    def _analyze(self, text, lang):
        import torch

        tokenizer, model = self._load(lang)

        def count_tokens(s):
            return len(tokenizer.tokenize(s))

        rows = []
        for chunk in _make_chunks(text, lang, count_tokens):
            inputs = tokenizer(chunk, return_tensors="pt", max_length=512, truncation=True)
            with torch.no_grad():
                probs = model(**inputs).logits[0].softmax(0)
            rows.append((chunk, float(probs[AI_LABEL_INDEX]), count_tokens(chunk)))
        total = sum(r[2] for r in rows) or 1
        overall = sum(r[1] * r[2] for r in rows) / total
        return overall, rows

    async def detect_ai_generated_text(self, text: str, language: str = "auto", __event_emitter__=None) -> str:
        """
        检测一段作业文本是否可能由 AI 生成，返回整体 AI 生成可能性、高/中/低等级和每段的分数。
        老师想知道学生作业是不是 AI（ChatGPT、DeepSeek、Qwen 等）写的时调用。把作业全文原样传入，不要删改或总结。
        :param text: 要检测的作业全文
        :param language: zh、en 或 auto（自动识别）
        :return: Markdown 格式的检测结果，结果仅供参考
        """
        text = (text or "").strip()
        if not text:
            return "没有收到要检测的文本。"
        lang = language if language in ("zh", "en") else _detect_language(text)

        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "正在本地检测 AI 生成可能性…", "done": False}})
        try:
            overall, rows = await asyncio.to_thread(self._analyze, text, lang)
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "检测失败", "done": True}})
            return f"检测失败：{e}"
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "检测完成", "done": True}})

        level = self._level(overall)
        lines = [
            f"检测模型分数：{overall:.0%}（等级：{level}），语言：{lang}",
            self._false_positive_note(level, lang),
            "提示：分数高的往往是写得规范、篇幅较短的议论文；文本只有一段时，一个分数就决定整篇。",
        ]
        if self._too_short(text, lang):
            lines.append("注意：文本过短，分数参考价值很低。")
        lines += ["", "| 段 | AI 可能性 | 等级 | 开头 |", "|---|---|---|---|"]
        for i, (chunk, p, _) in enumerate(rows, 1):
            head = re.sub(r"\s+", " ", chunk)
            head = (head[:40] + "…") if len(head) > 40 else head
            lines.append(f"| {i} | {p:.0%} | {self._level(p)} | {head.replace('|', '/')} |")
        lines += [
            "",
            "说明：分数来自本地开源检测模型，只表示文本与 AI 生成文本的相似程度，会误判（尤其是写作规范、句式简单或非母语写作的学生），"
            "也可能被改写绕过。不能单独作为认定作弊或处分的依据，请结合写作过程、面谈和以往作业综合判断。",
        ]
        return "\n".join(lines)
