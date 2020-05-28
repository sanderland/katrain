from kivy import Config
from kivy.storage.jsonstore import JsonStore
import os, sys
from katrain.core.utils import (
    OUTPUT_ERROR,
    OUTPUT_INFO,
    OUTPUT_KATAGO_STDERR,
    find_package_resource,
    OUTPUT_DEBUG,
    OUTPUT_EXTRA_DEBUG,
)


class KaTrainSettings:
    CONFIG_FILE = "katrain/config.json"

    """Settings and logging functionality, so other classes who need a katrain instance can be used without a GUI"""

    def __init__(self, **kwargs):
        self.debug_level = 0
        self.logger = lambda message, level=OUTPUT_INFO: self.log(message, level)
        self.config_file = self._load_config()
        self.debug_level = self.config("general/debug_level", OUTPUT_INFO)

        Config.set("kivy", "log_level", "error")
        if self.debug_level >= OUTPUT_DEBUG:
            Config.set("kivy", "log_enable", 1)
            Config.set("kivy", "log_level", "warning")

    #        if self.debug_level >= OUTPUT_EXTRA_DEBUG:
    #            Config.set("kivy", "log_level", "trace")

    def log(self, message, level=OUTPUT_INFO):
        if level == OUTPUT_ERROR:
            print(f"ERROR: {message}", sys.stderr)
        elif self.debug_level >= level:
            print(message)

    def _load_config(self):
        config_file = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else find_package_resource(self.CONFIG_FILE))
        try:
            self.log(f"Using config file {config_file}", OUTPUT_INFO)
            self._config_store = JsonStore(config_file, indent=4)
            self._config = dict(self._config_store)
            return config_file
        except Exception as e:
            self.log(f"Failed to load config {config_file}: {e}", OUTPUT_ERROR)
            sys.exit(1)

    def save_config(self):
        for k, v in self._config.items():
            self._config_store.put(k, **v)

    def config(self, setting, default=None):
        try:
            if "/" in setting:
                cat, key = setting.split("/")
                return self._config[cat].get(key, default)
            else:
                return self._config[setting]
        except KeyError:
            self.log(f"Missing configuration option {setting}", OUTPUT_ERROR)
