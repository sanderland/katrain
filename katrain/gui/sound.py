from kivy.clock import Clock
from kivymd.app import MDApp
from kivy.core.audio import SoundLoader

cached_sounds = {}
last_sound = None, None

# prefer ffpyplayer, then others, never gst
try:
    SoundLoader._classes = sorted(
        [c for c in SoundLoader._classes if "gst" not in c.__name__.lower()], key=lambda cls: "FFPy" not in cls.__name__
    )
except Exception as e:
    print("Exception sorting sound loaders: ", e)


def play_sound(file, volume=1, cache=True):
    def _play(sound):
        global last_sound
        lf, ls = last_sound
        if ls is not None:
            ls.stop()
        if sound:
            sound.play()
            sound.seek(0)
        last_sound = file, sound

    app = MDApp.get_running_app()
    if app and app.gui and app.gui.config("timer/sound"):
        sound = cached_sounds.get(file)
        if sound is None:
            sound = SoundLoader.load(file)
            if cache:
                cached_sounds[file] = sound
        sound.volume = volume
        Clock.schedule_once(lambda _dt: _play(sound), 0)


def stop_sound(file):
    lf, ls = last_sound
    if lf == file:
        ls.stop()
