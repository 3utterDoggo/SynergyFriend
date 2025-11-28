# -*- coding: utf-8 -*-
from aqt import mw
from aqt.qt import QAction, QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit
from aqt.utils import showInfo
import os
import shutil
import re
import json

# -----------------------------
# config.jsonから設定を読み込む・保存する
# -----------------------------
def get_addon_dir():
    """アドオンのディレクトリを取得"""
    return os.path.dirname(os.path.abspath(__file__))

def get_config_path():
    """config.jsonのパスを取得"""
    return os.path.join(get_addon_dir(), "config.json")

def load_config():
    try:
        config_path = get_config_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"config.jsonの読み込みに失敗しました: {e}")
        return None

def save_config(config):
    """config.jsonに設定を保存"""
    try:
        config_path = get_config_path()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"config.jsonの保存に失敗しました: {e}")
        return False

config = load_config()
if config:
    chrome_extension_path = config.get("chrome_extension_path", "")
    chrome_extension_id = config.get("chrome_extension_id", "")
    anki_target_deck = config.get("anki_target_deck", "")
else:
    chrome_extension_path = ""
    chrome_extension_id = ""
    anki_target_deck = ""

# -----------------------------
# デッキ選択・拡張機能パス入力ダイアログ
# -----------------------------
class DeckSelectionDialog(QDialog):
    def __init__(self, parent, default_deck, default_path, default_id):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.selected_deck = None
        self.extension_path = None
        self.extension_id = None

        layout = QVBoxLayout()

        # 拡張機能パス入力
        path_label = QLabel("拡張機能の場所：")
        layout.addWidget(path_label)

        self.path_input = QLineEdit()
        self.path_input.setText(default_path or "")
        self.path_input.setPlaceholderText("拡張機能のパス貼り付けてください")
        layout.addWidget(self.path_input)

        # 拡張機能ID入力
        id_label = QLabel("拡張機能ID：")
        layout.addWidget(id_label)

        self.id_input = QLineEdit()
        self.id_input.setText(default_id or "")
        self.id_input.setPlaceholderText("拡張機能IDを入力してください")
        layout.addWidget(self.id_input)

        # デッキ選択
        deck_label = QLabel("処理対象デッキ：")
        layout.addWidget(deck_label)

        self.combo = QComboBox()
        decks = mw.col.decks.all_names_and_ids()
        deck_names = [deck.name for deck in decks]
        self.combo.addItems(deck_names)

        # デフォルトデッキを選択
        if default_deck and default_deck in deck_names:
            index = deck_names.index(default_deck)
            self.combo.setCurrentIndex(index)

        layout.addWidget(self.combo)

        # OKボタン・キャンセルボタン
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        layout.addWidget(ok_button)

        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

        self.setLayout(layout)

    def get_selected_deck(self):
        return self.combo.currentText()

    def get_extension_path(self):
        return self.path_input.text()

    def get_extension_id(self):
        return self.id_input.text()

# -----------------------------
# 処理関数
# -----------------------------
def process_cards():
    if not mw or not mw.col:
        showInfo("mw が未初期化です。Ankiを再起動してください。")
        return

    # デッキ選択・拡張機能パス入力・拡張機能ID入力ダイアログを表示
    dialog = DeckSelectionDialog(
        mw,
        config.get("anki_target_deck", ""),
        config.get("chrome_extension_path", ""),
        config.get("chrome_extension_id", "")
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    selected_deck = dialog.get_selected_deck()
    extension_path = dialog.get_extension_path()
    extension_id = dialog.get_extension_id()

    # 設定をconfig.jsonに保存
    config["anki_target_deck"] = selected_deck
    config["chrome_extension_path"] = extension_path
    config["chrome_extension_id"] = extension_id
    if not save_config(config):
        showInfo(f"設定保存エラー: config.jsonの保存に失敗しました")
        return

    media_dir = mw.col.media.dir()
    print("collection.media:", media_dir)

    # 対象デッキのIDを取得
    try:
        did = mw.col.decks.id(selected_deck)
    except Exception as e:
        print("デッキ取得失敗:", e)
        showInfo(f"デッキ取得失敗: {e}")
        return

    # デッキ内のカードIDを取得
    cids = mw.col.findCards(f"deck:{selected_deck}")
    print(f"対象カード数: {len(cids)}")

    processed_count = 0  # 処理件数をカウント

    for cid in cids:
        try:
            note = mw.col.getNote(mw.col.getCard(cid).nid)
        except Exception as e:
            print("ノート取得失敗:", cid, e)
            continue

        for idx, field in enumerate(note.fields):
            matches = re.findall(r'<img[^>]+src="([^"]+)"', field)
            if not matches:
                continue

            new_field = field
            for src in matches:
                # URLから拡張機能IDを抽出
                id_match = re.search(r'chrome-extension://([a-z]+)/', src)
                if not id_match:
                    print("拡張機能IDが見つかりません:", src)
                    continue

                url_extension_id = id_match.group(1)

                # 設定されたIDと一致するかチェック
                if url_extension_id != extension_id:
                    print(f"拡張機能IDが一致しません。スキップします。 URL: {url_extension_id}, 設定: {extension_id}")
                    continue

                filename = os.path.basename(src)
                old_path = os.path.join(extension_path, "data/graphics/img", filename)
                new_filename = "synergy_img_" + filename
                new_path = os.path.join(media_dir, new_filename)

                print("カードID:", cid)
                print("コピー元:", old_path)
                print("コピー先:", new_path)

                if os.path.exists(old_path):
                    try:
                        shutil.copy(old_path, new_path)
                        print("コピー成功:", new_filename)
                        processed_count += 1  # 処理件数をインクリメント
                    except Exception as e:
                        print("コピー失敗:", e)
                else:
                    print("コピー元ファイルが存在しません:", old_path)

                # HTML の書き換え
                new_field = new_field.replace(src, new_filename)

            note.fields[idx] = new_field
        note.flush()

    showInfo(f"{processed_count}件の画像を修正しました")

# -----------------------------
# メニューに追加
# -----------------------------
action = QAction("SynergyFriend実行", mw)
action.triggered.connect(process_cards)
mw.form.menuTools.addAction(action)