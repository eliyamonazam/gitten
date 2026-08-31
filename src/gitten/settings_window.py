"""The settings panel (v1.11): the first *normal* window in this app.

Every other window (`KittenWindow`, `MouseWindow`, `CommandBarWindow`)
deliberately uses the frameless/always-on-top/transparent/tool-window flag
combination because each of them is an overlay-style pet/game/popup widget.
This one is an ordinary `QDialog` on purpose -- a normal title bar, normal
close/minimize behavior, not always-on-top, not click-through, not
transparent -- per `GITTEN_V1_11_SPEC.md`'s explicit instruction not to copy
that precedent here.

This window owns no state of its own beyond the widgets themselves: every
Save button calls straight into the *same* apply/persist logic the rest of
`GittenApp` already uses (`_apply_rename`, `_apply_birthday`,
`_prompt_choose_repo`, `_handle_cancel_command`, and the new
`_apply_distraction_config` / `_apply_focus_config` / `_apply_telegram_lists`
helpers added alongside this file) rather than re-implementing any of it
here -- each of those helpers is also responsible for pushing the change
into whatever live in-memory state the running app actually reads from, not
just writing the JSON file, so a Save here takes effect immediately without
a restart.

Each tab has its own Save button (rather than one dialog-wide Save) since
each tab edits an independent config surface with its own persistence file
-- saving one tab's list edits shouldn't require also committing whatever's
mid-edit in another tab. The Reminders tab has no Save button at all: it's
a live view with an immediate per-row Cancel action (reusing
`_handle_cancel_command`), not something you stage and commit.

v1.13 styles this window from `theme.py`, this app's shared design system
-- purely visual, no behavior changed: every button/tab/list/line-edit
picks up the shared palette via `theme.apply_theme(self)`, each tab's Save
button is tagged `theme.mark_primary_button(...)` so it reads as this
screen's one clear action, and field labels/status text are tagged
`mark_section_header`/`mark_muted_label` for a bit of visual hierarchy a
flat list of identical `QLabel`s didn't have before.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gitten import theme
from gitten.reminders import format_reminder_row, sorted_by_due
from gitten.telegram_lists import DEFAULT_TELEGRAM_LISTS_PATH, load_telegram_lists

_WINDOW_SIZE = (460, 640)


class SettingsWindow(QDialog):
    def __init__(self, app) -> None:
        super().__init__(None)
        self._app = app
        self.setWindowTitle("Gitten Settings")
        self.setWindowFlags(Qt.Window)
        self.resize(*_WINDOW_SIZE)
        theme.apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.SPACING_MD, theme.SPACING_MD, theme.SPACING_MD, theme.SPACING_MD)
        layout.setSpacing(theme.SPACING_SM)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_general_tab(), "General")
        self._tabs.addTab(self._build_distraction_tab(), "Distraction")
        self._tabs.addTab(self._build_focus_tab(), "Focus")
        self._tabs.addTab(self._build_telegram_tab(), "Telegram")
        self._reminders_tab_widget = self._build_reminders_tab()
        self._tabs.addTab(self._reminders_tab_widget, "Reminders")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    # -- shared helpers -----------------------------------------------------

    def _build_list_editor(self, initial_items: list[str]) -> tuple[QWidget, QListWidget]:
        """A QListWidget plus Add/Remove buttons -- the same small editor
        shape reused for every string-list config surface in this dialog
        (distraction titles/processes, the focus substring list, the
        Telegram favorite/bad lists)."""
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        list_widget.addItems(initial_items)
        column.addWidget(list_widget)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add...")
        remove_button = QPushButton("Remove")
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addStretch()
        column.addLayout(button_row)

        def _add() -> None:
            text, ok = QInputDialog.getText(self, "Add entry", "Value:")
            if ok and text.strip():
                list_widget.addItem(text.strip())

        def _remove() -> None:
            for item in list_widget.selectedItems():
                list_widget.takeItem(list_widget.row(item))

        add_button.clicked.connect(_add)
        remove_button.clicked.connect(_remove)
        return container, list_widget

    @staticmethod
    def _list_items(list_widget: QListWidget) -> list[str]:
        return [list_widget.item(i).text() for i in range(list_widget.count())]

    @staticmethod
    def _header(text: str) -> QLabel:
        """A field/section label styled per `theme.py`'s `sectionHeader`
        rule -- a small helper so every tab tags its labels the same way
        rather than repeating the `QLabel(...)` + `mark_section_header`
        pair at each call site."""
        label = QLabel(text)
        theme.mark_section_header(label)
        return label

    @staticmethod
    def _muted(text: str) -> QLabel:
        """A secondary/transient label (a "Saved." confirmation) styled
        per `theme.py`'s `muted` rule."""
        label = QLabel(text)
        theme.mark_muted_label(label)
        return label

    def _on_tab_changed(self, index: int) -> None:
        if self._tabs.widget(index) is self._reminders_tab_widget:
            self._refresh_reminders_tab()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Reopening the (reused) dialog should always reflect whatever's
        # actually true right now -- the cat could have been renamed, the
        # repo changed, or reminders set/cancelled via the command bar since
        # this window was last shown.
        self._refresh_repo_label()
        self._name_edit.setText(self._app.cat_name)
        self._birthday_edit.setText(self._app.birthday.isoformat() if self._app.birthday else "")
        if self._tabs.currentWidget() is self._reminders_tab_widget:
            self._refresh_reminders_tab()

    # -- General --------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(theme.SPACING_SM)

        layout.addWidget(self._header("Watched repository:"))
        repo_row = QHBoxLayout()
        self._repo_label = QLabel()
        self._repo_label.setWordWrap(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_repo)
        repo_row.addWidget(self._repo_label, stretch=1)
        repo_row.addWidget(browse_button)
        layout.addLayout(repo_row)
        self._refresh_repo_label()

        layout.addSpacing(theme.SPACING_MD)
        layout.addWidget(self._header("Cat's name:"))
        self._name_edit = QLineEdit(self._app.cat_name)
        layout.addWidget(self._name_edit)

        layout.addWidget(self._header("Cat's birthday (YYYY-MM-DD):"))
        self._birthday_edit = QLineEdit(
            self._app.birthday.isoformat() if self._app.birthday else ""
        )
        layout.addWidget(self._birthday_edit)

        save_row = QHBoxLayout()
        save_button = QPushButton("Save")
        theme.mark_primary_button(save_button)
        save_button.clicked.connect(self._save_general)
        save_row.addWidget(save_button)
        self._general_status = self._muted("")
        save_row.addWidget(self._general_status)
        save_row.addStretch()
        layout.addLayout(save_row)
        layout.addStretch()
        return widget

    def _refresh_repo_label(self) -> None:
        repo_path = self._app.watcher.repo_path
        self._repo_label.setText(str(repo_path) if repo_path else "(no repo chosen)")

    def _browse_repo(self) -> None:
        # Reuses the exact same file-dialog + git-repo validation +
        # persist + tooltip-refresh flow the tray's own "Choose watched
        # repo..." action already uses, rather than a parallel path here --
        # it applies live immediately, so there's no separate Save step for
        # this field.
        self._app._prompt_choose_repo(required=False)
        self._refresh_repo_label()

    def _save_general(self) -> None:
        name = self._name_edit.text().strip()
        if name:
            self._app._apply_rename(name)
        birthday_text = self._birthday_edit.text().strip()
        if birthday_text:
            self._app._apply_birthday(birthday_text)
        self._general_status.setText("Saved.")

    # -- Distraction ------------------------------------------------------

    def _build_distraction_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(theme.SPACING_SM)

        layout.addWidget(self._header("Distracting window titles (substring match):"))
        titles_editor, self._distraction_titles_list = self._build_list_editor(
            list(self._app.distracting_titles)
        )
        layout.addWidget(titles_editor)

        layout.addWidget(self._header("Distracting processes (exact match):"))
        processes_editor, self._distraction_processes_list = self._build_list_editor(
            list(self._app.distracting_processes)
        )
        layout.addWidget(processes_editor)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self._header("Nudge after (minutes):"))
        self._distraction_threshold_spin = QSpinBox()
        self._distraction_threshold_spin.setRange(1, 1440)
        self._distraction_threshold_spin.setValue(
            max(1, round(self._app.distraction_tracker.threshold_seconds / 60.0))
        )
        threshold_row.addWidget(self._distraction_threshold_spin)
        threshold_row.addStretch()
        layout.addLayout(threshold_row)

        save_row = QHBoxLayout()
        save_button = QPushButton("Save")
        theme.mark_primary_button(save_button)
        save_button.clicked.connect(self._save_distraction)
        save_row.addWidget(save_button)
        self._distraction_status = self._muted("")
        save_row.addWidget(self._distraction_status)
        save_row.addStretch()
        layout.addLayout(save_row)
        return widget

    def _save_distraction(self) -> None:
        titles = self._list_items(self._distraction_titles_list)
        processes = self._list_items(self._distraction_processes_list)
        threshold_minutes = self._distraction_threshold_spin.value()
        self._app._apply_distraction_config(titles, processes, threshold_minutes)
        self._distraction_status.setText("Saved.")

    # -- Focus ------------------------------------------------------------

    def _build_focus_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(theme.SPACING_SM)

        layout.addWidget(self._header("Test/build process command-line substrings:"))
        editor, self._focus_list = self._build_list_editor(list(self._app.focus_substrings))
        layout.addWidget(editor)

        save_row = QHBoxLayout()
        save_button = QPushButton("Save")
        theme.mark_primary_button(save_button)
        save_button.clicked.connect(self._save_focus)
        save_row.addWidget(save_button)
        self._focus_status = self._muted("")
        save_row.addWidget(self._focus_status)
        save_row.addStretch()
        layout.addLayout(save_row)
        return widget

    def _save_focus(self) -> None:
        substrings = self._list_items(self._focus_list)
        self._app._apply_focus_config(substrings)
        self._focus_status.setText("Saved.")

    # -- Telegram -----------------------------------------------------------

    def _build_telegram_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(theme.SPACING_SM)

        note = self._muted(
            "Configures who gets a reaction once Telegram is connected -- "
            "the connection itself is still pending (see DEVELOPMENT_NOTES.md, "
            "v1.3)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        favorites, bad = load_telegram_lists(DEFAULT_TELEGRAM_LISTS_PATH)

        layout.addWidget(self._header("Favorite senders:"))
        fav_editor, self._telegram_favorites_list = self._build_list_editor(favorites)
        layout.addWidget(fav_editor)

        layout.addWidget(self._header("Bad senders:"))
        bad_editor, self._telegram_bad_list = self._build_list_editor(bad)
        layout.addWidget(bad_editor)

        save_row = QHBoxLayout()
        save_button = QPushButton("Save")
        theme.mark_primary_button(save_button)
        save_button.clicked.connect(self._save_telegram)
        save_row.addWidget(save_button)
        self._telegram_status = self._muted("")
        save_row.addWidget(self._telegram_status)
        save_row.addStretch()
        layout.addLayout(save_row)
        return widget

    def _save_telegram(self) -> None:
        favorites = self._list_items(self._telegram_favorites_list)
        bad = self._list_items(self._telegram_bad_list)
        self._app._apply_telegram_lists(favorites, bad)
        self._telegram_status.setText("Saved.")

    # -- Reminders ------------------------------------------------------

    def _build_reminders_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        self._reminders_container = QWidget()
        self._reminders_container_layout = QVBoxLayout(self._reminders_container)
        self._reminders_container_layout.setContentsMargins(0, 0, 0, 0)
        self._reminders_container_layout.setSpacing(theme.SPACING_SM)
        outer.addWidget(self._reminders_container)
        outer.addStretch()
        self._refresh_reminders_tab()
        return widget

    def _refresh_reminders_tab(self) -> None:
        while self._reminders_container_layout.count():
            item = self._reminders_container_layout.takeAt(0)
            row_widget = item.widget()
            if row_widget is not None:
                row_widget.deleteLater()

        reminders = sorted_by_due(self._app.reminders)
        if not reminders:
            self._reminders_container_layout.addWidget(self._muted("No pending reminders."))
            return

        now = time.time()
        for reminder in reminders:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel(format_reminder_row(reminder, now)), stretch=1)
            cancel_button = QPushButton("Cancel")
            cancel_button.clicked.connect(
                lambda checked=False, rid=reminder.id: self._cancel_reminder(rid)
            )
            row_layout.addWidget(cancel_button)
            self._reminders_container_layout.addWidget(row)

    def _cancel_reminder(self, reminder_id: int) -> None:
        # Reuses the exact same cancel path the `cancel <id>` command-bar
        # command already calls, rather than reimplementing the
        # remove-from-list + persist logic here.
        self._app._handle_cancel_command(str(reminder_id))
        self._refresh_reminders_tab()
