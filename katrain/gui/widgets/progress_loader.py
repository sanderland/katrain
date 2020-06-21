# From KivyMD which will remove it in their next version, with some fixes
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.network.urlrequest import UrlRequest
from kivy.lang import Builder
from kivy.properties import StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout

Builder.load_string(
    """
#:import Window kivy.core.window.Window


<ProgressLoader>
    opacity: 0
    spacing: 10
    MDSpinner
        id: spinner
        size_hint: None, 0.8
        width: dp(32)
        color: 0.95,0.95,0.95,1
    MDLabel:
        id: label_download
        shorten: True
        max_lines: 1
        halign: 'left'
        valign: 'center'
        text_size: self.size
        color: 0.95,0.95,0.95,1
        text: root.label_downloading_text
"""
)


class ProgressLoader(BoxLayout):
    path_to_file = StringProperty()
    """The path to which the uploaded file will be saved."""

    download_url = StringProperty()
    """Link to uploaded file."""

    label_downloading_text = StringProperty("Downloading...")
    """Default text before downloading."""

    downloading_text = StringProperty("Downloading: {}%")
    """Progress text of the downloaded file."""

    download_complete = ObjectProperty()
    """Function, called after a successful file upload."""
    download_redirected = ObjectProperty()
    """Function, called after a redirect event."""

    request = ObjectProperty()
    """UrlRequest object."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_instance = None

    def start(self, root_instance):
        self.root_instance = root_instance
        self.root_instance.add_widget(self)
        self.request_download_file(self.download_url, self.path_to_file)
        Clock.schedule_once(self.animation_show, 1)

    def animation_show(self, _dt):
        animation = Animation(opacity=1, d=0.2, t="out_quad",)
        animation.start(self)

    def request_download_file(self, url, path):
        """
        :type url: str;
        :param url: link to content;

        :type path: str;
        :param path: path to save content;
        """

        self.request = UrlRequest(
            url,
            file_path=path,
            chunk_size=102400,
            on_progress=self.update_progress,
            on_success=self.on_success,
            on_redirect=self.redirected,
            on_error=self.download_error,
        )

    def redirected(self, request, *_args):
        new_url = request.resp_headers.get("location")
        if new_url:
            self.download_url = new_url
            self.request_download_file(self.download_url, self.path_to_file)
        if self.download_redirected:
            self.download_redirected(request)

    def download_error(self, request, *_args):
        pass

    def update_progress(self, request, current_size, total_size):
        if total_size < 1e4:
            current_size = 0
        percent = current_size * 100 // max(total_size, 1)
        self.label_downloading_text = self.downloading_text.format(percent)

    def on_success(self, request, result):
        self.root_instance.remove_widget(self)
        if self.download_complete:
            self.download_complete(request)
