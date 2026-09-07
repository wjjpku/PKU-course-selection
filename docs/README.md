# 文档导航

所有命令默认在项目根目录执行。不要直接打开 `app/web/index.html`，应启动后端并访问其本地地址。

| 你要做什么 | 入口 |
| --- | --- |
| 安装与首次启动 | [项目 README](../README.md) |
| 找课、创建任务、看日志 | [使用说明](usage.md) |
| 了解独立任务与配置边界 | [多任务说明](tasks.md) |
| 配置已有 macOS 后台服务 | [后台服务](background-service.md) |
| 查看参考项目及许可边界 | [前端来源](frontend-sources.md) |
| 开发与验证 | [贡献指南](../CONTRIBUTING.md) |
| 构建不含真实账号的展示版 | [展示版说明](../showcase/README.md) |
| 查看版本变化 | [更新记录](../CHANGELOG.md) / [v0.1.0](../releases/v0.1.0.md) |

## 文件放在哪里

- `docs/`：当前工作台的使用和设计说明，采用英文小写连字符文件名。
- `scripts/`：从项目根目录运行的开发辅助脚本。不要把产物写入源码目录。
- `showcase/`：公开展示适配和虚构数据；`showcase/tests/` 只测试模拟器。
- `app/autoelective/`、`app/web/`：实际应用源码；`app/test/` 保留现有测试入口和相对导入。
- `output/`：截图、导出验证文件、发布包及展示构建产物，由 Git 忽略。
- `releases/`：历史版本发布说明，保留原路径；最新本地改动写在 `CHANGELOG.md` 的未发布部分。

## 为何保留部分旧目录

应用目录已统一为 `app/`，模块内部相对导入和资源结构不变。`service_runner.py` 和 macOS 启动脚本仍位于根目录，但内部入口已更新。升级旧工作区请看 [路径迁移](path-migration.md)。原项目 README、LICENSE、Docker 与历史文档随应用目录整体迁移；当前用法以根目录 README 和本目录为准。

`config.ini`、`data/`、日志、虚拟环境、机器专用 plist、会话文件和个人备份均不属于可公开源码。应用目录内的私人文件随目录整体迁移，内容不变；其余私人文件保持原位，均不上传。忽略规则不是秘密扫描，提交前仍需核对实际文件内容。
