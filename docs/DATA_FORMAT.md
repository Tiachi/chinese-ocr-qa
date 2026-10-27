# 图像QA交付协议快照

维护日期：2026-10-27。本文记录本项目涉及的图像部分协议，供公开项目独立理解；维护者若持有更新的权威`data_format.md`，应全文重读并以其为准，不能用本文覆盖用户新要求。

## 一、交付结构

JSONL + 可直接读取的原始图片文件。最终训练不依赖LMDB、Parquet或TAR；LMDB只用作上游只读输入。图像字节从LMDB导出，不缩放、裁剪或重新编码。

```json
{
  "id": "UniRec_Chinese_OCR_QA_unique_id",
  "conversations": [
    {"from": "human", "value": "<image>\n请准确转写图片中的文字。"},
    {"from": "gpt", "value": "原图对应的文字"}
  ],
  "images": ["images/UniRec_Chinese_OCR_QA/ab/example.png"],
  "videos": [],
  "audios": [],
  "modal_mask": 1,
  "file_name": "原始LMDB键",
  "label": "未经改写的原始转写",
  "source_dataset": "topdu/UniRec40M",
  "source_subset": "TAL_OCR_HW"
}
```

conversations只使用human/gpt；占位符数量必须等于图片引用数。media路径为相对于`training_root`的列表，不使用服务器绝对路径。图片样本不添加无意义的音视频时长。保留每个原始字段在顶层，冲突字段有明确original_别名，保留来源标注和行索引。

禁止新增`estimated_tokens`、`token_length`、`text_tokens`、`audio_tokens`、`video_tokens`、`answer_tokens`及对应估计字段。新题型、质量/审查模式等放旁路attributes.jsonl，不混入原始label。

## 二、默认路径

|用途|默认示例|
|---|---|
|原始输入|`/mnt/sfs/unimoe_dataset/omni/UniRec40M/`|
|媒体路径基准|`/mnt/sfs/unimoe_dataset/training/`|
|图片|`training_root/images/UniRec_Chinese_OCR_QA/...`|
|训练JSONL|`/mnt/sfs/unimoe_dataset/omni/json/UniRec_Chinese_OCR_QA.jsonl`|
|数据集README|`/mnt/sfs/unimoe_dataset/omni/readmes/UniRec_Chinese_OCR_QA.md`|

实际根目录允许配置，但相对路径与训练器的基准必须一致。不要为了迁移代码而复制、移动或覆盖已有原始数据。

## 三、数据集README要求

生成的数据集README必须包含标题、完成日期/维护者、四个中文章节与表格：

1. 数据集介绍：样本/QA/图片引用/独立图片、modal_mask、来源、题型。
2. 原始字段说明：每个保留字段的类型、含义、示例及来源索引。
3. 处理说明：导图、清洗、标记映射、去重、QA构造与质量审查范围、排除项。
4. 路径对应：JSONL、README、属性、统计、原始输入、媒体相对路径基准与解析示例。

## 四、验收边界

代码自测不是实际数据验收。只有实际发布的JSONL、图片解码、图文对应、README及验证记录均核对后，才可声明完整合规。当前尚无生产数据交付，也没有人工金标准确率；不能把模型输出格式合法或自定义schema通过当成完整质量保证。
