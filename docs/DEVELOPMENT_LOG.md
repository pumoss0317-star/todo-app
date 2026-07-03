# Todoアプリ 開発記録

## 1. 概要

Streamlit製のTodoアプリ。Googleアカウントでログインし、各ユーザーのTodoをGoogleスプレッドシートに保存する。Streamlit Community Cloudで一般公開。

- 公開URL: https://todo-app-7lhwh9tsrsowkvkeltzdud.streamlit.app/
- リポジトリ: https://github.com/pumoss0317-star/todo-app

## 2. 要件定義

### 機能要件

| 項目 | 内容 |
|---|---|
| 認証 | Googleアカウントでログイン（`st.login`によるOIDC認証） |
| データ保存先 | Googleスプレッドシート（ユーザーごとに`user_email`で行を紐付け） |
| Todo登録 | タイトル・内容・期日を入力して新規登録 |
| Todo編集 | 既存Todoのタイトル・内容・期日を編集（完了状態・登録日時は保持） |
| Todo削除 | 削除ボタン（誤操作防止のため2段階確認） |
| 完了管理 | チェックボックスで完了/未完了を切り替え、未完了・完了済みタブで分類表示 |
| 期日アラート | 期限切れは赤、期限3日以内は オレンジで強調表示 |
| 登録日時表示 | 登録時刻を記録し、編集しても変わらない形で一覧に表示 |

### 非機能要件

- 一般公開（Streamlit Communityの無料枠で誰でもアクセス可能）
- 認証情報（Google OAuthクライアント・サービスアカウント鍵）はリポジトリに含めず、Streamlit Cloud側のSecretsで管理

## 3. 実装内容

### 使用技術

- Python / Streamlit（`st.login`によるネイティブ認証）
- gspread + google-auth（Googleスプレッドシート連携）
- Authlib + httpx（OIDC認証のバックエンド、Streamlitの内部依存）
- truststore（SSL証明書検証、Windows環境でのgspread通信向け）

### データ構造（スプレッドシート列）

`id / user_email / title / content / due_date / updated_at / completed / created_at`

- `created_at`: 新規登録時に1度だけ設定し、編集時も上書きしない（登録日時用）
- `updated_at`: 登録・編集のたびに更新（最終更新日時）

### 主な機能

- **一覧表示**: Todoごとにカード形式（枠付き）で表示。タイトル（太字・大きめ）→内容→期日（📅アイコン、期限に応じて色分け）→登録日時（小さいグレー文字）を縦に並べ、右側に編集（グレー）・削除（赤）ボタンを配置。
- **削除**: 「削除」ボタン押下で「削除する / 取消」の2択に切り替わり、確定後に`worksheet.delete_rows()`で行を削除。
- **編集**: 編集ボタンでフォームに既存値を読み込み、更新時は`created_at`のみ元の値を維持して他の列を上書き。

## 4. デプロイ時に発生したエラーと対処

Streamlit Community Cloudへの公開作業中、以下のエラーが連続して発生した。

### (1) 初回アクセス時に "Internal server error."

- **状況**: 公開URLに（ログイン前の状態で）アクセスしただけで真っ白なエラー画面。
- **原因**: Secretsの`redirect_uri`がローカル開発用の`http://localhost:8501/oauth2callback`のままで、Streamlitの認証初期化処理と食い違っていた。
- **対処**: `redirect_uri`を本番URL（`https://todo-app-.../oauth2callback`）に変更。あわせてGoogle Cloud ConsoleのOAuthクライアントの「承認済みのリダイレクトURI」にも同じURLを追加。

### (2) `StreamlitAuthError: ... missing the "cookie_secret" key`

- **状況**: (1)を修正後、ログインボタンを押すと発生。
- **原因**: Streamlit CloudのSecrets編集画面（テキストエリア）で`redirect_uri`を編集した際、隣接する`cookie_secret`の行が消えてしまっていた。
- **対処**: 消えていた`cookie_secret`の行を追記して保存。

### (3) 同様に `client_secret`, `server_metadata_url` が missing

- **状況**: (2)の修正作業中、再度別の行（`client_secret`・`server_metadata_url`）が消える事故が発生。
- **原因**: Secrets編集画面は大きなブロックを貼り直すとTOMLが壊れやすく（`Invalid format: please enter valid TOML.`）、編集の都度別の行が消失する問題があった。
- **対処**: 保存前に全文をチャットに貼って目視確認する運用に変更し、不足していた2行を追記。

### (4) 本質的な原因: `ModuleNotFoundError: No module named 'httpx'`

- **状況**: Secretsの内容は正しく揃っていたにもかかわらず、ログイン時に同じ`StreamlitAuthError`が再発。
- **原因**: 「Manage app」のログを最後までスクロールして判明。Streamlitのネイティブ認証（`st.login`）が内部で使う`Authlib`のStarlette連携が`httpx`に依存しているが、`requirements.txt`に`httpx`が含まれておらず、クラウド環境の起動時にインポートエラーでクラッシュしていた。手前に表示されていた「secrets keyが足りない」というエラーメッセージは、実際にはこのクラッシュに起因する誤解を招く表示だった。
- **対処**: `requirements.txt`に`httpx>=0.27`を追加してpush。Streamlit Cloudが自動で再デプロイし、ログインが正常に動作するようになった。

### 教訓

- `st.login`関連のエラーで「secrets keyが足りない」と出た場合、まず`Manage app`のログを一番下までスクロールして本当の例外（Import系エラーなど）が隠れていないか確認する。
- Streamlit CloudのSecrets編集画面は保存前に全文を目視確認する。大きなブロックを丸ごと貼り直すより、必要な行だけ最小限に追記する方が事故が少ない。

（上記の知見は `C:\Users\pumos\.claude\knowledge\errors\` にも別途記録済み）

## 5. 今後の課題（未着手）

- 特になし（2026-07-03時点で要望は全て反映済み）
