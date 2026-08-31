from gitten.git_watcher import is_git_repo


def test_directory_with_git_folder_is_a_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    assert is_git_repo(tmp_path) is True


def test_directory_without_git_folder_is_not_a_repo(tmp_path):
    assert is_git_repo(tmp_path) is False


def test_git_as_a_file_not_a_directory_is_not_a_repo(tmp_path):
    # e.g. a git submodule/worktree, where `.git` is a file pointing
    # elsewhere rather than the real directory -- deliberately not treated
    # as a match here, matching GitWatcher.set_repo's existing behavior.
    (tmp_path / ".git").write_text("gitdir: ../elsewhere", encoding="utf-8")
    assert is_git_repo(tmp_path) is False


def test_nonexistent_path_is_not_a_repo(tmp_path):
    assert is_git_repo(tmp_path / "does_not_exist") is False


def test_accepts_string_path(tmp_path):
    (tmp_path / ".git").mkdir()
    assert is_git_repo(str(tmp_path)) is True
