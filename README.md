# Tripadvisor
通过 Chrome DevTools Protocol (CDP) 直接控制真实浏览器，绕过 Tripadvisor 的 JavaScript 挑战、指纹识别和动态内容反爬，稳定采集欧洲 40+ 城市的景点数据。纯 Python 实现，无 Selenium/Puppeteer 依赖。

Tripadvisor 使用了多种阻拦技术：

- **JavaScript 挑战**：Tripadvisor 会以 CAPTCHA 的形式向你的浏览器发送简单的 JavaScript 挑战，如果浏览器无法解决，就很可能被判定为爬虫。
- **浏览器指纹识别**：它会向你的浏览器发送一个 cookie，然后用这个 cookie 来跟踪你的行为。
- **动态内容**：我们最初获得的页面是空白的，随后它会通过一系列 API 调用来获取并渲染数据。

传统的 `Python Requests` 和 `curl_cffi` 并不能胜任此工作。我们需要一个**真正的浏览器**。本项目通过 Chrome 底层的 **CDP 协议**（Chrome DevTools Protocol）在 Python 脚本中直接控制浏览器，彻底绕过反爬检测，稳定采集 Tripadvisor 欧洲主要城市的景点数据。

## ✨ 功能特点

- 🕵️ **真实浏览器环境**：直接控制带有调试端口的 Chrome 浏览器，完美执行 JS、处理 CAPTCHA（首次手动验证后即可自动运行）。
- 📄 **完整数据提取**：解析 SSR 渲染后的 HTML，获取景区 `location_id`、名称、排名、评分、评论数、详情页 URL 等。
- 🔄 **自动翻页**：自动识别分页链接并遍历全部列表页，支持断点续爬。
- 🌍 **欧洲主要城市**：内置 40+ 欧洲热门城市的 `geo_id`（巴黎、罗马、伦敦、柏林等），可轻松扩展。
- 📁 **增量保存**：每完成一个城市即保存数据到 JSON 文件，避免意外中断导致数据丢失。
- 📊 **进度追踪**：自动保存已完成城市列表，重启时自动跳过。


## 🛠 技术栈

- **Python 3.8+**
- **Chrome 浏览器**（需开启远程调试端口）
- **websocket-client**：与 Chrome 调试端口建立 WebSocket 连接
- **CDP (Chrome DevTools Protocol)**：直接发送 `Page.navigate`、`Runtime.evaluate` 等底层命令

## 📦 安装与配置

### 1. 克隆仓库
```bash
git clone https://github.com/yourusername/tripadvisor-scraper.git
cd tripadvisor-scraper
