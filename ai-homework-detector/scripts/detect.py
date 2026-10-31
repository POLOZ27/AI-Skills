#!/usr/bin/env python3
"""本地检测作业文本是否可能由 AI 生成。

使用 AIGC_text_detector（ICLR'24, Apache-2.0）的开源分类模型，完全离线运行：
  中文: yuchuantian/AIGC_detector_zhv3
  英文: yuchuantian/AIGC_detector_env3

用法:
  python detect.py --download                 # 首次使用前下载模型（需联网一次）
  python detect.py 作业.docx                   # 检测单个文件
  python detect.py 作业文件夹/ --out 报告.md    # 批量检测整个文件夹
  python detect.py --text "一段文字"
  python detect.py 作业.txt --json             # 输出 JSON，便于程序处理

结果只是"AI 生成可能性"的参考分数，不能单独作为认定学生作弊的依据。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

MODELS = {
    "zh": os.environ.get("AIGC_MODEL_ZH", "yuchuantian/AIGC_detector_zhv3"),
    "en": os.environ.get("AIGC_MODEL_EN", "yuchuantian/AIGC_detector_env3"),
}
AI_LABEL_INDEX = 1  # 模型输出 [人类, AI]
MAX_TOKENS = 510
SUPPORTED = {".txt", ".md", ".docx", ".pdf"}

# 低于这些长度时分数基本没有参考价值
MIN_CHARS_ZH = 150
MIN_WORDS_EN = 80

HIGH, MEDIUM = 0.85, 0.60


def level_of(p):
    if p >= HIGH:
        return "高"
    if p >= MEDIUM:
        return "中"
    return "低"


def detect_language(text):
    cjk = len(re.findall(r"[一-鿿]", text))
    letters = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk >= letters * 0.3 and cjk > 0 else "en"


def too_short(text, lang):
    if lang == "zh":
        return len(re.findall(r"[一-鿿]", text)) < MIN_CHARS_ZH
    return len(text.split()) < MIN_WORDS_EN


def read_file(path):
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        for enc in ("utf-8-sig", "gb18030", "utf-16"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeError:
                continue
        raise ValueError(f"无法识别文件编码: {path}")
    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            raise SystemExit("读取 .docx 需要先安装: pip install python-docx")
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise SystemExit("读取 .pdf 需要先安装: pip install pypdf")
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    raise ValueError(f"不支持的文件类型: {path.suffix}")


def split_sentences(paragraph, lang):
    if lang == "zh":
        parts = re.split(r"(?<=[。！？；!?])", paragraph)
    else:
        parts = re.split(r"(?<=[.!?])\s+", paragraph)
    return [p for p in parts if p.strip()]


def make_chunks(text, lang, count_tokens):
    """按段落切块，每块不超过模型上限；过长的段落再按句子切。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    pieces = []
    for para in paragraphs:
        if count_tokens(para) <= MAX_TOKENS:
            pieces.append(para)
        else:
            pieces.extend(split_sentences(para, lang))

    joiner = "" if lang == "zh" else " "
    chunks, current = [], ""
    for piece in pieces:
        candidate = (current + "\n" + piece) if current else piece
        if current and count_tokens(candidate) > MAX_TOKENS:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    # 单句仍超长时由分词器截断，这里不再处理
    return [c.replace("\n", joiner) if lang == "en" else c for c in chunks]


class Detector:
    def __init__(self, device=None):
        self._loaded = {}
        self.device = device

    def load(self, lang):
        if lang not in self._loaded:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            name = MODELS[lang]
            tokenizer = AutoTokenizer.from_pretrained(name)
            model = AutoModelForSequenceClassification.from_pretrained(name)
            device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            model.to(device).eval()
            self._loaded[lang] = (tokenizer, model, device)
        return self._loaded[lang]

    def score(self, text, lang):
        import torch

        tokenizer, model, device = self.load(lang)

        def count_tokens(s):
            return len(tokenizer.tokenize(s))

        chunks = make_chunks(text, lang, count_tokens)
        results = []
        for chunk in chunks:
            inputs = tokenizer(chunk, return_tensors="pt", max_length=512, truncation=True).to(device)
            with torch.no_grad():
                probs = model(**inputs).logits[0].softmax(0)
            results.append({"text": chunk, "ai_prob": round(float(probs[AI_LABEL_INDEX]), 4), "tokens": count_tokens(chunk)})
        return results


def analyze(name, text, detector, lang=None):
    text = text.strip()
    if not text:
        return {"name": name, "error": "文本为空"}
    lang = lang or detect_language(text)
    chunks = detector.score(text, lang)
    total = sum(c["tokens"] for c in chunks) or 1
    overall = sum(c["ai_prob"] * c["tokens"] for c in chunks) / total
    return {
        "name": name,
        "language": lang,
        "overall_ai_prob": round(overall, 4),
        "level": level_of(overall),
        "too_short": too_short(text, lang),
        "chunks": [dict(c, level=level_of(c["ai_prob"])) for c in chunks],
    }


def collect_inputs(paths):
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED and not f.name.startswith("~$")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"找不到: {raw}", file=sys.stderr)
    return files


def preview(text, n=60):
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= n else text[:n] + "…"


def to_markdown(results):
    lines = ["# AI 生成可能性检测报告", ""]
    lines.append("> 本报告由本地开源模型生成，只代表\"文本风格与 AI 生成文本的相似度\"，存在误判，"
                 "尤其对写作规范、句式简单或非母语写作的学生。请结合写作过程、面谈和学生以往作业综合判断，"
                 "不要单独作为处分依据。")
    lines.append("")
    if len(results) > 1:
        lines += ["## 汇总", "", "| 作业 | 语言 | AI 可能性 | 等级 | 备注 |", "|---|---|---|---|---|"]
        for r in results:
            if "error" in r:
                lines.append(f"| {r['name']} | - | - | - | {r['error']} |")
                continue
            note = "文本过短，结果不可靠" if r["too_short"] else ""
            lines.append(f"| {r['name']} | {r['language']} | {r['overall_ai_prob']:.0%} | {r['level']} | {note} |")
        lines.append("")
    for r in results:
        lines += [f"## {r['name']}", ""]
        if "error" in r:
            lines += [f"无法检测：{r['error']}", ""]
            continue
        lines.append(f"整体 AI 生成可能性：**{r['overall_ai_prob']:.0%}（{r['level']}）**，语言：{r['language']}")
        if r["too_short"]:
            lines.append("")
            lines.append("⚠️ 文本过短，分数参考价值很低。")
        lines += ["", "| 段 | AI 可能性 | 等级 | 开头 |", "|---|---|---|---|"]
        for i, c in enumerate(r["chunks"], 1):
            lines.append(f"| {i} | {c['ai_prob']:.0%} | {c['level']} | {preview(c['text']).replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)


def download_models():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    for lang, name in MODELS.items():
        print(f"下载 {lang} 模型: {name}")
        AutoTokenizer.from_pretrained(name)
        AutoModelForSequenceClassification.from_pretrained(name)
    print("完成。之后可设置环境变量 HF_HUB_OFFLINE=1 完全离线运行。")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="本地检测作业是否可能由 AI 生成（仅供参考）")
    ap.add_argument("paths", nargs="*", help="作业文件或文件夹（.txt .md .docx .pdf）")
    ap.add_argument("--text", help="直接检测一段文字")
    ap.add_argument("--lang", choices=["zh", "en"], help="强制指定语言，默认自动识别")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--out", help="把报告写入文件")
    ap.add_argument("--device", help="cpu 或 cuda，默认自动")
    ap.add_argument("--download", action="store_true", help="下载模型后退出")
    args = ap.parse_args()

    if args.download:
        download_models()
        return

    if not args.text and not args.paths:
        ap.error("请提供作业文件/文件夹，或使用 --text")

    detector = Detector(args.device)
    results = []
    if args.text:
        results.append(analyze("输入文本", args.text, detector, args.lang))
    for f in collect_inputs(args.paths):
        try:
            results.append(analyze(f.name, read_file(f), detector, args.lang))
        except (ValueError, OSError) as e:
            results.append({"name": f.name, "error": str(e)})

    output = json.dumps(results, ensure_ascii=False, indent=2) if args.json else to_markdown(results)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"报告已保存到 {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
