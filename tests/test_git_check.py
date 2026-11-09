import subprocess

from volleyball_stats import git_check


class TestBehindWarning:
    @staticmethod
    def git(cwd, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)

    def clones(self, tmp_path):
        """A remote, and two clones of it on main."""
        self.git(tmp_path, "init", "--bare", "-b", "main", "remote.git")
        for name in ("here", "other"):
            self.git(tmp_path, "clone", "remote.git", name)
        self.git(tmp_path / "other", "commit", "--allow-empty", "-m", "first")
        self.git(tmp_path / "other", "push", "origin", "main")
        self.git(tmp_path / "here", "pull")
        return tmp_path / "here", tmp_path / "other"

    def test_none_when_up_to_date(self, tmp_path):
        here, _ = self.clones(tmp_path)

        assert git_check.behind_warning(here) is None

    def test_fetches_then_counts_the_missing_commits(self, tmp_path):
        here, other = self.clones(tmp_path)
        for message in ("a", "b"):
            self.git(other, "commit", "--allow-empty", "-m", message)
        self.git(other, "push")

        assert git_check.behind_warning(here) == "Warning: main is 2 commits behind origin/main: run git pull --rebase."

    def test_says_when_diverged(self, tmp_path):
        here, other = self.clones(tmp_path)
        self.git(other, "commit", "--allow-empty", "-m", "a")
        self.git(other, "push")
        self.git(here, "commit", "--allow-empty", "-m", "b")

        assert git_check.behind_warning(here) == "Warning: main is 1 commit behind origin/main and 1 ahead: run git pull --rebase."

    def test_none_without_upstream(self, tmp_path):
        self.git(tmp_path, "init", "-b", "main")

        assert git_check.behind_warning(tmp_path) is None
