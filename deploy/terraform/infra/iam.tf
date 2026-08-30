# Cloud Run実行用SA（アプリ本体用）。最小権限: GCSの読み取り(storage.objectViewer、
# storage.tf側で付与)とSecret Managerからのsecrets.toml読み取り(secrets.tf側で付与)のみ。
# terraform実行自体は専用SAを作らず、プロジェクトOwnerである自分のGoogleアカウントの
# ADC（gcloud auth application-default login）を使う運用とする。
resource "google_service_account" "app_sa" {
  account_id   = var.app_sa_account_id
  display_name = "bt-log-vis-tool Cloud Run app SA (read-only)"
}
