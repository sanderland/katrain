import os
import signal
import sys
import threading
from queue import Queue

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from constants import OUTPUT_DEBUG, OUTPUT_ERROR, OUTPUT_EXTRA_DEBUG, OUTPUT_INFO
from engine import KataGoEngine
from game import Game, GameNode, IllegalMoveException, KaTrainSGF, Move
from gui import BadukPanWidget, BWCheckBoxHint, CensorableLabel, CensorableScoreLabel, CheckBoxHint, Controls, LoadSGFPopup


class KaTrainGui(BoxLayout):
    """Top level class responsible for tying everything together"""

    def __init__(self, **kwargs):
        super(KaTrainGui, self).__init__(**kwargs)
        self.debug_level = 0
        self._load_config()
        self.debug_level = self.config("debug/level", OUTPUT_INFO)
        self.logger = lambda message, level=OUTPUT_INFO: self.log(message, level)

        self.engine = None
        self.game = None
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
            self._config_store = JsonStore(config_file)
        except Exception as e:
            self.log(f"Failed to load config {config_file}: {e}", OUTPUT_ERROR)
            sys.exit(1)

    def config(self, setting, default=None):
        try:
            if "/" in setting:
                cat, key = setting.split("/")
                return self._config_store.get(cat).get(key, default)
            else:
                return self._config_store.get(setting)
        except Exception:
            self.log(f"Missing configuration option {setting}", OUTPUT_ERROR)

    def start(self):
        if self.engine:
            return
        self.board_gui.config = self.config("board_ui")
        self.engine = KataGoEngine(self, self.config("engine"))
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        self._do_new_game()

    def _message_loop_thread(self):
        while True:
            game, msg, *args = self.message_queue.get()
            try:
                self.log(f"Message Loop Received {msg}: {args} for Game {game}", OUTPUT_EXTRA_DEBUG)
                if game != self.game.game_id:
                    self.log(f"Message skipped as it is outdated (current game is {self.game.game_id}", OUTPUT_EXTRA_DEBUG)
                    continue
                getattr(self, f"_do_{msg.replace('-','_')}")(*args)
            except Exception as e:
                self.log(f"Exception in Engine thread: {e}", OUTPUT_ERROR)
                raise

    def __call__(self, message, *args):
        if self.game:
            self.message_queue.put([self.game.game_id, message, *args])

    def _do_new_game(self, board_size=None, move_tree=None):
        self.game = Game(self, self.engine, self.config("game"), board_size=board_size, move_tree=move_tree)
        # TODO controls reset -> Controls
        # if self.ai_lock.active:
        #            self.ai_lock.checkbox._do_press()
        #        for el in [self.ai_lock.checkbox, self.hints.black, self.hints.white, self.ai_auto.black, self.ai_auto.white, self.auto_undo.black, self.auto_undo.white, self.ai_move]:
        #            el.disabled = False

        self.update_state(include_board=True)

    def _do_aimove(self):
        self.game.ai_move()

    def _do_undo(self):
        if (
            self.controls.ai_lock.active
            and self.contols.auto_undo.active(self.game.current_node.player)
            and len(self.game.current_node.parent.children) > self.num_undos(self.game.current_node)
            and not self.train_settings.get("dont_lock_undos")
        ):
            self.info.text = f"Can't undo this move more than {self.num_undos(self.game.current_node)} time(s) when locked"
            return
        self.game.undo()
        self.update_state()

    def _do_redo(self):
        self.game.redo()
        self.update_state()

    def _do_switch_branch(self, direction):
        self.game.switch_branch(direction)
        self.update_state()

    def play(self, move: Move, faster=False, analysis_priority=None):
        try:
            next_node = self.board_gui.play(move)
        except IllegalMoveException as e:
            self.info.text = f"Illegal move: {str(e)}"
            return
        self.update_evaluation()
        if not next_node.analysis_ready:  # replayed old move
            self._request_analysis(next_node, faster=faster, priority=self.game_counter if analysis_priority is None else analysis_priority)
        return next_node

    def _do_play(self, *args):
        self.game.play(Move(args[0], player=self.game.next_player))
        self.update_state()

    def _do_analyze_extra(self, mode):
        self.game.analyze_extra(mode)

    def _do_analyze_sgf(self, sgf):
        fileselect_popup = Popup(title="Double Click SGF file to analyze", size_hint=(0.8, 0.8))
        popup_contents = LoadSGFPopup()
        fileselect_popup.add_widget(popup_contents)
        popup_contents.filesel.path = os.path.expanduser(self.config("files/sgf_load"))

        def readfile(files, _mouse):
            fileselect_popup.dismiss()
            self._do_new_game(self, move_tree=KaTrainSGF.parse_file(files[0]))

        popup_contents.filesel.on_submit = readfile
        fileselect_popup.open()

    def output_sgf(self):
        for pl in Move.PLAYERS:
            if not self.game.root.get_first(f"P{pl}"):
                _, model_file = os.path.split(self.engine.config["model"])
                self.game.root.properties[f"P{pl}"] = [f"KaTrain (KataGo {model_file})" if self.controls.ai_auto.active(pl) else "Player"]
        return self.game.write_sgf()

    def update_state(self, include_board=False):  # TODO: rename? does more now
        cn = self.game.current_node
        if cn.analysis_ready and self.controls.ai_auto.active(cn.next_player) and not cn.children and not self.game.game_ended:
            self._do_aimove()

        if include_board:
            Clock.schedule_once(self.board_gui.draw_board, -1)  # main thread needs to do this
        Clock.schedule_once(self.board_gui.draw_board_contents, -1)
        self.controls.update_evaluation()

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] == "up":
            self("undo")
        elif keycode[1] == "down":
            self("redo")
        elif keycode[1] == "right":
            self("switch-branch", 1)
        elif keycode[1] == "left":
            self("switch-branch", -1)
        elif keycode[1] == "s":
            self("analyze-extra", "sweep")
        elif keycode[1] == "x":
            self("analyze-extra", "extra")
        elif keycode[1] == "r":
            self("analyze-extra", "refine")
        elif keycode[1] == "a":
            if not self.controls.ai_thinking:
                self.controls.ai_move.trigger_action(duration=0)
        elif keycode[1] == "p":  # TODO: clean repetitive shortcuts
            self.controls.play.trigger_action(duration=0)
        elif keycode[1] == "f":
            self.controls.ai_fast.label.trigger_action(duration=0)
        elif keycode[1] == "h":
            self.controls.hints.label.trigger_action(duration=0)
        elif keycode[1] == "e":
            self.controls.eval.label.trigger_action(duration=0)
        elif keycode[1] == "u":
            self.controls.auto_undo.label.trigger_action(duration=0)
        elif keycode[1] == "b":
            self.controls.ai_balance.label.trigger_action(duration=0)
        elif keycode[1] == "o":
            self.controls.ownership.label.trigger_action(duration=0)
        elif keycode[1] == "l":  # ctrl-l?
            self.controls.load.trigger_action(duration=0)
        elif keycode[1] == "k":
            self.controls.save.trigger_action(duration=0)
        return True


class KaTrainApp(App):
    def build(self):
        self.icon = "./icon.png"
        self.gui = KaTrainGui()
        return self.gui

    def on_start(self):
        self.gui.start()
        signal.signal(signal.SIGINT, self.signal_handler)

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
        sys.exit(0)


if __name__ == "__main__":
    KaTrainApp().run()
