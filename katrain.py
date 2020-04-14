import signal
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from .engine import KataGoEngine
import os, sys, threading
from kivy.storage.jsonstore import JsonStore
from kivy.clock import Clock
from queue import Queue
from game import Game, IllegalMoveException, KaTrainSGF, Move
from game_node import GameNode

OUTPUT_ERROR = -1
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2

class KaTrainGui(BoxLayout):

    def __init__(self, **kwargs):
        super(KaTrainGui, self).__init__(**kwargs)
        self.debug_level = 0
        self._load_config()
        self.debug_level = self.config("debug/level",OUTPUT_INFO)
        self.logger = lambda message, level=OUTPUT_INFO: self.log(message, level)

        self.engine = None
        self.game = None
        self.message_queue = Queue()

        self._keyboard = Window.request_keyboard(None, self, "")
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def log(self, message, level=OUTPUT_INFO):
        if level==OUTPUT_ERROR:
            self.controls.set_status(f"ERROR: {message}")
            print(f"ERROR: {message}")
        elif self.debug_level >= level:
            print(message)

    def _load_config(self):
        try:
            base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # for pyinstaller
            config_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_path, "config.json")
            self.log(f"Using config file {config_file}",OUTPUT_INFO)
            self._config_store = JsonStore(config_file)
        except FileNotFoundError:
            self.log(f"Config file {config_file} not found",OUTPUT_ERROR)

    def config(self,setting,default=None):
        try:
            if '/' in setting:
                cat, key = setting.split('/')
                return self._config_store.get(cat).get(key,default)
            else:
                return self._config_store.get(setting)
        except Exception:
            self.log(f"Missing configuration option {setting}",OUTPUT_ERROR)

    def start(self):
        if self.engine:
            return
        self.engine = KataGoEngine(self.config("engine"),self.logger)
        threading.Thread(target=self._message_loop_thread, daemon=True).start()
        self._do_new_game()

    def _message_loop_thread(self):
        while True:
            game, msg, *args = self.message_queue.get()
            try:
                self.log(f"Message Loop Received {msg}: {args} for Game {game}",OUTPUT_EXTRA_DEBUG)
                if game != self.game.game_id:
                    self.log(f"Message skipped as it is outdated (current game is {self.game.game_id}", OUTPUT_EXTRA_DEBUG)
                    continue
                getattr(self, f"_do_{msg.replace('-','_')}")(*args)
            except Exception as e:
                self.log(f"Exception in Engine thread: {e}",OUTPUT_ERROR)
                raise

    def action(self, message, *args):
        if self.game:
            self.message_queue.put([self.game.game_id, message, *args])

    def _do_new_game(self,board_size=None):
        self.game = Game(self,self.engine,self.config("analysis"),self.config("board"),board_size=board_size)


    def play(self, move: Move, faster=False, analysis_priority=None):
        try:
            next_node = self.board.play(move)
        except IllegalMoveException as e:
            self.info.text = f"Illegal move: {str(e)}"
            return
        self.update_evaluation()
        if not next_node.analysis_ready:  # replayed old move
            self._request_analysis(next_node, faster=faster, priority=self.game_counter if analysis_priority is None else analysis_priority)
        return next_node

    def _do_play(self, *args):
        self.play(Move(args[0], player=self.board.next_player))

    def redraw(self, include_board=False):
        if include_board:
            Clock.schedule_once(self.board.draw_board, -1)  # main thread needs to do this
        Clock.schedule_once(self.board.draw_board_contents, -1)


    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] == "up":
            self.controls.action("undo")
        elif keycode[1] == "down":
            self.controls.action("redo")
        elif keycode[1] == "right":
            self.controls.action("redo-branch", 1)
        elif keycode[1] == "left":
            self.controls.action("redo-branch", -1)
        elif keycode[1] == "s":
            self.controls.action("analyze-extra", "sweep")
        elif keycode[1] == "x":
            self.controls.action("analyze-extra", "extra")
        elif keycode[1] == "r":
            self.controls.action("analyze-extra", "refine")
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
        elif keycode[1] == "l": # ctrl-l?
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
        self.gui.restart()
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signal, frame):
        import sys
        import traceback

        if self.gui.controls.debug:
            print("TRACEBACKS")
            for threadId, stack in sys._current_frames().items():
                print(f"\n# ThreadID: {threadId}")
                for filename, lineno, name, line in traceback.extract_stack(stack):
                    print("File: filename}, line {lineno}, in {name}")
                    if line:
                        print(f"  {line.strip()}")
        sys.exit(0)

if __name__ == "__main__":
    KaTrainApp().run()
