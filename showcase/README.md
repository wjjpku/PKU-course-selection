# Vercel 交互展示

展示版复用原有查询、课表、课程篮和任务 UI，只替换数据接口为浏览器内模拟。

- 所有课程、教师、余量与已选课均为虚构示例，不读取本机数据库或学校接口。
- 不提供登录；没有 Python 后端、真实选课、退课或数据库连接。
- `fetch` 无网络回退；CSP `connect-src 'none'` 和 `form-action 'none'` 阻止后台连接与表单提交。
- 任务使用当前标签页的 `sessionStorage`，刷新后停止，关闭页面后不会后台运行。每 5 轮演示成功，不代表真实结果。
- 课程篮与查询条件保存在当前站点的浏览器存储中；与 localhost 工作台隔离。不要输入个人信息。

在项目根目录执行构建：`node scripts/build-showcase.cjs`。检查：`node showcase/tests/demo.cjs`。展示源码位于本目录，测试位于 `tests/`，生成文件统一放在 `output/vercel-showcase/`。

仅将生成的 `output/vercel-showcase/` 目录作为 Vercel 项目部署。构建器只复制 11 个显式列出的网页文件，不得从仓库根目录直接上传部署。

此目录不包含账号配置、数据库、CSV、Cookie、日志、模型、虚拟环境或任何环境变量。部署不修改本地正在运行的服务。

## 首次上线记录（2026-09-07）

- 站点：https://pku-course-selection-demo.vercel.app/
- Vercel 项目：`pku-course-selection-demo`，项目 ID `prj_WCaYzE3rHbFTAVvSZNUKh1hbZjrf`。
- 部署 ID：`dpl_8gdpqc2GrHk171wkKUSoPBHQxxdF`；实际返回状态 `READY`、目标 `production`（首个部署），构建约 1.8 秒。
- 来源：v0.1.0 / `896eef3` 的前端，加当前目录的展示适配；不是未修改的 v0.1.0。
- 使用 Vercel 已授权集成上传 10 个明确列出的静态文件，未连接 Git 自动部署、个人网站或数据库。
- 自动测试覆盖：示例数据、任务启停、100 条日志上限、刷新后停止恢复、真实操作拦截。
- 浏览器验证覆盖：查询、课程篮、模拟启动与日志、停止恢复、CSV、390px 手机布局；网络记录只有静态资源。
- 线上验证：首页及主要脚本与本地发布包一致；CSP 生效，真实 API、配置和数据库路径返回 404；线上查询正常、浏览器无错误。
- 上线时 Vercel 错误检查未发现运行错误；静态站未新增持续监控或日志转存服务。
