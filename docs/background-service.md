# 工作台后台服务

返回 [文档导航](README.md)。本文中的程序、配置和日志路径均相对项目根目录，不是 `docs/`。

本说明适用于**已经自行配置好 LaunchAgent 的 macOS 安装**。下载仓库不会自动安装后台服务，也不会修改系统设置；新用户可以先按 README 在前台启动。配置 LaunchAgent 时，程序入口使用本机实际项目路径下的 `service_runner.py`，Python 使用本机虚拟环境；机器专用 plist 不随源码分发。

以下假设服务标识设为 `local.pku.workbench`，且已配置 `RunAtLoad`、`KeepAlive` 和 `ThrottleInterval=15`。登录 macOS 后自动启动，退出 Codex、关闭网页或锁屏不停止服务；进程退出后由 launchd 重新启动，重启尝试间隔至少 15 秒。

入口：http://127.0.0.1:7074/ 。仅本机可访问。不自动开始选课，不执行退课。

服务运行期间使用 caffeinate 防止闲置睡眠，不妨碍锁屏和屏幕关闭。建议接电并保持电脑开盖；电池消耗会增加。合盖、手动睡眠、注销、关机、断网不能保证继续运行。重启电脑后需登录用户账号。

任务配置、历史状态、最近100条轮询日志和课程缓存已保存至 `app/data/workbench.sqlite3`。账号密码仍使用原本的本机配置文件；Cookie不存入数据库。恢复的课表标记为历史缓存。

重启会恢复任务，但保持停止状态，需手动启动，不自动提交选课。进程卡死而不退出不会触发自动重启。正常轮询不再有固定4秒下限，按用户设置的正数间隔运行，保留请求串行和网络错误退避。

后台控制台日志位于 `service-logs/backend.log`，单文件约 2 MB，最多保留 3 个旧文件，避免无限占用空间。

停止后台服务（停止轮询，不退课）：

```sh
launchctl bootout gui/$(id -u)/local.pku.workbench
```

再次启动：

```sh
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/local.pku.workbench.plist"
```

永久关闭开机启动：先停止服务，再移走上述 LaunchAgents 中的 plist。工作台代码和课程配置不受影响。
