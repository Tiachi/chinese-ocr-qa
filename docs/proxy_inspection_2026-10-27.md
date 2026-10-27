# 2026-10-27：直连不通后的只读代理检查

## 已知事实与未知

服务器HF和hf-mirror的IPv4 TCP连接均超时，尚未到TLS/HTTP/CDN阶段；IPv6 errno99。镜像IPv4为160.16.86.14，与本次通过阿里公共HTTPS DNS取得的结果一致，不能将镜像失败简单归为DNS错误。HF解析结果可疑，但没有获得足够独立解析证据，不据此自动修改系统DNS或固定写死下载IP。

公开参考：[阿里HTTPDNS说明](https://www.alibabacloud.com/help/en/dns/httpdns-ali-public-dns-function-problem-summary)、[Cloudflare DNS JSON说明](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/)、[HF官方网络出口说明](https://huggingface.co/docs/hub/models-downloading)。官方提醒下载可能涉及额外存储域名；但本次服务器连前站TCP都未成功，不能误称只缺CDN白名单。

用户不清楚现有代理变量是机构出口还是个人Clash，已要求只读检查。当前授权不等于允许通过未知代理下载253.7GB数据。**本次没有启用代理，也不改变下载路由。**

## 实现与最短命令

```bash
cd /mnt/sfs/ltj/project/chinese-ocr-qa &&
bash scripts/sync.sh &&
bash scripts/run.sh proxy-inspect
```

它不需要读取数据集配置，也不创建工作目录/锁/报告；仅将脱敏结果打印成`PROXY_INSPECTION`一行。

读取范围：

- 当前进程HTTP_PROXY/HTTPS_PROXY/ALL_PROXY及Git代理配置，在内存解析，只保留协议、主机、端口、是否含凭据。
- 如果是loopback地址，仅用`ss`查看**该精确端口**的TCP监听进程；最多读取8个PID的`/proc/<pid>/comm`进程名。
- 不读取cmdline、environ、密钥、完整代理URL、账号密码、URL路径或查询参数；不扫描完整进程树。
- 不发DNS或代理连接，不发CONNECT或任何外网请求，不改变环境、Git、系统DNS或下载配置。

## 怎么解释

|结果|允许下的结论|
|---|---|
|loopback+sshd/ssh|说明很可能是SSH转发监听，**无法仅此判定转发最终来自个人Clash还是机构出口**|
|clash/mihomo等进程|说明有相关软件监听，不代表已经确认归属、计费或获准使用|
|private地址|可能是内网代理，仍不能凭IP确定属于公用出口|
|public或hostname|只反映配置地址类型，不试连、不自动使用|
|无本地监听|本机loopback代理配置可能已失效，不自动拉起任何转发|

拿到结果后再核对归属；只有确认属于已授权可用的网络通道，才设计显式、作用域内的下载接入。若是个人代理，继续保持默认禁用；可改用具备可用直连出口、且能访问同一SFS的机器运行已有下载脚本。

本地新增4项脱敏/只读边界测试；尚未替用户在服务器执行检查，不将代码实现冒充服务器结果。
