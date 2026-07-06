#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown設計書ビューア/簡易IDE
--------------------------------
要件1: 左側にファイルツリー表示 + 全て閉じるボタン
要件2: 選択したファイルをMarkdown整形(プレビュー)表示
要件3: 中央にMarkdown表示 + grep(全文検索)機能
その他: 目次(アウトライン)表示, 生Markdown編集/保存, フォントサイズ変更,
        ダークモード切替, 文字数/行数ステータス表示
"""

import os
import re
import sys

from PySide6.QtCore import Qt, QDir
from PySide6.QtGui import QFont, QTextCursor, QAction, QKeySequence, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileSystemModel,
    QTreeView,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QTextBrowser,
    QPlainTextEdit,
    QStackedWidget,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QToolBar,
    QLabel,
    QMessageBox,
    QStatusBar,
    QInputDialog,
)


DARK_STYLE = """
QWidget { background-color: #1e1e1e; color: #d4d4d4; }
QTreeView, QListWidget, QPlainTextEdit, QTextBrowser {
    background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c;
}
QLineEdit { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; padding: 3px; }
QPushButton { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; padding: 4px 8px; }
QPushButton:hover { background-color: #505050; }
QToolBar { background-color: #2d2d2d; border: none; }
QDockWidget::title { background-color: #2d2d2d; padding: 4px; }
QStatusBar { background-color: #007acc; color: white; }
"""

LIGHT_STYLE = ""  # デフォルトスタイルに戻す


class MarkdownIDE(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Markdown設計書 簡易IDE")
        self.resize(1400, 900)

        self.current_root = os.getcwd()
        self.current_file = None
        self.font_size = 11
        self.dark_mode = False

        self._build_tree_dock()
        self._build_central_widget()
        self._build_outline_dock()
        self._build_grep_dock()
        self._build_toolbar()
        self._build_statusbar()

        self.set_root(self.current_root)

    # ------------------------------------------------------------------
    # 左側: ファイルツリー
    # ------------------------------------------------------------------
    def _build_tree_dock(self):
        self.model = QFileSystemModel()
        self.model.setNameFilters(["*.md", "*.markdown"])
        self.model.setNameFilterDisables(False)  # フィルタ対象外は非表示

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        # ファイル名列以外(サイズ/種類/更新日時)は隠してすっきりさせる
        self.tree.setColumnHidden(1, True)
        self.tree.setColumnHidden(2, True)
        self.tree.setColumnHidden(3, True)
        self.tree.setHeaderHidden(True)
        self.tree.clicked.connect(self._on_tree_clicked)

        collapse_btn = QPushButton("すべて閉じる")
        collapse_btn.clicked.connect(self.tree.collapseAll)
        expand_btn = QPushButton("すべて展開")
        expand_btn.clicked.connect(self.tree.expandAll)

        btn_row = QHBoxLayout()
        btn_row.addWidget(collapse_btn)
        btn_row.addWidget(expand_btn)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(btn_row)
        layout.addWidget(self.tree)

        dock = QDockWidget("ファイルツリー", self)
        dock.setWidget(container)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.tree_dock = dock

    # ------------------------------------------------------------------
    # 中央: プレビュー / 編集切替
    # ------------------------------------------------------------------
    def _build_central_widget(self):
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)

        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._on_editor_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.preview)  # index 0: プレビュー
        self.stack.addWidget(self.editor)   # index 1: 編集

        self.setCentralWidget(self.stack)
        self._apply_font_size()

    def _on_editor_changed(self):
        # 編集中はタイトルに変更マークを付ける
        if self.current_file and not self.windowTitle().startswith("*"):
            self.setWindowTitle("* " + self.windowTitle())

    # ------------------------------------------------------------------
    # 右側: アウトライン(見出し一覧)
    # ------------------------------------------------------------------
    def _build_outline_dock(self):
        self.outline_list = QListWidget()
        self.outline_list.itemClicked.connect(self._on_outline_clicked)

        dock = QDockWidget("目次(アウトライン)", self)
        dock.setWidget(self.outline_list)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.outline_dock = dock

    def _build_outline(self, text):
        self.outline_list.clear()
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.*)", line)
            if m:
                level = len(m.group(1))
                heading = m.group(2).strip()
                item = QListWidgetItem(("　" * (level - 1)) + heading)
                item.setData(Qt.UserRole, heading)
                self.outline_list.addItem(item)

    def _on_outline_clicked(self, item):
        heading = item.data(Qt.UserRole)
        self.stack.setCurrentIndex(0)  # プレビューに切替
        cursor = self.preview.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.preview.setTextCursor(cursor)
        self.preview.find(heading)

    # ------------------------------------------------------------------
    # 下側: grep(全文検索)
    # ------------------------------------------------------------------
    def _build_grep_dock(self):
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("検索したい文字列を入力してEnter (フォルダ内の.md全文検索)")
        self.search_box.returnPressed.connect(self._run_grep)

        search_btn = QPushButton("検索")
        search_btn.clicked.connect(self._run_grep)

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_box)
        top_row.addWidget(search_btn)

        self.replace_box = QLineEdit()
        self.replace_box.setPlaceholderText("置換後の文字列を入力")

        replace_current_btn = QPushButton("開いているファイルのみ置換")
        replace_current_btn.clicked.connect(self._replace_in_current_file)

        replace_all_btn = QPushButton("検索結果の全ファイルを一括置換")
        replace_all_btn.clicked.connect(self._replace_in_all_files)

        replace_row = QHBoxLayout()
        replace_row.addWidget(self.replace_box)
        replace_row.addWidget(replace_current_btn)
        replace_row.addWidget(replace_all_btn)

        self.grep_results = QListWidget()
        self.grep_results.itemDoubleClicked.connect(self._on_grep_result_clicked)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top_row)
        layout.addWidget(self.grep_results)
        layout.addLayout(replace_row)

        dock = QDockWidget("grep検索 / 一括置換 (ダブルクリックでジャンプ)", self)
        dock.setWidget(container)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.grep_dock = dock

    def _run_grep(self):
        keyword = self.search_box.text().strip()
        self.grep_results.clear()
        if not keyword:
            return

        hit_count = 0
        for dirpath, _dirnames, filenames in os.walk(self.current_root):
            for fname in filenames:
                if not (fname.endswith(".md") or fname.endswith(".markdown")):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, start=1):
                            if keyword.lower() in line.lower():
                                rel = os.path.relpath(fpath, self.current_root)
                                snippet = line.strip()[:80]
                                item = QListWidgetItem(f"{rel}:{lineno}  {snippet}")
                                item.setData(Qt.UserRole, (fpath, lineno))
                                self.grep_results.addItem(item)
                                hit_count += 1
                except OSError:
                    continue

        self.statusBar().showMessage(f"「{keyword}」の検索結果: {hit_count} 件")

    def _on_grep_result_clicked(self, item):
        fpath, lineno = item.data(Qt.UserRole)
        self._load_file(fpath)
        self.stack.setCurrentIndex(1)  # 編集(生テキスト)モードで該当行へ
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(lineno - 1):
            cursor.movePosition(QTextCursor.Down)
        cursor.select(QTextCursor.LineUnderCursor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _replace_in_current_file(self):
        keyword = self.search_box.text().strip()
        replacement = self.replace_box.text()
        if not keyword:
            QMessageBox.information(self, "置換", "検索文字列が入力されていません。")
            return
        if not self.current_file:
            QMessageBox.information(self, "置換", "ファイルが開かれていません。")
            return

        text = self.editor.toPlainText()
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        new_text, count = pattern.subn(replacement, text)
        if count == 0:
            QMessageBox.information(self, "置換", "一致する文字列が見つかりませんでした。")
            return

        self.editor.setPlainText(new_text)  # 未保存マークが自動で付く
        self.preview.setMarkdown(new_text)
        self.statusBar().showMessage(f"{count} 件を置換しました(「保存」で確定してください)", 4000)

    def _replace_in_all_files(self):
        keyword = self.search_box.text().strip()
        replacement = self.replace_box.text()
        if not keyword:
            QMessageBox.information(self, "置換", "検索文字列が入力されていません。")
            return
        if self.grep_results.count() == 0:
            QMessageBox.information(self, "置換", "先に検索を実行してください。")
            return

        fpaths = set()
        for i in range(self.grep_results.count()):
            fpath, _lineno = self.grep_results.item(i).data(Qt.UserRole)
            fpaths.add(fpath)

        reply = QMessageBox.question(
            self,
            "一括置換の確認",
            f"「{keyword}」を「{replacement}」に置換します。\n"
            f"対象ファイル数: {len(fpaths)}件\n"
            "この操作は元に戻せません。実行しますか?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        total_count = 0
        changed_files = 0
        for fpath in fpaths:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                new_text, count = pattern.subn(replacement, text)
                if count > 0:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new_text)
                    total_count += count
                    changed_files += 1
            except OSError:
                continue

        # 現在開いているファイルが対象だった場合は表示も更新
        if self.current_file in fpaths:
            self._load_file(self.current_file)

        self.grep_results.clear()
        self.statusBar().showMessage(
            f"一括置換完了: {changed_files}ファイル / 合計{total_count}件", 5000
        )

    # ------------------------------------------------------------------
    # ツールバー
    # ------------------------------------------------------------------
    def _build_toolbar(self):
        toolbar = QToolBar("メイン操作")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_open = QAction("フォルダを開く", self)
        act_open.triggered.connect(self._open_folder_dialog)
        toolbar.addAction(act_open)

        act_refresh = QAction("更新", self)
        act_refresh.triggered.connect(self._refresh)
        toolbar.addAction(act_refresh)

        toolbar.addSeparator()

        act_toggle = QAction("プレビュー/編集 切替", self)
        act_toggle.setShortcut(QKeySequence("Ctrl+E"))
        act_toggle.triggered.connect(self._toggle_view)
        toolbar.addAction(act_toggle)

        act_save = QAction("保存", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self._save_file)
        toolbar.addAction(act_save)

        toolbar.addSeparator()

        act_font_up = QAction("文字大", self)
        act_font_up.triggered.connect(lambda: self._change_font_size(1))
        toolbar.addAction(act_font_up)

        act_font_down = QAction("文字小", self)
        act_font_down.triggered.connect(lambda: self._change_font_size(-1))
        toolbar.addAction(act_font_down)

        toolbar.addSeparator()

        act_dark = QAction("ダークモード切替", self)
        act_dark.triggered.connect(self._toggle_dark_mode)
        toolbar.addAction(act_dark)

    # ------------------------------------------------------------------
    # ステータスバー
    # ------------------------------------------------------------------
    def _build_statusbar(self):
        self.setStatusBar(QStatusBar())
        self.status_label = QLabel("")
        self.statusBar().addPermanentWidget(self.status_label)

    # ------------------------------------------------------------------
    # 動作ロジック
    # ------------------------------------------------------------------
    def set_root(self, path):
        self.current_root = path
        self.model.setRootPath(path)
        self.tree.setRootIndex(self.model.index(path))
        self.setWindowTitle(f"Markdown設計書 簡易IDE - {path}")

    def _open_folder_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "設計書フォルダを選択", self.current_root)
        if path:
            self.set_root(path)

    def _refresh(self):
        self.model.setRootPath("")
        self.model.setRootPath(self.current_root)
        self.statusBar().showMessage("ツリーを更新しました", 3000)

    def _on_tree_clicked(self, index):
        if self.model.isDir(index):
            return
        path = self.model.filePath(index)
        self._load_file(path)

    def _load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "読み込みエラー", f"ファイルを読み込めませんでした:\n{e}")
            return

        self.current_file = path
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self.preview.setMarkdown(text)
        self._build_outline(text)

        self.setWindowTitle(f"Markdown設計書 簡易IDE - {path}")
        lines = text.count("\n") + 1
        chars = len(text)
        self.status_label.setText(f"{os.path.basename(path)} | {lines}行 / {chars}文字")

    def _toggle_view(self):
        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)  # 編集モードへ
        else:
            # 編集内容をプレビューに反映してから切替
            self.preview.setMarkdown(self.editor.toPlainText())
            self.stack.setCurrentIndex(0)

    def _save_file(self):
        if not self.current_file:
            QMessageBox.information(self, "保存", "保存対象のファイルが選択されていません。")
            return
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "保存エラー", f"保存に失敗しました:\n{e}")
            return

        self.preview.setMarkdown(self.editor.toPlainText())
        title = self.windowTitle()
        if title.startswith("* "):
            self.setWindowTitle(title[2:])
        self.statusBar().showMessage("保存しました", 3000)

    def _change_font_size(self, delta):
        self.font_size = max(6, min(40, self.font_size + delta))
        self._apply_font_size()

    def _apply_font_size(self):
        font = QFont("Meiryo", self.font_size)
        self.editor.setFont(font)
        self.preview.setFont(font)

    def _toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.setStyleSheet(DARK_STYLE if self.dark_mode else LIGHT_STYLE)

    def closeEvent(self, event):
        if self.windowTitle().startswith("*"):
            reply = QMessageBox.question(
                self,
                "確認",
                "未保存の変更があります。保存せずに終了しますか?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MarkdownIDE()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
