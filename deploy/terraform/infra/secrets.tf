# Streamlitのネイティブ認証（st.login）は.streamlit/secrets.tomlの[auth]セクションを
# 読み込む仕様のため、client_secret/cookie_secretを含むsecrets.toml全体を1つのSecretとして
# 保持し、Cloud Run側でファイルとしてマウントする（app/cloudrun.tf参照）。
#
# 値（実際のsecrets.toml本文）はterraformでは一切扱わない。
# 中身がtfstateに平文で残ってしまうのを避けるため、シークレットの"箱"だけここで作り、
# 値は下記のようにgcloudコマンドで手動投入すること:
#
#   gcloud secrets versions add btlog-streamlit-secrets-toml \
#     --project=<project_id> --data-file=secrets.toml
#
resource "google_secret_manager_secret" "streamlit_secrets" {
  secret_id = var.streamlit_secrets_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "app_sa_secrets_access" {
  secret_id = google_secret_manager_secret.streamlit_secrets.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}
