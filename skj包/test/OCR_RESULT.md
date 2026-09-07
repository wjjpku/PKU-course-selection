# 本地验证码实测

2026-09-05，在 Python 3.12 独立环境 `.venv-ocr` 中调用项目实际的
`CaptchaRecognizer`，对 `test/data` 全部 20 张历史图片逐张核对文件名标签。

- 正确：20 / 20。
- 单张耗时中位数：2.525 ms；首次推理：288.23 ms。
- 模型初始化：15.23 ms，不包含 Python 导入依赖的耗时。
- 模型 SHA-256：`5f4e0cd3a680e9d5b142dd9f3b728196c4401bd64100be382eff40e0dd4472ba`。
- ddddocr 1.5.6、onnxruntime 1.29.0、Pillow 10.4.0、NumPy 2.5.2。

在工作区根目录复现：

```sh
.venv-ocr/bin/python skj包/test/benchmark_ocr.py
```

模型未更换。旧依赖 ddddocr 1.4.7 在本次安装源中不可用，因此采用
1.5.6 实测。该独立环境没有替换前端服务正在使用的 Python 环境。

这些图片来自项目历史样本，结果不代表当前学期线上识别率。
测试未登录选课网，也未调用学校验证码校验接口。
