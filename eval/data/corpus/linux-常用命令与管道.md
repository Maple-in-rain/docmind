# Linux 常用命令与管道

## 文件与目录

- `ls -la` 列出全部文件含隐藏项与权限；`ls -lh` 人类可读大小；
- `cd`、`pwd` 切换与显示当前目录；
- `cp -r` 递归复制，`mv` 移动/重命名，`rm -rf` 递归强制删除（危险，生产慎用）；
- `chmod 755 file` 修改权限（7=rwx, 5=r-x，分别为属主/属组/其他）；`chown user:group file` 改属主；
- `find /path -name '*.log' -mtime +7` 按名称与修改时间查找文件；`grep -rn 'keyword' dir` 递归搜索内容。

## 进程管理

- `ps aux` 查看全部进程（含 CPU/内存占用）；`ps aux | grep uvicorn` 定位服务进程；
- `top` / `htop` 实时监控负载与内存；
- `kill -9 PID` 强制结束进程（-9 不给程序清理机会，先用 -15 温和终止）；
- `nohup cmd &` 后台运行且不受终端退出影响；`jobs` 查看后台任务；
- `systemctl status nginx` 查看服务状态，`journalctl -u nginx -f` 跟踪服务日志。

## 管道与重定向

Unix 哲学：程序输出纯文本，用管道组合。`|` 把左侧 stdout 接右侧 stdin；`>` 覆盖写文件，`>>` 追加写；`2>&1` 把 stderr 并入 stdout；`/dev/null` 是丢弃输出的黑洞。

经典组合：`cat access.log | grep 502 | awk '{print $1}' | sort | uniq -c | sort -rn | head`——统计触发 502 最多的客户端 IP。其中 `awk` 按空白切列取第 1 列，`uniq -c` 统计相邻重复行，`sort -rn` 数值降序。

## 磁盘与网络

- `df -h` 文件系统用量；`du -sh dir` 目录占用；
- `netstat -tlnp` 或 `ss -tlnp` 查看监听端口与进程（排查端口占用）；
- `curl -v https://example.com` 详细调试 HTTP 请求；`curl -X POST -d '...' url` 发 POST；
- `lsof -i :8000` 查看占用某端口的进程（需要 lsof 包）。

## 文本三剑客

- **grep**：`-r` 递归、`-n` 行号、`-i` 忽略大小写、`-v` 反向匹配、`-E` 扩展正则、`-A/-B/-C N` 显示上下文；
- **sed**：`sed 's/old/new/g'` 全局替换、`sed -n '10,20p'` 打印行区间、`sed -i` 原地修改文件；
- **awk**：按列处理，`awk -F: '{print $1}'` 指定分隔符、`awk '$3 > 100 {print}'` 条件过滤、自带 BEGIN/END 块做汇总。

## 排查线上问题的标准流程

1. `uptime` 看负载，`top` 找高 CPU/内存进程；
2. `df -h` 排除磁盘满（磁盘满会导致各种诡异报错）；
3. `ss -tlnp` 确认服务端口存活；
4. `tail -f` 服务日志定位报错堆栈；
5. `curl -v` 从外部视角复现请求链路。
