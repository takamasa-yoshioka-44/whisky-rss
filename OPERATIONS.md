# 運用メモ

## 起動 / 停止

```bash
# 起動
docker compose up -d

# ログを見る (aggregatorのみ)
docker compose logs -f aggregator

# 停止
docker compose down

# 完全リセット (DBごと)
docker compose down -v
rm -rf data/
```

## ローカルで1回だけ走らせる (動作確認)

Docker を立てずに、ホストの Python で aggregator を1回実行できる。
RSSHub を使わないネイティブRSSのみのフィードで動作確認したい時に便利。

```bash
./scripts/run-local.sh
```

`.env` が存在すればそこから読む。`RSSHUB_BASE_URL` を設定していなければ
`${RSSHUB}` を含むフィードはエラーになるので、`config/feeds.yaml` で
それらを `enabled: false` にしておくこと。

## フィードの追加・削除

`config/feeds.yaml` を編集して:

```bash
docker compose restart aggregator
```

## キーワードの追加・削除

`config/keywords.yaml` を編集して同じく restart。

## 通知が来ない時のチェックリスト

1. `.env` に Webhook URL が入っているか
2. `config/feeds.yaml` で対象フィードが `enabled: true` か
3. `docker compose logs aggregator` でフィードが正常に取れているか
4. キーワードルールが空でないか (`channels: []` だと通知しない設定)
5. SQLite に既に「既読」として記録されていないか
   ```bash
   docker compose exec aggregator sqlite3 /app/data/whisky.sqlite \
     "SELECT feed_id, COUNT(*) FROM seen_entries GROUP BY feed_id;"
   ```
   テスト的に再通知させたい場合は該当行を DELETE する。

## RSSHub のレシピを探す

- 公式ドキュメント: https://docs.rsshub.app/
- Chrome拡張「RSSHub Radar」を入れると、見ているサイトに対応する
  RSSHubルートをサジェストしてくれて便利
- ルートが見つからない場合は generic スクレイパー (`/api/rss?url=...`) を試す

## バックアップ

`data/whisky.sqlite` だけ取れば既読履歴は復元できる。
Miniflux のデータは `miniflux-db-data` ボリュームに入っているので、
購読リストをエクスポートしたい場合は Miniflux のUIから OPML エクスポート可能。

## トラブルシュート

### `parse failed: <URLError ...>`
- ネットワーク到達性。Docker内から RSSHub に到達できているか
- `docker compose exec aggregator curl -s http://rsshub:1200/test/1` で確認

### Discord/Slackで 401/403
- Webhook URL の貼り間違い、または削除済み

### 通知量が多すぎる
- `config/keywords.yaml` の `catch-all` ルールが有効になっていないか確認
- 重要ルールだけ Discord、その他は出力RSSのみ、のように分けるとよい
