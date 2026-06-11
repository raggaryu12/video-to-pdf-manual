# 🎬 動画 → PDF 操作手順書メーカー

動画ファイル（MOV / MP4）をアップロードするだけで、スクリーンショット付きの操作手順書 PDF を自動生成する Streamlit アプリです。

## 🚀 機能

- 複数の動画ファイルを一括アップロード
- フレーム抽出間隔をスライダーで調整（1〜10秒）
- PDF タイトルを自由入力
- 1列 / 2列レイアウトを選択
- ワンクリックで PDF ダウンロード

## 💻 ローカルで使う

```bash
# 1. リポジトリをクローン
git clone https://github.com/YOUR_USERNAME/video-to-pdf-manual.git
cd video-to-pdf-manual

# 2. 依存ライブラリをインストール
pip install -r requirements.txt

# 3. アプリを起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` が開きます。

## ☁️ Streamlit Cloud でデプロイ

1. このリポジトリを GitHub に push する
2. [Streamlit Cloud](https://streamlit.io/cloud) にアクセスしてログイン
3. **「New app」** をクリック
4. リポジトリ・ブランチ・`app.py` を選択して **「Deploy」**
5. 数分後に公開 URL が発行されます

## 📁 ファイル構成

```
video-to-pdf-manual/
├── app.py              # アプリ本体
├── requirements.txt    # Python 依存ライブラリ
├── packages.txt        # apt パッケージ（Streamlit Cloud 用）
├── .gitignore
└── README.md
```

## 🛠 使用技術

- [Streamlit](https://streamlit.io/) — Web UI
- [OpenCV](https://opencv.org/) — 動画フレーム抽出
- [ReportLab](https://www.reportlab.com/) — PDF 生成
