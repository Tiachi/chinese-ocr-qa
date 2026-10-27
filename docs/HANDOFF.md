# 后续Agent交接：UniRec中文OCR QA

**本文件保留原实现背景。独立公开仓库的完整、最新接收文档为[AGENT_HANDOFF.md](AGENT_HANDOFF.md)，以其当前状态和迁移说明为准。**

## 用户目标与授权

仅九子库HWDB2Train、K-12、LSVT-2019、webdata_MTWI、K-12_exam、nongminribao_pdf_dpi300、hw_pdf、hw_xhs、TAL_OCR_HW。清洗→QA构建→本地Qwen3.8-27B质量审查→最终70%OE/30%MCQ。用户允许HF镜像高并发下载，不允许默认使用个人代理。允许直接SSH操作及代码GitHub备份，不能把媒体/标注/完整运行日志放Git。

## 已确认事实

- 2026-10-26直连ModelScope作者仓库仅2文件，无数据；HF固定revision和57文件哈希在research中，约253.7GB。
- 作者`tools/data/native_size_dataset.py`明确11份标签→10个LMDB/9子库及file_name前缀，按完整键读取。不能拿绝对源路径basename猜图，不能把region再盲目裁一遍。
- 原label有换行标记。只映射已知换行，未知控制标记进review；不清理LaTeX空格、转全半角或语义纠错。
- 参考DataTrove fork `85427cfd604300cae2f61bca181361148d41581f`。实际用了DataTrove typed reader/transform；不是仅在README提其名字。
- SSH已尝试，连接被拒；本轮没有远端下载或真实API调用。本地用真实LMDB/ijson/DataTrove、合成图片和模拟HTTP验证，不代表真实标签准确。

## 代码导航

|文件|职责|
|---|---|
|scripts/pipeline.py|CLI、外部配置、阶段编排、clean-checkout和锁|
|scripts/download.py|ModelScope目录核查、镜像4MiB测速、分段并发、SHA、HWDB派生合并|
|scripts/mechanical.py|流式bucket JSON、LMDB只读、原图字节导出、机械/像素去重/冲突|
|scripts/qa.py|DataTrove块、确定性近形字MCQ、短数字judge、请求缓存|
|scripts/delivery.py|清洗后配比、来源水位限额、MCQ标签旋转、README/属性/注册|
|scripts/service.py|独立视觉/文本vLLM命令、NPU空闲检查，前台运行|
|scripts/network_diagnose.py|有超时上限的直连DNS/IPv4/IPv6 TCP与TLS诊断，无媒体下载|
|config/pipeline.json / service.json|全部入口路径/API/服务参数|
|research/|小型非敏感来源/文件清单；绝无原始QA|
|tests/test_pipeline.py|合成端到端/请求恢复/图像冲突/精确配比等|

## 不可破坏的约束

1. 原始LMDB/分片/标签不可写。只在work_root合并；导出图片字节相同，不resize/crop/transcode。
2. 原label不因语句不通顺被纠错；教材题转写不能冒充解题QA。
3. 不按label文字重复删不同图片；同像素冲突双方隔离。
4. 技术错误/未知匹配不算低分或通过；不静默重试pending请求。成功请求缓存必须绑定完整输入+prompt+模型设置。
5. 配比按最终有效QA，MCQ四字母均衡；缺九来源或候选不足要失败，不能重复数据凑数。
6. 文本服务`--language-model-only`不具备本项目所需视觉验证，mode=text必须明确标代理。
7. 交付前重新全文读用户`Downloads/data_format.md`。README中文四节、原字段顶层、相对路径、禁止新增token估计字段；未验实际文件不得声称严格合规。

## 后续操作与实质边界

首先让服务器同步代码、部署、执行download-bench/download-fast（可先TAL小库），回传源选择/吞吐/下载结果。不要在本机测网速后外推服务器。执行assemble、inspect、vision pilot，核对真实图文和质量分布，再全量run/register。

当前不具备：评测图像近重复去污染、未知原页级聚类、人工金标准确率、DocVQA式自由问答生成、表格结构重建、自动修正OCR标签、全量自动视觉服务兼容性证明。默认阈值8和并发64都是待试跑校准的工程设置。

质量分数只作代理；模型仍可能漏识近形字。最好增加来源分层人工抽审，以及100%OE对照70/30的训练实验。未来加页级span QA必须验证答案出现在参考中且真实图像可定位，不能只让模型凭常识作答。

本任务属于UniMoE训练数据；与D-Spark/DeepSpec加速数据路线无关，未改动其研究索引或服务器根目录。

## 2026-10-27用户回传更新

服务器依赖安装和26项合成自测已通过；HF errno99、hf-mirror超时，尚无生产下载。新版本支持`download-fast --ipv4`及`network-diagnose`、脱敏重定向主机记录，本地29项通过，未在服务器验证新版本。详见[网络记录与命令](download_network_2026-10-27.md)。不要再要求重装依赖或删除请求缓存；不擅自开启环境里的个人代理。
