#!/usr/bin/env python3
"""
幽玄の間 (日本棋院) 直播棋谱获取工具
Yugen Live Kifu Fetcher

这是围棋职业比赛直播的「源头」获取工具。
幽玄の間是日本棋院的官方中继平台，是扇兴杯等比赛数据的原始来源。

使用方法:
  步骤1: 先在浏览器登录幽玄の間，用开发者工具提取cookie
  步骤2: 运行本脚本

  # 列出当前直播和历史中继棋谱
  python yugen_live_fetcher.py --list

  # 监控某一盘直播（需要 sno 编号）
  python yugen_live_fetcher.py --watch 19 --interval 15

  # 用浏览器开发者工具辅助抓包（推荐的方法）
  python yugen_live_fetcher.py --guide

已知的幽玄の間 URL 结构:
  直播列表:     /live/live_list.asp
  中继日程:     /live/schedule_list.asp
  棋谱鉴赏列表: /live/live_kifu_list.asp
  直播viewer:   /kifu_new/live/viewer.asp?sno={id}
  旧版viewer:   /common/java_kifu_viewer2.asp?no={id}
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from http.cookiejar import MozillaCookieJar

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    print("需要 requests 库，正在安装...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests
    from requests.adapters import HTTPAdapter

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ============================================================================
# 配置
# ============================================================================

BASE_URL = "https://u-gen.nihonkiin.or.jp"

URLS = {
    "login":          f"{BASE_URL}/login/login.asp",
    "login_post":     f"{BASE_URL}/login/login_check.asp",
    "live_list":      f"{BASE_URL}/live/live_list.asp",
    "schedule":       f"{BASE_URL}/live/schedule_list.asp",
    "kifu_list":      f"{BASE_URL}/live/live_kifu_list.asp",
    "kifu_list_jp":   f"{BASE_URL}/live/live_kifu_list.asp?gibo_div=1",
    "kifu_list_intl": f"{BASE_URL}/live/live_kifu_list.asp?gibo_div=2",
    "live_viewer":    f"{BASE_URL}/kifu_new/live/viewer.asp?sno={{sno}}",
    "old_viewer":     f"{BASE_URL}/common/java_kifu_viewer2.asp?no={{no}}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,zh-CN;q=0.9,zh;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


# ============================================================================
# NGF → SGF 转换
# ============================================================================

def ngf_to_sgf(ngf_text, metadata=None):
    """
    将 NGF 格式棋谱转换为 SGF 格式。
    NGF 是日本棋院专用格式，幽玄の間使用此格式保存棋谱。
    """
    metadata = metadata or {}
    moves = []

    lines = ngf_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        # NGF 走子行格式多种, 尝试匹配:
        #   "PM B Q16"  或  "1 B Q16"  或  "B Q16"
        m = re.match(r'(?:PM\s+|\d+\s+)?([BW])\s+([A-T])(\d+)', line, re.IGNORECASE)
        if m:
            color = m.group(1).upper()
            col_letter = m.group(2).upper()
            row_num = int(m.group(3))

            # NGF坐标 → SGF坐标
            col = ord(col_letter) - ord('A')
            if col > 7:  # NGF 跳过 'I'
                col -= 1
            row = 19 - row_num  # NGF行号从下往上

            if 0 <= col < 19 and 0 <= row < 19:
                sgf_coord = chr(ord('a') + col) + chr(ord('a') + row)
                moves.append(f";{color}[{sgf_coord}]")

    # 构建 SGF
    sgf = "(;GM[1]FF[4]SZ[19]"
    if metadata.get("black"):
        sgf += f"PB[{metadata['black']}]"
    if metadata.get("white"):
        sgf += f"PW[{metadata['white']}]"
    if metadata.get("event"):
        sgf += f"EV[{metadata['event']}]"
    if metadata.get("date"):
        sgf += f"DT[{metadata['date']}]"
    if metadata.get("result"):
        sgf += f"RE[{metadata['result']}]"
    if metadata.get("komi"):
        sgf += f"KM[{metadata['komi']}]"

    sgf += "\n"
    for i, move in enumerate(moves):
        sgf += move
        if (i + 1) % 10 == 0:
            sgf += "\n"
    sgf += ")\n"

    return sgf


# ============================================================================
# 幽玄の間 客户端
# ============================================================================

class YugenClient:
    """幽玄の間 网页版客户端"""

    def __init__(self, cookie_string=None, cookie_file=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        if cookie_string:
            self._set_cookies_from_string(cookie_string)
        elif cookie_file and os.path.exists(cookie_file):
            self._load_cookies_from_file(cookie_file)

    def _set_cookies_from_string(self, cookie_str):
        """
        从浏览器复制的 cookie 字符串设置 cookies。
        格式: "key1=value1; key2=value2; ..."
        """
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                name, value = item.split('=', 1)
                self.session.cookies.set(
                    name.strip(), value.strip(),
                    domain="u-gen.nihonkiin.or.jp"
                )
        print(f"已设置 {len(self.session.cookies)} 个 cookie")

    def _load_cookies_from_file(self, filepath):
        """从文件加载 cookies"""
        with open(filepath, 'r') as f:
            cookie_str = f.read().strip()
        self._set_cookies_from_string(cookie_str)

    def save_cookies(self, filepath):
        """保存 cookies 到文件"""
        cookies = "; ".join(f"{c.name}={c.value}" for c in self.session.cookies)
        with open(filepath, 'w') as f:
            f.write(cookies)
        print(f"Cookies 已保存到: {filepath}")

    def login(self, username, password):
        """
        登录幽玄の間。
        注意: 登录流程可能因网站更新而变化，需根据实际情况调整。
        """
        print(f"正在登录幽玄の間 (用户: {username})...")

        # 先访问登录页面获取可能的隐藏字段
        try:
            resp = self.session.get(URLS["login"], timeout=15)
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"访问登录页面失败: {e}")
            return False

        # 提取表单隐藏字段
        hidden_fields = {}
        if HAS_BS4:
            soup = BeautifulSoup(resp.text, "html.parser")
            for inp in soup.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                value = inp.get("value", "")
                if name:
                    hidden_fields[name] = value

        # 提交登录
        login_data = {
            **hidden_fields,
            "uid": username,
            "pwd": password,
        }

        try:
            resp = self.session.post(
                URLS["login_post"], data=login_data,
                timeout=15, allow_redirects=True
            )
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"登录请求失败: {e}")
            return False

        # 检查登录是否成功
        if "logout" in resp.text.lower() or "ログアウト" in resp.text:
            print("✓ 登录成功!")
            return True
        elif "エラー" in resp.text or "error" in resp.text.lower():
            print("✗ 登录失败，请检查用户名和密码。")
            return False
        else:
            print("? 登录状态不确定，继续尝试...")
            return True  # 可能已成功

    def get_live_list(self):
        """获取当前正在直播的棋局列表"""
        print("\n获取直播列表...")
        try:
            resp = self.session.get(URLS["live_list"], timeout=15)
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"获取直播列表失败: {e}")
            return []

        return self._parse_game_list(resp.text, "直播")

    def get_schedule(self):
        """获取中继日程"""
        print("\n获取中继日程...")
        try:
            resp = self.session.get(URLS["schedule"], timeout=15)
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"获取日程失败: {e}")
            return []

        return self._parse_game_list(resp.text, "日程")

    def get_kifu_list(self, division=None):
        """获取历史中继棋谱列表"""
        url = URLS["kifu_list"]
        if division == "jp":
            url = URLS["kifu_list_jp"]
        elif division == "intl":
            url = URLS["kifu_list_intl"]

        print(f"\n获取棋谱列表...")
        try:
            resp = self.session.get(url, timeout=15)
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"获取棋谱列表失败: {e}")
            return []

        return self._parse_game_list(resp.text, "棋谱")

    def _parse_game_list(self, html, list_type):
        """
        解析棋局列表页面。
        提取棋局信息（名称、对局者、链接等）。
        """
        games = []

        # 方法1: 使用 BeautifulSoup (更可靠)
        if HAS_BS4:
            soup = BeautifulSoup(html, "html.parser")

            # 查找所有链接到 viewer 的条目
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")

                # 匹配 viewer.asp?sno=N
                m = re.search(r'viewer\.asp\?sno=(\d+)', href)
                if m:
                    sno = m.group(1)
                    text = link.get_text(strip=True)
                    game = {
                        "sno": sno,
                        "title": text,
                        "url": f"{BASE_URL}/kifu_new/live/viewer.asp?sno={sno}",
                        "type": list_type,
                    }
                    games.append(game)
                    continue

                # 匹配 java_kifu_viewer2.asp?no=N
                m = re.search(r'java_kifu_viewer2\.asp\?no=(\d+)', href)
                if m:
                    no = m.group(1)
                    text = link.get_text(strip=True)
                    game = {
                        "no": no,
                        "title": text,
                        "url": f"{BASE_URL}/common/java_kifu_viewer2.asp?no={no}",
                        "type": list_type,
                    }
                    games.append(game)

        # 方法2: 正则表达式 (备用)
        if not games:
            # viewer.asp?sno=N
            for m in re.finditer(
                r'viewer\.asp\?sno=(\d+)[^>]*>([^<]+)', html
            ):
                games.append({
                    "sno": m.group(1),
                    "title": m.group(2).strip(),
                    "url": f"{BASE_URL}/kifu_new/live/viewer.asp?sno={m.group(1)}",
                    "type": list_type,
                })

            # java_kifu_viewer2.asp?no=N
            for m in re.finditer(
                r'java_kifu_viewer2\.asp\?no=(\d+)[^>]*>([^<]+)', html
            ):
                games.append({
                    "no": m.group(1),
                    "title": m.group(2).strip(),
                    "url": f"{BASE_URL}/common/java_kifu_viewer2.asp?no={m.group(1)}",
                    "type": list_type,
                })

        return games

    def fetch_live_viewer(self, sno):
        """
        获取直播 viewer 页面的完整内容。
        这是获取实时棋谱数据的关键步骤。

        viewer.asp 页面通常包含:
        - 嵌入的 JavaScript 中的棋谱数据
        - 或通过 AJAX 加载棋谱的 URL
        - 或直接嵌入的 NGF/SGF 数据
        """
        url = URLS["live_viewer"].format(sno=sno)
        print(f"\n获取直播 viewer: {url}")

        try:
            resp = self.session.get(url, timeout=15)
            resp.encoding = "shift_jis"
        except Exception as e:
            print(f"获取 viewer 失败: {e}")
            return None

        if resp.status_code != 200:
            print(f"HTTP {resp.status_code}")
            return None

        html = resp.text
        result = {
            "html": html,
            "url": url,
            "sno": sno,
            "moves": [],
            "metadata": {},
            "data_urls": [],
            "sgf": None,
        }

        # ===== 策略1: 从 HTML/JS 中提取棋谱数据 =====

        # 查找嵌入的 SGF
        sgf_match = re.search(r'\(;GM\[1\].*?\)', html, re.DOTALL)
        if sgf_match:
            result["sgf"] = sgf_match.group()
            print(f"  ✓ 发现嵌入的 SGF 数据!")

        # 查找 JavaScript 变量中的走子数据
        # 常见模式: var moves = [...] 或 var kifu = "..." 等
        for pattern in [
            r'var\s+(?:moves|kifu|gamedata|gibo)\s*=\s*"([^"]+)"',
            r'var\s+(?:moves|kifu|gamedata|gibo)\s*=\s*\'([^\']+)\'',
            r'var\s+(?:moves|kifu|gamedata|gibo)\s*=\s*(\[[^\]]+\])',
            r'var\s+(?:moves|kifu|gamedata|gibo)\s*=\s*(\{[^}]+\})',
            r"'sgf'\s*:\s*'([^']+)'",
            r'"sgf"\s*:\s*"([^"]+)"',
        ]:
            m = re.search(pattern, html)
            if m:
                print(f"  ✓ 发现 JS 变量中的棋谱数据!")
                result["js_data"] = m.group(1)

        # 查找 AJAX 数据加载 URL
        for pattern in [
            r'(?:url|src|href)\s*[=:]\s*["\']([^"\']*(?:kifu|gibo|data|sgf|ngf)[^"\']*)["\']',
            r'(?:fetch|ajax|get|load)\s*\(\s*["\']([^"\']+)["\']',
            r'XMLHttpRequest.*?open\s*\(\s*["\'](?:GET|POST)["\']\s*,\s*["\']([^"\']+)["\']',
        ]:
            for m in re.finditer(pattern, html, re.IGNORECASE):
                data_url = m.group(1)
                if not data_url.startswith("http"):
                    data_url = BASE_URL + ("/" if not data_url.startswith("/") else "") + data_url
                result["data_urls"].append(data_url)
                print(f"  ✓ 发现数据加载URL: {data_url}")

        # 查找对局者信息
        for pattern in [
            r'(?:黒|黑|Black|PB)[^a-zA-Z\u4e00-\u9fff]*([a-zA-Z\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+)',
            r'(?:白|White|PW)[^a-zA-Z\u4e00-\u9fff]*([a-zA-Z\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+)',
        ]:
            m = re.search(pattern, html)
            if m:
                result["metadata"]["player"] = m.group(1)

        # ===== 策略2: 尝试获取 AJAX 数据 URL =====

        for data_url in result["data_urls"]:
            print(f"  尝试获取: {data_url}")
            try:
                data_resp = self.session.get(data_url, timeout=10)
                data_content = data_resp.text.strip()

                if data_content.startswith("(;"):
                    result["sgf"] = data_content
                    print(f"  ✓ 获得 SGF 数据! ({len(data_content)} 字节)")
                    break
                elif data_content.startswith("{"):
                    try:
                        json_data = json.loads(data_content)
                        result["json_data"] = json_data
                        print(f"  ✓ 获得 JSON 数据!")
                        # 尝试从JSON中提取SGF
                        for key in ["sgf", "kifu", "gibo", "data"]:
                            if key in json_data:
                                val = json_data[key]
                                if isinstance(val, str) and val.startswith("(;"):
                                    result["sgf"] = val
                                    break
                    except json.JSONDecodeError:
                        pass
                else:
                    print(f"  ? 返回了 {len(data_content)} 字节的未知格式数据")
                    result["raw_data"] = data_content
            except Exception as e:
                print(f"  ✗ 获取失败: {e}")

        return result

    def watch_live(self, sno, interval=15, output_dir="./live_sgf"):
        """
        持续监控直播棋局，实时获取每一手落子。
        """
        print(f"\n{'='*60}")
        print(f"开始监控幽玄の間直播")
        print(f"棋局编号 (sno): {sno}")
        print(f"刷新间隔: {interval}秒")
        print(f"输出目录: {output_dir}")
        print(f"按 Ctrl+C 停止")
        print(f"{'='*60}\n")

        os.makedirs(output_dir, exist_ok=True)
        last_move_count = 0
        last_content_hash = None
        consecutive_errors = 0

        try:
            while True:
                result = self.fetch_live_viewer(sno)

                if result is None:
                    consecutive_errors += 1
                    if consecutive_errors > 5:
                        print("\n连续5次获取失败，可能需要重新登录。")
                        break
                    time.sleep(interval)
                    continue

                consecutive_errors = 0

                if result.get("sgf"):
                    sgf = result["sgf"]
                    content_hash = hash(sgf)

                    if content_hash != last_content_hash:
                        last_content_hash = content_hash
                        moves = re.findall(r';([BW])\[([a-s]{2})\]', sgf)
                        move_count = len(moves)

                        if move_count > last_move_count:
                            ts = datetime.now().strftime('%H:%M:%S')
                            new_count = move_count - last_move_count
                            print(f"\n[{ts}] +{new_count} 手 (共 {move_count} 手)")

                            # 显示新走子
                            for i in range(last_move_count, move_count):
                                color, pos = moves[i]
                                color_name = "黑" if color == "B" else "白"
                                col = ord(pos[0]) - ord('a')
                                row = ord(pos[1]) - ord('a')
                                col_letter = chr(ord('A') + col + (1 if col >= 8 else 0))
                                row_num = 19 - row
                                print(f"  第{i+1}手: {color_name} {col_letter}{row_num}")

                            last_move_count = move_count

                            # 保存
                            fname = f"live_{move_count:03d}.sgf"
                            fpath = os.path.join(output_dir, fname)
                            with open(fpath, "w", encoding="utf-8") as f:
                                f.write(sgf)
                            with open(os.path.join(output_dir, "latest.sgf"), "w", encoding="utf-8") as f:
                                f.write(sgf)
                            print(f"  已保存: {fname}")
                        else:
                            print(".", end="", flush=True)
                    else:
                        print(".", end="", flush=True)
                else:
                    # 没有找到 SGF，保存原始HTML供分析
                    ts = datetime.now().strftime('%H%M%S')
                    debug_path = os.path.join(output_dir, f"debug_{ts}.html")
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(result.get("html", ""))
                    print(f"\n[提示] 未找到SGF数据，已保存原始HTML到 {debug_path}")
                    print("  请用浏览器开发者工具检查实际的数据加载方式。")
                    if result.get("data_urls"):
                        print(f"  发现的数据URL: {result['data_urls']}")

                time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n\n监控已停止。共获取 {last_move_count} 手棋。")
            print(f"棋谱保存在: {output_dir}/")


# ============================================================================
# 浏览器抓包指南
# ============================================================================

def print_browser_guide():
    """打印使用浏览器开发者工具获取数据的详细指南"""
    guide = """
╔══════════════════════════════════════════════════════════╗
║       浏览器抓包获取幽玄の間直播棋谱 - 详细指南          ║
╚══════════════════════════════════════════════════════════╝

这是最可靠的方法。通过浏览器开发者工具，你可以精确地
看到幽玄の間加载棋谱数据的请求，然后用程序复现。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【第一步】登录并打开直播页面

  1. 用浏览器打开 https://u-gen.nihonkiin.or.jp/
  2. 登录你的账号（免费账号即可观看大赛直播）
  3. 进入 "ライブ中継"（直播中继）页面
  4. 点击你要观看的比赛

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【第二步】打开开发者工具，观察网络请求

  1. 按 F12 打开开发者工具
  2. 切换到 "Network"（网络）标签
  3. 在 Filter 中输入以下关键词逐一尝试:
     - kifu
     - gibo
     - sgf
     - ngf
     - data
     - move
     - live

  4. 观察哪些请求返回了棋谱数据
  5. 特别注意:
     - XHR/Fetch 类型的请求（这些通常是AJAX数据请求）
     - 定时刷新的请求（直播中会定期拉取新数据）
     - 返回内容包含坐标或走子信息的请求

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【第三步】提取关键信息

  找到棋谱数据请求后，记录以下信息:

  A) 请求URL (完整URL，包括参数)
     例: https://u-gen.nihonkiin.or.jp/some/api/kifu.asp?id=123

  B) Cookie (在 Request Headers 中)
     右键请求 → Copy → Copy as cURL
     或者在 Application 标签 → Cookies 中查看

  C) 响应数据格式 (在 Response 标签中查看)
     是 SGF? JSON? NGF? 还是其他格式?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【第四步】提取 Cookie

  方法A - 从开发者工具:
    1. F12 → Application → Cookies → u-gen.nihonkiin.or.jp
    2. 复制所有 cookie 的 name=value 对
    3. 用分号连接: "cookie1=val1; cookie2=val2"

  方法B - 从 Console:
    1. F12 → Console
    2. 输入: document.cookie
    3. 复制输出的字符串

  方法C - 从 cURL:
    1. Network 标签中右键任意请求
    2. Copy → Copy as cURL
    3. 从 cURL 命令中找到 -H 'Cookie: ...' 部分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【第五步】使用本工具

  将cookie保存到文件:
    echo "你的cookie字符串" > yugen_cookies.txt

  列出直播:
    python yugen_live_fetcher.py --cookie-file yugen_cookies.txt --list

  监控直播:
    python yugen_live_fetcher.py --cookie-file yugen_cookies.txt --watch 19

  或直接传入cookie字符串:
    python yugen_live_fetcher.py --cookie "ASPSESSIONID=xxx; ..." --list

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【进阶】如果发现了具体的数据API

  一旦你通过抓包发现了具体的数据请求URL和格式，
  可以将信息告诉我，我可以帮你写一个更精确的获取脚本。

  关键信息:
  1. 数据请求的完整URL
  2. 请求方法 (GET/POST)
  3. 请求参数
  4. 响应数据格式 (截一段样本)
  5. Cookie中哪些字段是必须的

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【关于直播数据的自动刷新】

  直播页面通常通过以下方式获取新走子:
  1. 定时轮询 (setInterval + AJAX) — 最常见
  2. 长轮询 (long polling)
  3. WebSocket — 较新的方式
  4. Server-Sent Events (SSE)

  在 Network 标签中观察一段时间，当对局者落子后，
  看看浏览器发出了什么新请求，就能确定刷新机制。

  提示: 在 Network 标签中勾选 "Preserve log" 可以
  保留所有请求历史，方便分析。
"""
    print(guide)


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="幽玄の間 (日本棋院) 直播棋谱获取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查看浏览器抓包指南
  python yugen_live_fetcher.py --guide

  # 用cookie列出直播 (cookie从浏览器开发者工具获取)
  python yugen_live_fetcher.py --cookie "ASP.NET_SessionId=xxx" --list

  # 用cookie文件
  python yugen_live_fetcher.py --cookie-file cookies.txt --list

  # 用账号密码登录
  python yugen_live_fetcher.py --user myname --pass mypass --list

  # 监控直播
  python yugen_live_fetcher.py --cookie-file cookies.txt --watch 19

  # 获取中继日程
  python yugen_live_fetcher.py --cookie-file cookies.txt --schedule
        """
    )

    auth_group = parser.add_argument_group("认证方式 (三选一)")
    auth_group.add_argument("--cookie", metavar="STRING",
                            help="Cookie字符串 (从浏览器复制)")
    auth_group.add_argument("--cookie-file", metavar="FILE",
                            help="包含cookie字符串的文件")
    auth_group.add_argument("--user", metavar="USERNAME",
                            help="幽玄の間用户名")

    parser.add_argument("--pass", dest="password", metavar="PASSWORD",
                        help="幽玄の間密码 (与 --user 配合使用)")

    action_group = parser.add_argument_group("操作")
    action_group.add_argument("--list", action="store_true",
                              help="列出当前直播和棋谱")
    action_group.add_argument("--schedule", action="store_true",
                              help="查看中继日程")
    action_group.add_argument("--watch", metavar="SNO", type=int,
                              help="监控指定编号的直播棋局")
    action_group.add_argument("--fetch", metavar="SNO", type=int,
                              help="获取指定编号的棋局数据 (单次)")
    action_group.add_argument("--guide", action="store_true",
                              help="显示浏览器抓包详细指南")

    parser.add_argument("--interval", type=int, default=15,
                        help="监控刷新间隔(秒), 默认15秒")
    parser.add_argument("--output", default="./live_sgf",
                        help="输出目录, 默认 ./live_sgf")

    args = parser.parse_args()

    # 显示指南
    if args.guide:
        print_browser_guide()
        return

    # 创建客户端
    client = YugenClient(
        cookie_string=args.cookie,
        cookie_file=args.cookie_file
    )

    # 登录
    if args.user:
        if not args.password:
            import getpass
            args.password = getpass.getpass("密码: ")
        success = client.login(args.user, args.password)
        if not success:
            print("登录失败，退出。")
            sys.exit(1)
        # 保存cookie供下次使用
        client.save_cookies("yugen_cookies.txt")

    # 执行操作
    if args.list:
        print("\n" + "="*60)
        print("幽玄の間 直播与棋谱列表")
        print("="*60)

        # 直播列表
        live_games = client.get_live_list()
        if live_games:
            print(f"\n【正在直播】({len(live_games)} 局)")
            for i, g in enumerate(live_games, 1):
                sno = g.get('sno', g.get('no', '?'))
                print(f"  {i}. [{sno}] {g.get('title', '未知')}")
                print(f"     URL: {g.get('url', '')}")
        else:
            print("\n【正在直播】无 (或需要登录)")

        # 棋谱列表
        kifu_games = client.get_kifu_list()
        if kifu_games:
            print(f"\n【历史棋谱】(最近 {min(len(kifu_games), 20)} 局)")
            for i, g in enumerate(kifu_games[:20], 1):
                sno = g.get('sno', g.get('no', '?'))
                print(f"  {i}. [{sno}] {g.get('title', '未知')}")
        else:
            print("\n【历史棋谱】无 (或需要登录)")

    elif args.schedule:
        games = client.get_schedule()
        if games:
            print(f"\n找到 {len(games)} 个日程:")
            for g in games:
                print(f"  {g.get('title', '未知')}")
        else:
            print("未获取到日程信息。")

    elif args.fetch is not None:
        result = client.fetch_live_viewer(args.fetch)
        if result:
            if result.get("sgf"):
                print(f"\n获得SGF棋谱:")
                print(result["sgf"][:500])
                fname = f"game_{args.fetch}.sgf"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(result["sgf"])
                print(f"\n已保存: {fname}")
            else:
                print("\n未直接找到SGF数据。")
                if result.get("data_urls"):
                    print(f"发现数据URL: {result['data_urls']}")
                if result.get("js_data"):
                    print(f"发现JS数据: {result['js_data'][:200]}")
                # 保存HTML供分析
                debug_file = f"debug_sno{args.fetch}.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(result.get("html", ""))
                print(f"已保存原始HTML到 {debug_file}，请手动分析。")
        else:
            print("获取失败。")

    elif args.watch is not None:
        if not (args.cookie or args.cookie_file or args.user):
            print("监控需要认证信息。请使用 --cookie, --cookie-file 或 --user 参数。")
            print("运行 --guide 查看如何获取cookie。")
            sys.exit(1)
        client.watch_live(args.watch, interval=args.interval, output_dir=args.output)

    else:
        parser.print_help()
        print("\n" + "="*60)
        print("推荐流程:")
        print("="*60)
        print("1. 先运行 --guide 查看浏览器抓包指南")
        print("2. 在浏览器登录幽玄の間，提取cookie")
        print("3. 运行 --list 查看直播列表")
        print("4. 运行 --watch SNO 监控直播")


if __name__ == "__main__":
    main()
