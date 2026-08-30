resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = var.artifact_repo_name
  description   = "Docker repo for bt-log-vis-tool dashboard"
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  # ストレージ課金を抑えるため、最新1件だけ残して古いイメージは自動削除する
  # （デプロイタグは日時ベースの一意タグを都度使う運用のため、放置すると無限に積み上がる）
  cleanup_policies {
    id     = "keep-latest"
    action = "KEEP"
    most_recent_versions {
      keep_count = 1
    }
  }

  # 年齢条件は付けない（付けるとその期間内は「最新以外」も削除対象にならず溜まり続ける）。
  # keep-latestで保護される最新1件以外は、経過時間に関係なく即削除対象にする。
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }
}
