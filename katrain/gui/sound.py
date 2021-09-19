from kivy.clock import Clock
from kivymd.app import MDApp
from kivy.core.audio import SoundLoader
from kivy.utils import platform

cached_sounds = {}

# prefer ffpyplayer on linux, then others, avoid gst and avoid or ffpyplayer on windows
ranking = [("ffpy", 98 if platform in ["win", "macosx"] else -2), ("sdl", -1), ("gst", 99), ("", 0)]
try:
    SoundLoader._classes.sort(key=lambda cls: [v for k, v in ranking if k in cls.__name__.lower()][0])
except Exception as e:
    print("Exception sorting sound loaders: ", e)  # private vars, so could break with versions etc


def play_sound(file, volume=1, cache=True):
    def _play(sound):
        if sound:
            sound.play()
            sound.seek(0)

    app = MDApp.get_running_app()
    if app and app.gui and app.gui.config("timer/sound"):
        sound = cached_sounds.get(file)
        if sound is None:
            sound = SoundLoader.load(file)
            if cache:
                cached_sounds[file] = sound
        if sound is not None:
            sound.volume = volume
            Clock.schedule_once(lambda _dt: _play(sound), 0)


def stop_sound(file):
    sound = cached_sounds.get(file)
    if sound:
        sound.stop()
