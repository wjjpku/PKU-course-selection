# 参与开发

## 跑起来

按 README 安装 Python 依赖；前端为原生 JavaScript、HTML、CSS，无需打包。开发检查另需 Node.js。运行 `.venv-ocr/bin/python scripts/check.py`，使用临时示例配置完成离线回归，无需学校账号。

## 代码入口

目录分工见 [文档导航](docs/README.md)。应用测试继续放在 `app/test/`；展示测试放在 `showcase/tests/`；构建与检查脚本放在 `scripts/`；生成物放在被忽略的 `output/`。不要为了目录命名而移动运行中的数据或服务入口。

- `app/web/course-query.js`：纯本地筛选、字段选项、CSV 导出；可直接用 Node.js 测试。
- `app/web/course-planner.js`：纯时间对照与冲突说明，不发选课请求。
- `app/web/workbench-insights.js`：数据可信度与任务状态说明。
- `app/web/app.js`、`planner.css`：查询卡片、课程篮及任务操作。
- `app/autoelective/course_library.py`：从当前账号导出的 CSV 读取课程库，不访问学校。
- `app/autoelective/course_export.py`：受限的只读课程查询、分页与原始 CSV。
- `app/autoelective/control.py`、`tasks.py`：账号会话及独立任务。修改这里需要特别检查运行安全边界。

## 提交前检查

除完整离线回归外，涉及展示版时执行 `node showcase/tests/demo.cjs` 和 `node scripts/build-showcase.cjs`；仅部署生成的展示目录，不上传整个项目。

- 用虚构课程和模拟响应覆盖缺字段、无时间、跨入口重复、部分导出等情况；不以真实选退课作为测试。
- 不把学号、密码、Cookie、数据库、个人课程 CSV 或浏览器截图加入提交。`.gitignore` 不是历史泄密检查，提交前仍应检查暂存内容。
- 新字段保留来源；查询入口类型不替代学校课程类别，未知不能默认为无冲突或有资格选课。
- 浏览器展示外部课程文本必须转义；CSV 单元格防止公式注入。
- 改动限于查询界面时，不改变登录、选课、退课或自动启动语义。
- 参考外部项目注明来源；复制代码前先检查许可证与分发条件，不删除原作者声明。

问题反馈请写明操作步骤、期望结果与实际结果。日志、截图及 CSV 请先去除个人信息。
