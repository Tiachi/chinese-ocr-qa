# Chinese OCR QA Pipeline

公开仓库：**[Tiachi/chinese-ocr-qa](https://github.com/Tiachi/chinese-ocr-qa)**。

**接手Agent首先阅读：[docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md)。** 文档自包含：任务目标、代码导航、格式、配置、阶段产物、当前网络阻塞、已修问题、恢复策略和下一步。

本仓库从原项目提取为独立代码快照，不含私有仓库历史、训练数据、媒体、凭据或完整日志。来源记录见`PROVENANCE.json`，图像训练格式见[DATA_FORMAT.md](docs/DATA_FORMAT.md)。

## 独立使用

Python3.10+，Linux为目标部署环境。首次克隆前确认网络不经未经授权的个人代理；存在代理配置不代表已获准使用。服务器独立代码目录建议为`/mnt/sfs/ltj/project/chinese-ocr-qa`，尚未实际部署此独立checkout。

```bash
git clone https://github.com/Tiachi/chinese-ocr-qa.git
cd chinese-ocr-qa
bash scripts/run.sh deploy
bash scripts/run.sh configure --base-url http://IP:PORT/v1 --model qwen3.8-27b --mode vision
bash scripts/run.sh api-check
```

已有独立checkout用`bash scripts/sync.sh`更新：核对公开仓库/main、要求干净工作树、只快进；子进程禁用代理，不改变全局配置，不依赖原私有仓库的deploy key。

保留服务器既有venv、外部配置、原始数据和工作目录，迁移代码不搬数据。先解决网络出口再download/pilot/run；不要并行启动旧版和独立版操作同一工作目录。公开可见不等于完成上游数据授权或质量验收，数据与依赖许可分别适用。

## 功能与文档

基于UniRec40M的指定九个子库，构建**清洗后70%开放式转写、30%文字辨别MCQ**的图像QA训练集。参考你已有的DataTrove SFT链路，实际使用DataTrove `Document/PipelineStep`；以原OCR标注为答案，不让模型改写错别字或编造试题解答。

- [部署、镜像下载、配置、试跑、全量命令手册](docs/runbook_2026-10-26.md)
- [来源核查、优秀OCR QA形式与设计依据](docs/research_and_design_2026-10-26.md)
- [后续Agent完整交接](docs/HANDOFF.md)
- [部署自测并发问题修复与续跑命令](docs/deploy_failure_fix_2026-10-26.md)
- [服务器自测已通过：IPv4下载与网络诊断](docs/download_network_2026-10-27.md)
- [现有代理归属不明：只读检查命令与边界](docs/proxy_inspection_2026-10-27.md)
- 配置：[输入/输出/API/清洗/比例](config/pipeline.json)、[16NPU本地vLLM服务](config/service.json)
- [57个源文件的固定revision与哈希](research/source_files.json)

**已核实的下载情况：** ModelScope作者仓库`topdktu/UniRec40M`只有2个说明文件，缺少九子库数据；不能把同名卡片当作可下载镜像。HF已定位57个必需/辅助文件，合计253,686,654,321字节（约253.7GB），不下载其他子库或锁文件。用户已允许HF镜像高并发下载；不使用个人代理。

默认4文件×8分段=最多32个HTTP请求；支持断点、精确Range和上游SHA验证。`download-fast`只对配置源各读取4MiB，选择实测较快源后下载；并非已证明某站最快。默认比较官方源与hf-mirror，可自行加入可信镜像。

```bash
cd /mnt/sfs/ltj/project/chinese-ocr-qa
bash scripts/sync.sh
bash scripts/run.sh deploy
bash scripts/run.sh download-fast
```

后续先assemble/inspect/pilot，再run/register，详见手册。原始媒体仅从LMDB原字节导出，不缩放/裁剪/转码；所有中间阶段有统计及收据。模型接口只需`http://IP:PORT/v1`和served model name；默认vision审图文，text模式单独标识代理评审。

**验证状态：** 原实现本地33项测试通过；用户回传服务器依赖安装、26项合成自测通过。生产下载因TCP连接超时尚未开始；最近一次代理检查为空。独立仓库需单独验证，尚未部署到服务器。真实27B/910C吞吐与图文准确率未测；模型通过不等于人工金标，未对实际产物宣称严格`data_format.md`合规。
