from __future__ import annotations

import copy
import os
import platform
import shlex

from katago_client import JsonKataGoClient

from katrain.core.constants import (
    OUTPUT_ERROR,
    DATA_FOLDER,
    RULESETS,
    RULESETS_ABBR,
)
from katrain.core.platform import APP_PLATFORM
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move
from katrain.core.utils import find_package_resource


class BaseEngine:  # some common elements between analysis and contribute engine

    RULESETS_ABBR = RULESETS_ABBR
    RULESETS = RULESETS

    def __init__(self, katrain, config):
        self.katrain = katrain
        self.config = config

    @staticmethod
    def get_rules(ruleset):
        return JsonKataGoClient.get_rules(ruleset)

    def advance_showing_game(self):
        pass  # avoid transitional error

    def status(self):
        return ""  # avoid transitional error

    def get_engine_path(self, exe):
        if not exe:
            # v2: KataGo binaries are no longer bundled in the package; prefer a local download in ~/.katrain.
            data_dir = os.path.abspath(os.path.expanduser(DATA_FOLDER))
            local_name = "katago.exe" if APP_PLATFORM == "win" else "katago"
            local_exe = os.path.join(data_dir, local_name)
            if os.path.isfile(local_exe):
                exe = local_exe
            elif APP_PLATFORM == "win":
                exe = "katrain/KataGo/katago.exe"
            elif APP_PLATFORM == "linux":
                exe = "katrain/KataGo/katago"
            else:
                exe = find_package_resource("katrain/KataGo/katago-osx")  # github actions built
                if not os.path.isfile(exe) or "arm64" in platform.version().lower():
                    exe = "katago"  # e.g. MacOS after brewing

        if exe.startswith("katrain"):
            resolved = find_package_resource(exe)
            if os.path.isfile(resolved):
                exe = resolved
            else:
                # Legacy config pointing at bundled binaries - fall back to PATH.
                exe = "katago.exe" if APP_PLATFORM == "win" else "katago"
        exepath, exename = os.path.split(exe)
        if exepath:
            # Support configs like "~/.katrain/katago" (bootstrapper default) and other user paths.
            exe = os.path.abspath(os.path.expanduser(exe))
            exepath, exename = os.path.split(exe)

        if exepath and not os.path.isfile(exe):
            self.on_error(i18n._("Kata exe not found").format(exe=exe), "KATAGO-EXE")
            return None
        elif not exepath:
            paths = os.getenv("PATH", ".").split(os.pathsep) + ["/opt/homebrew/bin/"]
            exe_with_paths = [os.path.join(path, exe) for path in paths if os.path.isfile(os.path.join(path, exe))]
            if not exe_with_paths:
                self.on_error(i18n._("Kata exe not found in path").format(exe=exe), "KATAGO-EXE")
                return None
            exe = exe_with_paths[0]
        return exe

    def on_error(self, message, code, allow_popup):
        print("ERROR", message, code)


class KataGoEngine(BaseEngine, JsonKataGoClient):
    """Starts and communicates with the KataGO analysis engine"""

    PONDER_KEY = "_kt_continuous"

    def __init__(self, katrain, config):
        super().__init__(katrain, config)
        if config.get("altcommand", ""):
            command = config["altcommand"]
        else:
            model = find_package_resource(config["model"])
            cfg = find_package_resource(config["config"])
            exe = self.get_engine_path(config.get("katago", "").strip())

            if not exe:
                self.command = None
                return

            # Add human model to command if provided
            if config.get("humanlike_model", ""):
                human_model_path = find_package_resource(config.get("humanlike_model", ""))
                if os.path.isfile(human_model_path):
                    command = shlex.split(
                        f'"{exe}" analysis -model "{model}" -human-model "{human_model_path}" -config "{cfg}" -override-config "homeDataDir={os.path.expanduser(DATA_FOLDER)}"'
                    )
                else:
                    self.katrain.log(f"Human model not found at {human_model_path}", -1)
                    # Fall back to regular command without human model
                    command = shlex.split(
                        f'"{exe}" analysis -model "{model}" -config "{cfg}" -override-config "homeDataDir={os.path.expanduser(DATA_FOLDER)}"'
                    )
            else:
                # Regular command without human model
                command = shlex.split(
                    f'"{exe}" analysis -model "{model}" -config "{cfg}" -override-config "homeDataDir={os.path.expanduser(DATA_FOLDER)}"'
                )
        self.command = command
        JsonKataGoClient.__init__(
            self,
            command,
            config,
            logger=self.katrain.log,
            on_error=self.on_error,
            allow_recovery=self.config.get("allow_recovery", True),
        )

    def on_error(self, message, code=None, allow_popup=True):
        self.katrain.log(message, OUTPUT_ERROR)
        if self.allow_recovery and allow_popup:
            self.katrain("engine_recovery_popup", message, code)

    def request_analysis(
        self,
        analysis_node: GameNode,
        callback,
        error_callback=None,
        visits: int = None,
        analyze_fast: bool = False,
        time_limit=True,
        find_alternatives: bool = False,
        priority: int = 0,
        ponder=False,  # infinite visits, cancellable
        ownership: bool | None = None,
        next_move: GameNode | None = None,
        extra_settings: dict | None = None,
        include_policy=True,
        report_every: float | None = None,
    ):
        return JsonKataGoClient.request_analysis(
            self,
            analysis_node,
            callback=callback,
            error_callback=error_callback,
            visits=visits,
            analyze_fast=analyze_fast,
            time_limit=time_limit,
            find_alternatives=find_alternatives,
            priority=priority,
            ponder=ponder,
            ownership=ownership,
            next_move=next_move,
            extra_settings=extra_settings,
            include_policy=include_policy,
            report_every=report_every,
        )
