"""isort:skip_file"""
from __future__ import annotations

# first, logging level lower
import os
import sys

os.environ["KCFG_KIVY_LOG_LEVEL"] = os.environ.get("KCFG_KIVY_LOG_LEVEL", "warning")

from kivy.utils import platform as kivy_platform

if kivy_platform == "win":
    from ctypes import windll, c_int64

    if hasattr(windll.user32, "SetProcessDpiAwarenessContext"):
        windll.user32.SetProcessDpiAwarenessContext(c_int64(-4))

import kivy

kivy.require("2.0.0")

# next, icon
from katrain.core.utils import find_package_resource, PATHS
from kivy.config import Config

if kivy_platform == "macosx":
    ICON = find_package_resource("katrain/img/icon.icns")
else:
    ICON = find_package_resource("katrain/img/icon.ico")
Config.set("kivy", "window_icon", ICON)
Config.set("input", "mouse", "mouse,multitouch_on_demand")

# next, certificates on package builds https://github.com/sanderland/katrain/issues/414
if getattr(sys, "frozen", False):
    import ssl

    if ssl.get_default_verify_paths().cafile is None and hasattr(sys, "_MEIPASS"):
        os.environ["SSL_CERT_FILE"] = os.path.join(sys._MEIPASS, "certifi", "cacert.pem")


import re
import signal
import json
import shutil
import stat
import threading
import traceback
from zipfile import ZipFile
from queue import Queue
import urllib3
import webbrowser
import time
import random
import glob

from kivy.base import ExceptionHandler, ExceptionManager
from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.resources import resource_find
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.factory import Factory
from katrain.core.ai import generate_ai_move

from katrain.core.lang import i18n
from katrain.core.constants import (
    OUTPUT_ERROR,
    OUTPUT_KATAGO_STDERR,
    OUTPUT_INFO,
    OUTPUT_DEBUG,
    OUTPUT_EXTRA_DEBUG,
    MODE_ANALYZE,
    HOMEPAGE,
    VERSION,
    STATUS_ERROR,
    STATUS_INFO,
    PLAYING_NORMAL,
    PLAYER_HUMAN,
    SGF_INTERNAL_COMMENTS_MARKER,
    MODE_PLAY,
    DATA_FOLDER,
    AI_DEFAULT,
)
from katrain.gui.popups import (
    ConfigTeacherPopup,
    SaveSGFPopup,
    EngineRecoveryPopup,
)
from katrain.gui.components.popup import PopupManager, PopupSpec
from katrain.gui.sound import play_sound
from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game, IllegalMoveException, KaTrainSGF
from katrain.core.sgf_parser import Move, ParseError
from katrain.gui.popups import ConfigPopup, LoadSGFPopup, NewGamePopup, ConfigAIPopup
from katrain.gui.theme import Theme

# used in kv
from katrain.gui.kivyutils import *
from katrain.gui.widgets import MoveTree, I18NFileBrowser, SelectionSlider, ScoreGraph  # noqa F401
from katrain.gui.widgets.progress_loader import ProgressLoader
from katrain.gui.badukpan import AnalysisControls, BadukPanControls, BadukPanWidget  # noqa F401
from katrain.gui.controlspanel import ControlsPanel, PlayAnalyzeSelect  # noqa F401


class KaTrainGui(Screen, KaTrainBase):
    """Top level class responsible for tying everything together"""

    __no_builder__ = True

    controls = ObjectProperty(None)
    board_gui = ObjectProperty(None)
    board_controls = ObjectProperty(None)
    play_mode = ObjectProperty(None)
    analysis_controls = ObjectProperty(None)
    nav_drawer = ObjectProperty(None)
    nav_drawer_contents = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None

        # Many KV rules use `katrain: app.gui`. During `KaTrainApp.build`, the app assigns
        # `self.gui = KaTrainGui()` only *after* this constructor returns, so without this
        # early binding `app.gui` is still None while KV rules are being applied to child widgets.
        app = App.get_running_app()
        if app and getattr(app, "gui", None) is None:
            app.gui = self

        # Centralized popup lifecycle/caching.
        self.popup_manager = PopupManager()

        self._build_main_layout()

        self.pondering = False
        self.show_move_num = False

        self.message_queue = Queue()

        self.last_key_down = None
        self.last_focus_event = 0

        self.bind(size=lambda *_: self._sync_layout_metrics())

    def _build_main_layout(self):
        root = FloatLayout()

        bg = BGBoxLayout(background_color=Theme.BACKGROUND_COLOR)
        bg.pos = self.pos
        bg.size = self.size
        self.bind(pos=lambda *_: setattr(bg, "pos", self.pos), size=lambda *_: setattr(bg, "size", self.size))

        outer = BoxLayout(orientation="vertical")

        # top toolbar: analysis controls only (full width)
        toolbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
        self.analysis_controls = AnalysisControls()
        toolbar.add_widget(self.analysis_controls)
        outer.add_widget(toolbar)

        # main content: board (left) + sidebar (right)
        content = BoxLayout(orientation="horizontal")

        left = BoxLayout(orientation="vertical")
        self.board_gui = BadukPanWidget()
        self.board_controls = BadukPanControls()
        left.add_widget(self.board_gui)
        left.add_widget(self.board_controls)

        right = BoxLayout(orientation="vertical", size_hint_x=None)
        self.play_mode = PlayAnalyzeSelect()
        self.controls = ControlsPanel()
        right.add_widget(self.play_mode)
        right.add_widget(self.controls)

        content.add_widget(left)
        content.add_widget(right)
        outer.add_widget(content)

        bg.add_widget(outer)
        root.add_widget(bg)

        self.nav_drawer = MyNavigationDrawer(
            size_hint=(None, None),
            swipe_edge_width=0,
            close_on_click=True,
        )
        self.nav_drawer.x = -self.nav_drawer.width
        self.nav_drawer.y = 0
        self.nav_drawer.bind(state=lambda _inst, state: self.update_state() if state == "close" else None)

        self.nav_drawer_contents = Factory.HamburgerMenuContents()
        self.nav_drawer.add_widget(self.nav_drawer_contents)
        root.add_widget(self.nav_drawer)

        self.add_widget(root)
        Clock.schedule_once(lambda _dt: self._sync_layout_metrics(), 0)

    def _sync_layout_metrics(self):
        if not self.analysis_controls or not self.board_controls:
            return

        toolbar_h = dp(44)

        # board navigation bar
        nav_h = max(dp(36), min(dp(44), self.width / 20))
        self.board_controls.height = nav_h
        self.board_controls.size_hint_y = None
        self.board_controls.opacity = 1

        # analysis controls fill the full toolbar width
        self.analysis_controls.size_hint_x = 1
        self.analysis_controls.height = toolbar_h
        self.analysis_controls.size_hint_y = None
        self.analysis_controls.opacity = 1

        if self.play_mode and self.controls:
            # play/analyze at top of sidebar, full width
            self.play_mode.size_hint_x = 1
            self.play_mode.size_hint_y = None
            self.play_mode.height = dp(48)

            right = self.controls.parent
            if right:
                right.width = self.height * Theme.RIGHT_PANEL_ASPECT_RATIO
                right.opacity = 1

        if self.nav_drawer:
            available_h = self.height - toolbar_h
            self.nav_drawer.height = available_h
            self.nav_drawer.width = available_h * 0.45
            if self.nav_drawer.state == "close":
                self.nav_drawer.x = -self.nav_drawer.width

    def log(self, message, level=OUTPUT_INFO):
        super().log(message, level)
        if level == OUTPUT_KATAGO_STDERR and "ERROR" not in self.controls.status.text:
            if "starting" in message.lower():
                self.controls.set_status("KataGo engine starting...", STATUS_INFO)
            elif message.startswith("Tuning"):
                self.controls.set_status(
                    "KataGo is tuning settings for first startup, please wait." + message, STATUS_INFO
                )
                return
            elif "ready" in message.lower():
                self.controls.set_status("KataGo engine ready.", STATUS_INFO)
        if (
            level == OUTPUT_ERROR
            or (level == OUTPUT_KATAGO_STDERR and "error" in message.lower() and "tuning" not in message.lower())
        ) and getattr(self, "controls", None):
            self.controls.set_status(f"ERROR: {message}", STATUS_ERROR)

    def handle_animations(self, *_args):
        if self.pondering:
            self.board_controls.engine_status_pondering += 5
        else:
            self.board_controls.engine_status_pondering = -1

    @property
    def play_analyze_mode(self):
        return self.play_mode.mode

    def toggle_continuous_analysis(self, quiet=False):
        if self.pondering:
            self.controls.set_status("", STATUS_INFO)
        elif not quiet:  # See #549
            Clock.schedule_once(self.analysis_controls.hints.activate, 0)
        self.pondering = not self.pondering
        self.update_state()

    def toggle_move_num(self):
        self.show_move_num = not self.show_move_num
        self.update_state()

    def _ensure_analysis_config_file(self) -> None:
        """Ensure `~/.katrain/analysis_config.cfg` exists and config points to it if missing.

        KaTrain v2 stops bundling `katrain/KataGo`, so the analysis config must be external.
        """

        data_dir = os.path.expanduser(DATA_FOLDER)
        os.makedirs(data_dir, exist_ok=True)

        desired_cfg_setting = os.path.join(DATA_FOLDER, "analysis_config.cfg")
        desired_cfg_path = os.path.expanduser(desired_cfg_setting)
        if not os.path.isfile(desired_cfg_path):
            template = find_package_resource("katrain/resources/analysis_config.cfg")
            shutil.copyfile(template, desired_cfg_path)

        current_cfg_setting = (self.config("engine/config", "") or "").strip()
        current_cfg_path = find_package_resource(current_cfg_setting) if current_cfg_setting else ""
        if not current_cfg_setting or not os.path.isfile(current_cfg_path):
            self._config.setdefault("engine", {})["config"] = desired_cfg_setting
            self.save_config("engine")

    def _resolve_executable_setting(self, exe_setting: str) -> str | None:
        """Resolve a config value to a concrete executable path, if it exists."""

        exe_setting = (exe_setting or "").strip()
        if not exe_setting:
            return None

        if exe_setting.startswith("katrain"):
            resolved = find_package_resource(exe_setting)
            return resolved if os.path.isfile(resolved) else None

        expanded = os.path.expanduser(exe_setting)
        exepath, _ = os.path.split(expanded)
        if exepath:
            resolved = os.path.abspath(expanded)
            return resolved if os.path.isfile(resolved) else None

        # No directory component -> look in PATH.
        resolved = shutil.which(exe_setting)
        return resolved if resolved and os.path.isfile(resolved) else None

    def _resolve_katago_executable(self) -> str | None:
        exe_setting = (self.config("engine/katago", "") or "").strip()
        resolved = self._resolve_executable_setting(exe_setting)
        if resolved:
            return resolved

        # v2 default location for auto-downloaded binaries.
        data_dir = os.path.expanduser(DATA_FOLDER)
        local_name = "katago.exe" if kivy_platform == "win" else "katago"
        local_exe = os.path.join(data_dir, local_name)
        if os.path.isfile(local_exe):
            return local_exe

        # PATH fallback (useful on macOS via homebrew, and for developers).
        if kivy_platform == "win":
            for name in ["katago.exe", "katago"]:
                resolved = shutil.which(name)
                if resolved and os.path.isfile(resolved):
                    return resolved
        else:
            resolved = shutil.which("katago")
            return resolved if resolved and os.path.isfile(resolved) else None

        return None

    def _install_katago_zip(self, zip_path: str, exe_path: str) -> None:
        with ZipFile(zip_path, "r") as zip_obj:
            want = "katago.exe" if kivy_platform == "win" else "katago"
            names = zip_obj.namelist()
            candidates = [n for n in names if os.path.basename(n).lower() == want]
            if not candidates:
                candidates = [n for n in names if os.path.basename(n).lower().startswith("katago")]
            if len(candidates) != 1:
                raise FileNotFoundError(
                    f"Zip file {zip_path} does not contain exactly 1 kata executable (contents: {names})"
                )

            os.makedirs(os.path.dirname(exe_path), exist_ok=True)
            with open(exe_path, "wb") as fout:
                fout.write(zip_obj.read(candidates[0]))

            if kivy_platform != "win":
                os.chmod(exe_path, os.stat(exe_path).st_mode | stat.S_IXUSR | stat.S_IXGRP)

            # Windows builds need adjacent DLLs.
            if kivy_platform == "win":
                out_dir = os.path.dirname(exe_path)
                for name in names:
                    if name.lower().endswith(".dll"):
                        with open(os.path.join(out_dir, os.path.basename(name)), "wb") as fout:
                            fout.write(zip_obj.read(name))

    # URLs for auto-download of missing assets.
    KATAGO_URLS = {
        "win": {
            "OpenCL": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-windows-x64.zip",
            "Eigen AVX2": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigenavx2-windows-x64.zip",
            "Eigen (CPU)": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigen-windows-x64.zip",
        },
        "linux": {
            "OpenCL": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-opencl-linux-x64.zip",
            "Eigen AVX2": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigenavx2-linux-x64.zip",
            "Eigen (CPU)": "https://github.com/lightvector/KataGo/releases/download/v1.16.0/katago-v1.16.0-eigen-linux-x64.zip",
        },
    }
    MAIN_MODEL_URL = "https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"
    MAIN_MODEL_FILENAME = "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"
    HUMAN_MODEL_URL = "https://github.com/lightvector/KataGo/releases/download/v1.15.0/b18c384nbt-humanv0.bin.gz"
    HUMAN_MODEL_FILENAME = "b18c384nbt-humanv0.bin.gz"

    def _resolve_model(self, config_key: str) -> str | None:
        """Return resolved path if the configured model exists, else None."""
        setting = (self.config(config_key, "") or "").strip()
        if not setting:
            return None
        resolved = find_package_resource(setting)
        return resolved if os.path.isfile(resolved) else None

    def _find_model_in_dir(self, models_dir: str, pattern: str) -> str | None:
        """Find first model file matching pattern in models_dir."""
        if not os.path.isdir(models_dir):
            return None
        for f in sorted(os.listdir(models_dir)):
            if f.endswith(".bin.gz") and ".tmp" not in f and pattern in f.lower():
                return f
        return None

    def ensure_engine_ready(self, on_ready) -> None:
        """Startup bootstrap: ensure katago + models exist, download any missing assets."""
        self._ensure_analysis_config_file()

        # Build list of missing assets: (label, url, target_path, config_key, is_zip)
        missing = []
        data_dir = os.path.expanduser(DATA_FOLDER)
        os.makedirs(data_dir, exist_ok=True)
        models_dir = find_package_resource("katrain/models")
        os.makedirs(models_dir, exist_ok=True)

        # 1) KataGo executable
        if not self._resolve_katago_executable():
            if kivy_platform in self.KATAGO_URLS:
                # Pick the first (best) option for this platform
                label, url = next(iter(self.KATAGO_URLS[kivy_platform].items()))
                exe_name = "katago.exe" if kivy_platform == "win" else "katago"
                exe_setting = os.path.join(DATA_FOLDER, exe_name)
                exe_path = os.path.expanduser(exe_setting)
                missing.append(("KataGo engine", url, exe_path, "engine/katago", True, exe_setting))
            elif kivy_platform == "macosx":
                msg = (
                    "KataGo executable not found.\n\n"
                    "On macOS, install via Homebrew (`brew install katago`) or set the path in Settings."
                )
                message_label = Label(
                    text=msg, font_name=i18n.font_name, halign="left", valign="top", text_size=(dp(540), None),
                )
                popup = Popup(
                    title="KataGo setup required", content=message_label,
                    size_hint=(None, None), size=(dp(560), dp(220)), auto_dismiss=False,
                )
                popup.open()
                return

        # 2) Main model
        if not self._resolve_model("engine/model"):
            existing = self._find_model_in_dir(models_dir, self.MAIN_MODEL_FILENAME.split("-")[0])
            if existing:
                self._config.setdefault("engine", {})["model"] = f"katrain/models/{existing}"
                self.save_config("engine")
            else:
                target = os.path.join(models_dir, self.MAIN_MODEL_FILENAME)
                missing.append(("Main model", self.MAIN_MODEL_URL, target, "engine/model", False, f"katrain/models/{self.MAIN_MODEL_FILENAME}"))

        # 3) Human-like model
        if not self._resolve_model("engine/humanlike_model"):
            existing = self._find_model_in_dir(models_dir, "human")
            if existing:
                self._config.setdefault("engine", {})["humanlike_model"] = f"katrain/models/{existing}"
                self.save_config("engine")
            else:
                target = os.path.join(models_dir, self.HUMAN_MODEL_FILENAME)
                missing.append(("Human-like model", self.HUMAN_MODEL_URL, target, "engine/humanlike_model", False, f"katrain/models/{self.HUMAN_MODEL_FILENAME}"))

        if not missing:
            on_ready()
            return

        # Show download popup and process downloads sequentially.
        status_label = Label(
            text=f"Downloading {missing[0][0]}...",
            font_name=i18n.font_name,
            halign="left",
            valign="middle",
            text_size=(dp(536), None),
            size_hint_y=None,
            height=dp(30),
        )
        progress_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        progress_box.bind(minimum_height=progress_box.setter("height"))
        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=[dp(12)] * 4)
        content.add_widget(status_label)
        content.add_widget(progress_box)

        popup = Popup(
            title="Setting up KaTrain",
            content=content,
            size_hint=(None, None),
            size=(dp(560), dp(170)),
            auto_dismiss=False,
        )
        popup.open()

        download_queue = list(missing)

        def _start_next():
            if not download_queue:
                status_label.text = "Setup complete!"
                Clock.schedule_once(lambda _dt: popup.dismiss(), 0.5)
                Clock.schedule_once(lambda _dt: on_ready(), 0.6)
                return

            label, url, target_path, config_key, is_zip, config_value = download_queue[0]
            remaining = len(download_queue)
            status_label.text = f"Downloading {label}... ({remaining} remaining)"
            tmp_path = target_path + ".part"

            # Clear stale partial downloads
            for stale in [tmp_path, target_path + ".tmp.download"]:
                try:
                    if os.path.exists(stale):
                        os.remove(stale)
                except OSError:
                    pass

            # Remove old progress bar widgets
            for child in list(progress_box.children):
                progress_box.remove_widget(child)

            def download_complete(_req):
                try:
                    if is_zip:
                        self._install_katago_zip(tmp_path, target_path)
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                        self._config.setdefault("engine", {})[config_key.split("/")[1]] = config_value
                    else:
                        os.rename(tmp_path, target_path)
                        self._config.setdefault("engine", {})[config_key.split("/")[1]] = config_value
                    self.save_config("engine")
                    self.log(f"Downloaded {label} to {target_path}")
                except Exception as e:
                    self.log(f"Failed to install {label}: {e}", OUTPUT_ERROR)
                    status_label.text = f"Failed: {e}"
                    return

                download_queue.pop(0)
                _start_next()

            def download_error(_req, error):
                self.log(f"Failed to download {label} from {url}: {error}", OUTPUT_ERROR)
                # Skip this item and continue with the rest
                download_queue.pop(0)
                if download_queue:
                    status_label.text = f"Download of {label} failed, continuing..."
                    Clock.schedule_once(lambda _dt: _start_next(), 0.5)
                else:
                    status_label.text = "Some downloads failed. Check Settings."
                    Clock.schedule_once(lambda _dt: popup.dismiss(), 2)
                    Clock.schedule_once(lambda _dt: on_ready(), 2.1)

            ProgressLoader(
                root_instance=progress_box,
                download_url=url,
                path_to_file=tmp_path,
                downloading_text=f"Downloading {label}: " + "{}",
                label_downloading_text="Starting download...",
                download_complete=download_complete,
                download_error=download_error,
                download_redirected=lambda req: self.log(f"Download redirected: {req.resp_headers}", OUTPUT_DEBUG),
            )

        _start_next()

    def start(self):
        if self.engine:
            return
        self.board_gui.trainer_config = self.config("trainer")
        self.engine = KataGoEngine(self, self.config("engine"))
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        sgf_args = [
            f
            for f in sys.argv[1:]
            if os.path.isfile(f) and any(f.lower().endswith(ext) for ext in ["sgf", "ngf", "gib"])
        ]
        if sgf_args:
            self.load_sgf_file(sgf_args[0], fast=True, rewind=True)
        else:
            self._do_new_game()

        Clock.schedule_interval(self.handle_animations, 0.1)
        Window.request_keyboard(None, self, "").bind(on_key_down=self._on_keyboard_down, on_key_up=self._on_keyboard_up)

        def set_focus_event(*args):
            self.last_focus_event = time.time()

        App.get_running_app().root_window.bind(focus=set_focus_event)


    def update_gui(self, cn, redraw_board=False):
        # Handle prisoners and next player display
        prisoners = self.game.prisoner_count
        top, bot = [w.__self__ for w in self.board_controls.circles]  # no weakref
        if self.next_player_info.player == "W":
            top, bot = bot, top
            self.controls.players["W"].active = True
            self.controls.players["B"].active = False
        else:
            self.controls.players["W"].active = False
            self.controls.players["B"].active = True
        self.board_controls.mid_circles_container.clear_widgets()
        self.board_controls.mid_circles_container.add_widget(bot)
        self.board_controls.mid_circles_container.add_widget(top)

        self.controls.players["W"].captures = prisoners["W"]
        self.controls.players["B"].captures = prisoners["B"]

        # update engine status dot
        if not self.engine or not self.engine.katago_process or self.engine.katago_process.poll() is not None:
            self.board_controls.engine_status_col = Theme.ENGINE_DOWN_COLOR
        elif self.engine.is_idle():
            self.board_controls.engine_status_col = Theme.ENGINE_READY_COLOR
        else:
            self.board_controls.engine_status_col = Theme.ENGINE_BUSY_COLOR
        self.board_controls.queries_remaining = self.engine.queries_remaining()

        # redraw board/stones
        if redraw_board:
            self.board_gui.draw_board()
        self.board_gui.redraw_board_contents_trigger()
        self.controls.update_evaluation()
        # update move tree
        self.controls.move_tree.current_node = self.game.current_node

    def update_state(self, redraw_board=False):  # redirect to message queue thread
        self("update_state", redraw_board=redraw_board)

    def _do_update_state(
        self, redraw_board=False
    ):  # is called after every message and on receiving analyses and config changes
        # AI and Trainer/auto-undo handlers
        if not self.game or not self.game.current_node:
            return
        cn = self.game.current_node
        last_player, next_player = self.players_info[cn.player], self.players_info[cn.next_player]
        if self.play_analyze_mode == MODE_PLAY and self.nav_drawer.state != "open" and self.popup_open is None:
            teaching_undo = cn.player and last_player.being_taught and cn.parent
            if (
                teaching_undo
                and cn.analysis_complete
                and cn.parent.analysis_complete
                and not cn.children
                and not self.game.end_result
            ):
                self.game.analyze_undo(cn)  # not via message loop
            if (
                cn.analysis_complete
                and next_player.ai
                and not cn.children
                and not self.game.end_result
                and not (teaching_undo and cn.auto_undo is None)
            ):  # cn mismatch stops this if undo fired. avoid message loop here or fires repeatedly.
                self._do_ai_move(cn)
                Clock.schedule_once(self._play_stone_sound, 0.25)
        if self.engine:
            if self.pondering:
                self.game.analyze_extra("ponder")
            else:
                self.engine.stop_pondering()
        Clock.schedule_once(lambda _dt: self.update_gui(cn, redraw_board=redraw_board), -1)  # trigger?

    def update_player(self, bw, **kwargs):
        super().update_player(bw, **kwargs)
        if self.game:
            sgf_name = self.game.root.get_property("P" + bw)
            self.players_info[bw].name = None if not sgf_name or SGF_INTERNAL_COMMENTS_MARKER in sgf_name else sgf_name
        if self.controls:
            self.controls.update_players()
            self.update_state()
        for player_setup_block in PlayerSetupBlock.INSTANCES:
            player_setup_block.update_player_info(bw, self.players_info[bw])

    def set_note(self, note):
        self.game.current_node.note = note

    # The message loop is here to make sure moves happen in the right order, and slow operations don't hang the GUI
    def _message_loop_thread(self):
        while True:
            game, msg, args, kwargs = self.message_queue.get()
            try:
                self.log(f"Message Loop Received {msg}: {args} for Game {game}", OUTPUT_EXTRA_DEBUG)
                if game != self.game.game_id:
                    self.log(
                        f"Message skipped as it is outdated (current game is {self.game.game_id}", OUTPUT_EXTRA_DEBUG
                    )
                    continue
                msg = msg.replace("-", "_")
                fn = getattr(self, f"_do_{msg}")
                fn(*args, **kwargs)
                if msg != "update_state":
                    self._do_update_state()
            except Exception as exc:
                self.log(f"Exception in processing message {msg} {args}: {exc}", OUTPUT_ERROR)
                traceback.print_exc()

    def __call__(self, message, *args, **kwargs):
        if self.game:
            if message.endswith("popup"):  # gui code needs to run in main kivy thread.
                fn = getattr(self, f"_do_{message.replace('-', '_')}")
                Clock.schedule_once(lambda _dt: fn(*args, **kwargs), -1)
            else:  # game related actions
                self.message_queue.put([self.game.game_id, message, args, kwargs])

    def _do_new_game(self, move_tree=None, analyze_fast=False, sgf_filename=None):
        self.pondering = False
        mode = self.play_analyze_mode
        if (move_tree is not None and mode == MODE_PLAY) or (move_tree is None and mode == MODE_ANALYZE):
            self.play_mode.switch_ui_mode()  # for new game, go to play, for loaded, analyze
        self.board_gui.animating_pv = None
        self.engine.on_new_game()  # clear queries
        self.game = Game(
            self,
            self.engine,
            move_tree=move_tree,
            analyze_fast=analyze_fast or not move_tree,
            sgf_filename=sgf_filename,
        )
        for bw, player_info in self.players_info.items():
            player_info.sgf_rank = self.game.root.get_property(bw + "R")
            player_info.calculated_rank = None
            if sgf_filename is not None:  # load game->no ai player
                player_info.player_type = PLAYER_HUMAN
                player_info.player_subtype = PLAYING_NORMAL
            self.update_player(bw, player_type=player_info.player_type, player_subtype=player_info.player_subtype)
        self.controls.graph.initialize_from_game(self.game.root)
        self.update_state(redraw_board=True)

    def _do_ai_move(self, node=None):
        if node is None or self.game.current_node == node:
            mode = self.next_player_info.strategy
            settings = self.config(f"ai/{mode}")
            if settings is not None:
                generate_ai_move(self.game, mode, settings)
            else:
                self.log(f"AI Mode {mode} not found!", OUTPUT_ERROR)

    def _do_undo(self, n_times=1):
        if n_times == "smart":
            n_times = 1
            if self.play_analyze_mode == MODE_PLAY and self.last_player_info.ai and self.next_player_info.human:
                n_times = 2
        self.board_gui.animating_pv = None
        self.game.undo(n_times)

    def _do_reset_analysis(self):
        self.game.reset_current_analysis()

    def _do_resign(self):
        self.game.current_node.end_state = f"{self.game.current_node.player}+R"

    def _do_redo(self, n_times=1):
        self.board_gui.animating_pv = None
        self.game.redo(n_times)

    def _do_find_mistake(self, fn="redo"):
        self.board_gui.animating_pv = None
        getattr(self.game, fn)(9999, stop_on_mistake=self.config("trainer/eval_thresholds")[-4])

    def _do_switch_branch(self, *args):
        self.board_gui.animating_pv = None
        self.controls.move_tree.switch_branch(*args)

    def _play_stone_sound(self, _dt=None):
        play_sound(random.choice(Theme.STONE_SOUNDS))

    def _do_play(self, coords):
        self.board_gui.animating_pv = None
        try:
            old_prisoner_count = self.game.prisoner_count["W"] + self.game.prisoner_count["B"]
            self.game.play(Move(coords, player=self.next_player_info.player))
            if old_prisoner_count < self.game.prisoner_count["W"] + self.game.prisoner_count["B"]:
                play_sound(Theme.CAPTURING_SOUND)
            elif not self.game.current_node.is_pass:
                self._play_stone_sound()

        except IllegalMoveException as e:
            self.controls.set_status(f"Illegal Move: {str(e)}", STATUS_ERROR)

    def _do_analyze_extra(self, mode, **kwargs):
        self.game.analyze_extra(mode, **kwargs)

    def _do_new_game_popup(self):
        popup = self.popup_manager.show(
            PopupSpec(title_key="New Game title", size=[800, 620], cache_key="new_game"),
            NewGamePopup(self),
        )
        popup.content.update_from_current_game()

    def _do_teacher_popup(self):
        self.popup_manager.show(
            PopupSpec(title_key="teacher settings", size=[800, 850], cache_key="teacher_settings"),
            ConfigTeacherPopup(self),
        )

    def _do_config_popup(self):
        popup = self.popup_manager.show(
            PopupSpec(title_key="general settings title", size=[1200, 950], cache_key="general_settings"),
            ConfigPopup(self),
        )
        # Preserve the existing behavior of showing which config file is active.
        if self.config_file and self.config_file not in popup.title:
            popup.title += ": " + self.config_file

    def _do_ai_popup(self):
        self.popup_manager.show(
            PopupSpec(title_key="ai settings", size=[750, 480], cache_key="ai_settings"),
            ConfigAIPopup(self),
        )

    def _do_engine_recovery_popup(self, error_message, code):
        current_open = self.popup_open
        if current_open and isinstance(current_open.content, EngineRecoveryPopup):
            self.log(f"Not opening engine recovery popup with {error_message} as one is already open", OUTPUT_DEBUG)
            return
        self.popup_manager.show(
            PopupSpec(title_key="engine recovery", size=[600, 380]),
            EngineRecoveryPopup(self, error_message=error_message, code=code),
        )

    def load_sgf_file(self, file, fast=False, rewind=True):
        try:
            file = os.path.abspath(file)
            move_tree = KaTrainSGF.parse_file(file)
        except (ParseError, FileNotFoundError) as e:
            self.log(i18n._("Failed to load SGF").format(error=e), OUTPUT_ERROR)
            return
        self._do_new_game(move_tree=move_tree, analyze_fast=fast, sgf_filename=file)
        if not rewind:
            self.game.redo(999)

    def _do_analyze_sgf_popup(self):
        cache_key = "load_sgf"
        cached = self.popup_manager.get_cached(cache_key)
        if cached:
            popup = cached
            popup.open()
        else:
            popup_contents = LoadSGFPopup(self)
            popup_contents.filesel.path = os.path.abspath(os.path.expanduser(self.config("general/sgf_load", ".")))

            def readfile(*_args):
                filename = popup_contents.filesel.filename
                popup.dismiss()
                path, file = os.path.split(filename)
                if path != self.config("general/sgf_load"):
                    self.log(f"Updating sgf load path default to {path}", OUTPUT_DEBUG)
                    self._config["general"]["sgf_load"] = path
                self.save_config("general")
                fast = bool(self.config("general/load_fast_analysis", False))
                rewind = bool(self.config("general/load_sgf_rewind", True))
                self.load_sgf_file(filename, fast=fast, rewind=rewind)

            popup_contents.filesel.on_success = readfile
            popup_contents.filesel.on_submit = readfile
            popup = self.popup_manager.show(
                PopupSpec(title_key="load sgf title", size=[1200, 800], cache_key=cache_key),
                popup_contents,
            )
        popup.content.filesel.ids.list_view._trigger_update()

    def _do_save_game(self, filename=None):
        filename = filename or self.game.sgf_filename
        if not filename:
            return self("save-game-as-popup")
        try:
            msg = self.game.write_sgf(filename)
            self.log(msg, OUTPUT_INFO)
            self.controls.set_status(msg, STATUS_INFO, check_level=False)
        except Exception as e:
            self.log(f"Failed to save SGF to {filename}: {e}", OUTPUT_ERROR)

    def _do_save_game_as_popup(self):
        popup_contents = SaveSGFPopup(suggested_filename=self.game.generate_filename())

        def readfile(*_args):
            filename = popup_contents.filesel.filename
            if not filename.lower().endswith(".sgf"):
                filename += ".sgf"
            popup.dismiss()
            path, file = os.path.split(filename.strip())
            if not path:
                path = popup_contents.filesel.path  # whatever dir is shown
            if path != self.config("general/sgf_save"):
                self.log(f"Updating sgf save path default to {path}", OUTPUT_DEBUG)
                self._config["general"]["sgf_save"] = path
                self.save_config("general")
            self._do_save_game(os.path.join(path, file))

        popup_contents.filesel.on_success = readfile
        popup_contents.filesel.on_submit = readfile
        popup = self.popup_manager.show(PopupSpec(title_key="save sgf title", size=[1200, 800]), popup_contents)

    def load_sgf_from_clipboard(self):
        clipboard = Clipboard.paste()
        if not clipboard:
            self.controls.set_status("Ctrl-V pressed but clipboard is empty.", STATUS_INFO)
            return

        url_match = re.match(r"(?P<url>https?://[^\s]+)", clipboard)
        if url_match:
            self.log("Recognized url: " + url_match.group(), OUTPUT_INFO)
            http = urllib3.PoolManager()
            response = http.request("GET", url_match.group())
            clipboard = response.data.decode("utf-8")

        try:
            move_tree = KaTrainSGF.parse_sgf(clipboard)
        except Exception as exc:
            self.controls.set_status(
                i18n._("Failed to import from clipboard").format(error=exc, contents=clipboard[:50]), STATUS_INFO
            )
            return
        move_tree.nodes_in_tree[-1].analyze(
            self.engine, analyze_fast=False
        )  # speed up result for looking at end of game
        self._do_new_game(move_tree=move_tree, analyze_fast=True)
        self("redo", 9999)
        self.log("Imported game from clipboard.", OUTPUT_INFO)

    def on_touch_up(self, touch):
        if touch.is_mouse_scrolling:
            touching_board = self.board_gui.collide_point(*touch.pos) or self.board_controls.collide_point(*touch.pos)
            touching_control_nonscroll = self.controls.collide_point(
                *touch.pos
            ) and not self.controls.notes_panel.collide_point(*touch.pos)
            if self.board_gui.animating_pv is not None and touching_board:
                if touch.button == "scrollup":
                    self.board_gui.adjust_animate_pv_index(1)
                elif touch.button == "scrolldown":
                    self.board_gui.adjust_animate_pv_index(-1)
            elif touching_board or touching_control_nonscroll:  # scroll through moves
                if touch.button == "scrollup":
                    self("redo")
                elif touch.button == "scrolldown":
                    self("undo")
        return super().on_touch_up(touch)

    @property
    def shortcuts(self):
        return {
            k: v
            for ks, v in [
                (Theme.KEY_ANALYSIS_CONTROLS_SHOW_CHILDREN, self.analysis_controls.show_children),
                (Theme.KEY_ANALYSIS_CONTROLS_EVAL, self.analysis_controls.eval),
                (Theme.KEY_ANALYSIS_CONTROLS_HINTS, self.analysis_controls.hints),
                (Theme.KEY_ANALYSIS_CONTROLS_OWNERSHIP, self.analysis_controls.ownership),
                (Theme.KEY_ANALYSIS_CONTROLS_POLICY, self.analysis_controls.policy),
                (Theme.KEY_AI_MOVE, ("ai-move",)),
                (Theme.KEY_RESET_ANALYSIS, ("reset-analysis",)),
                (Theme.KEY_PASS, ("play", None)),
                (Theme.KEY_NAV_PREV_BRANCH, ("undo", "branch")),
                (Theme.KEY_NAV_BRANCH_DOWN, ("switch-branch", 1)),
                (Theme.KEY_NAV_BRANCH_UP, ("switch-branch", -1)),
                (Theme.KEY_TEACHER_POPUP, ("teacher-popup",)),
                (Theme.KEY_AI_POPUP, ("ai-popup",)),
                (Theme.KEY_CONFIG_POPUP, ("config-popup",)),
                (Theme.KEY_STOP_ANALYSIS, ("analyze-extra", "stop")),
            ]
            for k in (ks if isinstance(ks, list) else [ks])
        }

    @property
    def popup_open(self) -> Popup:
        app = App.get_running_app()
        if app:
            first_child = app.root_window.children[0]
            return first_child if isinstance(first_child, Popup) else None

    def _on_keyboard_down(self, _keyboard, keycode, _text, modifiers):
        self.last_key_down = keycode
        ctrl_pressed = "ctrl" in modifiers or ("meta" in modifiers and kivy_platform == "macosx")
        shift_pressed = "shift" in modifiers
        if self.controls.note.focus:
            return  # when making notes, don't allow keyboard shortcuts
        popup = self.popup_open
        if popup:
            if keycode[1] in [
                Theme.KEY_TEACHER_POPUP,
                Theme.KEY_AI_POPUP,
                Theme.KEY_CONFIG_POPUP,
            ]:  # switch between popups
                popup.dismiss()

                return
            elif keycode[1] in Theme.KEY_SUBMIT_POPUP:
                fn = getattr(popup.content, "on_submit", None)
                if fn:
                    fn()
                return
            else:
                return

        if keycode[1] == Theme.KEY_TOGGLE_CONTINUOUS_ANALYSIS:
            self.toggle_continuous_analysis(quiet=shift_pressed)
        elif keycode[1] == Theme.KEY_TOGGLE_MOVENUM:
            self.toggle_move_num()
        elif keycode[1] == Theme.KEY_TOGGLE_COORDINATES:
            self.board_gui.toggle_coordinates()
        elif keycode[1] in Theme.KEY_NAV_PREV:
            self("undo", 1 + shift_pressed * 9 + ctrl_pressed * 9999)
        elif keycode[1] in Theme.KEY_NAV_NEXT:
            self("redo", 1 + shift_pressed * 9 + ctrl_pressed * 9999)
        elif keycode[1] == Theme.KEY_NAV_GAME_START:
            self("undo", 9999)
        elif keycode[1] == Theme.KEY_NAV_GAME_END:
            self("redo", 9999)
        elif keycode[1] == Theme.KEY_MOVE_TREE_MAKE_SELECTED_NODE_MAIN_BRANCH:
            self.controls.move_tree.make_selected_node_main_branch()
        elif keycode[1] == Theme.KEY_NAV_MISTAKE and not ctrl_pressed:
            self("find-mistake", "undo" if shift_pressed else "redo")
        elif keycode[1] == Theme.KEY_MOVE_TREE_DELETE_SELECTED_NODE and ctrl_pressed:
            self.controls.move_tree.delete_selected_node()
        elif keycode[1] == Theme.KEY_NEW_GAME and ctrl_pressed:
            self("new-game-popup")
        elif keycode[1] == Theme.KEY_LOAD_GAME and ctrl_pressed:
            self("analyze-sgf-popup")
        elif keycode[1] == Theme.KEY_SAVE_GAME and ctrl_pressed:
            self("save-game")
        elif keycode[1] == Theme.KEY_SAVE_GAME_AS and ctrl_pressed:
            self("save-game-as-popup")
        elif keycode[1] == Theme.KEY_COPY and ctrl_pressed:
            Clipboard.copy(self.game.root.sgf())
            self.controls.set_status(i18n._("Copied SGF to clipboard."), STATUS_INFO)
        elif keycode[1] == Theme.KEY_PASTE and ctrl_pressed:
            self.load_sgf_from_clipboard()
        elif keycode[1] == Theme.KEY_NAV_PREV_BRANCH and shift_pressed:
            self("undo", "main-branch")
        elif keycode[1] == "f10" and self.debug_level >= OUTPUT_EXTRA_DEBUG:
            import yappi

            yappi.set_clock_type("cpu")
            yappi.start()
            self.log("starting profiler", OUTPUT_ERROR)
        elif keycode[1] == "f11" and self.debug_level >= OUTPUT_EXTRA_DEBUG:
            import time
            import yappi

            stats = yappi.get_func_stats()
            filename = f"callgrind.{int(time.time())}.prof"
            stats.save(filename, type="callgrind")
            self.log(f"wrote profiling results to {filename}", OUTPUT_ERROR)
        elif not ctrl_pressed:
            shortcut = self.shortcuts.get(keycode[1])
            if shortcut is not None:
                if isinstance(shortcut, Widget):
                    shortcut.trigger_action(duration=0)
                else:
                    self(*shortcut)

    def _on_keyboard_up(self, _keyboard, keycode):
        if keycode[1] in ["alt", "tab"]:
            Clock.schedule_once(lambda *_args: self._single_key_action(keycode), 0.05)

    def _single_key_action(self, keycode):
        if (
            self.controls.note.focus
            or self.popup_open
            or keycode != self.last_key_down
            or time.time() - self.last_focus_event < 0.2  # this is here to prevent alt-tab from firing alt or tab
        ):
            return
        if keycode[1] == "alt":
            self.nav_drawer.set_state("toggle")
        elif keycode[1] == "tab":
            self.play_mode.switch_ui_mode()


class KaTrainApp(App):
    gui = ObjectProperty(None)

    def __init__(self):
        super().__init__()

    def is_valid_window_position(self, left, top, width, height):
        try:
            from screeninfo import get_monitors

            monitors = get_monitors()
            for monitor in monitors:
                if (
                    left >= monitor.x
                    and left + width <= monitor.x + monitor.width
                    and top >= monitor.y
                    and top + height <= monitor.y + monitor.height
                ):
                    return True
            return False
        except Exception as e:
            return True  # yolo

    def build(self):
        self.icon = ICON  # how you're supposed to set an icon

        self.title = f"KaTrain v{VERSION}"

        kv_file = find_package_resource("katrain/gui.kv")
        popup_kv_file = find_package_resource("katrain/popups.kv")
        resource_add_path(PATHS["PACKAGE"] + "/fonts")
        resource_add_path(PATHS["PACKAGE"] + "/sounds")
        resource_add_path(PATHS["PACKAGE"] + "/img")
        resource_add_path(os.path.abspath(os.path.expanduser(DATA_FOLDER)))  # prefer resources in .katrain

        theme_files = glob.glob(os.path.join(os.path.expanduser(DATA_FOLDER), "theme*.json"))
        for theme_file in sorted(theme_files):
            try:
                with open(theme_file) as f:
                    theme_overrides = json.load(f)
                for k, v in theme_overrides.items():
                    setattr(Theme, k, v)
                    print(f"[{theme_file}] Found theme override {k} = {v}")
            except Exception as e:  # noqa E722
                print(f"Failed to load theme file {theme_file}: {e}")

        Theme.DEFAULT_FONT = resource_find(Theme.DEFAULT_FONT)
        Builder.load_file(kv_file)

        Window.bind(on_request_close=self.on_request_close)
        Window.bind(on_dropfile=lambda win, file: self.gui.load_sgf_file(file.decode("utf8")))
        self.gui = KaTrainGui()
        Builder.load_file(popup_kv_file)

        win_left = win_top = win_size = None
        if self.gui.config("ui_state/restoresize", True):
            win_size = self.gui.config("ui_state/size", [])
            win_left = self.gui.config("ui_state/left", None)
            win_top = self.gui.config("ui_state/top", None)
        if not win_size:
            window_scale_fac = 1
            try:
                from screeninfo import get_monitors

                for m in get_monitors():
                    window_scale_fac = min(window_scale_fac, (m.height - 100) / 1000, (m.width - 100) / 1300)
            except Exception as e:
                window_scale_fac = 0.85
            win_size = [1300 * window_scale_fac, 1000 * window_scale_fac]
        self.gui.log(f"Setting window size to {win_size} and position to {[win_left, win_top]}", OUTPUT_DEBUG)
        Window.size = (win_size[0], win_size[1])
        if (
            win_left is not None
            and win_top is not None
            and self.is_valid_window_position(win_left, win_top, win_size[0], win_size[1])
        ):
            Window.left = win_left
            Window.top = win_top

        return self.gui

    def webbrowser(self, site_key):
        websites = {
            "homepage": HOMEPAGE + "#manual",
            "support": HOMEPAGE + "#support",
            "engine:help": HOMEPAGE + "/blob/master/ENGINE.md",
        }
        if site_key in websites:
            webbrowser.open(websites[site_key])

    def on_start(self):
        self.gui.ensure_engine_ready(self.gui.start)

    def on_request_close(self, *_args, source=None):
        if source == "keyboard":
            return True  # do not close on esc
        if getattr(self, "gui", None):
            self.gui.play_mode.save_ui_state()
            self.gui._config["ui_state"]["size"] = list(Window._size)
            self.gui._config["ui_state"]["top"] = Window.top
            self.gui._config["ui_state"]["left"] = Window.left
            self.gui.save_config("ui_state")
            if self.gui.engine:
                self.gui.engine.shutdown(finish=None)

    def signal_handler(self, _signal, _frame):
        if self.gui.debug_level >= OUTPUT_DEBUG:
            print("TRACEBACKS")
            for threadId, stack in sys._current_frames().items():
                print(f"\n# ThreadID: {threadId}")
                for filename, lineno, name, line in traceback.extract_stack(stack):
                    print(f"\tFile: {filename}, line {lineno}, in {name}")
                    if line:
                        print(f"\t\t{line.strip()}")
        self.stop()


def run_app():
    class CrashHandler(ExceptionHandler):
        def handle_exception(self, inst):
            ex_type, ex, tb = sys.exc_info()
            trace = "".join(traceback.format_tb(tb))
            app = App.get_running_app()

            if app and app.gui:
                app.gui.log(
                    f"Exception {inst.__class__.__name__}: {', '.join(repr(a) for a in inst.args)}\n{trace}",
                    OUTPUT_ERROR,
                )
            else:
                print(f"Exception {inst.__class__}: {inst.args}\n{trace}")
            return ExceptionManager.PASS

    ExceptionManager.add_handler(CrashHandler())
    app = KaTrainApp()
    signal.signal(signal.SIGINT, app.signal_handler)
    app.run()


if __name__ == "__main__":
    run_app()
