# Chinese OCR QA Pipeline：其他Agent完整接收文档

维护日期：2026-10-27。仓库：**[Tiachi/chinese-ocr-qa](https://github.com/Tiachi/chinese-ocr-qa)**，公开，稳定分支main。本文是独立项目的首要接收入口，不能用旧聊天摘要替代当前代码、配置和服务器回执。

## 1. 用一句话理解目标

将UniRec40M指定九个中文候选子库，经过媒体/标注机械清洗、去重、QA构造和本地Qwen3.8-27B审查，输出**70%开放式OCR QA、30%OCR选择题**的训练数据，附属性、统计、README和可恢复收据。

这不是将试卷OCR标注转成解题答案，也不是无依据生成DocVQA、表格结构或知识问答。可靠监督是图中实际文字；原文即使有错别字、口语、重复或不通顺，也不能擅自纠正。

## 2. 接手时的真实状态

|事项|截至本次交接的状态|证据/限制|
|---|---|---|
|来源文件定位|已完成|HF固定revision、57文件及上游hash在research/source_files.json|
|ModelScope可用性|作者同名库检查不可下载九子库|当时只有2个说明文件；不等于证明整个ModelScope没有其他镜像，后续可重新probe|
|原项目本地验证|33项通过|真实DataTrove/LMDB/Pillow、合成图片与模拟HTTP，不是生产模型准确率|
|原项目服务器部署|用户回传依赖安装、26项合成自测通过|不是独立公开checkout已经部署；后来的只读代理检查也已执行|
|生产数据下载|**没有成功开始**|HF、hf-mirror直连TCP超时；IPv4也未成功，无下载完成证据|
|当前代理|最近一次只读输出为空|旧日志有代理变量，不能假设当前终端仍有；也不能据此推断其他终端都没有|
|真实27B模型请求|未验证|没有OCR生产pilot或吞吐/准确率结果|
|最终数据集|**未生成**|没有实际QA量、70/30成品、人工错误率或严格媒体验收结果|
|独立仓库|代码提取与便携性适配|新仓库没有私有单仓库历史；发布后仍需服务器独立部署验证|

不要把“代码有download/run命令”“格式输出合法”“单元测试通过”写成数据已下载/已清洗/已验真。向用户汇报时应分别列出实现、本地测试、用户回传服务器验证和生产验证。

## 3. 仓库来源与公开边界

原实现位于维护者的Dataset项目，提取基线`e15bdf278df2bf89a33b8e2e049811389362a6d7`。仅复制该子项目的已提交代码、例配置、小型非敏感清单和文档；**不复制原仓库.git或任何其他项目历史**。具体文件来源在PROVENANCE.json。

独立仓库修正了原common.code_sha使用父级单仓库目录的假设，运行手册改为顶层scripts/，新增公开仓库的干净快进更新入口。不要再调用旧私有仓库的同步helper、deploy key或兄弟项目代码。DataTrove以正常依赖安装，不需要访问私有Dataset。

AGENTS.md约束、docs/DATA_FORMAT.md协议快照适用于维护。若维护者提供更新的权威data_format.md，必须全文读后再改数据格式；公开快照不能覆盖新要求。

## 4. 九子库、体量、键映射

上游为[topdu/UniRec40M](https://huggingface.co/datasets/topdu/UniRec40M)，固定revision `b8fe2f83c49102edd51b7438616799e399b4ae1a`。57个允许文件合计**253,686,654,321 bytes**，约253.7GB十进制。运行锁文件不下载。不要把作者全库约40M当成这九个子库可用样本数。

|子库|label文件（相对子库）|LMDB目录|file_name前缀|
|---|---|---|---|
|HWDB2Train|label_key.json、label_key_region.json|image_lmdb|hwdb_|
|K-12|label_key_qwen.json|image_lmdb_qwen|k12_|
|LSVT-2019|label_key.json|image_lmdb|lsvt_|
|webdata_MTWI|label_key.json|image_lmdb|mtwi_|
|K-12_exam|label_key_qwen.json|image_lmdb_qwen|exam_|
|nongminribao_pdf_dpi300|label_keys.json|image_lmdb|nongminribao_pdf_|
|hw_pdf|label_key_qwen_tex_norm.json|image_lmdb_qwen_tex_norm|page_hwpdf|
|hw_pdf|label_key_qwen_crop_tex_norm.json|image_lmdb_qwen_crop_tex_norm|crop_hwpdf|
|hw_xhs|label_key_qwen_tex_norm.json|image_lmdb_qwen_tex_norm|xhs_hw_|
|TAL_OCR_HW|label_key.json|image_lmdb|tal_|

依据作者[tools/data/native_size_dataset.py](https://github.com/Topdu/OpenOCR/blob/main/tools/data/native_size_dataset.py)，使用完整file_name精确txn.get，不能拿basename猜路径。尺寸桶键不是逐图实测尺寸。label非字符串或未知布局进入review，不把列表强转字符串。

HWDB的data.mdb是分片；assemble只在work_root创建派生合并库，不改原分片。额外合并空间约192GB，后续导出原图又会占空间；253.7GB并非全流程空间预算。字节相同图片与解码后相同像素是两个不同hash，均保留用途。

## 5. 配置与路径

|位置|默认值/说明|
|---|---|
|独立代码目录|`/mnt/sfs/ltj/project/chinese-ocr-qa`，拟部署|
|旧代码位置|维护者原项目仍保留；迁移不删除旧checkout，也不要同时操作同一work_root|
|CPU/HTTP venv|`/mnt/sfs/ltj/runtime/ocr-qa`|
|服务器用户配置|`/mnt/sfs/ltj/ocr_qa/config/unirec9.json`|
|原始九库|`/mnt/sfs/unimoe_dataset/omni/UniRec40M`|
|检查点/中间产物|`/mnt/sfs/ltj/ocr_qa/unirec9-v1`|
|训练媒体基准|`/mnt/sfs/unimoe_dataset/training`|
|图片导出|`training_root/images/UniRec_Chinese_OCR_QA/`|
|训练JSONL|`/mnt/sfs/unimoe_dataset/omni/json/UniRec_Chinese_OCR_QA.jsonl`|
|数据集README|`/mnt/sfs/unimoe_dataset/omni/readmes/UniRec_Chinese_OCR_QA.md`|

全部是可配置的部署示例，不含凭据；不表示这些新产物已经存在。现有服务器配置不因deploy被覆盖。不要为了迁移代码移动、复制或删除原始媒体/工作目录。

config/pipeline.json控制source清单、根目录、清洗、judge、mix。config/service.json控制已有模型路径、原生解释器、vLLM目录与并行参数。配置文件不写API key；可选key从OCR_QA_API_KEY环境变量读取。

## 6. 各阶段机制、产物和边界

### 00_download：限定文件、直接网络与续传

probe仅查作者ModelScope。download-fast对配置的每个源取4MiB，要求精确Range，选实测较快者下载；默认比较HF和hf-mirror。默认4文件×8分段=最多32个HTTP请求、每段64MiB，总HTTP并发上限128。

文件完成后比对LFS SHA256或普通Git对象SHA1；不是只看大小。已存在原文件不覆盖，先验证；完成范围缓存可复用。未完成尝试仅处理自己的精确缓存，不递归清理共享存储。断点或SHA失败时保留证据，不以跳过校验提速。

`--ipv4`只影响该次下载连接，不全局修改socket/DNS，TLS/SNI校验仍保留。network-diagnose只作有上限的DNS/TCP/TLS检查；proxy-inspect不发任何代理请求、不读cmdline/environ/密钥、不打印账号密码。

### 01_mechanical：标注与媒体一致性基础

ijson流式遍历尺寸桶，LMDB readonly/create=False/lock=False读取。Pillow解码、尺寸/像素预算检查，原图字节无重新编码导出。空/纯空白转写分流；中文目标默认要求至少一个汉字，不代表非中文标签本身错误。

只映射已知换行标记为换行，未知控制标记进review；保留原label、标点、全半角和LaTeX。重复循环只是review信号，不把正常重复文字直接改掉。像素相同+label相同去重；像素相同+label冲突双方隔离；不同字迹的相同label保留。

**模糊阈值默认null，尚未校准启用。** 可选边缘方差只作review代理，不能说默认已经筛完模糊图片。没有MinHash、感知近重复或未知原页级去重。holdout默认未配置，不声称完整评测去污染。

输出all/candidate/review/rejected/duplicate、SQLite索引及来源/原因计数。receipt绑定输入路径/大小/mtime、规则、代码SHA；阶段快速复用检查大小，不等于每次重hash全部输入。未提交机械阶段会重跑，不是逐图片完美恢复。

### 02_qa_drafts：原标注约束，不自由造答案

使用真实DataTrove Document/PipelineStep。OE问题要求按阅读顺序转写，答案来自规范换行后的原标注。MCQ由完整正确转写及三个不同的单字符近形/数字变化构造；不生成无关常识答案。

长于256字符或不足三个干扰项的图作OE候选。候选题型初分不保证最终70/30，最终在过滤后再配。当前只实现转写和转写辨别，不具备页级自由问答、表格结构重建或考试解题生成。

### 03_quality：本地Qwen API与缓存

仅需`http://IP:PORT/v1`和实际served model name。默认vision包含图片；text只作文字一致性快筛，summary明确标代理范围。`api-check`只GET/models，不证明视觉支持。

prompt在scripts/qa.py::PROMPT。模型仅输出三个数字：质量1~10、匹配0/1/2、唯一性0/1/2。程序解析，不要求模型写长JSON/解释。默认质量≥8且匹配=1、唯一=1才accepted；阈值8是待校准工程选择，未知项review。

成功请求绑定完整payload、prompt、端点/模型/模式/可选revision，复用缓存。相同进程内相同请求合并调用，等待者复用首个结果；历史孤儿pending仍阻止自动重发，不通过删除pending绕过。--retry-errors只处理明确结果错误，不等于允许重发所有未知请求。

技术错误不是低质量0分。模型分数/图文判定仍可能错，必须抽审，不可称人工金标。

### 04_delivery：后置配比与无覆盖注册

接受候选按来源容量水位分配，保证九来源最小覆盖；不是固定原始比例，也不强迫低容量来源重复。最终精确70%OE、30%MCQ，MCQ正确字母A/B/C/D各25%，每张图最多选一条。可行总数须为40的倍数；target_qa缺省按容量算最大可行值，短缺/缺源明确失败。

输出训练JSONL、attributes、中文四节README、stats.md、summary.json、receipt。QA字段只用human/gpt、相对images、modal_mask1，保留原字段顶层，不添加token估计字段。register使用同文件系统无覆盖硬链接，拒绝覆盖已有不同版本；不会自动复制大数据。

## 7. 模型服务与16张910C

优先复用用户已经启动且确认具备视觉能力的API，不安装/下载新权重。例配置原生Python `/usr/local/python3.12.13/bin/python3`，vLLM `/vllm-workspace/vllm`，权重 `/mnt/sfs/ltj/modelscope/Qwen3.8-27B`，served name默认qwen3.8-27b。

service前台启动TP2/DP8，前缀缓存、align、chunked prefill、async、decode graph；vision允许1张图片，禁止误加language-model-only。逐卡使用torch_npu.npu.mem_get_info，不使用之前出错的通用accelerator allocator。显式设置VLLM_PATH避免KeyError。端口或显存被占就停止，不kill其他服务。

这套启动方法参考历史运行记录，但当前OCR视觉服务未在真实910C验证。模型标签不代替实际config.json架构检查；不同vLLM/Ascend版本可能需要调整。不要把历史纯文本测速外推到OCR图文吞吐。先小pilot，再测并发64/128/256，不直接承诺全量耗时。

## 8. 最短接手操作

先读AGENTS.md、本文、DATA_FORMAT.md，检查当前Git branch/status/origin，再看服务器既有配置和阶段回执。完整命令在运行手册，独立checkout的常用入口如下：

```bash
bash scripts/run.sh self-test
bash scripts/run.sh proxy-inspect
bash scripts/run.sh network-diagnose
```

网络出口恢复前不反复测速/全量下载，也不请求生产模型。若有另一台已确认能直连且挂载相同SFS的机器，可用同一原始目录下载，不将253.7GB经本机转存或个人代理搬运。

网络可用后：

```bash
bash scripts/run.sh download-fast --ipv4 --subset TAL_OCR_HW
bash scripts/run.sh inspect --subset TAL_OCR_HW
bash scripts/run.sh configure --base-url http://IP:PORT/v1 --model qwen3.8-27b --mode vision --concurrency 64
bash scripts/run.sh api-check
bash scripts/run.sh pilot --subset TAL_OCR_HW --limit 100
```

全九库下载后先assemble、inspect，再pilot --limit100；这是每份label的前缀，最多1100条，不是随机质量样本。正式放量前必须随机分层人工图文核查。不要用TAL一个小库的质量外推所有来源。

全量run完成只产生delivery，需检查summary/README再显式register。不要把临时TAL pilot误注册成全九来源正式数据。

## 9. 已知问题、解决情况、接下来优先级

|问题|状态|接手Agent应做|
|---|---|---|
|相同文本请求并发误判pending|已修，明确16线程回归测试|保留按键合并调用及真孤儿保护，不能删保护求PASS|
|服务器下载连接超时|未解决|确认可用直连出口；若需代理先确认归属/授权，不默认用个人Clash|
|proxy-inspect最近无配置|用户回传|不要继续假设存在可用公用代理；不同终端/环境结果可不同|
|HF解析可疑|仅疑点|没有已验证DoH修复；不修改系统DNS、不写死可疑IP、不关TLS|
|独立仓库部署|尚未在服务器完成|新建独立代码目录，保留现有配置、venv及数据，不覆盖原checkout|
|低清筛选|默认未启用阈值|抽图校准后再定，不拿图像尺寸或任意边缘阈值自证清晰|
|自由文档QA/答案span/表格|未实现|先验证原页上下文和答案位置，不凭常识自由扩写|
|质量阈值与70/30训练收益|未证明|独立抽审，必要时对照100%OE，记录CER/漏字/近形字，不给无证据收益结论|

当前最优先事项是**服务器网络出口**，不是重装环境、重启NPU或把并发调高。下载实际成功后，才进入映射/质量/训练收益验证。

## 10. 开发与发布检查单

本地合成测试命令：`python -B -m unittest discover -s tests -v`，需先安装requirements；本地测试不应访问生产API。测试包含真实LMDB/Pillow/DataTrove、模拟HTTP、冲突去重、配比、缓存、TLS/IPv4与代理脱敏。

每次改动检查：精确staging、diff --check、测试、公开内容审计、远端SHA；main只快进，不自动stash/reset/clean，不force-push。禁止将原始QA/媒体/LMDB/SQLite/模型/密钥/完整日志/签名URL放仓库。例配置允许修改，但不能覆盖服务器用户配置。

改下载要保持源hash、Range上限、禁止代理默认回退；改并发要保持不重发未知请求；改构造要保持GT不改写；改导出要重读协议、核对实际产物。任何新规则都应写清实现/本地测试/服务器验证状态。

## 11. 本项目明确不涉及的工作

不是音频数据清洗、不是已有图片3M/6M配比池、不是视频帧缓存项目、不是DeepSpec/D-Spark推理加速数据。不得因旧项目名称相似就复用其字段/路径、停止其服务或改其研究索引。
