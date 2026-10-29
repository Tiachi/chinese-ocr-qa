# V5 全量九库清洗与构建状态（2026-10-29）

本文是 `docs/AGENT_HANDOFF.md` 的当前进展补充；两者冲突时以本文和当前代码/回执为准。

## 当前结论

- v4 已完成：4 来源 200K draft-only QA，路径 `/mnt/sfs/ltj/data/UniRec40M_QA_200K_v4_20261029_110039`，100 条抽检 100/100，全量扫描 0 失败。
- v5 全量清洗已完成：剩余五源机械清洗 + 九源图片 blur 审核均已结束；候选 1,118,514，blur 后可用 1,028,052。
- D 方案数据集已构建：`/mnt/sfs/ltj/data/UniRec40M_QA_FULL_D_20261029_160700`，1,028,052 QA（807,524 OE / 220,528 MCQ，约 78.55/21.45），162 个模板。
- 8018 已由本项目 Qwen3.8-27B 服务接管（媒体清洗 vLLM 已退出）；1,000 条视觉 pilot 通过 api-check，745 accepted / 248 review，吞吐约 22.9 条/秒；全量质量审查已启动，预计约 12.5 小时。
- 代码在分支 `feature/v4-clean-prompts`；v4 代码提交 `11bbdd328c9fe752ea86a493ab751abbb598a543`，基于 `e85399ed`（main）。38/38 合成测试通过。

## v5 数据规模与容量

| 项 | 数值 |
|---|---:|
| 九库标签行数 | 1,429,104 |
| 预门槛 MCQ 容量（label 级） | 296,670 |
| 理论最大精确 70/30 | 988,880 |
| 已处理候选（HWDB/K-12/LSVT/TAL） | 776,980 |
| 未处理五源标签行 | 483,073 |

预门槛只是上限；实际受 no_han、图片解码、blur review 和模型审查影响。目标规模必须在完整 mechanical 后按最终候选重新计算，不能预先承诺 98 万。

### 实测清洗结果

| 指标 | 数值 |
|---|---:|
| 九源候选 | 1,118,514 |
| blur 检查 | 1,118,514（100%） |
| blur review（阈值10） | 89,641 |
| probe 失败 | 821 |
| blur 后可用的候选 | 1,028,052 |
| 可用候选中的 MCQ 容量 | 220,528 |
| 文本 datatrove review | 0 |
| 理论最大精确 70/30 | 735,080 |
| 500K 目标是否可行 | 是（需 150K MCQ） |

按来源（候选 / blur 后可用 / MCQ 容量）：HWDB 375,741 / 286,206 / 55,968；K-12 179,779 / 179,778 / 40,185；LSVT 211,050 / 210,305 / 16,535；MTWI 83,066 / 82,902 / 3,800；K-12_exam 42,301 / 42,301 / 27,823；nongminribao 97,849 / 97,849 / 49,656；hw_pdf 65,146 / 65,146 / 16,252；hw_xhs 53,172 / 53,156 / 9,786；TAL 10,410 / 10,409 / 523。

## v5 阶段

1. `01a` 剩余五源机械清洗：K-12_exam、webdata_MTWI、nongminribao_pdf_dpi300、hw_pdf、hw_xhs。
2. `01b` 九源图片 blur 审核（并行 FFmpeg，24 workers）。
3. `02` 多样 OE/MCQ 草稿；`03` Qwen 视觉审查；`04` 70/30 交付；`05` 验收。

## 清洗规则

### 文本（datatrove SFT 规则）

- token 化：汉字 / 字母数字串 / 非空白单字符
- 8-gram；≥128 tokens；重复比 `1-unique/total ≥0.6` → `possible_repetition`（review）
- 保留原有 OCR 检查：空标签、非字符串、无汉字、marker/控制符、超长标签、短循环 review
- 不改写原文；不同图片的相同 label 不按文本去重

### 图片（image-video-cleaner）

- FFmpeg 使用 `/mnt/sfs/ltj/runtime/ffmpeg-blur/linuxarm64/bin/ffmpeg`
- `blurdetect` 参数：`low=0.078431372549:high=0.196078431373:radius=50:block_pct=100:planes=1`
- 自适应 block：min side ≥64→32，≥32→16，≥16→8，否则 4
- 阈值 **10**；`mean_blur > 10` → review
- probe 失败/NaN → review，不当成清晰
- 同像素同 label → duplicate；同像素冲突 label → review；不同字迹同 label 保留

v4 实测：HWDB blur>10 30,323/93,526 检查；K-12 0；LSVT 25 blur>10 + 166 probe 失败；TAL 1 probe 失败。阈值 10 适合 review，不是统一 reject；LSVT 极小图仍可能通过，后续建议加最小边过滤。

## 多样提问

- 代码 `scripts/qa.py`，v4 使用 98 个模板。
- 覆盖 general/handwriting/printed/scene/document/exam/formula。
- 只改变问题措辞，不改变答案、选项、正确字母；attributes 记录 `question_template`。
- 全量会启用 document/exam/formula 模板。

## 运行监控

- 编排器：`/mnt/sfs/ltj/ocr_qa/v5_orchestrator.py`
- 监控目录：`/mnt/sfs/ltj/data/monitor_v5/`
- 容器内端口：`8766`
- 页面：`http://127.0.0.1:8766/`（本机 SSH 转发后）
- 进度 JSON：`progress.json`，每 5 秒由页面刷新
- 编排器只写监控和清洗结果，不会触发模型请求

## D 数据集与质量审查

- 用户选择 D：使用全部 blur 后可用候选和全部 MCQ 候选，**不是 70/30**。
- 输出：`/mnt/sfs/ltj/data/UniRec40M_QA_FULL_D_20261029_160700`
  - 1,028,052 QA；807,524 OE / 220,528 MCQ
  - A/B/C/D 各 55,132；162 个模板
- 全量扫描：唯一 ID/图片 1,028,052；除 **6,819 条 MCQ 选项块解析歧义**（标签内含以 `A./B.` 开头的行，约 3.1% MCQ）外，结构/OE/MCQ 检查通过；质量审查将这些行标为 review。
- 质量 pilot：993 条可解析样本，745 accepted / 248 review，0 技术错误，22.9 条/秒；7 条 MCQ 解析歧义未进入 pilot。
- 全量质量审查已启动（`quality_D_full.py`），预计约 12.5 小时；输出 accepted/review 旁路文件，不直接改写原 D JSONL。
- 未完成审查/人工抽审前，D 仍是 `DRAFT_ONLY_NOT_MODEL_REVIEWED`。

## 交付边界

- 精确 70/30、A/B/C/D 均衡、九来源最小覆盖、每图最多一条。
- 目标数必须是 40 的倍数；容量不足要明确失败，不复制数据。
- 未完成模型审查、人工抽审和全量验收前，不得注册为正式训练数据。

## 安全与发布

- 仓库只提交代码、测试、示例配置、文档和小型非敏感清单。
- 不提交原始 QA、图片、LMDB、SQLite、模型、完整日志、缓存、密钥或签名 URL。
- 服务器配置、监控数据、运行日志留在代码目录外。
- 公开仓库同步前必须做 secret 扫描；任何 API key/token/password 只从环境变量读取。
