import os

from volleyball_stats import git_check

# The commands the tests start (`python -m volleyball_stats.X`) fetch no git remote.
os.environ[git_check.CHECKED_ENV] = "1"
