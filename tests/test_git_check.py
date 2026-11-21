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


class TestCommitsSince:
    @staticmethod
    def repo(tmp_path):
        def commit(text: str, subject: str) -> str:
            (tmp_path / "page.html").write_text(text)
            subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
            subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", subject], check=True)
            return git_check.hashlib.sha256(text.encode()).hexdigest()[:16]

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        return commit

    def test_the_commits_after_the_version_sent_newest_first_by_short_subject(self, tmp_path):
        commit = self.repo(tmp_path)
        sent = commit("a\n", "feat: the first page")
        commit("b\n", "feat: the net drawn thinner (net.ts); fix: x")
        now = commit("c\n", 'fix: the question "Haut : d\'une main ?": details')
        (tmp_path / "other.txt").write_text("x")

        found = git_check.commits_since(tmp_path / "page.html", sent, now)

        assert [subject for _, subject in found] == ['the question "Haut : d\'une main ?"', "the net drawn thinner"]
        assert git_check.commits_since(tmp_path / "page.html", now, now) == []

    def test_a_version_not_in_the_history_or_no_history_tells_nothing(self, tmp_path):
        commit = self.repo(tmp_path / "repo")
        commit("a\n", "feat: a")

        assert git_check.commits_since(tmp_path / "repo" / "page.html", "0123456789abcdef", "x") is None
        (tmp_path / "alone").mkdir()
        assert git_check.commits_since(tmp_path / "alone" / "page.html", "0123456789abcdef", "x") is None

    def test_a_checkout_with_windows_line_ends_finds_its_version(self, tmp_path):
        commit = self.repo(tmp_path)
        commit("a\n", "feat: a")
        commit("b\n", "feat: b")

        assert [s for _, s in git_check.commits_since(tmp_path / "page.html", git_check.hashlib.sha256(b"a\r\n").hexdigest()[:16], "y")] == ["b"]
