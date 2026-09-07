# PKUAutoElective Docker Image

当前镜像使用 Python 3.10，并从 `requirements.txt` 安装与源码一致的依赖。

## Tags

1. latest
2. monitor

## latest

包含python3，依赖库，以及项目源代码。

### 运行方法

``` bash
docker run -d \
           --name=pae \
           -v /path/to/config/folder:/config \
           yousiki/pkuautoelective:latest   # 运行工具
docker logs pae # 查看输出
docker stop pae # 停止工具
```

## monitor

额外包含Monitor运行依赖的库。

### 运行方法

为了避免暴露学号和会话状态，工作台只允许绑定本机回环地址。如需准备期页面，建议直接在本机运行 `python3 main.py`，不要将监控端口公开发布。

``` bash
docker run -d \
           --name=pae \
           -p 7074:7074 \
           -v /path/to/config/folder:/config \
           yousiki/pkuautoelective:latest   # 运行工具
docker logs pae # 查看输出
docker stop pae # 停止工具
```
