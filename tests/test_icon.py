import numpy as np
from PIL import Image

from volleyball_stats import icon


def logo(path, *colours):
    """A logo of vertical bands, white around them."""
    image = Image.new("RGBA", (120, 60), "#ffffff")
    for k, colour in enumerate(colours):
        image.paste(colour, (10 + 40 * k, 10, 40 + 40 * k, 50))
    image.save(path)
    return path


class TestIcon:
    def test_takes_the_logos_two_colours_the_darker_on_top(self, tmp_path):
        logo(tmp_path / "logo.png", "#d01214", "#2c2b79")
        assert icon.colours({"logo": "logo.png", "accent": "#e30613"}, tmp_path) == ("#2c2b79", "#d01214")

    def test_leaves_out_white_black_and_grey(self, tmp_path):
        logo(tmp_path / "logo.png", "#000000", "#808080", "#d01214")
        assert icon.logo_colours(tmp_path / "logo.png") == ["#d01214"]

    def test_falls_back_on_the_main_colour_then_the_apps(self, tmp_path):
        pair = icon.colours({"logo": None, "accent": "#e30613"}, tmp_path)
        assert "#e30613" in pair and len(set(pair)) == 2
        assert icon.colours(None) == icon.DEFAULT

    def test_does_without_an_unreadable_logo(self, tmp_path):
        (tmp_path / "logo.png").write_bytes(b"not a picture")
        assert "#e30613" in icon.colours({"logo": "logo.png", "accent": "#e30613"}, tmp_path)

    def test_draws_a_ball_on_a_clear_background(self):
        image = np.asarray(icon.render(icon.DEFAULT, 64))
        assert image.shape == (64, 64, 4)
        assert image[0, 0, 3] == 0 and image[32, 32, 3] == 255

    def test_puts_the_colours_in_the_favicon(self):
        url = icon.favicon(("#2c2b79", "#d01214"))
        assert url.startswith("data:image/svg+xml,") and "%232c2b79" in url and "%23d01214" in url

    def test_writes_each_format(self, tmp_path):
        for suffix in (".png", ".ico", ".icns"):
            assert icon.write(icon.DEFAULT, tmp_path / f"i{suffix}").stat().st_size > 0
