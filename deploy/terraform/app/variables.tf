variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  description = "GCPリージョン"
  default     = "asia-northeast1"
}

variable "artifact_repo_name" {
  type        = string
  description = "infraフェーズの出力（artifact_repo_name）"
}

variable "image_name" {
  type        = string
  description = "Cloud Runサービス名・イメージ名"
  default     = "bt-log-vis-tool"
}

variable "image_tag" {
  type        = string
  description = "デプロイするDockerイメージのタグ"
  default     = "latest"
}

variable "app_sa_email" {
  type        = string
  description = "infraフェーズの出力（app_sa_email）"
}

variable "streamlit_secrets_id" {
  type        = string
  description = "infraフェーズの出力（streamlit_secrets_id）"
}

variable "bucket_name" {
  type        = string
  description = "infraフェーズの出力（bucket_name）。アプリのGCSパス入力欄のデフォルト値に使う"
}
