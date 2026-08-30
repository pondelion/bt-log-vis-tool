# 常時HTTPを受けるWebサービス（バッチジョブではない）。
# openなデータは誰でも見られる必要があるため、ingressは公開のまま
# （closedデータの閲覧制御はCloud Run側ではなく、GoogleのOAuth Test Users制限＋
#   アプリ層のst.login判定で行う設計）。
resource "google_cloud_run_v2_service" "btlog_dashboard" {
  name     = var.image_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.app_sa_email

    scaling {
      min_instance_count = 0 # 無料枠を活かすためアイドル時はスケールtoゼロ
      # 1に固定: Streamlitのst.login()フローはインスタンス間でstateが共有されないため、
      # 複数インスタンスに分散すると/auth/login〜/oauth2callbackの間で
      # 別インスタンスに振られてログインが失敗する（"NoneType" object does not
      # support item assignment）。低トラフィック用途なので1で十分。
      max_instance_count = 1
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo_name}/${var.image_name}:${var.image_tag}"

      ports {
        container_port = 8501
      }

      env {
        name  = "GCS_BASE_DIR"
        value = "gs://${var.bucket_name}/backtest_experiments/results"
      }

      resources {
        limits = {
          cpu = "1"
          # 1024Miだとキャッシュ(TTL長め)保持中のDataFrame(銘柄別データは600万行規模)で
          # OOM→再起動を繰り返すクラッシュループが発生したため引き上げ
          memory = "2048Mi"
        }
      }

      volume_mounts {
        name       = "streamlit-secrets"
        mount_path = "/app/.streamlit"
      }
    }

    # infra/secrets.tfで作成したsecrets.toml全体を、コンテナ内に
    # .streamlit/secrets.tomlとしてそのままファイルマウントする
    # （Streamlitのst.login/st.userはこのファイルパスを直接読みに行くため、
    #   env var経由に変換するアプリ側の追加実装が不要になる）。
    volumes {
      name = "streamlit-secrets"
      secret {
        secret = var.streamlit_secrets_id
        items {
          version = "latest"
          path    = "secrets.toml"
        }
      }
    }
  }
}

# openなコンテンツを未ログインでも閲覧できるようにするため、
# Cloud Run自体は誰でも呼び出し可能にする（アプリ層で閲覧範囲を制御する設計）
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.btlog_dashboard.location
  name     = google_cloud_run_v2_service.btlog_dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
