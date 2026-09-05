# Docker 容器与镜像

## 容器 vs 虚拟机

虚拟机在硬件之上虚拟出完整操作系统（Guest OS），每个 VM 独立内核，启动秒级到分钟级，占用 GB 级内存；容器共享宿主机内核，只隔离进程、文件系统、网络等用户空间，启动毫秒级，内存占用小。隔离性上虚拟机更强（内核级隔离），容器共享内核存在逃逸风险——生产环境常用云厂商的"安全容器"（如 Kata Containers）折中。

## 镜像与分层

Dockerfile 的每条指令（RUN/COPY/ADD）生成一个只读镜像层，多个层叠加成最终镜像。分层带来两个特性：

1. **复用缓存**：层内容不变则跨镜像复用，多个镜像共享基础层（如 python:3.12-slim），节省磁盘与传输；
2. **构建缓存**：Dockerfile 指令不变则构建时直接使用缓存层，只有变化指令及其之后的层重新构建。

因此 Dockerfile 写法讲究：先拷贝依赖清单（`COPY requirements.txt` + `RUN pip install`）再拷贝源代码——源代码改动不会让依赖层缓存失效。

## Dockerfile 最佳实践

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- 基础镜像选 slim/alpine 减小体积（alpine 用 musl libc，某些二进制 wheel 不兼容）；
- `--no-cache-dir` 避免 pip 缓存进镜像；
- 用 `CMD` 的 exec 形式（JSON 数组）正确接收信号；
- 多阶段构建：编译阶段用完整镜像，运行阶段只拷贝产物，最终镜像可以小一个数量级。

## 常用命令

- `docker build -t name:tag .` 构建镜像（注意最后有个点，表示构建上下文）；
- `docker run -d -p 8080:80 --name web name:tag` 后台运行并映射端口；
- `docker exec -it web bash` 进入运行中的容器；
- `docker logs -f web` 跟踪日志；
- `docker ps` 列运行中容器，`docker images` 列本地镜像；
- `docker system prune` 清理无用的镜像、容器、网络（注意会删掉未运行的容器）。

## 卷与网络

容器文件系统是临时的——容器删除后写入的数据消失。`docker run -v /host/path:/container/path` 挂载卷持久化数据；命名卷 `-v myvol:/data` 由 Docker 管理，更推荐。默认 bridge 网络下容器间可通过容器名互访；`--network host` 直接共享宿主机网络（Linux 下性能最好但隔离弱）。

## 编排

单机 `docker compose` 用 YAML 定义多容器应用（app + db + redis），`docker compose up -d` 一键启动。集群场景用 Kubernetes：Pod 是最小调度单元（一个 Pod 内可含多个共享网络的容器）、Deployment 管理副本与滚动更新、Service 提供负载均衡入口。面试区分点：Docker 解决"环境一致"，K8s 解决"规模与自愈"。
