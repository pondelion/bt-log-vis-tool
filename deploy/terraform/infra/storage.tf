# 実験結果を格納するGCSバケット。
# open/closedの区別はアプリ層（bt_log_vis_tool/permissions.py）でのみ行うため、
# バケット自体は常に完全非公開（誰にも公開IAM/ACLを付与しない）。
# public_access_prevention="enforced" により、将来の設定ミスで誤って公開されることも防ぐ。
resource "google_storage_bucket" "results_bucket" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

# Cloud Run実行用SAは読み取り専用。書き込み（実験結果のアップロード）は
# ローカルの学習スクリプトからユーザー自身のADCで行う想定で、アプリ本体からは書き込まない。
resource "google_storage_bucket_iam_member" "app_sa_bucket_read" {
  bucket = google_storage_bucket.results_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.app_sa.email}"
}
