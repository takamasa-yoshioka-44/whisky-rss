# whisky-rss

ウイスキー情報の自動収集ハブ。RSS / RSS非対応サイト / SNS を一括で集約し、
キーワードでフィルタして Discord / Slack に通知することで、
**「情報収集のハードルを下げ、日々のキャッチアップを円滑にする」** ことを目的とする。

---

## アーキテクチャ

```
                       ┌─────────────────────────┐
                       │  情報源(JP / 海外)      │
                       │  ・蒸溜所公式           │
                       │  ・ニュース/ブログ      │
                       │  ・抽選販売サイト       │
                       │  ・オークション         │
                       │  ・Reddit / X / IG …    │
                       └────────────┬────────────┘
                                    │
                ┌───────────────────┴────────────────┐
                │                                    │
        ┌───────▼────────┐                  ┌────────▼────────┐
        │ ネイティブRSS  │                  │ RSS非対応サイト │
        │ (そのまま購読) │                  │  → RSSHubで変換 │
        └───────┬────────┘                  └────────┬────────┘
                │                                    │
                └────────────────┬───────────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │   Aggregator       │
                       │   (Python)         │
                       │  ・ fetch          │
                       │  ・ dedupe (SQLite)│
                       │  ・ keyword filter │
                       │  ・ notify         │
                       └─────────┬──────────┘
                                 │
                  ┌──────────────┼──────────────┐
                  │              │              │
            ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
            │  Discord  │  │   Slack   │  │   出力RSS │
            │  Webhook  │  │  Webhook  │  │ (filtered)│
            └───────────┘  └───────────┘  └───────────┘
```

### コンポーネント

| 役割 | 採用技術 | 理由 |
|------|----------|------|
| RSS非対応サイトのRSS化 | **[RSSHub](https://docs.rsshub.app/)** (Docker) | X/Reddit/各サイトを公式メンテのレシピで一気にRSS化できる |
| フィード集約 / フィルタ / 通知 | **Python** スクリプト (`feedparser` + `requests`) | 軽量・依存少・cron で回しやすい |
| 既読・重複管理 | **SQLite** | ファイル1個で完結。バックアップ容易 |
| 閲覧UI (任意) | **[Miniflux](https://miniflux.app/)** | 軽量で見やすいセルフホスト型RSSリーダー |
| オーケストレーション | **docker-compose** | RSSHub / Miniflux / Aggregator を1コマンドで起動 |
| 定期実行 | docker-compose 内 cron / GitHub Actions | 環境に合わせて選択 |

---

## ディレクトリ構成

```
whisky-rss/
├── README.md
├── docker-compose.yml          # RSSHub + Miniflux + Aggregator
├── .env.example                # Webhook URLなどの設定例
├── .gitignore
├── config/
│   ├── feeds.yaml              # 購読フィード一覧
│   └── keywords.yaml           # 通知キーワード / 除外ワード
└── aggregator/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                 # 集約・フィルタ・通知の本体
    ├── notifier.py             # Discord / Slack 送信
    ├── storage.py              # SQLite 既読管理
    └── crontab                 # 定期実行設定
```

---

## クイックスタート

### 1. 環境変数を設定

```bash
cp .env.example .env
# .env を編集して Discord / Slack の Webhook URL を入れる
```

### 2. 起動

```bash
docker compose up -d
```

これで以下が立ち上がる:

- **RSSHub**: `http://localhost:1200`
- **Miniflux** (任意のWeb UI): `http://localhost:8080`
- **Aggregator**: バックグラウンドで定期実行

### 3. フィードを編集

`config/feeds.yaml` を編集して購読フィードを追加・削除する。
編集後は `docker compose restart aggregator` で反映。

### 4. キーワードを編集

`config/keywords.yaml` で通知対象のキーワード(例: `山崎`, `イチローズモルト`, `抽選`)を指定。

---

## 推奨情報源リスト

### 日本 — ネイティブRSS対応

- ウイスキー文化研究所 ニュース
- WHISKY Magazine Japan
- WhiskyDB ブログ
- リカーズハセガワ 入荷情報 (RSSあり)
- 各蒸溜所の公式ブログ (Atom配信があるもの)

### 日本 — RSS非対応 → RSSHub経由

- **X (Twitter)** アカウント: 各蒸溜所公式、酒販店、レビュアー
  - `/twitter/user/SUNTORY_dy` などのパスを利用
- **各蒸溜所サイトの新着** (サントリー / ニッカ / 本坊酒造 / ベンチャーウイスキー / 厚岸 / 三郎丸…)
- **抽選販売サイト** (リカマン / イオンリカー / ビックカメラ / 阪急百貨店 など)
- **Amazon 新着** (whisky カテゴリ): `/amazon/jp/...`

### 海外 — ネイティブRSS対応

- [Whisky Advocate](https://whiskyadvocate.com/)
- [Whisky Magazine](https://whiskymag.com/)
- [Master of Malt Blog](https://www.masterofmalt.com/blog/)
- [The Whiskey Wash](https://thewhiskeywash.com/)
- [The Whisky Exchange Blog](https://blog.thewhiskyexchange.com/)
- [Dramming](https://www.dramming.com/)
- [Whisky Notes](https://www.whiskynotes.be/)

### 海外 — RSS非対応 → RSSHub経由

- **Reddit**: `r/Scotch`, `r/whisky`, `r/bourbon`, `r/JapaneseWhisky`
- **X**: 主要レビュアー、各蒸溜所公式
- **Instagram**: 蒸溜所公式 (注: Instagram は不安定)

### オークション

- [Whisky Auctioneer](https://whiskyauctioneer.com/)
- [Scotch Whisky Auctions](https://www.scotchwhiskyauctions.com/)
- [Just Whisky Auctions](https://www.justwhisky.co.uk/)
- Catawiki Whisky (RSSHub経由)

具体的なURL/パスは `config/feeds.yaml` を参照。

---

## キーワードフィルタ運用のコツ

`config/keywords.yaml` では以下のような運用が便利:

- **include** (どれかに一致したら通知): `山崎`, `白州`, `響`, `イチローズ`, `厚岸`, `ジャパニーズウイスキー`, `抽選`, `auction`, `cask strength` …
- **exclude** (含むと除外): `転売`, `偽物`, アフィリエイト系のスパム語など
- **channels** で「これは Discord の `#抽選` チャンネルへ」のようにキーワード → 通知先のマッピングを可能にする

---

## 拡張アイデア

- LLM 要約 (Claude / OpenAI) を挟んで、長文記事の要点を Discord 通知に同梱
- 出力RSSフィードを `aggregator/out/whisky.xml` に生成し、Feedly などからも読めるようにする
- 価格情報 (オークション結果) を時系列でDBに蓄積して、推移グラフを生成
- Telegram / LINE Notify への通知対応
