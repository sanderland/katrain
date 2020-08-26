"""isort:skip_file"""
# first, logging level lower
import os

os.environ["KCFG_KIVY_LOG_LEVEL"] = os.environ.get("KCFG_KIVY_LOG_LEVEL", "warning")
if "KIVY_AUDIO" not in os.environ:
    os.environ["KIVY_AUDIO"] = "sdl2"  # some backends hard crash / this seems to be most stable

# next, icon
from katrain.core.utils import find_package_resource, PATHS
from kivy.config import Config
from kivy.utils import platform

ICON = find_package_resource("katrain/img/icon.ico")
Config.set("kivy", "window_icon", ICON)

# finally, window size
WINDOW_SCALE_FAC, WINDOW_X, WINDOW_Y = 1, 1300, 1000
try:
    from screeninfo import get_monitors

    for m in get_monitors():
        WINDOW_SCALE_FAC = min(WINDOW_SCALE_FAC, (m.height - 100) / WINDOW_Y, (m.width - 100) / WINDOW_X)
except Exception as e:
    if platform != "macosx":
        print(f"Exception {e} while getting screen resolution.")
        WINDOW_SCALE_FAC = 0.85

Config.set("graphics", "width", max(400, int(WINDOW_X * WINDOW_SCALE_FAC)))
Config.set("graphics", "height", max(400, int(WINDOW_Y * WINDOW_SCALE_FAC)))
Config.set("input", "mouse", "mouse,multitouch_on_demand")

import signal
import sys
import threading
import traceback
from queue import Queue
import webbrowser

from kivy.base import ExceptionHandler, ExceptionManager
from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from katrain.core.ai import generate_ai_move
from kivy.core.window import Window
from kivy.metrics import dp

from katrain.core.lang import DEFAULT_LANGUAGE, i18n
from katrain.core.constants import (
    OUTPUT_ERROR,
    OUTPUT_KATAGO_STDERR,
    OUTPUT_INFO,
    OUTPUT_DEBUG,
    OUTPUT_EXTRA_DEBUG,
    MODE_PLAY,
    MODE_ANALYZE,
    HOMEPAGE,
    VERSION,
    STATUS_ERROR,
    STATUS_INFO,
    PLAYING_NORMAL,
    PLAYER_HUMAN,
)
from katrain.gui.popups import ConfigTeacherPopup, ConfigTimerPopup, I18NPopup
from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game, IllegalMoveException, KaTrainSGF
from katrain.core.sgf_parser import Move, ParseError
from katrain.gui.kivyutils import *
from katrain.gui.popups import ConfigPopup, LoadSGFPopup, NewGamePopup, ConfigAIPopup
from katrain.gui.style import ENGINE_BUSY_COL, ENGINE_DOWN_COL, ENGINE_READY_COL, LIGHTGREY
from katrain.gui.widgets import *
from katrain.gui.badukpan import AnalysisControls, BadukPanControls, BadukPanWidget
from katrain.gui.controlspanel import ControlsPanel


class KaTrainGui(Screen, KaTrainBase):
    """Top level class responsible for tying everything together"""

    zen = NumericProperty(0)
    controls = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None

        self.new_game_popup = None
        self.fileselect_popup = None
        self.config_popup = None
        self.ai_settings_popup = None
        self.teacher_settings_popup = None
        self.timer_settings_popup = None

        self.idle_analysis = False
        self.message_queue = Queue()

        self._keyboard = Window.request_keyboard(None, self, "")
        self._keyboard.bind(on_key_down=self._on_keyboard_down)
        Clock.schedule_interval(self.animate_pondering, 0.1)

    def log(self, message, level=OUTPUT_INFO):
        super().log(message, level)
        if level == OUTPUT_KATAGO_STDERR and "ERROR" not in self.controls.status.text:
            if "starting" in message.lower():
                self.controls.set_status(f"KataGo engine starting...", STATUS_INFO)
            if message.startswith("Tuning"):
                self.controls.set_status(
                    f"KataGo is tuning settings for first startup, please wait." + message, STATUS_INFO
                )
                return
            if "ready" in message.lower():
                self.controls.set_status(f"KataGo engine ready.", STATUS_INFO)
        if (
            level == OUTPUT_ERROR
            or (level == OUTPUT_KATAGO_STDERR and "error" in message.lower() and "tuning" not in message.lower())
        ) and getattr(self, "controls", None):
            self.controls.set_status(f"ERROR: {message}", STATUS_ERROR)

    def animate_pondering(self, *_args):
        if not self.idle_analysis:
            self.board_controls.engine_status_pondering = -1
        else:
            self.board_controls.engine_status_pondering += 5

    @property
    def play_analyze_mode(self):
        return self.play_mode.mode

    def toggle_continuous_analysis(self):
        self.idle_analysis = not self.idle_analysis
        if not self.idle_analysis:
            self.controls.set_status("", STATUS_INFO)
        self.update_state()

    def start(self):
        if self.engine:
            return
        self.board_gui.trainer_config = self.config("trainer")
        self.engine = KataGoEngine(self, self.config("engine"))
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        self._do_new_game()

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
        self.board_controls.branch.disabled = not cn.parent or len(cn.parent.children) <= 1
        self.controls.players["W"].captures = prisoners["W"]
        self.controls.players["B"].captures = prisoners["B"]

        # update engine status dot
        if not self.engine or not self.engine.katago_process or self.engine.katago_process.poll() is not None:
            self.board_controls.engine_status_col = ENGINE_DOWN_COL
        elif len(self.engine.queries) == 0:
            self.board_controls.engine_status_col = ENGINE_READY_COL
        else:
            self.board_controls.engine_status_col = ENGINE_BUSY_COL

        # redraw board/stones
        if redraw_board:
            self.board_gui.draw_board()
        self.board_gui.redraw_board_contents_trigger()
        self.controls.update_evaluation()
        self.controls.update_timer(1)
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
                and cn.analysis_ready
                and cn.parent.analysis_ready
                and not cn.children
                and not self.game.ended
            ):
                self.game.analyze_undo(cn)  # not via message loop
            if (
                cn.analysis_ready
                and next_player.ai
                and not cn.children
                and not self.game.ended
                and not (teaching_undo and cn.auto_undo is None)
            ):  # cn mismatch stops this if undo fired. avoid message loop here or fires repeatedly.
                self._do_ai_move(cn)
                Clock.schedule_once(self.board_gui.play_stone_sound, 0)
        if len(self.engine.queries) == 0 and self.idle_analysis:
            self("analyze-extra", "extra", continuous=True)
        Clock.schedule_once(lambda _dt: self.update_gui(cn, redraw_board=redraw_board), -1)  # trigger?

    def update_player(self, bw, **kwargs):
        super().update_player(bw, **kwargs)
        if self.controls:
            self.controls.update_players()
            self.update_state()
        for player_setup_block in PlayerSetupBlock.INSTANCES:
            player_setup_block.update_players(bw, self.players_info[bw])

    def set_note(self, note):
        self.game.current_node.note = note

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
                fn = getattr(self, f"_do_{msg.replace('-','_')}")
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

    def _do_new_game(self, move_tree=None, analyze_fast=False):
        self.idle_analysis = False
        mode = self.play_analyze_mode
        if (move_tree is not None and mode == MODE_PLAY) or (move_tree is None and mode == MODE_ANALYZE):
            self.play_mode.switch_ui_mode()  # for new game, go to play, for loaded, analyze
        self.board_gui.animating_pv = None
        self.engine.on_new_game()  # clear queries
        self.game = Game(self, self.engine, move_tree=move_tree, analyze_fast=analyze_fast)
        if move_tree:
            for bw, player_info in self.players_info.items():
                player_info.player_type = PLAYER_HUMAN
                player_info.player_subtype = PLAYING_NORMAL
                player_info.sgf_rank = move_tree.root.get_property(bw + "R")
                player_info.calculated_rank = None
                player_info.name = move_tree.root.get_property("P" + bw)
                self.update_player(bw)
        self.controls.graph.initialize_from_game(self.game.root)
        self.controls.rank_graph.initialize_from_game(self.game.root)
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

    def _do_redo(self, n_times=1):
        self.board_gui.animating_pv = None
        self.game.redo(n_times)

    def _do_cycle_children(self, *args):
        self.board_gui.animating_pv = None
        self.game.cycle_children(*args)

    def _do_switch_branch(self, *args):
        self.board_gui.animating_pv = None
        self.controls.move_tree.switch_branch(*args)

    def _do_play(self, coords):
        self.board_gui.animating_pv = None
        try:
            self.game.play(Move(coords, player=self.next_player_info.player))
        except IllegalMoveException as e:
            self.controls.set_status(f"Illegal Move: {str(e)}", STATUS_ERROR)

    def _do_analyze_extra(self, mode, **kwargs):
        self.game.analyze_extra(mode, **kwargs)

    def _do_new_game_popup(self):
        self.controls.timer.paused = True
        if not self.new_game_popup:
            self.new_game_popup = I18NPopup(
                title_key="New Game title", size=[dp(800), dp(800)], content=NewGamePopup(self)
            ).__self__
            self.new_game_popup.content.popup = self.new_game_popup
        self.new_game_popup.open()

    def _do_timer_popup(self):
        self.controls.timer.paused = True
        if not self.timer_settings_popup:
            self.timer_settings_popup = I18NPopup(
                title_key="timer settings", size=[dp(350), dp(400)], content=ConfigTimerPopup(self)
            ).__self__
            self.timer_settings_popup.content.popup = self.timer_settings_popup
        self.timer_settings_popup.open()

    def _do_teacher_popup(self):
        self.controls.timer.paused = True
        if not self.teacher_settings_popup:
            self.teacher_settings_popup = I18NPopup(
                title_key="teacher settings", size=[dp(800), dp(750)], content=ConfigTeacherPopup(self)
            ).__self__
            self.teacher_settings_popup.content.popup = self.teacher_settings_popup
        self.teacher_settings_popup.open()

    def _do_config_popup(self):
        self.controls.timer.paused = True
        if not self.config_popup:
            self.config_popup = I18NPopup(
                title_key="general settings title", size=[dp(1200), dp(950)], content=ConfigPopup(self)
            ).__self__
            self.config_popup.content.popup = self.config_popup
        self.config_popup.open()

    def _do_ai_popup(self):
        self.controls.timer.paused = True
        if not self.ai_settings_popup:
            self.ai_settings_popup = I18NPopup(
                title_key="ai settings", size=[dp(600), dp(650)], content=ConfigAIPopup(self)
            ).__self__
            self.ai_settings_popup.content.popup = self.ai_settings_popup
        self.ai_settings_popup.open()

    def load_sgf_file(self, file, fast=False, rewind=False):
        try:
            move_tree = KaTrainSGF.parse_file(file)
        except ParseError as e:
            self.log(i18n._("Failed to load SGF").format(error=e), OUTPUT_ERROR)
            return
        self._do_new_game(move_tree=move_tree, analyze_fast=fast)
        if not rewind:
            self.game.redo(999)

    def _do_analyze_sgf_popup(self):
        if not self.fileselect_popup:
            popup_contents = LoadSGFPopup()
            popup_contents.filesel.path = os.path.abspath(os.path.expanduser(self.config("general/sgf_load", ".")))
            self.fileselect_popup = I18NPopup(
                title_key="load sgf title", size=[dp(1200), dp(800)], content=popup_contents
            ).__self__

            def readfile(*_args):
                filename = popup_contents.filesel.filename
                self.fileselect_popup.dismiss()
                path, file = os.path.split(filename)
                settings_path = self.config("general/sgf_load")
                if path != settings_path:
                    self.log(f"Updating sgf load path default to {path}", OUTPUT_INFO)
                    self._config["general"]["sgf_load"] = path
                    self.save_config("general")
                self.load_sgf_file(filename, popup_contents.fast.active, popup_contents.rewind.active)

            popup_contents.filesel.on_success = readfile
            popup_contents.filesel.on_submit = readfile
        self.fileselect_popup.open()

    def _do_output_sgf(self):
        msg = self.game.write_sgf(self.config("general/sgf_save"))
        self.log(msg, OUTPUT_INFO)
        self.controls.set_status(msg, STATUS_INFO)

    def load_sgf_from_clipboard(self):
        clipboard = Clipboard.paste()
        if not clipboard:
            self.controls.set_status(f"Ctrl-V pressed but clipboard is empty.", STATUS_INFO)
            return
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
        self("redo", 999)
        self.log("Imported game from clipboard.", OUTPUT_INFO)

    def on_touch_up(self, touch):
        if (
            self.board_gui.collide_point(*touch.pos)
            or self.board_controls.collide_point(*touch.pos)
            or self.controls.move_tree.collide_point(*touch.pos)
        ):
            if touch.is_mouse_scrolling:
                if touch.button == "scrollup":
                    self("redo")
                elif touch.button == "scrolldown":
                    self("undo")
        return super().on_touch_up(touch)

    @property
    def shortcuts(self):
        return {
            "q": self.analysis_controls.show_children,
            "w": self.analysis_controls.eval,
            "e": self.analysis_controls.hints,
            "t": self.analysis_controls.ownership,
            "r": self.analysis_controls.policy,
            "enter": ("ai-move",),
            "numpadenter": ("ai-move",),
            "a": ("analyze-extra", "extra"),
            "s": ("analyze-extra", "equalize"),
            "d": ("analyze-extra", "sweep"),
            "p": ("play", None),
            "down": ("switch-branch", 1),
            "up": ("switch-branch", -1),
            "f5": ("timer-popup",),
            "f6": ("teacher-popup",),
            "f7": ("ai-popup",),
            "f8": ("config-popup",),
        }

    @property
    def popup_open(self) -> Popup:
        app = App.get_running_app()
        first_child = app.root_window.children[0]
        return first_child if isinstance(first_child, Popup) else None

    def _on_keyboard_down(self, _keyboard, keycode, _text, modifiers):
        if self.controls.note.focus:
            return  # when making notes, don't allow keyboard shortcuts

        popup = self.popup_open
        if popup:
            if keycode[1] in ["f5", "f6", "f7", "f8"]:  # switch between popups
                popup.dismiss()
                return
            else:
                return

        shortcuts = self.shortcuts
        if keycode[1] == "tab":
            self.play_mode.switch_ui_mode()
        elif keycode[1] == "shift":
            self.nav_drawer.set_state("toggle")
        elif keycode[1] == "spacebar":
            self.toggle_continuous_analysis()
        elif keycode[1] == "b" and "ctrl" not in modifiers:
            self.controls.timer.paused = not self.controls.timer.paused
        elif keycode[1] in ["`", "~", "m"] and "ctrl" not in modifiers:
            self.zen = (self.zen + 1) % 3
        elif keycode[1] in ["left", "z"]:
            self("undo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] in ["right", "x"]:
            self("redo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] == "n" and "ctrl" in modifiers:
            self("new-game-popup")
        elif keycode[1] == "l" and "ctrl" in modifiers:
            self("analyze-sgf-popup")
        elif keycode[1] == "s" and "ctrl" in modifiers:
            self("output-sgf")
        elif keycode[1] == "c" and "ctrl" in modifiers:
            Clipboard.copy(self.game.root.sgf())
            self.controls.set_status(i18n._("Copied SGF to clipboard."), STATUS_INFO)
        elif keycode[1] == "v" and "ctrl" in modifiers:
            self.load_sgf_from_clipboard()
        elif keycode[1] in shortcuts.keys() and "ctrl" not in modifiers:
            shortcut = shortcuts[keycode[1]]
            if isinstance(shortcut, Widget):
                shortcut.trigger_action(duration=0)
            else:
                self(*shortcut)
        return True


class KaTrainApp(MDApp):
    gui = ObjectProperty(None)
    language = StringProperty(DEFAULT_LANGUAGE)

    def __init__(self):
        super().__init__()

    def build(self):
        self.icon = ICON  # how you're supposed to set an icon

        self.title = f"KaTrain v{VERSION}"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Gray"
        self.theme_cls.primary_hue = "200"

        kv_file = find_package_resource("katrain/gui.kv")
        popup_kv_file = find_package_resource("katrain/popups.kv")
        resource_add_path(PATHS["PACKAGE"])
        Builder.load_file(kv_file)

        Window.bind(on_request_close=self.on_request_close)
        Window.bind(on_dropfile=lambda win, file: self.gui.load_sgf_file(file.decode("utf8")))

        self.gui = KaTrainGui()
        Builder.load_file(popup_kv_file)
        return self.gui

    def on_language(self, _instance, language):
        self.gui.log(f"Switching language to {language}", OUTPUT_INFO)
        i18n.switch_lang(language)
        self.gui._config["general"]["lang"] = language
        self.gui.save_config()
        if self.gui.game:
            self.gui.update_state()
            self.gui.controls.set_status("", STATUS_INFO)

    def webbrowser(self, site_key):
        websites = {"homepage": HOMEPAGE + "#manual", "support": HOMEPAGE + "#support"}
        if site_key in websites:
            webbrowser.open(websites[site_key])

    def on_start(self):
        self.language = self.gui.config("general/lang")
        self.gui.start()

    def on_request_close(self, *_args):
        if getattr(self, "gui", None):
            self.gui.play_mode.save_ui_state()
            if self.gui.engine:
                self.gui.engine.shutdown()

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
            app = MDApp.get_running_app()
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
