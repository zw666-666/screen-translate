# Screen Translate｜屏幕翻译助手

一个 Windows 托盘翻译工具：可直接翻译文本，也可框选屏幕内容进行本地 OCR，再校正识别结果、调用翻译并朗读。

> 仓库只包含项目源码和依赖清单，**不包含任何可用的个人 DeepSeek API Key**。其他人克隆仓库后，需要配置自己的 Key 和服务商账户，不能使用你的 API 额度。

## 功能

- 使用快捷键 Shift + Win + Z 呼出翻译窗口
- 支持粘贴/输入文本翻译，支持中、英、日、韩语言设置
- 框选屏幕区域后使用本地 Tesseract OCR 识别，可手动校正再翻译
- 译文支持复制和语音朗读；Edge TTS 失败时，系统语音仅在用户同意后启用
- 后台任务避免 OCR、翻译和语音请求阻塞界面
- 打开窗口不会自动读取剪贴板；请求由用户主动操作触发

## 技术栈

Python、PyQt5、MSS、Tesseract OCR、DeepSeek API、Edge TTS、SQLite/本地配置。

## 安装与运行

需要 Windows 10/11、Python 3.12，以及已安装并配置语言包的 Tesseract OCR（eng、chi_sim、jpn、kor）。

1. 在项目目录创建并激活 Python 虚拟环境。
2. 安装依赖：python -m pip install -r requirements.txt
3. 将你自己的 DeepSeek API Key 写入本机文件：%LOCALAPPDATA%/ScreenTranslator/deepseek_key.txt
4. 启动 launcher.pyw，或使用 pythonw.exe 运行。

Key 只保存在本机应用数据目录，不要写入源码、README、截图或 GitHub 提交。

## 隐私与密钥说明

- 复制或输入的文本只会在点击“翻译”后发送给翻译服务。
- 框选截图使用本地 Tesseract OCR；翻译请求发送的是识别后的文本。
- Git 仓库忽略本机 Key 文件、配置、日志、Python 缓存和快捷方式。
- 如果 Key 曾被提交到 Git，即使后来删除文件，旧提交历史仍可能保留；应立即在 DeepSeek 控制台撤销并重新生成。

## 项目结构

- launcher.pyw：无命令窗口启动入口
- screen_translator/main.py：窗口和任务编排
- screen_translator/overlay.py、ocr_engine.py：区域框选与 OCR
- screen_translator/translator.py：翻译接口
- screen_translator/speech_service.py：语音播放
- screen_translator/settings.py、tray_icon.py：本地设置与托盘
