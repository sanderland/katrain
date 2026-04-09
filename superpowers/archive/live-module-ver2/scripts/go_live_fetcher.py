#!/usr/bin/env python3
"""
围棋比赛实时棋谱获取工具
Go Game Live SGF Fetcher

支持从多个公开源头获取职业围棋比赛的实时棋谱数据:
  1. 幽玄の間 (日本棋院) - 日本职业比赛的原始中继源
  2. 新浪围棋 (sinago.com) - 国内最早的棋谱中继平台
  3. 野狐围棋 (foxwq.com) - 腾讯旗下围棋平台
  4. 19x19.com (星阵围棋) - 作为备用/对照源

数据链说明:
  比赛现场(电子棋盘/手动录入)
    → 主办方中继服务器(如幽玄の間、韩国棋院等)
    → 各第三方平台(星阵、野狐、弈客等) 叠加AI分析

用法:
  python go_live_fetcher.py --help
  python go_live_fetcher.py --probe URL          # 探测URL返回的数据格式
  python go_live_fetcher.py --watch URL           # 持续监控某个直播URL
  python go_live_fetcher.py --sina                # 列出新浪当前直播棋局
  python go_live_fetcher.py --sina-watch ID       # 监控新浪直播棋局
"""

import argparse
import json
import re
import sys
import time
import os
from datetime import datetime
from urllib.parse import urlparse, urljoin

try:
    import requests
except ImportError:
    print("需要 requests 库，正在安装...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


# ============================================================================
# SGF 工具函数
# ============================================================================

def coord_to_sgf(x, y, board_size=19):
    """将数字坐标 (0-based) 转换为 SGF 坐标 (如 'pd')"""
    return chr(ord('a') + x) + chr(ord('a') + y)


def sgf_to_coord(sgf_pos):
    """将 SGF 坐标 (如 'pd') 转换为数字坐标"""
    if len(sgf_pos) < 2:
        return None
    return (ord(sgf_pos[0]) - ord('a'), ord(sgf_pos[1]) - ord('a'))


def moves_to_sgf(moves, black_player="Black", white_player="White",
                  event="", date="", result="", komi="6.5", board_size=19):
    """
    将走子列表转换为 SGF 格式字符串。
    moves: list of (color, x, y) 或 (color, sgf_coord_str)
           color: 'B' or 'W'
    """
    sgf = f"(;GM[1]FF[4]SZ[{board_size}]"
    sgf += f"PB[{black_player}]PW[{white_player}]"
    if komi:
        sgf += f"KM[{komi}]"
    if event:
        sgf += f"EV[{event}]"
    if date:
        sgf += f"DT[{date}]"
    if result:
        sgf += f"RE[{result}]"
    sgf += "\n"

    for i, move in enumerate(moves):
        if len(move) == 3:
            color, x, y = move
            pos = coord_to_sgf(x, y, board_size)
        elif len(move) == 2:
            color, pos = move
        else:
            continue
        sgf += f";{color}[{pos}]"
        if (i + 1) % 10 == 0:
            sgf += "\n"

    sgf += ")\n"
    return sgf


# ============================================================================
# 数据源 1: 幽玄の間 (日本棋院) — 日本比赛的原始源头
# ============================================================================

class YugenSource:
    """
    幽玄の間 (u-gen.nihonkiin.or.jp)
    日本棋院官方中继平台，是扇兴杯等日本主办比赛的原始数据源。

    数据格式: NGF (Nihon-Kiin Game Format)
    访问方式:
      - 网页版: u-gen.nihonkiin.or.jp/live/live_list.asp (需免费注册)
      - 专用客户端: Java 桌面程序
      - 手机APP: iOS/Android

    注意: 幽玄の間没有公开的 REST API，需要通过网页抓取或客户端协议。
    大型比赛(如扇兴杯)通常对免费会员开放观战。
    """

    BASE_URL = "https://u-gen.nihonkiin.or.jp"
    LIVE_LIST = f"{BASE_URL}/live/live_list.asp"
    KIFU_LIST = f"{BASE_URL}/live/live_kifu_list.asp"
    SCHEDULE  = f"{BASE_URL}/live/schedule_list.asp"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ja,zh-CN;q=0.9,zh;q=0.8,en;q=0.7",
        })

    def get_live_list(self):
        """获取当前正在直播的棋局列表"""
        try:
            resp = self.session.get(self.LIVE_LIST, timeout=15)
            resp.encoding = "shift_jis"
            return self._parse_live_list(resp.text)
        except Exception as e:
            print(f"[幽玄の間] 获取直播列表失败: {e}")
            return []

    def get_schedule(self):
        """获取中继日程"""
        try:
            resp = self.session.get(self.SCHEDULE, timeout=15)
            resp.encoding = "shift_jis"
            return resp.text
        except Exception as e:
            print(f"[幽玄の間] 获取日程失败: {e}")
            return ""

    def _parse_live_list(self, html):
        """从直播列表页面解析出棋局信息"""
        games = []
        # 尝试匹配直播链接和棋局信息
        # 幽玄の間页面结构: 包含棋局标题、对局者、链接等
        pattern = r'live_viewer\.asp\?.*?id=(\d+)'
        matches = re.findall(pattern, html)
        for game_id in matches:
            games.append({"id": game_id, "source": "yugen"})

        # 也尝试提取棋局名称
        title_pattern = r'<td[^>]*>(.*?)</td>'
        titles = re.findall(title_pattern, html)

        return games

    @staticmethod
    def ngf_to_sgf(ngf_content):
        """将 NGF 格式转换为 SGF 格式"""
        lines = ngf_content.strip().split('\n')
        moves = []
        black_player = ""
        white_player = ""
        event = ""
        result = ""

        for line in lines:
            line = line.strip()
            if line.startswith("PM"):
                # PM行: 对局者信息
                # 格式因版本而异
                pass
            elif line.startswith("GN"):
                event = line[2:].strip()
            elif line.startswith("PB"):
                black_player = line[2:].strip()
            elif line.startswith("PW"):
                white_player = line[2:].strip()
            elif line.startswith("RE"):
                result = line[2:].strip()
            elif re.match(r'\d+\s+[BW]\s+\w\d+', line):
                # 走子行: "1 B Q16" 或类似格式
                parts = line.split()
                if len(parts) >= 3:
                    color = parts[1]
                    pos_str = parts[2]
                    # NGF坐标转换
                    try:
                        col = ord(pos_str[0].upper()) - ord('A')
                        if col > 7:  # NGF 跳过 I
                            col -= 1
                        row = 19 - int(pos_str[1:])
                        moves.append((color, col, row))
                    except (ValueError, IndexError):
                        pass

        return moves_to_sgf(moves, black_player, white_player,
                            event=event, result=result)


# ============================================================================
# 数据源 2: 新浪围棋 — 国内传统中继平台
# ============================================================================

class SinaGoSource:
    """
    新浪围棋 (sinago.com / weiqi.sina.com.cn)
    国内最老牌的围棋直播中继平台之一。

    数据格式: SGF (直接提供!)
    棋谱URL模式: http://sinago.com/cgibo/YYYYMM/filename.sgf
    直播页面: http://sinago.com/gibo/giboviewer/giboprint.asp?gibo=<sgf_url>

    新浪围棋的棋谱是公开可访问的SGF文件，非常适合程序化获取。
    """

    BASE_URL = "http://sinago.com"
    LIVE_PAGE = f"{BASE_URL}/qipu/new_gibo.asp"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "http://sinago.com/",
        })

    def get_latest_games(self):
        """获取新浪最新棋谱列表"""
        try:
            resp = self.session.get(self.LIVE_PAGE, timeout=15)
            resp.encoding = "gb2312"
            return self._parse_game_list(resp.text)
        except Exception as e:
            print(f"[新浪围棋] 获取棋谱列表失败: {e}")
            return []

    def _parse_game_list(self, html):
        """解析新浪棋谱列表页面"""
        games = []
        # 匹配 SGF 文件链接
        pattern = r'(cgibo/\d+/[^"\']+\.sgf)'
        matches = re.findall(pattern, html)
        for sgf_path in matches:
            full_url = f"{self.BASE_URL}/{sgf_path}"
            games.append({
                "sgf_url": full_url,
                "source": "sina",
                "filename": sgf_path.split('/')[-1]
            })
        return games

    def fetch_sgf(self, sgf_url):
        """直接下载 SGF 棋谱文件"""
        try:
            resp = self.session.get(sgf_url, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code == 200 and resp.text.strip().startswith("("):
                return resp.text
            # 尝试其他编码
            resp.encoding = "gb2312"
            if resp.text.strip().startswith("("):
                return resp.text
            return None
        except Exception as e:
            print(f"[新浪围棋] 下载SGF失败 {sgf_url}: {e}")
            return None

    def watch_game(self, sgf_url, interval=10):
        """持续监控一个SGF文件的更新 (适用于直播中的棋谱)"""
        print(f"[新浪围棋] 开始监控: {sgf_url}")
        print(f"[新浪围棋] 刷新间隔: {interval}秒")

        last_move_count = 0
        while True:
            sgf = self.fetch_sgf(sgf_url)
            if sgf:
                # 统计走子数
                move_count = len(re.findall(r';[BW]\[', sgf))
                if move_count > last_move_count:
                    new_moves = move_count - last_move_count
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                          f"新增 {new_moves} 手，共 {move_count} 手")
                    # 提取最新一手
                    all_moves = re.findall(r';([BW])\[([a-s]{2})\]', sgf)
                    if all_moves:
                        last_color, last_pos = all_moves[-1]
                        color_name = "黑" if last_color == "B" else "白"
                        print(f"  最新一手: {color_name} {last_pos}")
                    last_move_count = move_count

                    # 保存最新棋谱
                    save_path = f"live_game_{move_count}.sgf"
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(sgf)
                    print(f"  棋谱已保存: {save_path}")
            else:
                print(".", end="", flush=True)

            time.sleep(interval)


# ============================================================================
# 数据源 3: 野狐围棋 (foxwq.com)
# ============================================================================

class FoxWqSource:
    """
    野狐围棋 (foxwq.com)
    腾讯旗下围棋平台，有大量职业比赛直播。

    野狐围棋使用自有协议进行对局和直播。
    比赛新闻页面: https://www.foxwq.com/news/
    """

    BASE_URL = "https://www.foxwq.com"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def search_news(self, keyword):
        """在野狐围棋新闻中搜索包含关键词的比赛"""
        try:
            # 尝试搜索新闻页面
            resp = self.session.get(f"{self.BASE_URL}/news/", timeout=15)
            resp.encoding = "utf-8"
            # 查找包含关键词的链接
            pattern = rf'<a[^>]*href="([^"]*)"[^>]*>[^<]*{re.escape(keyword)}[^<]*</a>'
            matches = re.findall(pattern, resp.text)
            return matches
        except Exception as e:
            print(f"[野狐围棋] 搜索失败: {e}")
            return []


# ============================================================================
# 数据源 4: 19x19.com (星阵围棋) — 作为参考/对照
# ============================================================================

class GolaxySource:
    """
    星阵围棋 (19x19.com)
    虽然不是原始源头，但其 API 可作为对照和补充。

    API 格式: https://19x19.com/engine/live/data/{game_id}
    返回 JSON 数据，包含棋局信息和走子序列。
    """

    BASE_URL = "https://19x19.com"
    LIVE_API = f"{BASE_URL}/engine/live/data"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://19x19.com/",
        })

    def fetch_game(self, game_id):
        """获取指定 game_id 的比赛数据"""
        url = f"{self.LIVE_API}/{game_id}"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[星阵] HTTP {resp.status_code}: {url}")
                return None
        except json.JSONDecodeError:
            # 可能返回的是 SGF 文本而非 JSON
            if resp.text.strip().startswith("("):
                return {"sgf": resp.text}
            print(f"[星阵] 返回非JSON数据，内容前100字: {resp.text[:100]}")
            return {"raw": resp.text}
        except Exception as e:
            print(f"[星阵] 请求失败: {e}")
            return None

    def parse_response(self, data):
        """
        解析星阵 API 返回的数据并转换为统一格式。
        由于无法在当前环境测试，此函数会自动探测多种可能的格式。
        """
        if data is None:
            return None

        # 情况1: 直接返回 SGF
        if isinstance(data, dict) and "sgf" in data:
            return {"type": "sgf", "content": data["sgf"]}

        # 情况2: 返回原始文本 (可能是 SGF)
        if isinstance(data, dict) and "raw" in data:
            raw = data["raw"]
            if raw.strip().startswith("("):
                return {"type": "sgf", "content": raw}
            return {"type": "unknown", "content": raw}

        # 情况3: JSON 中包含 moves 数组
        if isinstance(data, dict):
            # 探测各种可能的字段名
            for key in ["moves", "move_list", "steps", "kifu", "record"]:
                if key in data:
                    return {"type": "moves", "moves": data[key], "data": data}

            # 探测嵌套结构
            for key in ["game", "data", "result", "info"]:
                if key in data and isinstance(data[key], dict):
                    nested = data[key]
                    for mkey in ["moves", "move_list", "steps", "kifu"]:
                        if mkey in nested:
                            return {"type": "moves", "moves": nested[mkey], "data": data}

            # 如果有 sgf 相关字段
            for key in ["sgf_content", "sgf_text", "kifu_sgf"]:
                if key in data:
                    return {"type": "sgf", "content": data[key]}

        return {"type": "raw_json", "data": data}

    def watch_game(self, game_id, interval=10):
        """持续监控星阵直播数据"""
        print(f"[星阵] 开始监控 game_id={game_id}")
        print(f"[星阵] API: {self.LIVE_API}/{game_id}")
        print(f"[星阵] 刷新间隔: {interval}秒")

        last_move_count = 0
        while True:
            data = self.fetch_game(game_id)
            if data:
                parsed = self.parse_response(data)
                if parsed:
                    if parsed["type"] == "sgf":
                        move_count = len(re.findall(r';[BW]\[', parsed["content"]))
                        if move_count > last_move_count:
                            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                                  f"共 {move_count} 手 (+{move_count - last_move_count})")
                            last_move_count = move_count
                            save_path = f"golaxy_live_{game_id}_{move_count}.sgf"
                            with open(save_path, "w", encoding="utf-8") as f:
                                f.write(parsed["content"])
                            print(f"  已保存: {save_path}")
                    elif parsed["type"] == "moves":
                        move_count = len(parsed["moves"])
                        if move_count > last_move_count:
                            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                                  f"共 {move_count} 手 (+{move_count - last_move_count})")
                            last_move_count = move_count
                    elif parsed["type"] == "raw_json":
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                              f"原始JSON数据 (前200字):")
                        print(json.dumps(parsed["data"], ensure_ascii=False)[:200])
            else:
                print(".", end="", flush=True)

            time.sleep(interval)


# ============================================================================
# 通用 URL 探测器
# ============================================================================

class URLProber:
    """探测任意 URL 返回的围棋数据格式"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        })

    def probe(self, url):
        """探测 URL 返回的数据格式"""
        print(f"\n{'='*60}")
        print(f"探测 URL: {url}")
        print(f"{'='*60}")

        try:
            resp = self.session.get(url, timeout=15)
        except Exception as e:
            print(f"请求失败: {e}")
            return None

        print(f"HTTP 状态码: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('Content-Type', 'unknown')}")
        print(f"响应大小: {len(resp.content)} 字节")

        content = resp.text.strip()

        # 1. 检查是否为 SGF
        if content.startswith("(;"):
            print(f"\n✓ 数据格式: SGF 棋谱")
            move_count = len(re.findall(r';[BW]\[', content))
            print(f"  走子数: {move_count}")
            self._extract_sgf_info(content)
            return {"type": "sgf", "content": content, "url": url}

        # 2. 检查是否为 JSON
        try:
            data = json.loads(content)
            print(f"\n✓ 数据格式: JSON")
            print(f"  顶级键: {list(data.keys()) if isinstance(data, dict) else f'array[{len(data)}]'}")
            if isinstance(data, dict):
                for k, v in data.items():
                    val_repr = repr(v)[:80]
                    print(f"  {k}: {type(v).__name__} = {val_repr}")
            return {"type": "json", "data": data, "url": url}
        except (json.JSONDecodeError, ValueError):
            pass

        # 3. 检查是否为 NGF
        if any(line.startswith(("PM", "GN", "WH")) for line in content.split('\n')[:10]):
            print(f"\n✓ 数据格式: NGF (日本棋院格式)")
            return {"type": "ngf", "content": content, "url": url}

        # 4. 检查是否为 HTML (可能需要进一步解析)
        if "<html" in content.lower() or "<!doctype" in content.lower():
            print(f"\n✓ 数据格式: HTML 网页")
            # 查找嵌入的 SGF
            sgf_match = re.search(r'\(;GM\[1\].*?\)', content, re.DOTALL)
            if sgf_match:
                print(f"  发现嵌入的 SGF 数据!")
                return {"type": "html_with_sgf", "sgf": sgf_match.group(),
                        "html": content, "url": url}
            # 查找 JSON 数据
            json_match = re.search(r'var\s+\w+\s*=\s*(\{.*?\});', content, re.DOTALL)
            if json_match:
                print(f"  发现嵌入的 JSON 数据!")
                try:
                    embedded_json = json.loads(json_match.group(1))
                    return {"type": "html_with_json", "data": embedded_json,
                            "html": content, "url": url}
                except json.JSONDecodeError:
                    pass
            return {"type": "html", "content": content, "url": url}

        # 5. 未知格式
        print(f"\n? 未知格式，前500字符:")
        print(content[:500])
        return {"type": "unknown", "content": content, "url": url}

    def _extract_sgf_info(self, sgf):
        """从 SGF 中提取基本信息"""
        props = {
            "PB": "黑方", "PW": "白方", "EV": "赛事",
            "DT": "日期", "RE": "结果", "KM": "贴目",
        }
        for prop, label in props.items():
            match = re.search(rf'{prop}\[([^\]]*)\]', sgf)
            if match:
                print(f"  {label}: {match.group(1)}")


# ============================================================================
# 通用直播监控器
# ============================================================================

class LiveWatcher:
    """通用的直播棋谱监控器"""

    def __init__(self, url, interval=10, output_dir="."):
        self.url = url
        self.interval = interval
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        })
        self.last_content_hash = None
        self.last_move_count = 0
        self.game_moves = []

    def watch(self):
        """开始监控"""
        print(f"\n{'='*60}")
        print(f"开始监控直播")
        print(f"URL: {self.url}")
        print(f"刷新间隔: {self.interval}秒")
        print(f"输出目录: {self.output_dir}")
        print(f"按 Ctrl+C 停止")
        print(f"{'='*60}\n")

        os.makedirs(self.output_dir, exist_ok=True)

        # 先探测一次格式
        prober = URLProber()
        result = prober.probe(self.url)
        if result is None:
            print("无法访问URL，请检查网络连接。")
            return

        data_type = result["type"]
        print(f"\n检测到数据格式: {data_type}")
        print(f"开始持续监控...\n")

        try:
            while True:
                self._poll(data_type)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(f"\n\n监控已停止。")
            self._save_final()

    def _poll(self, data_type):
        """一次轮询"""
        try:
            resp = self.session.get(self.url, timeout=15)
            content = resp.text.strip()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 请求失败: {e}")
            return

        # 检查内容是否有变化
        content_hash = hash(content)
        if content_hash == self.last_content_hash:
            print(".", end="", flush=True)
            return
        self.last_content_hash = content_hash

        # 根据数据类型处理
        if data_type == "sgf":
            self._handle_sgf(content)
        elif data_type == "json":
            self._handle_json(content)
        elif data_type == "html_with_sgf":
            sgf_match = re.search(r'\(;GM\[1\].*?\)', content, re.DOTALL)
            if sgf_match:
                self._handle_sgf(sgf_match.group())
        else:
            # 尝试自动检测
            if content.startswith("(;"):
                self._handle_sgf(content)
            else:
                try:
                    data = json.loads(content)
                    self._handle_json(json.dumps(data))
                except (json.JSONDecodeError, ValueError):
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 数据已更新 (未知格式)")

    def _handle_sgf(self, sgf_content):
        """处理 SGF 格式的数据"""
        moves = re.findall(r';([BW])\[([a-s]{2})\]', sgf_content)
        move_count = len(moves)

        if move_count > self.last_move_count:
            new_count = move_count - self.last_move_count
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{timestamp}] +{new_count} 手 (共 {move_count} 手)")

            # 显示新增的走子
            for i in range(self.last_move_count, move_count):
                color, pos = moves[i]
                color_name = "黑" if color == "B" else "白"
                move_num = i + 1
                # 转换为人类可读坐标
                col = ord(pos[0]) - ord('a')
                row = ord(pos[1]) - ord('a')
                col_letter = chr(ord('A') + col + (1 if col >= 8 else 0))  # 跳过 I
                row_num = 19 - row
                print(f"  第{move_num}手: {color_name} {col_letter}{row_num} ({pos})")

            self.last_move_count = move_count

            # 保存棋谱
            filename = f"live_{move_count:03d}.sgf"
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(sgf_content)

            # 同时保存一个 latest.sgf
            latest_path = os.path.join(self.output_dir, "latest.sgf")
            with open(latest_path, "w", encoding="utf-8") as f:
                f.write(sgf_content)
            print(f"  已保存: {filename}")

    def _handle_json(self, json_content):
        """处理 JSON 格式的数据"""
        try:
            data = json.loads(json_content) if isinstance(json_content, str) else json_content
        except (json.JSONDecodeError, ValueError):
            return

        timestamp = datetime.now().strftime('%H:%M:%S')

        # 尝试从 JSON 中提取走子信息
        moves = None
        sgf = None

        if isinstance(data, dict):
            # 查找 SGF 字段
            for key in ["sgf", "sgf_content", "kifu_sgf", "sgf_text"]:
                if key in data and isinstance(data[key], str):
                    sgf = data[key]
                    break

            # 查找走子列表
            if sgf is None:
                for key in ["moves", "move_list", "steps", "kifu", "record"]:
                    if key in data:
                        moves = data[key]
                        break

                # 在嵌套结构中查找
                if moves is None:
                    for key in ["game", "data", "result", "info"]:
                        if key in data and isinstance(data[key], dict):
                            for mkey in ["moves", "move_list", "steps"]:
                                if mkey in data[key]:
                                    moves = data[key][mkey]
                                    break

        if sgf:
            self._handle_sgf(sgf)
        elif moves:
            move_count = len(moves)
            if move_count > self.last_move_count:
                print(f"\n[{timestamp}] +{move_count - self.last_move_count} 手 (共 {move_count} 手)")
                print(f"  最新走子数据: {moves[-1]}")
                self.last_move_count = move_count

                # 保存原始 JSON
                filename = f"live_{move_count:03d}.json"
                filepath = os.path.join(self.output_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  已保存: {filename}")
        else:
            print(f"\n[{timestamp}] JSON 数据已更新")
            print(f"  顶级键: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
            # 保存供分析
            filepath = os.path.join(self.output_dir, "latest_response.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_final(self):
        """保存最终状态"""
        print(f"共监控到 {self.last_move_count} 手棋")
        if self.last_move_count > 0:
            print(f"棋谱文件保存在: {self.output_dir}/")


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="围棋比赛实时棋谱获取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
数据源说明:
  职业围棋比赛的直播数据链:
    比赛现场 (电子棋盘/手动录入)
      → 主办方中继服务器
        (日本: 幽玄の間, 韩国: Tygem/WBaduk, 中国: 中国棋院)
      → 第三方平台 (星阵/野狐/弈客/新浪等)

  对于扇兴杯(SENKO Cup)等日本棋院主办的比赛:
    原始源头 = 幽玄の間 (u-gen.nihonkiin.or.jp)

使用示例:
  # 探测某个URL的数据格式
  python go_live_fetcher.py --probe https://19x19.com/engine/live/data/183695

  # 持续监控星阵直播
  python go_live_fetcher.py --watch https://19x19.com/engine/live/data/183695

  # 列出新浪最新棋谱
  python go_live_fetcher.py --sina

  # 监控新浪某个SGF的更新
  python go_live_fetcher.py --sina-watch http://sinago.com/cgibo/202603/example.sgf
        """
    )

    parser.add_argument("--probe", metavar="URL",
                        help="探测指定URL返回的数据格式")
    parser.add_argument("--watch", metavar="URL",
                        help="持续监控指定URL的直播数据")
    parser.add_argument("--interval", type=int, default=10,
                        help="轮询间隔(秒), 默认10秒")
    parser.add_argument("--output", default="./live_sgf",
                        help="输出目录, 默认 ./live_sgf")
    parser.add_argument("--sina", action="store_true",
                        help="列出新浪围棋最新棋谱")
    parser.add_argument("--sina-watch", metavar="SGF_URL",
                        help="监控新浪围棋某个SGF棋谱的更新")
    parser.add_argument("--yugen", action="store_true",
                        help="查看幽玄の間直播列表")
    parser.add_argument("--golaxy", metavar="GAME_ID",
                        help="获取星阵围棋指定比赛数据")

    args = parser.parse_args()

    if args.probe:
        prober = URLProber()
        result = prober.probe(args.probe)
        if result:
            print(f"\n{'='*60}")
            print(f"探测结果摘要:")
            print(f"  格式: {result['type']}")
            print(f"  URL:  {result.get('url', args.probe)}")
            if result['type'] == 'json' and 'data' in result:
                # 保存完整响应以便分析
                with open("probe_result.json", "w", encoding="utf-8") as f:
                    json.dump(result['data'], f, ensure_ascii=False, indent=2)
                print(f"  完整JSON已保存至: probe_result.json")
            elif result['type'] == 'sgf':
                with open("probe_result.sgf", "w", encoding="utf-8") as f:
                    f.write(result['content'])
                print(f"  SGF已保存至: probe_result.sgf")

    elif args.watch:
        watcher = LiveWatcher(args.watch, interval=args.interval,
                              output_dir=args.output)
        watcher.watch()

    elif args.sina:
        sina = SinaGoSource()
        games = sina.get_latest_games()
        if games:
            print(f"\n找到 {len(games)} 个棋谱:")
            for i, g in enumerate(games, 1):
                print(f"  {i}. {g['filename']}")
                print(f"     URL: {g['sgf_url']}")
        else:
            print("未找到棋谱或无法访问新浪围棋。")

    elif args.sina_watch:
        sina = SinaGoSource()
        sina.watch_game(args.sina_watch, interval=args.interval)

    elif args.yugen:
        yugen = YugenSource()
        print("\n幽玄の間 相关页面:")
        print(f"  直播列表: {YugenSource.LIVE_LIST}")
        print(f"  中继日程: {YugenSource.SCHEDULE}")
        print(f"  棋谱鉴赏: {YugenSource.KIFU_LIST}")
        print(f"\n尝试获取直播列表...")
        games = yugen.get_live_list()
        if games:
            print(f"找到 {len(games)} 个直播棋局")
            for g in games:
                print(f"  ID: {g['id']}")
        else:
            print("未找到直播棋局或需要登录。")
            print("\n提示: 幽玄の間需要注册账号（免费）才能观看直播中继。")
            print("  注册地址: https://u-gen.nihonkiin.or.jp/")

    elif args.golaxy:
        golaxy = GolaxySource()
        data = golaxy.fetch_game(args.golaxy)
        if data:
            parsed = golaxy.parse_response(data)
            print(f"\n解析结果: {parsed['type']}")
            if parsed['type'] == 'sgf':
                print(parsed['content'][:500])
            elif parsed['type'] == 'raw_json':
                print(json.dumps(parsed['data'], ensure_ascii=False, indent=2)[:500])

    else:
        parser.print_help()
        print("\n" + "="*60)
        print("快速开始:")
        print("="*60)
        print(f"\n1. 探测星阵直播数据格式:")
        print(f"   python {sys.argv[0]} --probe https://19x19.com/engine/live/data/183695")
        print(f"\n2. 持续监控直播 (每10秒刷新):")
        print(f"   python {sys.argv[0]} --watch https://19x19.com/engine/live/data/183695")
        print(f"\n3. 查看新浪最新棋谱:")
        print(f"   python {sys.argv[0]} --sina")
        print(f"\n4. 查看幽玄の間(原始源头):")
        print(f"   python {sys.argv[0]} --yugen")


if __name__ == "__main__":
    main()
