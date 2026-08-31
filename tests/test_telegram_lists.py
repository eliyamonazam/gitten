from gitten.telegram_lists import GITTEN_DIR, load_telegram_lists, save_telegram_lists


def test_default_path_lives_under_gitten_dir():
    from gitten.telegram_lists import DEFAULT_TELEGRAM_LISTS_PATH

    assert DEFAULT_TELEGRAM_LISTS_PATH.parent == GITTEN_DIR
    assert DEFAULT_TELEGRAM_LISTS_PATH.name == "telegram_lists.json"


def test_load_missing_file_returns_empty_lists(tmp_path):
    favorites, bad = load_telegram_lists(tmp_path / "does_not_exist.json")
    assert favorites == []
    assert bad == []


def test_load_invalid_json_returns_empty_lists(tmp_path):
    path = tmp_path / "telegram_lists.json"
    path.write_text("not valid json", encoding="utf-8")
    favorites, bad = load_telegram_lists(path)
    assert favorites == []
    assert bad == []


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "telegram_lists.json"
    save_telegram_lists(["alice", "42"], ["spammer_bot"], path)

    favorites, bad = load_telegram_lists(path)

    assert favorites == ["alice", "42"]
    assert bad == ["spammer_bot"]


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "a" / "b" / "telegram_lists.json"
    save_telegram_lists([], [], path)
    assert path.exists()
