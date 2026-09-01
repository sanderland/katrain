from katrain.gui.widgets.panels import PlayerInfo


def test_player_info_refreshes_its_label_after_kv_build():
    refreshed = []

    class PlayerInfoAfterKv:
        def set_label(self):
            refreshed.append(True)

    PlayerInfo.on_kv_post(PlayerInfoAfterKv(), None)

    assert refreshed == [True]
