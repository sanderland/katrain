from kivy.lang import Builder
from kivy.metrics import sp
from kivy.properties import ObjectProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.app import MDApp
from kivymd.uix.menu import MDDropdownMenu, RightContent


class AnalysisDropdownMenuRightContent(RightContent):
    pass


class AnalysisDropdownMenu(MDDropdownMenu):
    pass


ANALYSIS_ICONS = ["git", "git", "git"]
ANALYSIS_OPTIONS = ["aaa", "bbb", "ccc"]
ANALYSIS_SHORTCUTS = ["a", "s", "d"]


class MenuOpener(BoxLayout):
    analysis_button = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        menu_items = [
            {"icon": icon, "text": text, "right_content_cls": AnalysisDropdownMenuRightContent(text=shortcut)}
            for icon, text, shortcut in zip(ANALYSIS_ICONS, ANALYSIS_OPTIONS, ANALYSIS_SHORTCUTS)
        ]
        self.analysis_menu = AnalysisDropdownMenu(caller=self.analysis_button, items=menu_items, width_mult=6, use_icon_item=False, callback=lambda _: print(_),)

    def open_analysis_menu(self):
        self.analysis_menu.open()


KV = """
               
<AnalysisDropdownMenuRightContent>:
    Label:
        width: dp(30)
        text: root.text
        color: [1,0,1,1]
                    
<MenuOpener>:
    analysis_button:analysis_button
    Button:
        id: analysis_button
        text:'open!'
        on_press: root.open_analysis_menu()
    Label:
        text: 'text'
"""


Builder.load_string(KV)


class MenuApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def build(self):
        return MenuOpener()


MenuApp().run()
