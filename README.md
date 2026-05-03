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
```

### 2. 安装 Python 依赖
```bash
pip install websocket-client
```

### 3. 创建必要目录
脚本默认将数据保存在上级目录的 data/ 和 logs/ 文件夹中，请手动创建：
```bash
mkdir -p ../data ../logs
```

### 4. 启动 Chrome 调试模式
在终端中执行以下命令（根据你的操作系统）：
Windows：
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=*
```

macOS：
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-allow-origins=*
```

Linux：
```bash
google-chrome --remote-debugging-port=9222 --remote-allow-origins=*
```

⚠️ 确保此时 Chrome 浏览器窗口已经打开一个空白标签页（或任意页面），并且没有其他程序占用 9222 端口。

### 基本运行
```bash
python scraper.py
```


首次运行注意事项
脚本启动后会首先访问 Tripadvisor 首页检查 CAPTCHA 状态。如果浏览器弹出验证码，请手动完成验证（可能只需一次），然后重新运行脚本即可。

验证通过后，脚本将自动开始采集所有内置城市的景点数据。

断点续爬
若中途中断，再次运行脚本时会自动读取 ../data/progress.json，跳过已完成的城市，从下一个未采集的城市继续。

📁 输出文件
项目运行后会在 ../data/ 目录下生成两个文件：

文件	说明
europe_attractions.json	最终采集的所有景点数据，每条记录包含：location_id, name, rank, rating, review_count, url, city, country, geo_id 等字段。
progress.json	进度文件，记录已完成的城市列表和当前总景点数，用于断点续爬。
日志文件位于 ../logs/scraper.log，可查看详细运行信息。

🔧 自定义采集
添加/修改城市
编辑脚本中的 EUROPE_TARGETS 字典，按照 "城市名, 国家": geo_id 的格式添加新城市。geo_id 可从 Tripadvisor 景点列表页的 URL 中获取（例如 https://www.tripadvisor.com/Attractions-g187070-... 中的 187070 就是巴黎的 geo_id）。

修改采集上限
PAGE_SIZE = 30：每页景点数（Tripadvisor 固定为 30，请勿随意修改）

翻页安全上限：脚本中设置了 if offset > 1000: break，可根据需要调整。


📝 代码结构
'''text
.
├── scraper.py               # 主脚本
├── README.md                # 本文档
└── requirements.txt         # 依赖列表（仅 websocket-client）
主要核心类：
CDP：封装 WebSocket 通信、CDP 命令发送、JS 执行等。
scrape_city()：采集单个城市的所有分页。
EXTRACT_JS：在浏览器内执行的 JS 脚本，用于提取页面景点数据。


⚠️ 免责声明与注意事项
尊重 robots.txt：请在使用前查看 Tripadvisor 的 robots.txt，确保你的采集行为符合网站规定。

请求频率：脚本已在每次请求之间添加随机延迟（3~8 秒，城市间 5~12 秒），但请勿在短时间内对大量城市进行高并发采集，以免 IP 被封禁。

仅供学习参考：本项目仅用于技术研究和学习目的，请勿用于商业用途或对 Tripadvisor 服务器造成压力。

CAPTCHA 处理：虽然浏览器可以自动呈现验证码，但首次可能需要手动完成。脚本不会自动识别验证码，请按照提示操作。
