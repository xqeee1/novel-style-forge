#!/usr/bin/env python3
"""Chinese fiction stylometry primitives for novel-style-forge.

Only requires jieba. When jieba is unavailable, falls back to character
bigrams and marks the result as degraded so that downstream reasoning knows
vocabulary-level numbers are approximations.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff]")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
SENT_RE = re.compile(r"[^。！？!?…；;]*[。！？!?…；;]+[”\"』」）)]*|[^。！？!?…；;]+$")
DLG_RE = re.compile(r"[“「『\"]([^”」』\"]{1,500})[”」』\"]")
CHAPTER_RE = re.compile(r"^\s*(第[零〇一二三四五六七八九十百千两0-9]+[章节回卷部篇]|Chapter\s+\d+|CHAPTER\s+\d+)", re.M)
AA_RE = re.compile(r"([\u4e00-\u9fff])\1")
AABB_RE = re.compile(r"([\u4e00-\u9fff])\1([\u4e00-\u9fff])\2")

STOPWORDS = set("""
的 了 在 是 和 就 不 也 很 到 说 要 去 会 着 没有 看 好 自己 这 那 它 们 中 为 对 与 以 及 等 被 把 让 从 但 而 并 或 如 若 虽 却 又 再 还 只 更 最 已 曾 将 时 后 前 里 下 内 外 间 之 其 此 该 某 每 各 些 个 啊 呢 吧 吗 呀 哦 嗯 唉 嘿 哈 一 二 三 上 来 起 过 得 地 得 所 由 于 向 给 同 当 用 能 可 都 才 便 就 才 又 忽 一 个 什么 怎么 怎样 如此 这样 那样 这里 那里 时候 现在 已经 因为 所以 虽然 但是 如果 而且 并且 于是 然后 一直 只是 还是 或者 一个 一声 一下 一点 有些 有些 这些 那些
""".split())

PRONOUNS_1 = ["我", "我们", "咱", "咱们", "俺", "本人", "自家"]
PRONOUNS_2 = ["你", "你们", "您", "尔等", "汝"]
PRONOUNS_3 = ["他", "她", "他们", "她们", "它", "它们", "那人", "此人"]

CLASSICAL_MARKERS = [
    "亦", "乃", "皆", "甚", "颇", "曰", "遂", "俄而", "须臾", "少顷",
    "但见", "只见", "却说", "兀自", "端的", "不曾", "未曾", "方才",
    "登时", "竟自", "堪堪", "且说", "话说", "登时", "一径", "越发",
]
COLLOQUIAL_MARKERS = [
    "吧", "嘛", "呗", "啥", "咋", "嗯", "哎", "哦", "嘞", "甭",
    "咋整", "可不", "得了吧", "拉倒", "玩意儿", "一准", "准保", "搁这儿",
]
SIMILE_MARKERS = ["仿佛", "宛如", "犹如", "好似", "如同", "恰似", "好比", "像是", "似乎", "竟似"]
COLOR_WORDS = ["红", "白", "黑", "青", "灰", "蓝", "绿", "黄", "紫", "金", "银", "苍白", "通红", "漆黑", "灰白", "暗红", "雪白", "乌黑"]
SENSORY_GROUPS = {
    "视觉": ["望见", "瞧见", "凝视", "注视", "瞥见", "打量", "端详", "闪过", "映入", "泛着", "蒙着", "晃了晃", "影影绰绰"],
    "听觉": ["听见", "听得", "传来", "响起", "沙沙", "簌簌", "叮当", "轰隆", "嗡嗡", "回声", "静得", "悄无声息"],
    "嗅觉": ["闻到", "气味", "香味", "腥味", "焦味", "清香", "刺鼻", "芬芳", "霉味"],
    "味觉": ["尝到", "甜味", "苦味", "酸涩", "发涩", "腥甜", "回甘"],
    "触觉": ["摸到", "触到", "冰凉", "滚烫", "粗糙", "滑腻", "潮湿", "刺痛", "拂过", "黏腻"],
}

CAT_NOUN = {"n", "nr", "ns", "nt", "nz", "ng", "nrt", "s", "t", "j", "l"}
CAT_VERB = {"v", "vd", "vn", "vg", "vi", "vq", "vf"}
CAT_ADJ = {"a", "ad", "an", "ag", "al", "z"}
CAT_ADV = {"d", "df", "dg"}


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def cjk_len(s: str) -> int:
    return len(CJK.findall(s))


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n+", text) if p.strip()]


def split_sentences(paragraph: str) -> list[str]:
    return [m.group().strip() for m in SENT_RE.finditer(paragraph) if m.group().strip()]


def _jieba_posseg():
    try:
        import jieba
        import jieba.posseg as pseg
        try:
            jieba.setLogLevel(60)
        except Exception:
            pass
        return pseg
    except ImportError:
        return None


def tokenize(text: str) -> tuple[list[tuple[str, str]], str]:
    """Return [(word, pos_flag)] plus the tokenizer mode."""
    chunks = CJK_RUN.findall(text)
    pseg = _jieba_posseg()
    out: list[tuple[str, str]] = []
    if pseg is not None:
        for chunk in chunks:
            for word, flag in pseg.lcut(chunk):
                word = word.strip()
                if word and CJK.search(word):
                    out.append((word, flag))
        return out, "jieba"
    for chunk in chunks:
        for i in range(0, len(chunk) - 1, 2):
            out.append((chunk[i: i + 2], "x"))
    return out, "fallback-bigram"


def pos_category(flag: str) -> str:
    if flag in CAT_NOUN:
        return "noun"
    if flag in CAT_VERB:
        return "verb"
    if flag in CAT_ADJ:
        return "adj"
    if flag in CAT_ADV:
        return "adv"
    if flag in ("r",):
        return "pronoun"
    if flag in ("i", "l"):
        return "idiom"
    if flag in ("o",):
        return "onomatopoeia"
    if flag in ("y", "e"):
        return "modal"
    if flag in ("c", "p", "u", "q", "m", "f", "w", "x"):
        return "function"
    return "other"


def moving_ttr(words: list[str], window: int = 1000) -> float:
    n = len(words)
    if n == 0:
        return 0.0
    if n <= window:
        return len(set(words)) / n
    counts = Counter(words[:window])
    distinct = len(counts)
    values = [distinct / window]
    for i in range(window, n):
        leaving = words[i - window]
        counts[leaving] -= 1
        if counts[leaving] == 0:
            del counts[leaving]
            distinct -= 1
        entering = words[i]
        if entering not in counts:
            distinct += 1
        counts[entering] += 1
        values.append(distinct / window)
    return sum(values) / len(values)


def _density(count: int, chars: int) -> float:
    return round(1000.0 * count / max(chars, 1), 3)


def _count_terms(text: str, terms: list[str]) -> int:
    """Count term occurrences directly in the text, longest first to avoid overlap.
    Keeps person statistics reliable even when jieba is unavailable."""
    if not terms:
        return 0
    pattern = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return len(re.findall(pattern, text))


def _safe_std(values: list[float]) -> float:
    return round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1)))], 2)


def compute_profile(text: str, title: str = "", author: str = "", max_chars: int = 500000) -> dict:
    text = normalize(text)
    warnings: list[str] = []
    total_chars = cjk_len(text)
    if total_chars > max_chars:
        warnings.append(f"Text exceeds {max_chars} CJK characters; only the first window was measured.")
        # keep a coherent prefix at a paragraph boundary
        kept, used = [], 0
        for p in split_paragraphs(text):
            n = cjk_len(p)
            if used + n > max_chars:
                break
            kept.append(p)
            used += n
        text = "\n\n".join(kept)
        total_chars = cjk_len(text)
    if total_chars < 300:
        warnings.append("Sample shorter than 300 Chinese characters: all metrics are unstable.")
    elif total_chars < 3000:
        warnings.append("Sample shorter than 3000 Chinese characters: treat vocabulary statistics as indicative only.")
    if total_chars and total_chars / max(len(text), 1) < 0.35:
        warnings.append("Low CJK ratio: file may contain markup, code, or non-Chinese prose.")

    paragraphs = split_paragraphs(text)
    sentences: list[str] = []
    dialogue_chars = 0
    dialogue_turns = 0
    dialogue_paragraphs = 0
    for p in paragraphs:
        sentences.extend(split_sentences(p))
        for m in DLG_RE.finditer(p):
            dialogue_chars += cjk_len(m.group(1))
            dialogue_turns += 1
        if p.lstrip().startswith(("“", "「", "『", '"')) and DLG_RE.search(p):
            dialogue_paragraphs += 1

    sent_lens = [cjk_len(s) for s in sentences]
    sent_lens = [n for n in sent_lens if n > 0]
    para_lens = [cjk_len(p) for p in paragraphs]
    para_lens = [n for n in para_lens if n > 0]
    hist = {
        "le10": sum(1 for n in sent_lens if n <= 10),
        "11to20": sum(1 for n in sent_lens if 11 <= n <= 20),
        "21to35": sum(1 for n in sent_lens if 21 <= n <= 35),
        "36to60": sum(1 for n in sent_lens if 36 <= n <= 60),
        "gt60": sum(1 for n in sent_lens if n > 60),
    }
    n_sent = max(len(sent_lens), 1)
    tokens, tokenizer = tokenize(text)
    words = [w for w, _ in tokens]
    word_count = max(len(words), 1)
    counter = Counter(words)
    first_flag: dict[str, str] = {}
    for w, flag in tokens:
        first_flag.setdefault(w, flag)
    cats = Counter(pos_category(flag) for _, flag in tokens)
    if tokenizer != "jieba":
        warnings.append("jieba unavailable: vocabulary metrics use character bigrams and are approximate. Run `run.py setup`.")

    def top_words(cat: str | None, n: int = 20) -> list[dict]:
        out = []
        for w, c in counter.most_common():
            if w in STOPWORDS or len(w) < 2:
                continue
            if cat is not None and pos_category(first_flag.get(w, "x")) != cat:
                continue
            out.append({"word": w, "count": c, "flag": first_flag.get(w, "x")})
            if len(out) >= n:
                break
        return out

    openers = Counter()
    enders = Counter()
    for s in sentences:
        run = "".join(CJK.findall(s))
        if len(run) >= 2:
            openers[run[:2]] += 1
            enders[run[-2:]] += 1

    sensory: dict[str, int] = {}
    for k, group in SENSORY_GROUPS.items():
        sensory[k] = sum(text.count(w) for w in group)
    classical_hits = sum(text.count(w) for w in CLASSICAL_MARKERS)
    colloquial_hits = sum(text.count(w) for w in COLLOQUIAL_MARKERS)
    simile_hits = sum(text.count(w) for w in SIMILE_MARKERS)
    color_hits = sum(text.count(w) for w in COLOR_WORDS)
    four_char = sum(1 for w in words if len(w) >= 4 and CJK.search(w))
    idioms = cats.get("idiom", 0)
    aa = len(AA_RE.findall(text))
    aabb = len(AABB_RE.findall(text))
    chapters = len(CHAPTER_RE.findall(text))

    p1 = _count_terms(text, PRONOUNS_1)
    p2 = _count_terms(text, PRONOUNS_2)
    p3 = _count_terms(text, PRONOUNS_3)
    person_scores = {"first": p1, "second": p2, "third": p3}
    dominant = max(person_scores, key=person_scores.get) if max(person_scores.values()) > 0 else "undetermined"

    comma = text.count("，") + text.count(",")
    punctuation = {
        "comma_per_1k": _density(comma, total_chars),
        "period_per_1k": _density(text.count("。"), total_chars),
        "semicolon_per_1k": _density(text.count("；") + text.count(";"), total_chars),
        "colon_per_1k": _density(text.count("：") + text.count(":"), total_chars),
        "dash_per_1k": _density(text.count("——") + text.count("—"), total_chars),
        "ellipsis_per_1k": _density(text.count("……") + text.count("…"), total_chars),
        "exclamation_per_1k": _density(text.count("！") + text.count("!"), total_chars),
        "question_per_1k": _density(text.count("？") + text.count("?"), total_chars),
        "quote_pairs_per_1k": _density(dialogue_turns, total_chars),
    }
    syntax = {
        "avg_sentence_chars": round(statistics.fmean(sent_lens), 2) if sent_lens else 0.0,
        "median_sentence_chars": round(statistics.median(sent_lens), 2) if sent_lens else 0.0,
        "std_sentence_chars": _safe_std(sent_lens),
        "p90_sentence_chars": _pct(sent_lens, 0.9),
        "short_sentence_ratio_le10": round(sum(1 for n in sent_lens if n <= 10) / n_sent, 4),
        "long_sentence_ratio_ge36": round(sum(1 for n in sent_lens if n >= 36) / n_sent, 4),
        "sentence_length_histogram": hist,
        "avg_paragraph_chars": round(statistics.fmean(para_lens), 2) if para_lens else 0.0,
        "std_paragraph_chars": _safe_std(para_lens),
        "single_sentence_paragraph_ratio": round(
            sum(1 for p in paragraphs if len(split_sentences(p)) == 1) / max(len(paragraphs), 1), 4),
        "comma_per_sentence": round(comma / n_sent, 3),
        "sentence_count": len(sent_lens),
        "paragraph_count": len(paragraphs),
    }
    vocabulary = {
        "ttr": round(len(counter) / word_count, 4),
        "mattr_1000": round(moving_ttr(words), 4),
        "hapax_ratio": round(sum(1 for c in counter.values() if c == 1) / len(counter), 4) if counter else 0.0,
        "avg_word_len": round(statistics.fmean([len(w) for w in words]), 3) if words else 0.0,
        "single_char_word_ratio": round(sum(1 for w in words if len(w) == 1) / word_count, 4),
        "two_char_word_ratio": round(sum(1 for w in words if len(w) == 2) / word_count, 4),
        "four_char_per_1k": _density(four_char, total_chars),
        "idiom_per_1k": _density(idioms, total_chars),
        "reduplication_aa_per_1k": _density(aa, total_chars),
        "reduplication_aabb_per_1k": _density(aabb, total_chars),
        "classical_per_1k": _density(classical_hits, total_chars),
        "colloquial_per_1k": _density(colloquial_hits, total_chars),
        "simile_per_1k": _density(simile_hits, total_chars),
        "sensory_per_1k": _density(sum(sensory.values()), total_chars),
        "color_per_1k": _density(color_hits, total_chars),
        "noun_ratio": round(cats.get("noun", 0) / word_count, 4),
        "verb_ratio": round(cats.get("verb", 0) / word_count, 4),
        "adj_ratio": round(cats.get("adj", 0) / word_count, 4),
        "adv_ratio": round(cats.get("adv", 0) / word_count, 4),
        "pronoun_ratio": round(cats.get("pronoun", 0) / word_count, 4),
        "function_word_ratio": round(cats.get("function", 0) / word_count, 4),
        "idiom_ratio": round(idioms / word_count, 4),
        "onomatopoeia_per_1k": _density(cats.get("onomatopoeia", 0), total_chars),
    }
    dialogue_ratio = round(dialogue_chars / max(total_chars, 1), 4)
    narration = {
        "dialogue_char_ratio": dialogue_ratio,
        "dialogue_paragraph_ratio": round(dialogue_paragraphs / max(len(paragraphs), 1), 4),
        "dialogue_turns": dialogue_turns,
        "first_person_per_1k": _density(p1, total_chars),
        "second_person_per_1k": _density(p2, total_chars),
        "third_person_per_1k": _density(p3, total_chars),
        "dominant_person": dominant,
        "chapter_count": chapters,
        "avg_chapter_chars": round(total_chars / chapters, 1) if chapters else None,
    }
    if dialogue_ratio > 0.55:
        warnings.append("Dialogue exceeds 55% of the text: sentence-length metrics are dominated by speech.")

    profile = {
        "meta": {
            "title": title, "author": author, "chars": total_chars,
            "sentences": len(sent_lens), "paragraphs": len(paragraphs),
            "words": len(words), "tokenizer": tokenizer,
        },
        "syntax": syntax,
        "punctuation": punctuation,
        "vocabulary": vocabulary,
        "narration": narration,
        "signature": {
            "top_content_words": top_words(None, 40),
            "top_verbs": top_words("verb", 20),
            "top_nouns": top_words("noun", 20),
            "top_adjectives": top_words("adj", 20),
            "top_adverbs": top_words("adv", 20),
            "sentence_openers": [{"word": w, "count": c} for w, c in openers.most_common(20)],
            "sentence_enders": [{"word": w, "count": c} for w, c in enders.most_common(20)],
            "sensory_profile": sensory,
        },
        "warnings": warnings,
    }
    return profile


# Numeric metrics used by compare_style.py. Weight reflects how much a metric
# shapes the reader's perception of "the same voice".
METRIC_SPECS = [
    ("syntax.avg_sentence_chars", "平均句长", 1.5,
     "句长偏短：把两三个短句并成长句，补入状语、定语或从句，减少句号；目标约 {t} 字/句。",
     "句长偏长：拆开长句，多用句号与短促独立句，删去叠加的修饰；目标约 {t} 字/句。"),
    ("syntax.std_sentence_chars", "句长起伏", 1.0,
     "句长过于均匀：刻意插入极短句（3–8 字）与一个长句，制造长短落差。",
     "句长落差过大：收紧极端长句，让节奏更均匀一些。"),
    ("syntax.short_sentence_ratio_le10", "短句比例", 1.0,
     "短句太少：在动作或转折处改用 10 字以内的独立短句。",
     "短句太多：合并部分短句，增加连贯叙述。"),
    ("syntax.long_sentence_ratio_ge36", "长句比例", 0.9,
     "长句太少：补一两处 36 字以上的铺陈句（环境、心理、回忆）。",
     "长句太多：把长句切成两到三句。"),
    ("syntax.avg_paragraph_chars", "平均段长", 0.9,
     "段落偏短：把同场景的叙述合并成更长的段落，减少换行。",
     "段落偏长：在场景切换、动作转折处分段。"),
    ("syntax.comma_per_sentence", "句内逗号密度", 0.8,
     "逗号偏少：句内多用逗号分层，容许一逗到底的绵长语气。",
     "逗号偏多：减少分句，改用句号收束。"),
    ("narration.dialogue_char_ratio", "对话占比", 1.2,
     "对话太少：增加直接引语与人物交锋，减少概述性叙述。",
     "对话太多：补入叙述、描写与心理活动，压缩直接引语。"),
    ("narration.dialogue_paragraph_ratio", "对话独立成段比例", 0.6,
     "对话未独立成段：让每轮对话单独起段。",
     "对话分段过多：把部分对话并入叙述段落。"),
    ("narration.first_person_per_1k", "第一人称密度", 0.9,
     "第一人称偏少：若目标是第一人称叙述，增加「我」的感知与判断。",
     "第一人称偏多：改用客观陈述或他人视角，减少「我」。"),
    ("narration.third_person_per_1k", "第三人称密度", 0.9,
     "第三人称偏少：多用人物姓名或「他/她」推进叙述。",
     "第三人称偏多：增加人物自称或直述，拉开距离感。"),
    ("vocabulary.mattr_1000", "词汇丰富度", 1.2,
     "用词重复度高：替换重复实词，引入同义与更具体的名词动词。",
     "用词过于花哨：适当复用核心词，减少生僻替换，让语流更稳。"),
    ("vocabulary.avg_word_len", "平均词长", 0.6,
     "词长偏短：多用双音节/书面词与四字格。",
     "词长偏长：改用短词、口语词，减少四字格。"),
    ("vocabulary.single_char_word_ratio", "单字词比例", 0.5,
     "单字词偏少：适度启用单字动词与单字形容词，制造古简感。",
     "单字词偏多：改用双音节词，语感更现代。"),
    ("vocabulary.four_char_per_1k", "四字格密度", 0.7,
     "四字格偏少：在描写与概括处加入成语或四字短语。",
     "四字格偏多：拆成白话短句，减少整齐的四字节奏。"),
    ("vocabulary.classical_per_1k", "文言/旧白话标记", 0.8,
     "书面古语偏少：加入「方才」「但见」「不曾」「遂」一类标记。",
     "书面古语偏多：改成现代白话，删去旧小说套语。"),
    ("vocabulary.colloquial_per_1k", "口语标记", 0.8,
     "口语味不足：加入语气词、俗语与短促应答。",
     "口语味过重：收敛语气词与俚俗表达。"),
    ("vocabulary.simile_per_1k", "比喻标记密度", 0.8,
     "比喻偏少：增加「仿佛」「宛如」类明喻，注意喻体要贴合原文的意象域。",
     "比喻偏多：删去部分明喻，改用直陈。"),
    ("vocabulary.sensory_per_1k", "感官描写密度", 0.8,
     "感官描写不足：补入视觉之外的听觉、嗅觉、触觉细节。",
     "感官描写过密：删减部分感官词，留出白描。"),
    ("vocabulary.color_per_1k", "色彩词密度", 0.6,
     "色彩词偏少：在景物与服饰处点入颜色。",
     "色彩词偏多：减少直白的颜色词，改用光影与质感。"),
    ("vocabulary.verb_ratio", "动词占比", 0.9,
     "动词偏少：把静态「是/有」结构换成动作动词，让句子推进。",
     "动词偏多：增加状态描写与停顿，别让画面一直赶。"),
    ("vocabulary.adj_ratio", "形容词占比", 0.9,
     "形容词偏少：补入限定与修饰，让描写更铺陈。",
     "形容词偏多：删去堆叠的修饰，改用白描与名词。"),
    ("vocabulary.noun_ratio", "名词占比", 0.6,
     "名词密度偏低：增加具体物象与名词性细节。",
     "名词密度偏高：增加动作与连接，避免名词罗列。"),
    ("vocabulary.pronoun_ratio", "代词占比", 0.5,
     "代词偏少：若原文靠代词承接，补足人物指代。",
     "代词偏多：改用姓名或具体名词，减少「他/她」堆叠。"),
    ("punctuation.ellipsis_per_1k", "省略号密度", 0.5,
     "省略号偏少：在迟疑、留白处使用省略号。",
     "省略号偏多：改用句号或动作描写收束。"),
    ("punctuation.dash_per_1k", "破折号密度", 0.5,
     "破折号偏少：在补充说明、语气转折处使用破折号。",
     "破折号偏多：改为逗号或分句。"),
    ("punctuation.exclamation_per_1k", "感叹号密度", 0.5,
     "情绪强度不足：在冲突高潮处使用感叹与短促句。",
     "感叹号偏多：收住外露情绪，改用克制的陈述。"),
    ("punctuation.question_per_1k", "问号密度", 0.4,
     "问句偏少：增加人物追问与反问。",
     "问句偏多：把部分问句改成陈述或内心判断。"),
    ("punctuation.comma_per_1k", "逗号密度", 0.5,
     "逗号偏少：增加句内停顿与分层。",
     "逗号偏多：减少细碎停顿。"),
]


def get_metric(profile: dict, path: str) -> float:
    node = profile
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return 0.0
        node = node[part]
    return float(node) if isinstance(node, (int, float)) else 0.0


def content_word_sets(profile: dict, n: int = 40) -> tuple[set[str], dict[str, int]]:
    items = profile.get("signature", {}).get("top_content_words", [])[:n]
    return {x["word"] for x in items}, {x["word"]: x["count"] for x in items}
