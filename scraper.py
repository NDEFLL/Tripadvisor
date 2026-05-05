"""
TripAdvisor 欧洲景区数据采集 — CDP 浏览器自动化 (v4 最终版)
通过 Chrome DevTools Protocol 直接控制浏览器请求页面
DataDome CAPTCHA 由浏览器自动处理
解析 SSR HTML 中的景区卡片数据
"""

import re
import json
import time
import random
import logging
import os
from typing import Optional
import urllib.request

import websocket

# ---------- 日志配置 ----------
# 日志同时输出到控制台和文件
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("../logs/scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------- 全局配置 ----------
CDP_PORT = 9222     # Chrome 远程调试端口，启动时需保持一致
PAGE_SIZE = 30      # 每页包含的景点数量（TripAdvisor 分页步长）
PROGRESS_FILE = "../data/progress.json"     # 记录已完成城市和总数，用于断点续爬
OUTPUT_FILE = "../data/europe_attractions.json"     # 最终保存的所有景点数据

# ---------- 欧洲目标城市列表 ----------
# 格式：{"城市名, 国家": geo_id}，geo_id 是 TripAdvisor 内部的地点标识
EUROPE_TARGETS = {
    "Paris, France": 187070,
    "Nice, France": 187234,
    "Lyon, France": 187265,
    "Rome, Italy": 187791,
    "Florence, Italy": 187895,
    "Venice, Italy": 187871,
    "Milan, Italy": 187849,
    "Naples, Italy": 187876,
    "Barcelona, Spain": 187497,
    "Madrid, Spain": 187514,
    "Seville, Spain": 187427,
    "Berlin, Germany": 187323,
    "Munich, Germany": 187307,
    "Hamburg, Germany": 187326,
    "London, England": 186338,
    "Edinburgh, Scotland": 186525,
    "Athens, Greece": 189400,
    "Santorini, Greece": 189413,
    "Mykonos, Greece": 189408,
    "Crete, Greece": 189401,
    "Amsterdam, Netherlands": 188590,
    "Lisbon, Portugal": 189158,
    "Porto, Portugal": 189174,
    "Vienna, Austria": 190454,
    "Salzburg, Austria": 190456,
    "Zurich, Switzerland": 188110,
    "Lucerne, Switzerland": 188114,
    "Interlaken, Switzerland": 188106,
    "Geneva, Switzerland": 188089,
    "Prague, Czech Republic": 274707,
    "Budapest, Hungary": 274889,
    "Dubrovnik, Croatia": 294458,
    "Zagreb, Croatia": 294453,
    "Split, Croatia": 294460,
    "Krakow, Poland": 274613,
    "Warsaw, Poland": 274656,
    "Dublin, Ireland": 186605,
    "Stockholm, Sweden": 189622,
    "Copenhagen, Denmark": 189541,
    "Bruges, Belgium": 188627,
    "Brussels, Belgium": 188634,
    "Oslo, Norway": 190625,
    "Bergen, Norway": 190620,
    "Helsinki, Finland": 189596,
    "Reykjavik, Iceland": 189180,
}

# 将国家名称映射为 URL 中使用的路径片段（用于构造景点列表页）
COUNTRY_URL = {
    "France": "France", "Italy": "Italy", "Spain": "Spain", "Germany": "Germany",
    "England": "England", "Scotland": "Scotland", "Greece": "Greece",
    "Netherlands": "Netherlands", "Portugal": "Portugal", "Austria": "Austria",
    "Switzerland": "Switzerland", "Czech Republic": "Czech_Republic",
    "Hungary": "Hungary", "Croatia": "Croatia", "Poland": "Poland",
    "Ireland": "Ireland", "Sweden": "Sweden", "Denmark": "Denmark",
    "Belgium": "Belgium", "Norway": "Norway", "Finland": "Finland", "Iceland": "Iceland",
}


# ==================== CDP 客户端 ====================

class CDP:
    """封装 Chrome DevTools Protocol 的基础操作，支持断线重连"""
    def __init__(self):
        self.ws = None
        self.mid = 0
        self._ws_url = None

    def connect(self, ws_url=None):
        """建立或重新建立 WebSocket 连接"""
        if ws_url:
            self._ws_url = ws_url
        if not self._ws_url:
            self._ws_url = get_ws_url()
        if not self._ws_url:
            raise ConnectionError("无法获取 Chrome WebSocket URL")
        self.ws = websocket.create_connection(self._ws_url, timeout=120)
        self.mid = 0
        self.send("Page.enable")
        self.send("Network.enable")
        return True

    def _reconnect(self):
        """断线重连"""
        log.warning("CDP 连接断开，尝试重连...")
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        time.sleep(2)
        # 获取新的页面 URL（Chrome 可能重新分配了页面 ID）
        new_url = get_ws_url()
        if new_url:
            self._ws_url = new_url
        self.ws = websocket.create_connection(self._ws_url, timeout=120)
        self.mid = 0
        self.send("Page.enable")
        self.send("Network.enable")
        log.info("CDP 重连成功")

    def send(self, method, params=None):
        """发送 CDP 命令，失败时自动重连重试"""
        self.mid += 1
        msg = {"id": self.mid, "method": method}
        if params:
            msg["params"] = params
        try:
            self.ws.send(json.dumps(msg))
            while True:
                raw = self.ws.recv()
                data = json.loads(raw)
                if "id" in data and data["id"] == self.mid:
                    return data
        except (websocket.WebSocketException, ConnectionError, OSError) as e:
            log.warning(f"CDP 发送失败: {e}, 重连重试...")
            self._reconnect()
            # 重试一次
            self.mid += 1
            msg = {"id": self.mid, "method": method}
            if params:
                msg["params"] = params
            self.ws.send(json.dumps(msg))
            while True:
                raw = self.ws.recv()
                data = json.loads(raw)
                if "id" in data and data["id"] == self.mid:
                    return data

    def eval(self, expr, return_by_value=True):
        """在浏览器页面中执行 JavaScript 表达式"""
        try:
            r = self.send("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": return_by_value,
                "awaitPromise": True,
            })
            return r.get("result", {}).get("result", {}).get("value")
        except Exception as e:
            log.error(f"JS 执行失败: {e}")
            return None

    def navigate(self, url, wait=10):
        """导航到指定 URL"""
        self.send("Page.navigate", {"url": url})
        time.sleep(wait)

    def scroll_down(self, pixels=2000, steps=3):
        """模拟向下滚动"""
        for i in range(steps):
            self.eval(f"window.scrollTo(0, {(i + 1) * pixels})")
            time.sleep(1.5)

    def close(self):
        if self.ws:
            self.ws.close()


def get_ws_url():
    """
    从 Chrome 的 /json 列表中找到第一个可用页面的 WebSocket 调试地址
    前提：Chrome 已用 --remote-debugging-port=9222 启动，且至少打开一个标签页
    """
    resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json")
    pages = json.loads(resp.read())
    for p in pages:
        if p.get("type") == "page":     # 只取普通页面，忽略 service worker 等
            return p["webSocketDebuggerUrl"]
    return None


# ==================== 页面解析 (在浏览器内执行) ====================
# 这个 JS 字符串会被发送到浏览器执行，返回当前页面中所有景区卡片的信息。
# 使用了多种选择器和策略，目的是尽可能从不同版本的 TripAdvisor 页面布局中提取数据。
EXTRACT_JS = """
(function() {
    var results = [];

    // 方法1: 从 cardTitle 提取
    var cards = document.querySelectorAll('[data-automation="cardTitle"]');
    cards.forEach(function(card) {
        var title = card.textContent.trim();
        var rank = 0;
        var name = title;
        var m = title.match(/^(\\d+)\\.\\s*(.+)/);
        if (m) { rank = parseInt(m[1]); name = m[2]; }

        // 向上找父级 <a> 链接
        var parent = card.closest('a[href*="Attraction_Review"]');
        var locationId = '';
        var url = '';
        if (parent) {
            var href = parent.getAttribute('href') || '';
            var lm = href.match(/-d(\\d+)-/);
            if (lm) locationId = lm[1];
            url = href;
        }

        // 如果没在卡片直接父级找到，搜索附近
        if (!locationId) {
            var container = card.closest('[class*="X"]') || card.parentElement.parentElement;
            if (container) {
                var links = container.querySelectorAll('a[href*="Attraction_Review"]');
                for (var i = 0; i < links.length; i++) {
                    var lm2 = links[i].getAttribute('href').match(/-d(\\d+)-/);
                    if (lm2) { locationId = lm2[1]; url = links[i].getAttribute('href'); break; }
                }
            }
        }

        // 提取评分和评论数
        var rating = 0;
        var reviewCount = 0;
        var searchArea = card;
        for (var i = 0; i < 8; i++) {
            if (searchArea.parentElement) searchArea = searchArea.parentElement;
        }
        if (searchArea) {
            var text = searchArea.textContent;
            var rm = text.match(/(\\d\\.?\\d?)\\s*(?:of\\s+5|\\/5|bubbles?)/i);
            if (rm) rating = parseFloat(rm[1]);
            var rcm = text.match(/([\\d,]+)\\s*review/i);
            if (rcm) reviewCount = parseInt(rcm[1].replace(/,/g, ''));
            var rkm = text.match(/#(\\d+)\\s+of\\s+([\\d,]+)\\s+things/);
            if (rkm) rank = parseInt(rkm[1]);
        }
        // 尝试从 svg title 中提取评分
        if (rating === 0 && card.parentElement) {
            var anc = card.parentElement.parentElement;
            if (anc) {
                var svgs = anc.querySelectorAll('svg title');
                for (var s = 0; s < svgs.length; s++) {
                    var t = svgs[s].textContent;
                    var sm = t.match(/(\\d\\.?\\d?)\\s+of\\s+5/i);
                    if (sm) { rating = parseFloat(sm[1]); break; }
                }
            }
        }

        results.push({
            location_id: locationId,
            name: name,
            rank: rank,
            rating: rating,
            review_count: reviewCount,
            url: url,
            source: 'card'
        });
    });

    // 方法2: 从所有 Attraction_Review 链接补充
    var allLinks = document.querySelectorAll('a[href*="Attraction_Review"]');
    var seen = {};
    results.forEach(function(r) { if (r.location_id) seen[r.location_id] = true; });

    allLinks.forEach(function(a) {
        var href = a.getAttribute('href') || '';
        var lm = href.match(/-d(\\d+)-Reviews-([^"?]+)/);
        if (lm && !seen[lm[1]]) {
            seen[lm[1]] = true;
            results.push({
                location_id: lm[1],
                name: lm[2].replace(/_/g, ' '),
                rank: 0,
                rating: 0,
                review_count: 0,
                url: href,
                source: 'link'
            });
        }
    });

    // 检查分页
    var nextOffset = 0;
    var pageLinks = document.querySelectorAll('a[href*="Activities-oa"]');
    pageLinks.forEach(function(a) {
        var m = a.getAttribute('href').match(/oa(\\d+)/);
        if (m) {
            var o = parseInt(m[1]);
            if (o > nextOffset) nextOffset = o;
        }
    });

    var currentOffset = 0;
    var curMatch = window.location.href.match(/oa(\\d+)/);
    if (curMatch) currentOffset = parseInt(curMatch[1]);

    return {
        attractions: results,
        next_offset: nextOffset,
        current_offset: currentOffset,
        has_more: nextOffset > currentOffset,
        page_title: document.title
    };
})()
"""


# ==================== 核心采集 ====================

def scrape_city(cdp, city_name, geo_id):
    """
    采集单个城市的所有景区（分页遍历）
    参数：
        cdp: CDP 实例
        city_name: 显示用，如 "Paris, France"
        geo_id: TripAdvisor 的地点 ID
    返回：该城市所有景区信息的列表（字典）
    """
    country = city_name.split(", ")[-1]
    country_slug = COUNTRY_URL.get(country, country.replace(" ", "_"))
    log.info(f"===== 采集: {city_name} (geoId={geo_id}) =====")

    all_attractions = []
    ids = set()     # 用于去重，基于 location_id
    offset = 0      # 当前分页偏移量
    page_num = 0

    while True:
        page_num += 1
        # 构造分页 URL：第一页无 oa 参数，后续页使用 oa{offset}
        if offset == 0:
            url = f"https://www.tripadvisor.com/Attractions-g{geo_id}-Activities-{country_slug}.html"
        else:
            url = f"https://www.tripadvisor.com/Attractions-g{geo_id}-Activities-oa{offset}-{country_slug}.html"

        log.info(f"  第 {page_num} 页 (offset={offset})")

        # 让浏览器加载该页面
        cdp.navigate(url, wait=8)

        # 滚动页面确保加载
        cdp.scroll_down(1500, 3)
        time.sleep(2)

        # 在浏览器中提取数据
        result = cdp.eval(EXTRACT_JS)

        if not result:
            log.warning("  提取结果为空")
            break

        attractions = result.get("attractions", [])
        has_more = result.get("has_more", False)    # 根据是否存在更大的 oa 链接判断是否有下一页

        if not attractions:
            log.info(f"  无景区数据，结束")
            break

        new_count = 0
        for a in attractions:
            lid = a.get("location_id", "")
            if lid and lid not in ids:
                ids.add(lid)
                # 补充城市和国家信息，便于后续统计
                a["city"] = city_name.split(", ")[0]
                a["country"] = country
                a["geo_id"] = str(geo_id)
                # 补全 URL
                if a.get("url") and not a["url"].startswith("http"):
                    a["url"] = "https://www.tripadvisor.com" + a["url"]
                all_attractions.append(a)
                new_count += 1

        log.info(f"  第 {page_num} 页: {len(attractions)} 条, 新增 {new_count}, 累计 {len(all_attractions)}")

        if not has_more:
            log.info("  无更多页面")
            break

        offset += PAGE_SIZE

        # 安全上限
        if offset > 1000:
            log.info("  达到安全上限")
            break

        # 随机延迟
        delay = random.uniform(3, 8)
        log.info(f"  等待 {delay:.1f}s...")
        time.sleep(delay)

    log.info(f"===== {city_name}: 共 {len(all_attractions)} 个景区 =====")
    return all_attractions


# ==================== 断点续爬与存储 ====================

def load_progress():
    """加载已采集的城市进度，用于断点续爬"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_cities": [], "total_saved": 0}

def save_progress(p):
    """保存进度"""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def load_data():
    """加载现有景区数据（之前已采集的）"""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(d):
    """保存全部景区数据到 JSON 文件"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# ==================== 主流程 ====================

def main():
    log.info("=" * 60)
    log.info("TripAdvisor 欧洲景区采集 v4 — CDP 浏览器自动化")
    log.info("=" * 60)

    # 连接 Chrome，如果连不上则自动启动
    cdp = CDP()
    try:
        cdp.connect()
    except Exception:
        log.warning("无法连接 Chrome 调试端口 (9222)，尝试自动启动...")
        import subprocess
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        user_data = r"D:\MCP_Reverse_Project\Ai_obstacle\ChromeDebug"
        subprocess.Popen([
            chrome_path,
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data}",
        ])
        log.info("等待 Chrome 启动...")
        time.sleep(8)
        try:
            cdp.connect()
        except Exception as e2:
            log.error(f"Chrome 启动后仍无法连接: {e2}")
            log.error("请手动运行以下命令启动 Chrome 后重试:")
            log.error(f'  "{chrome_path}" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="{user_data}"')
            return

    # 先确认 CAPTCHA 状态 — 导航到 TripAdvisor 首页
    log.info("检查 CAPTCHA 状态...")
    cdp.navigate("https://www.tripadvisor.com/", wait=5)
    title = cdp.eval("document.title") or ""
    if "captcha" in title.lower() or len(title) < 5:
        log.warning("需要通过 CAPTCHA! 请在浏览器中手动完成验证，然后重新运行")
        cdp.close()
        return
    log.info(f"浏览器就绪: {title}")

    # 加载进度
    progress = load_progress()
    existing = load_data()
    existing_ids = {a.get("location_id") for a in existing}
    done = set(progress.get("completed_cities", []))
    log.info(f"已有 {len(existing)} 条, {len(done)} 城市已完成")

    todo = [(n, g) for n, g in EUROPE_TARGETS.items() if n not in done]
    log.info(f"待采集: {len(todo)} 个城市")
    if not todo:
        log.info("全部完成!")
        cdp.close()
        return

    new_all = []
    for idx, (city, gid) in enumerate(todo, 1):
        log.info(f"\n[{idx}/{len(todo)}] {city}")

        try:
            attrs = scrape_city(cdp, city, gid)
        except Exception as e:
            log.error(f"采集异常: {e}")
            attrs = None

        new = 0
        for a in (attrs or []):
            lid = a.get("location_id", "")
            if lid and lid not in existing_ids:
                existing_ids.add(lid)
                existing.append(a)
                new_all.append(a)
                new += 1
        log.info(f"  新增 {new}")

        done.add(city)
        progress["completed_cities"] = list(done)
        progress["total_saved"] = len(existing)
        save_progress(progress)
        save_data(existing)

        # 城市间延迟
        if idx < len(todo):
            delay = random.uniform(5, 12)
            log.info(f"  城市间等待 {delay:.1f}s...")
            time.sleep(delay)

    save_data(existing)
    cdp.close()

    log.info("\n" + "=" * 60)
    log.info(f"完成! 总计 {len(existing)} 景区, 本次新增 {len(new_all)}")
    stats = {}
    for a in existing:
        c = a.get("country", "?")
        stats[c] = stats.get(c, 0) + 1
    for c, n in sorted(stats.items(), key=lambda x: -x[1]):
        log.info(f"  {c}: {n}")


if __name__ == "__main__":
    main()
