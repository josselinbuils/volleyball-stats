import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def outline(text: str) -> dict:
    """What two translations of a page share: heading levels, images, links (the language switch and the badges, whose
    words are translated, aside), commands."""
    commands = re.findall(r"```(\w*)\n(.*?)```", text, re.S)
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    links = [target for target in re.findall(r"\]\(([^)]+)\)", prose) if not target.startswith(("README", "https://img.shields.io/"))]
    return {
        "headings": [len(level) for level in re.findall(r"^(#+) ", prose, re.M)],
        "images": re.findall(r'<img src="([^"]+)"', prose),
        "links": links,
        "commands": [(kind, "\n".join(line.split("#")[0].rstrip() for line in body.splitlines())) for kind, body in commands if kind != "mermaid"],
        "diagram": [body.count("-->") for kind, body in commands if kind == "mermaid"],
    }


class TestReadme:
    def test_the_french_readme_follows_the_english_one(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        french = (ROOT / "README.fr.md").read_text(encoding="utf-8")
        # Updated together (CLAUDE.md): a section, picture, link or command in one only is a forgotten translation.
        assert outline(french) == outline(english)
        assert "[Français](README.fr.md)" in english and "[English](README.md)" in french

    def test_the_release_page_says_the_same_in_both_languages(self):
        text = (ROOT / "packaging/release/release.md").read_text(encoding="utf-8")
        french, english = text.split("\n## Français\n")[1].split("\n## English\n")
        assert outline(french) == outline(english)
