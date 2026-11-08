# 工具链、命令与排错

## 依赖

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.9+ | `run.py` 用系统 Python 启动 |
| jieba | 自动安装 | 唯一依赖，纯 Python；装在 `~/.workbuddy/.cache/novel-style-forge-venv`，首次需联网一次 |

`run.py setup` 预先准备环境；`run.py check` 打印解释器、实际运行时与 jieba 版本。

**离线机器**：若系统 Python 已装 jieba 则直接可用。装不上时脚本不会崩溃，会降级为「汉字二元组」分词并在 `warnings` 标注降级；此时 `ttr`/词长/词性/高频词表均为近似值，句长、段落、标点、对话、人称统计仍然可靠。不要拿降级档案的词汇指标做精确结论。

## 输入准备

- 脚本读纯文本：`.txt` / `.md`，自动尝试 UTF-8-SIG、UTF-8、GB18030、Big5。
- 用户直接粘贴小说正文时，先把正文原样写入档案目录的 `source.txt`，再传给 `--input`。
- PDF / docx / epub 等先用对应的文件读取能力转成纯文本，**只保留正文**：删掉目录、页码、章节广告、评论、插图说明，否则会污染词频与段落统计。
- 建议样本 ≥3000 汉字，理想 1–5 万字；短篇可整篇，长篇优先取连续的 2–3 万字（避免只取对话密集章节）。
- 样本里若含章回标题，脚本会统计章节数；标题行本身也会进入词频，解读 `top_nouns` 时留意。

## 命令参考

```
python "{SKILL_DIR}/scripts/run.py" check
python "{SKILL_DIR}/scripts/run.py" setup
python "{SKILL_DIR}/scripts/run.py" analyze --input source.txt --out profile.json \
    [--title "书名"] [--author "作者"] [--max-chars 500000]
python "{SKILL_DIR}/scripts/run.py" compare --profile profile.json --input draft.txt \
    --out comparison.json [--top 8]
```

- `analyze` 输出 `profile.json`：句法、标点、词汇、叙事、用词签名、warnings。
- `compare` 输出 `comparison.json`：综合相似度、等级、词汇重合、按优先级排序的偏离项与中文改写建议。
- 所有路径参数加英文双引号；Windows 控制台输出为 ASCII，中文内容写在 JSON/Markdown 文件里（UTF-8）。
- 较长样本（>50 万汉字）默认只测前 50 万字并给出 warning；可用 `--max-chars` 调整。

## 档案库约定

在用户当前工作区建立：

```
novel-style-forge/
└── profiles/
    └── <slug>/                 # 由作者名或书名生成的短英文/拼音标识
        ├── source.txt           # 原始样本（仅本地，不随 Skill 分发）
        ├── profile.json         # 客观指标
        ├── style-profile.md     # 完整风格档案
        ├── style-card.md        # 精简创作卡（≤600 字）
        └── runs/
            └── <日期>-<题材>/
                ├── draft.md
                ├── comparison.json
                └── final.md
```

- 用户说「用上次那个风格写」「用某某的风格」时，先列 `profiles/` 找对应档案；多个候选要问清是哪一个，不要猜。
- 同一作者补充新样本时，新生成一个 `<slug>-2` 档案，或与用户确认后覆盖；不要静默合并。
- 档案可跨会话复用，只要工作区不变。

## JSON 关键字段速查

| 路径 | 含义 |
| --- | --- |
| `meta.chars` / `meta.tokenizer` | 有效汉字数、分词器（`jieba` 或 `fallback-bigram`） |
| `syntax.avg_sentence_chars` / `std_sentence_chars` | 句长均值与起伏 |
| `syntax.sentence_length_histogram` | 五档句长分布计数 |
| `vocabulary.mattr_1000` | 滑动窗口词汇丰富度 |
| `vocabulary.verb_ratio` / `adj_ratio` / `noun_ratio` | 词性占比（动作 vs 铺陈） |
| `narration.dialogue_char_ratio` | 对话汉字占比 |
| `narration.dominant_person` | 人称代词统计推断，需回原文确认 |
| `signature.top_verbs` / `top_nouns` / `top_adjectives` | 高频实词榜 |
| `comparison.top_deviations[].hint` | 可直接执行的改写动作 |
| `comparison.word_overlap.target_word_coverage` | 特征词重合率，**过高反而是警讯** |

## 故障排查

| 现象 | 处理 |
| --- | --- |
| `jieba installation failed` | 检查网络；或手动 `python -m pip install jieba`。离线时接受降级档案，并在报告里标注词汇指标不可靠 |
| 输出乱码 / 报编码错 | 把文件另存为 UTF-8；脚本已兼容 GB18030/Big5，混杂编码需先统一 |
| `Sample shorter than 3000` 警告 | 补样本；若只能是短篇，明确降低结论置信度，不做精确词汇判断 |
| `Dialogue exceeds 55%` 警告 | 补一段纯叙述章节重测，或按对话体解释句长 |
| `Low CJK ratio` 警告 | 文件含 HTML/代码/大量英文；先清洗出正文 |
| `top_nouns` 全是人名地名 | 正常：分词会把专名切成名词；解读风格词时人工剔除题材专名 |
| 相似度 1.0 | 拿同一份文本比自己，属自检通过；创作稿不应追求 1.0 |
| 改了两轮相似度仍低 | 按 `craft-guide.md` 第四章如实说明保留的偏离，不要硬凑数字 |
| 路径含空格或中文 | 所有路径加英文双引号 |

## 测量局限

- 只测表层语言特征，**测不到**情节、人物、主题、结构巧思、幽默与反讽。
- jieba 对人名、方言、自造词会切错；高频词表需人工复核。
- 短稿（<1500 汉字）的词汇与标点密度噪声大；比对结果只作方向参考。
- 跨体裁、跨时代、节选片段与全篇的指标不可直接比较。
- 相似度不是文学质量评分，也不是抄袭判定。
