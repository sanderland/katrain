from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform

cached_sounds = {}
_audio_available = False

# prefer ffpyplayer on linux, then others, avoid gst and avoid or ffpyplayer on windows
ranking = [("ffplay", 98 if platform in ["win", "macosx"] else -2), ("sdl", -1), ("gst", 99), ("", 0)]
try:
    SoundLoader._classes.sort(key=lambda cls: [v for k, v in ranking if k in cls.__name__.lower()][0])
except Exception as e:
    print("Exception sorting sound loaders: ", e)  # private vars, so could break with versions etc


def preload_sounds(sound_dir):
    """Preload all sounds before the SDL2 window is created.

    SoundLoader.load() deadlocks when no audio output device is available,
    so we test audio in a subprocess first.
    """
    global _audio_available
    import os
    import sys
    import subprocess

    audio_files = [
        os.path.join(sound_dir, fn) for fn in os.listdir(sound_dir)
        if fn.endswith((".wav", ".ogg", ".mp3"))
    ]
    if not audio_files:
        return

    # Test if audio subsystem works by loading one sound in a subprocess
    try:
        subprocess.run(
            [sys.executable, "-c",
             f"from kivy.core.audio import SoundLoader; SoundLoader.load({audio_files[0]!r})"],
            timeout=3, capture_output=True,
        )
    except subprocess.TimeoutExpired as e:
        print(f"Warning: Audio unavailable ({e}). Sounds disabled.", file=sys.stderr)
        return

    # Audio works, preload all sounds
    for path in audio_files:
        cached_sounds[os.path.basename(path)] = SoundLoader.load(path)
    _audio_available = True


def play_sound(file, volume=1, cache=True):
    if not _audio_available:
        return

    from kivymd.app import MDApp
    app = MDApp.get_running_app()
    if app and app.gui and app.gui.config("timer/sound"):
        sound = cached_sounds.get(file)
        if sound is not None:
            sound.volume = volume
            sound.play()
            sound.seek(0)


def stop_sound(file):
    sound = cached_sounds.get(file)
    if sound:
        sound.stop()
