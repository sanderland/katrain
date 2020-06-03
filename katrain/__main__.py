# first, logging level lower
import os
os.environ["KCFG_KIVY_LOG_LEVEL"] = os.environ.get("KCFG_KIVY_LOG_LEVEL", "warning")

# next, icon
from katrain.core.utils import find_package_resource  # isort:skip
from kivy.config import Config  # isort:skip
ICON = find_package_resource("katrain/img/icon.ico")  # isort:skip  # find icon
Config.set("kivy", "window_icon", ICON)  # isort:skip  # set icon

# finally, window size
from kivy.metrics import dp
WINDOW_X, WINDOW_Y = 1300, 1000
try:
    from screeninfo import get_monitors
    scale = 1.0
    for m in get_monitors():
        scale = min(scale, (m.height-100) / WINDOW_Y, (m.width-100) / WINDOW_X)
    WINDOW_SCALE_FAC = max(0.4,scale)
except Exception as e:
    print("Exception while getting screen resolution", e)
    WINDOW_SCALE_FAC = 1

Config.set("graphics", "width", int(WINDOW_SCALE_FAC*WINDOW_X))
Config.set("graphics", "height", int(WINDOW_SCALE_FAC*WINDOW_Y))
Config.set("input", "mouse", "mouse,multitouch_on_demand")

import signal
import sys
import threading
import traceback
from queue import Queue
import webbrowser

from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from katrain.core.ai import ai_move
from kivy.core.window import Window

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
)
from katrain.gui.popups import ConfigTeacherPopup, ConfigTimerPopup, I18NPopup
from katrain.core.base_katrain import KaTrainBase
from katrain.core.engine import KataGoEngine
from katrain.core.game import Game, IllegalMoveException, KaTrainSGF
from katrain.core.sgf_parser import Move, ParseError
from katrain.gui.kivyutils import *
from katrain.gui.popups import ConfigPopup, LoadSGFPopup, NewGamePopup, AIPopup
from katrain.gui.style import ENGINE_BUSY_COL, ENGINE_DOWN_COL, ENGINE_READY_COL
from katrain.gui.widgets.graph import ScoreGraph
from katrain.gui.widgets.filebrowser import I18NFileBrowser
from katrain.gui.badukpan import AnalysisControls, BadukPanControls, BadukPanWidget
from katrain.gui.controlspanel import ControlsPanel


class KaTrainGui(Screen, KaTrainBase):
    """Top level class responsible for tying everything together"""

    zen = BooleanProperty(False)
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

        self.message_queue = Queue()

        self._keyboard = Window.request_keyboard(None, self, "")
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def log(self, message, level=OUTPUT_INFO):
        super().log(message, level)
        if level == OUTPUT_KATAGO_STDERR and "ERROR" not in self.controls.status.text:
            if "starting" in message.lower():
                self.controls.set_status(f"KataGo engine starting...")
            if message.startswith("Tuning"):
                self.controls.set_status(f"KataGo is tuning settings for first startup, please wait." + message)
                return
            if "ready" in message.lower():
                self.controls.set_status(f"KataGo engine ready.")
        if (level == OUTPUT_ERROR or (level == OUTPUT_KATAGO_STDERR and "error" in message.lower())) and getattr(
            self, "controls", None
        ):
            self.controls.set_status(f"ERROR: {message}")

    @property
    def play_analyze_mode(self):
        return self.play_mode.play_analyze_mode

    def start(self):
        if self.engine:
            return
        self.board_gui.trainer_config = self.config("trainer")
        self.engine = KataGoEngine(self, self.config("engine"))
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        self._do_new_game()

    def update_state(
        self, redraw_board=False
    ):  # is called after every message and on receiving analyses and config changes
        # AI and Trainer/auto-undo handlers
        cn = self.game and self.game.current_node
        if not cn:
            return
        last_player, next_player = self.players_info[cn.player], self.players_info[cn.next_player]
        if self.play_analyze_mode == MODE_PLAY:
            teaching_undo = cn.player and last_player.being_taught
            if (
                teaching_undo
                and cn.analysis_ready
                and cn.parent
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
            ):
                self._do_ai_move(
                    cn
                )  # cn mismatch stops this if undo fired. avoid message loop here or fires repeatedly.

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

        # redraw
        if redraw_board:
            Clock.schedule_once(self.board_gui.draw_board, -1)
        self.board_gui.redraw_board_contents_trigger()
        self.controls.update_evaluation()
        self.controls.update_timer(1)

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
            game, msg, *args = self.message_queue.get()
            try:
                self.log(f"Message Loop Received {msg}: {args} for Game {game}", OUTPUT_EXTRA_DEBUG)
                if game != self.game.game_id:
                    self.log(
                        f"Message skipped as it is outdated (current game is {self.game.game_id}", OUTPUT_EXTRA_DEBUG
                    )
                    continue
                fn = getattr(self, f"_do_{msg.replace('-','_')}")
                fn(*args)
                self.update_state()
            except Exception as exc:
                self.log(f"Exception in processing message {msg} {args}: {exc}", OUTPUT_ERROR)
                traceback.print_exc()

    def __call__(self, message, *args):
        if self.game:
            if message.endswith("popup"):  # gui code needs to run in main kivy thread.
                fn = getattr(self, f"_do_{message.replace('-', '_')}")
                Clock.schedule_once(lambda _dt: fn(*args), -1)
            else:  # game related actions
                self.message_queue.put([self.game.game_id, message, *args])

    def _do_new_game(self, move_tree=None, analyze_fast=False):
        if move_tree is None:
            self.play_mode.select_mode(MODE_PLAY)
        else:
            self.play_mode.select_mode(MODE_ANALYZE)
        self.board_gui.animating_pv = None
        self.engine.on_new_game()  # clear queries
        self.game = Game(self, self.engine, move_tree=move_tree, analyze_fast=analyze_fast)
        self.controls.graph.initialize_from_game(self.game.root)
        self.update_state(redraw_board=True)

    def _do_ai_move(self, node=None):
        if node is None or self.game.current_node == node:
            mode = self.next_player_info.strategy
            settings = self.config(f"ai/{mode}")
            if settings is not None:
                ai_move(self.game, mode, settings)
            else:
                self.log(f"AI Mode {mode} not found!", OUTPUT_ERROR)

    def _do_undo(self, n_times=1):
        if n_times == "smart":
            n_times = 1
            if self.play_analyze_mode == "play" and self.last_player_info.ai and self.next_player_info.human:
                n_times = 2
        self.board_gui.animating_pv = None
        self.game.undo(n_times)

    def _do_redo(self, n_times=1):
        self.board_gui.animating_pv = None
        self.game.redo(n_times)

    def _do_switch_branch(self, direction):
        self.board_gui.animating_pv = None
        self.game.switch_branch(direction)

    def _do_play(self, coords):
        self.board_gui.animating_pv = None
        try:
            self.game.play(Move(coords, player=self.next_player_info.player))
        except IllegalMoveException as e:
            self.controls.set_status(f"Illegal Move: {str(e)}")

    def _do_analyze_extra(self, mode):
        self.game.analyze_extra(mode)

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
                title_key="teacher settings", size=[dp(800), dp(800)], content=ConfigTeacherPopup(self)
            ).__self__
            self.teacher_settings_popup.content.popup = self.teacher_settings_popup
        self.teacher_settings_popup.open()

    def _do_config_popup(self):
        self.controls.timer.paused = True
        if not self.config_popup:
            self.config_popup = I18NPopup(
                title_key="general settings title", size=[dp(1200), dp(800)], content=ConfigPopup(self)
            ).__self__
            self.config_popup.content.popup = self.config_popup
        self.config_popup.open()

    def _do_ai_popup(self):
        self.controls.timer.paused = True
        if not self.ai_settings_popup:
            self.ai_settings_popup = I18NPopup(title_key="ai settings", size=[dp(600), dp(600)], content=AIPopup(self)).__self__
            self.ai_settings_popup.content.popup = self.ai_settings_popup
        self.ai_settings_popup.open()

    def _do_analyze_sgf_popup(self):
        if not self.fileselect_popup:
            popup_contents = LoadSGFPopup()
            popup_contents.filesel.path = os.path.abspath(os.path.expanduser(self.config("general/sgf_load", ".")))
            self.fileselect_popup = I18NPopup(
                title_key="load sgf title", size=[dp(1200), dp(800)], content=popup_contents
            ).__self__

            def readfile(*args):
                files = popup_contents.filesel.selection
                self.fileselect_popup.dismiss()
                try:
                    move_tree = KaTrainSGF.parse_file(files[0])
                except ParseError as e:
                    self.log(i18n._("Failed to load SGF").format(error=e), OUTPUT_ERROR)
                    return
                self._do_new_game(move_tree=move_tree, analyze_fast=popup_contents.fast.active)
                if not popup_contents.rewind.active:
                    self.game.redo(999)

            popup_contents.filesel.on_success = readfile
            popup_contents.filesel.on_submit = readfile
        self.fileselect_popup.open()

    def _do_output_sgf(self):
        msg = self.game.write_sgf(self.config("general/sgf_save"))
        self.log(msg, OUTPUT_INFO)
        self.controls.set_status(msg)

    def load_sgf_from_clipboard(self):
        clipboard = Clipboard.paste()
        if not clipboard:
            self.controls.set_status(f"Ctrl-V pressed but clipboard is empty.")
            return
        try:
            move_tree = KaTrainSGF.parse(clipboard)
        except Exception as e:
            self.controls.set_status(i18n._("Failed to import from clipboard").format(error=e, contents=clipboard[:50]))
            return
        move_tree.nodes_in_tree[-1].analyze(
            self.engine, analyze_fast=False
        )  # speed up result for looking at end of game
        self._do_new_game(move_tree=move_tree, analyze_fast=True)
        self("redo", 999)
        self.log("Imported game from clipboard.", OUTPUT_INFO)

    def on_touch_up(self, touch):
        if self.board_gui.collide_point(*touch.pos) or self.board_controls.collide_point(*touch.pos):
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
            "right": ("switch-branch", 1),
            "left": ("switch-branch", -1),
            "f5": ("timer-popup",),
            "f6": ("teacher-popup",),
            "f7": ("ai-popup",),
            "f8": ("config-popup",),
        }

    def _on_keyboard_down(self, _keyboard, keycode, _text, modifiers):
        if self.controls.note.focus:
            return  # when making notes, don't allow keyboard shortcuts
        app = App.get_running_app()
        first_child = app.root_window.children[0]
        if isinstance(first_child, Popup):
            if keycode[1] not in ["f5", "f6", "f7", "f8"]:
                return
            first_child.dismiss()

        shortcuts = self.shortcuts
        if keycode[1] == "tab":
            self.play_mode.switch_mode()
        elif keycode[1] == "shift":
            self.nav_drawer.set_state("toggle")
        elif keycode[1] == "spacebar":
            self.controls.timer.paused = not self.controls.timer.paused
        elif keycode[1] in ["`", "~", "m"]:
            self.zen = not self.zen
        elif keycode[1] in ["up", "z"]:
            self("undo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] in ["down", "x"]:
            self("redo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] == "n" and "ctrl" in modifiers:
            self("new-game-popup")
        elif keycode[1] == "l" and "ctrl" in modifiers:
            self("analyze-sgf-popup")
        elif keycode[1] == "f12" and "ctrl" in modifiers:
            app.language = "haha"
        elif keycode[1] == "s" and "ctrl" in modifiers:
            self("output-sgf")
        elif keycode[1] == "c" and "ctrl" in modifiers:
            Clipboard.copy(self.game.root.sgf())
            self.controls.set_status(i18n._("Copied SGF to clipboard."))
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
    def build(self):
        self.icon = ICON  # how you're supposed to set an icon

        kv_file = find_package_resource("katrain/gui.kv")
        popup_kv_file = find_package_resource("katrain/popups.kv")
        resource_add_path(os.path.split(kv_file)[0])
        Builder.load_file(kv_file)
        Builder.load_file(popup_kv_file)

        self.gui = KaTrainGui()
        self.title = f"KaTrain v{VERSION}"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"

        Window.bind(on_request_close=self.on_request_close)
        return self.gui

    def on_language(self, _instance, language):
        self.gui.log(f"Switching language to {language}", OUTPUT_INFO)
        i18n.switch_lang(language)
        if language != "haha":
            self.gui._config["general"]["lang"] = language
            self.gui.save_config()
        if self.gui.game:
            self.gui.update_state()
            self.gui.controls.set_status("")

    def webbrowser(self, site_key):
        WEBSITES = {"homepage": HOMEPAGE, "support": HOMEPAGE + "#support"}
        if site_key in WEBSITES:
            webbrowser.open(WEBSITES[site_key])

    def on_start(self):
        self.language = self.gui.config("general/lang")
        self.gui.start()

    def on_request_close(self, *_args):
        if getattr(self, "gui", None) and self.gui.engine:
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
        self.on_request_close()
        sys.exit(0)


def run_app():
    app = KaTrainApp()
    signal.signal(signal.SIGINT, app.signal_handler)

    try:
        app.run()
    except Exception as e:
        print(e)
        app.on_request_close()
        raise

if __name__ == "__main__":
    run_app()
