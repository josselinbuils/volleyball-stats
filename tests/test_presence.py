from volleyball_stats import presence


class Clock:
    def __init__(self):
        self.at = 0.0

    def __call__(self):
        return self.at


def pages():
    clock = Clock()
    return presence.Presence(clock), clock


class TestPresence:
    def test_waits_for_the_first_window(self):
        open_, clock = pages()
        clock.at = presence.START_S - 1
        assert not open_.closed()
        clock.at = presence.START_S
        assert open_.closed()

    def test_closes_soon_after_the_last_window_goes(self):
        open_, clock = pages()
        open_.seen("a")
        open_.seen("b")
        open_.left("a")
        clock.at = 100
        assert not open_.closed()
        open_.left("b")
        clock.at += presence.AFTER_LEAVING_S - 1
        assert not open_.closed()
        clock.at += 1
        assert open_.closed()

    def test_stays_for_a_page_coming_back(self):
        open_, clock = pages()
        open_.seen("a")
        clock.at = 100
        open_.left("a")
        clock.at += 1
        open_.seen("b")
        clock.at += presence.AFTER_LEAVING_S
        assert not open_.closed()

    def test_forgets_a_page_gone_silent(self):
        open_, clock = pages()
        open_.seen("a")
        clock.at = presence.SILENT_S - 1
        assert not open_.closed()
        clock.at = presence.SILENT_S
        assert open_.closed()
