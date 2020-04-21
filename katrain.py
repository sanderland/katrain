import os
import signal
import sys
import threading
from queue import Queue

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget

from constants import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG, OUTPUT_INFO
from engine import KataGoEngine
from game import Game, IllegalMoveException, KaTrainSGF, Move
from gui import *
from gui.popups import ConfigPopup, NewGamePopup
from sgf_parser import ParseError


class KaTrainGui(BoxLayout):
    """Top level class responsible for tying everything together"""

    def __init__(self, **kwargs):
        super(KaTrainGui, self).__init__(**kwargs)
        self.debug_level = 0
        self.engine = None
        self.game = None
        self.logger = lambda message, level=OUTPUT_INFO: self.log(message, level)

        self._load_config()
        self.debug_level = self.config("debug/level", OUTPUT_INFO)
        self.message_queue = Queue()

        self._keyboard = Window.request_keyboard(None, self, "")
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def log(self, message, level=OUTPUT_INFO):
        if level == OUTPUT_ERROR:
            self.controls.set_status(f"ERROR: {message}")
            print(f"ERROR: {message}")
        elif self.debug_level >= level:
            print(message)

    def _load_config(self):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # for pyinstaller
        config_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_path, "config.json")
        try:
            self.log(f"Using config file {config_file}", OUTPUT_INFO)
            self._config_store = JsonStore(config_file,indent=4)
            self._config = dict(self._config_store)
        except Exception as e:
            self.log(f"Failed to load config {config_file}: {e}", OUTPUT_ERROR)
            sys.exit(1)

    def save_config(self, cat, **kwargs):
        self._config_store.put(cat, **kwargs)

    def config(self, setting, default=None):
        try:
            if "/" in setting:
                cat, key = setting.split("/")
                return self._config[cat].get(key, default)
            else:
                return self._config[setting]
        except KeyError:
            self.log(f"Missing configuration option {setting}", OUTPUT_ERROR)

    def start(self):
        if self.engine:
            return
        self.board_gui.trainer_config = self.config("trainer")  # TODO: could be cleaner
        self.board_gui.ui_config = self.config("board_ui")
        self.engine = KataGoEngine(self, self.config("engine"))
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        self._do_new_game()

    def update_state(self, redraw_board=False):
        # AI and Trainer/auto-undo handlers
        cn = self.game.current_node
        auto_undo = cn.player and "undo" in self.controls.player_mode(cn.player)
        if auto_undo and cn.analysis_ready:
            self.game.analyze_undo(cn, self.config("trainer"))  # not via message loop

        if cn.analysis_ready and "ai" in self.controls.player_mode(cn.next_player) and not cn.children and not self.game.game_ended and not (auto_undo and cn.auto_undo is None):
            self("ai-move", cn)  # cn mismatch stops this if undo fired

        # Handle prisoners and next player display
        prisoners = self.game.prisoner_count
        top, bot = self.board_controls.black_prisoners, self.board_controls.white_prisoners
        if self.game.next_player == "W":
            top, bot = bot, top
        self.board_controls.mid_circles_container.clear_widgets()
        self.board_controls.mid_circles_container.add_widget(bot)
        self.board_controls.mid_circles_container.add_widget(top)
        self.board_controls.black_prisoners.text = str(prisoners[1])
        self.board_controls.white_prisoners.text = str(prisoners[0])

        # Update board and status
        if redraw_board:
            Clock.schedule_once(self.board_gui.draw_board, -1)  # main thread needs to do this
        Clock.schedule_once(self.board_gui.draw_board_contents, -1)
        self.controls.update_evaluation()

    def _message_loop_thread(self):
        while True:
            game, msg, *args = self.message_queue.get()
            try:
                self.log(f"Message Loop Received {msg}: {args} for Game {game}", OUTPUT_EXTRA_DEBUG)
                if game != self.game.game_id:
                    self.log(f"Message skipped as it is outdated (current game is {self.game.game_id}", OUTPUT_EXTRA_DEBUG)
                    continue
                getattr(self, f"_do_{msg.replace('-','_')}")(*args)  # TODO update state?
            except Exception as e:
                self.log(f"Exception in Engine thread: {e}", OUTPUT_ERROR)
                raise

    def __call__(self, message, *args):
        if self.game:
            self.message_queue.put([self.game.game_id, message, *args])

    def _do_new_game(self, move_tree=None):
        self.game = Game(self, self.engine, self.config("game"), move_tree=move_tree)
        self.controls.select_mode("analyze" if move_tree and len(move_tree.nodes_in_tree) > 1 else "play")
        self.controls.graph.initialize_from_game(self.game.root)
        self.update_state(redraw_board=True)  # TODO: just board here/redraw is in all anyway?

    def _do_ai_move(self, node=None):
        if node is None or self.game.current_node == node:
            self.game.ai_move(self.config("trainer"))
            self.update_state()

    def _do_undo(self, n_times=1):
        self.game.undo(n_times)
        self.update_state()

    def _do_redo(self, n_times=1):
        self.game.redo(n_times)
        self.update_state()

    def _do_switch_branch(self, direction):
        self.game.switch_branch(direction)
        self.update_state()

    def _do_play(self, coords):
        try:
            self.game.play(Move(coords, player=self.game.next_player))
        except IllegalMoveException as e:
            self.controls.set_status(f"Illegal Move: {str(e)}")
        self.update_state()

    def _do_analyze_extra(self, mode):
        self.game.analyze_extra(mode)

    def _do_analyze_sgf_popup(self):
        fileselect_popup = Popup(title="Double Click SGF file to analyze", size_hint=(0.8, 0.8))
        popup_contents = LoadSGFPopup()
        fileselect_popup.add_widget(popup_contents)
        popup_contents.filesel.path = os.path.expanduser(self.config("files/sgf_load"))

        def readfile(files, _mouse):
            fileselect_popup.dismiss()
            try:
                move_tree = KaTrainSGF.parse_file(files[0])
            except ParseError as e:
                self.log(f"Failed to load SGF. Parse Error: {e}", OUTPUT_ERROR)
                return
            self._do_new_game(move_tree=move_tree)

        popup_contents.filesel.on_submit = readfile
        fileselect_popup.open()

    def _do_new_game_popup(self):
        new_game_popup = Popup(title="New Game", size_hint=(0.5, 0.6))
        popup_contents = NewGamePopup(self, new_game_popup, {k: v[0] for k, v in self.game.root.properties.items() if len(v) == 1})
        new_game_popup.add_widget(popup_contents)
        new_game_popup.open()

    def _do_config_popup(self):
        config_popup = Popup(title="Edit Settings", size_hint=(0.9, 0.9))
        popup_contents = ConfigPopup(self, config_popup, dict(self._config), ignore_cats=("board_ui"))
        config_popup.add_widget(popup_contents)
        config_popup.open()

    def _do_output_sgf(self):
        for pl in Move.PLAYERS:
            if not self.game.root.get_first(f"P{pl}"):
                _, model_file = os.path.split(self.engine.config["model"])
                self.game.root.properties[f"P{pl}"] = [f"KaTrain (KataGo {model_file})" if 'ai' in self.controls.player_mode(pl) else "Player"]
        msg = self.game.write_sgf(self.config("files/sgf_save"))
        self.log(msg, OUTPUT_INFO)
        self.controls.set_status(msg)

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if isinstance(App.get_running_app().root_window.children[0], Popup):
            return  # if in new game or load, don't allow keyboard shortcuts

        shortcuts = {
            "u": self.controls.eval,
            "i": self.controls.hints,
            "p": self.controls.policy,
            "o": self.controls.ownership,
            "a": ("ai-move",),
            "right": ("switch-branch", 1),
            "left": ("switch-branch", -1),
            "z": ("analyze-extra", "sweep"),
            "x": ("analyze-extra", "extra"),
            "c": ("analyze-extra", "refine"),
        }
        if keycode[1] in shortcuts.keys():
            shortcut = shortcuts[keycode[1]]
            if isinstance(shortcut, Widget):
                shortcut.trigger_action(duration=0)
            else:
                self(*shortcut)
        elif keycode[1] == "up":
            self("undo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] == "down":
            self("redo", 1 + ("shift" in modifiers) * 9 + ("ctrl" in modifiers) * 999)
        elif keycode[1] == "n" and "ctrl" in modifiers:
            self("new-game-popup")
        elif keycode[1] == "l" and "ctrl" in modifiers:
            self("analyze-sgf-popup")
        elif keycode[1] == "s" and "ctrl" in modifiers:
            self("output-sgf")
        elif keycode[1] == "c" and "ctrl" in modifiers:
            Clipboard.copy(self.game.root.sgf())
            self.controls.set_status("Copied SGF to clipboard.")
        elif keycode[1] == "v" and "ctrl" in modifiers:  # TODO: refactor
            clipboard = Clipboard.paste()
            if not clipboard:
                self.controls.set_status(f"Ctrl-V pressed but clipboard is empty.")
                return
            try:
                move_tree = KaTrainSGF.parse(clipboard)
            except Exception as e:
                self.controls.set_status(f"Failed to imported game from clipboard: {e}")
                return
            self._do_new_game(move_tree=move_tree)
            self("redo", 999)
            self.log("Imported game from clipboard.", OUTPUT_INFO)
        return True


class KaTrainApp(App):
    def build(self):
        self.icon = "./img/icon.png"
        self.gui = KaTrainGui()
        Window.bind(on_request_close=self.on_request_close)
        return self.gui

    def on_start(self):
        self.gui.start()

    def on_request_close(self, *args):
        if getattr(self, "gui", None) and self.gui.engine:
            self.gui.engine.shutdown()

    def signal_handler(self, signal, frame):
        import sys
        import traceback

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


if __name__ == "__main__":
    #    with open("katrain.kv", encoding="utf-8") as f:  # avoid windows using another encoding
    #        Builder.load_string(f.read())
    app = KaTrainApp()
    signal.signal(signal.SIGINT, app.signal_handler)
    try:
        app.run()
    except Exception:
        app.on_request_close()
        raise
