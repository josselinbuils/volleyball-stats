import json

from volleyball_stats import analysis


class TestCode:
    def test_comments_layout_and_docstrings_change_nothing(self, tmp_path):
        a, b, c = (tmp_path / n for n in ("a.py", "b.py", "c.py"))
        a.write_text('def f(x):\n    """Twice."""\n    return 2 * x\n')
        b.write_text("def f(x):\n    # twice\n    return 2*x\n")
        c.write_text("def f(x):\n    return 3 * x\n")

        assert analysis.code(a) == analysis.code(b) != analysis.code(c)


class TestModules:
    def test_the_pipeline_and_what_it_imports_without_the_pages(self):
        names = {p.stem for p in analysis.modules()}

        assert {"match", "actions", "attribution", "rallies"} <= names
        assert not names & {"web", "review", "app"}


class TestMadeBy:
    def test_what_the_last_run_wrote_none_before_any(self, tmp_path):
        assert analysis.made_by(tmp_path) is None
        analysis.write(tmp_path, "abc")

        assert analysis.made_by(tmp_path) == "abc"
        assert json.loads((tmp_path / analysis.FILE).read_text()) == {"code": "abc"}
