#!/usr/bin/env python3
"""
Tiny harness for visually checking popup layout.

Usage:
  uv run python scripts/popup_harness.py config
  uv run python scripts/popup_harness.py ai
  uv run python scripts/popup_harness.py ai-human
  uv run python scripts/popup_harness.py ai-proyear
  uv run python scripts/popup_harness.py newgame
  uv run python scripts/popup_harness.py teacher
  uv run python scripts/popup_harness.py recovery
  uv run python scripts/popup_harness.py load
  uv run python scripts/popup_harness.py save
  uv run python scripts/popup_harness.py menu
"""

import sys

from kivy.clock import Clock

from katrain.__main__ import KaTrainApp


def main() -> None:
    which = (sys.argv[1] if len(sys.argv) > 1 else "config").strip().lower()

    class HarnessApp(KaTrainApp):
        def on_start(self):
            def after_ready():
                self.gui.start()

                def open_popup(_dt):
                    if which == "config":
                        self.gui._do_config_popup()
                    elif which == "ai":
                        self.gui._do_ai_popup()
                    elif which == "ai-human":
                        self.gui._do_ai_popup()
                        popup = self.gui.popup_open
                        if popup and getattr(popup, "content", None) and hasattr(popup.content, "_strategy_select"):
                            popup.content._strategy_select.select_key("ai:human")
                    elif which == "ai-proyear":
                        self.gui._do_ai_popup()
                        popup = self.gui.popup_open
                        if popup and getattr(popup, "content", None) and hasattr(popup.content, "_strategy_select"):
                            popup.content._strategy_select.select_key("ai:human")
                            if hasattr(popup.content, "_human_profile"):
                                popup.content._human_profile.select_key("proyear")
                    elif which == "newgame":
                        self.gui._do_new_game_popup()
                    elif which == "teacher":
                        self.gui._do_teacher_popup()
                    elif which == "recovery":
                        self.gui._do_engine_recovery_popup("Test engine error", "TEST")
                    elif which == "load":
                        self.gui._do_analyze_sgf_popup()
                    elif which == "save":
                        self.gui._do_save_game_as_popup()
                    elif which == "menu":
                        self.gui.nav_drawer.set_state("open")
                    else:
                        # Unknown selector: just show the main window.
                        pass

                    # Don't hang forever when running this from a terminal.
                    Clock.schedule_once(lambda _dt2: self.stop(), 6)

                Clock.schedule_once(open_popup, 0.1)

            self.gui.ensure_engine_ready(after_ready)

    HarnessApp().run()


if __name__ == "__main__":
    main()

