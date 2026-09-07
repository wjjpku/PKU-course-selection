# PKU Course Selection

北大选课本地工作台：课程查询与时间预览、独立刷课任务、最近 100 条轮询日志、SQLite 任务持久化，以及 macOS 后台服务入口。

## 本地启动

需要 Python 3.12。进入项目目录后：

```sh
python3.12 -m venv .venv-ocr
.venv-ocr/bin/pip install -r requirements-local.txt
cp skj包/config.sample.ini skj包/config.ini
.venv-ocr/bin/python skj包/main.py
```

访问 <http://127.0.0.1:7074/>，不要直接打开 HTML 文件。启动默认仅开启本地工作台，登录、读取课程及启动选课任务均由用户操作。遵守学校选课规则及开放时间；学校返回禁止访问提示时不要继续重试。

## 数据与安全

- 账号保存在本机 `skj包/config.ini`，不会提交 Git。
- 任务和最近日志保存在 `skj包/data/workbench.sqlite3`，不会上传；重启恢复任务但不自动选课。
- 登录 Cookie 不持久化。课程缓存不代表实时名额。
- 请求串行，正常轮询间隔由用户设置；网络异常保留退避等待。
- 不提供退课或自动换课操作。
- 浏览器会话、截图、数据库、运行日志和个人任务备份均排除在仓库之外。

`service_runner.py` 可作为 macOS 后台托管入口，需按本机实际路径配置 LaunchAgent。它防止闲置睡眠，不保证关机、合盖或断网时继续工作。

## 测试

```sh
cd skj包
../.venv-ocr/bin/python -m unittest discover -s test -p 'test_*.py'
node test/test_plan_helpers.cjs
node test/test_course_planner.cjs
```

## 来源与许可

本项目基于原 PKUAutoElective 系列代码扩展，保留 [原项目说明](skj包/README.md) 和 [MIT 许可证及原作者声明](skj包/LICENSE)。前端参考思路见 [来源说明](前端改进来源与边界.md)，未直接复制 PKU Art 用户脚本。
