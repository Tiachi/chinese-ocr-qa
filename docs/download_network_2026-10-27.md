# 2026-10-27：自测通过后的下载网络问题

## 服务器实情

用户日志：代码`6477fab3886c9d16bff6f456ac55981631fe7610`，26项自测全部通过，缓存并发问题已解决。生产下载尚未开始。

|源|实际错误|当前能判断的范围|
|---|---|---|
|huggingface.co|URLError → OSError，errno99|Linux常见为EADDRNOTAVAIL，地址不可用；不能仅此认定是DNS或IPv6，也可能是出口/地址资源问题|
|hf-mirror.com|URLError → TimeoutError|连接过程超时；旧输出没有记录重定向，尚不知道前站还是后端存储站不可达|

环境里存在代理变量及2项Git代理设置，但下载器显式不使用它们。没有授权将个人代理作为下载回退路线；不改变这些全局设置，也不将其值打印出来。

## 本次实现

1. `download-fast --ipv4`：只为本次HTTPS下载及其重定向连接选择AF_INET，不全局替换socket/DNS、不修改系统设置。仍使用目标域名做SNI/证书验证，不关闭TLS检查。若IPv4也无出口，仍会失败，不宣称已经解决服务器网络。
2. 测速输出新增`redirect_hosts`：只记录重定向目的主机、协议、状态码，不记录完整签名URL或参数。用来区分前站可达但CDN不可达。
3. `network-diagnose`：默认仅检查两个配置源，每源一个IPv4和一个IPv6地址，进行TCP443和证书校验TLS握手；每源子进程最多20秒。只打印诊断，不下载数据正文、不启动模型、不尝试代理。

本地29项测试通过，包括IPv4作用域不影响全局解析器、TLS校验保留、重定向脱敏/禁止HTTPS降级，以及原有OCR管道回归。尚未在服务器验证IPv4下载成功。

## 服务器操作

已安装的环境和配置继续使用，不需要deploy或删除缓存。同步后可先试IPv4下载：

```bash
cd /mnt/sfs/ltj/project/chinese-ocr-qa &&
bash scripts/sync.sh &&
bash scripts/run.sh download-fast --ipv4
```

若还失败，只补这一条轻量诊断：

```bash
bash scripts/run.sh network-diagnose
```

贴回`DOWNLOAD_BENCH`和`NETWORK_DIAGNOSIS`两行即可。若IPv4也无法建立TCP/TLS，需要服务器能使用的直连出口或经用户明确确认的非个人网络通道；并发数和更换下载器本身不能修复断网。
