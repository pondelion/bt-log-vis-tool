# デプロイ手順（GCP Cloud Run）

bt-log-vis-toolをGCP Cloud Runにデプロイするための手順書。`terraform apply`・`gcloud`コマンドはすべて自分で実行する前提（Claudeは代行しない）。

## 前提

- 専用のGoogleアカウント（会社のプロジェクトとは無関係な個人アカウント）でGCPプロジェクトを作成済み
- `gcloud auth login`で上記アカウントにログイン済み
- terraform / docker / **jq** がローカルにインストール済み（jqは出力をenv変数化するスクリプトで使用）

```bash
gcloud auth list   # 対象アカウントがACTIVEになっているか確認
```

---

## 0. 初回のみ: プロジェクト共通の準備

### 0-0. `.env`の準備

```bash
cp .env.example .env
# .env を開いて PROJECT_ID / BUCKET_NAME（globally unique）等を埋める
```

`.env`の中身をterraformが読める`TF_VAR_*`環境変数に変換してexport（infra/app両方のフェーズで毎回このシェルセッションで実行しておく）:

```bash
export $(grep -v -E '^\s*#|^\s*$' .env | \
  sed -E 's/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/TF_VAR_\L\1=\2/' | \
  xargs -d '\n')
```

これで`terraform.tfvars`を手で作らなくても、`project_id`/`region`/`bucket_name`/`image_name`/`image_tag`がinfra/app両方のterraformに渡る。

### 0-1. Application Default Credentials（Terraformが使う認証情報）

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project ${TF_VAR_project_id}
```

terraform実行用の専用SA・鍵ファイルは作らず、このADC（＝自分のOwnerアカウント）でterraformを実行する方針。

### 0-2. 課金アカウントのリンク

Cloud Run/GCS/Secret Manager等は無料枠内でも課金アカウントのリンクが必須。

```bash
gcloud billing accounts list
gcloud billing projects link ${TF_VAR_project_id} --billing-account=<BILLING_ACCOUNT_ID>
```

### 0-3. 必要なAPIを有効化

```bash
gcloud config set project ${TF_VAR_project_id}

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com
```

---

## 1. infra フェーズ（`apply`自体は初回のみ・リソース作成）

GCSバケット（非公開）・Artifact Registry・Cloud Run実行用SA・Secret Managerの箱を作成する。

```bash
terraform -chdir=deploy/terraform/infra init
terraform -chdir=deploy/terraform/infra plan
terraform -chdir=deploy/terraform/infra apply
```

（`project_id`/`bucket_name`は0-0で`.env`からexportした`TF_VAR_*`が使われるので、ここで`.tfvars`を作る必要はない）

apply後、次フェーズで使う出力値（SAメール等、apply前には決まらない値）を環境変数に変換しておく:

```bash
source tf_infra_phase_outputs_to_env.sh
# TF_VAR_app_sa_email / TF_VAR_artifact_repo_name / TF_VAR_bucket_name / TF_VAR_streamlit_secrets_id がexportされる
```

> **⚠️ 注意**: `terraform apply`自体は初回だけでよいが、`source tf_infra_phase_outputs_to_env.sh`は**シェルセッション（ターミナル）を開き直す度に毎回**実行し直す必要がある。exportした環境変数はそのターミナルセッション内でしか有効でないため、新しいターミナルでアプリ更新（4章）を行う際は、`terraform apply`は不要でも**このsourceコマンドだけは毎回最初に実行すること**（0-0の`.env`のexportも同様に毎回必要）。詳しくは4章冒頭を参照。

---

## 2. Google OAuthクライアントの作成（初回のみ・GCPコンソール操作）

Googleログイン（`st.login()`）に使うOAuthクライアントをコンソールで作成する。

**アクセス制御の方針**: 当初はGoogleのOAuth同意画面をTesting状態＋Test Usersに限定することで「管理者発行アカウントのみ」を実現する想定だったが、**実際にはTest User未登録のアカウントでもログインできてしまうことを確認した**（`openid`/`email`/`profile`という非機密スコープのみの場合、Testing/Test Usersの制限が有効に機能しないと見られる）。そのため、**Google側の設定には依存せず、アプリ側の許可リスト（`_admin/allowlist.yaml`、3章で作成）を実効的なアクセス制御として使う**。Test Usersの登録自体は無意味ではない（多少の抑止にはなる）ので設定はしておくが、これだけでアクセス制御が完結していると考えないこと。

（GoogleのコンソールUIは "Google Auth Platform" として再編されているため、以下のラベルは実際の画面と多少異なる場合がある。「公開ステータス（Audience）」と「OAuth Client作成（Clients）」に相当する箇所を探すこと）

1. Google Cloud Consoleの「Google Auth Platform」（旧OAuth consent screen）を開く
   - User Type: **External**
   - 公開ステータスは **Testing のまま**にする（In productionにはしない）
   - **Test Users**に、ログインさせたい許可済みメールアドレスを追加（上記の通り実効的な制御ではないが、念のため設定しておく）
   - 「データアクセス」で`openid`/`.../auth/userinfo.email`/`.../auth/userinfo.profile`スコープを追加しておく（未設定だと「OAuth構成が完了していません」という警告が出るが、追加してもTest Users制限自体は直らないことを確認済み）
2. 「Clients」（旧Credentials）から **Create OAuth client** > **Web application**
   - Authorized redirect URIs に、まずローカル検証用だけ追加:
     - `http://localhost:8501/oauth2callback`
   - 作成後に表示される **Client ID** と **Client Secret** を控えておく（本番用のredirect URIは4章のデプロイ後、5章で追記する）

---

## 3. secrets.tomlの作成とアップロード（初回のみ）

Streamlitのネイティブ認証が読む`secrets.toml`をローカルで作成する（**リポジトリにはコミットしない**、一時ファイル）。

2章で控えたClient ID/Secretを埋めて実行（`cookie_secret`はコマンドでランダム生成してそのまま埋め込む）:

```bash
GOOGLE_CLIENT_ID="<2章で控えたClient ID>"
GOOGLE_CLIENT_SECRET="<2章で控えたClient Secret>"
COOKIE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > secrets.toml <<EOF
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "${COOKIE_SECRET}"
client_id = "${GOOGLE_CLIENT_ID}"
client_secret = "${GOOGLE_CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
```

（`redirect_uri`は4章のデプロイ後、5章で本番URLに更新する）

Secret Managerへアップロード（`TF_VAR_streamlit_secrets_id`は1章末尾の`tf_infra_phase_outputs_to_env.sh`でexport済み）:

```bash
gcloud secrets versions add ${TF_VAR_streamlit_secrets_id} \
  --project=${TF_VAR_project_id} \
  --data-file=secrets.toml

rm secrets.toml   # ローカルにも平文で残さない
```

### 許可リスト（実効的なアクセス制御。管理者発行アカウントのみ、のための許可メール一覧）

> **⚠️ 置き場所に注意**: 必ず**バケットルート直下**（`gs://${TF_VAR_bucket_name}/_admin/...`）に置くこと。`GCS_BASE_DIR`（`.../backtest_experiments/results`）の配下に置くと、`ExperimentLoader.list_experiments()`が`_admin`を実験名として誤検出し、アプリの実験名一覧が壊れる（実際に事故った）。

```bash
cat > allowlist.yaml <<EOF
allowed_emails:
  - your-email@gmail.com
EOF

gsutil cp allowlist.yaml gs://${TF_VAR_bucket_name}/_admin/allowlist.yaml
rm allowlist.yaml
```

運用中に許可ユーザーを追加・削除する場合は、上記を書き換えて再度`gsutil cp`するだけでよい（再デプロイ不要、次回アクセス時から反映される）。

---

## 4. イメージのbuild & push、appフェーズのデプロイ（アプリ更新の度に毎回）

### 4-0. 新しいターミナルセッションなら、まずこれを実行（毎回）

`terraform apply`（infra/app）自体は必要な時だけでよいが、以下の環境変数exportは**新しいターミナルを開く度に毎回**必要（前のセッションでexportした環境変数は引き継がれないため）。すでに同じセッションで1章まで終えている場合はスキップしてよい。

```bash
# .env → TF_VAR_* （0-0と同じコマンド）
export $(grep -v -E '^\s*#|^\s*$' .env | \
  sed -E 's/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/TF_VAR_\L\1=\2/' | \
  xargs -d '\n')

# infraの出力（SAメール等） → TF_VAR_* （1章と同じコマンド。infra apply済みなら何度実行してもOK）
source tf_infra_phase_outputs_to_env.sh
```

### 4-1. build & push

> **⚠️ `latest`固定タグは使わない**: `image_tag=latest`のような固定タグのままだと、Terraformは「imageの文字列が前回と同じ」としか見ないため、**新しいイメージをpushしてもCloud Run側に新しいリビジョンがデプロイされないことがある**（`terraform apply`が差分無しと判断してしまう）。これにより「直したはずなのに古いバグが再現し続ける」という事態が起きるので、**ビルドの度に一意のタグ**を使うこと。

```bash
# リポジトリのDockerイメージ認証
gcloud auth configure-docker ${TF_VAR_region}-docker.pkg.dev

# ビルド毎に一意なタグ（日時）を使う
export TF_VAR_image_tag=$(date +%Y%m%d%H%M%S)

# build
docker build --platform linux/amd64 \
  -t ${TF_VAR_region}-docker.pkg.dev/${TF_VAR_project_id}/${TF_VAR_artifact_repo_name}/${TF_VAR_image_name}:${TF_VAR_image_tag} \
  .
# push
docker push ${TF_VAR_region}-docker.pkg.dev/${TF_VAR_project_id}/${TF_VAR_artifact_repo_name}/${TF_VAR_image_name}:${TF_VAR_image_tag}
```

### 4-2. app apply

```bash
terraform -chdir=deploy/terraform/app init
terraform -chdir=deploy/terraform/app plan
terraform -chdir=deploy/terraform/app apply
terraform -chdir=deploy/terraform/app output cloud_run_url   # デプロイされたURLを確認
```

（`project_id`/`region`/`image_name`は0-0の`.env`、`image_tag`は4-1で上書きした値、`artifact_repo_name`/`app_sa_email`/`streamlit_secrets_id`は1章末尾の`tf_infra_phase_outputs_to_env.sh`から、それぞれ環境変数経由で渡っているので、こちらも`.tfvars`は不要）

---

## 5. 本番のredirect_uriを反映（初回デプロイ後の1回だけ）

Cloud RunのURLは初回デプロイまで確定しないため、初回のみ以下を後追いで行う。

1. `terraform output cloud_run_url`で得たURLをもとに、2章のOAuthクライアントの **Authorized redirect URIs** に
   `<cloud_run_url>/oauth2callback` を追加
2. 3章の`secrets.toml`の`redirect_uri`を本番URLに書き換え、`gcloud secrets versions add`で新バージョンとして再アップロード
3. Cloud Runは`latest`バージョンのシークレットマウントを自動的に追随するが、反映されない場合は`terraform -chdir=deploy/terraform/app apply`を再実行して新しいリビジョンを出す

以降のアプリ更新（コード変更のみ）は4章のbuild & push → `terraform apply`だけでよい（1〜3章・5章は初回のみ）。

---

## 動作確認

```bash
curl -I "$(terraform -chdir=deploy/terraform/app output -raw cloud_run_url)"
```

ブラウザで開き、openなデータがログイン無しで見える・closedなデータがログイン後のみ見えることを確認する。
