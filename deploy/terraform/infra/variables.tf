variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  description = "GCPリージョン"
  default     = "asia-northeast1"
}

variable "bucket_name" {
  type        = string
  description = "実験結果を格納するGCSバケット名（非公開）"
}

variable "artifact_repo_name" {
  type        = string
  description = "Artifact RegistryのDockerリポジトリ名"
  default     = "bt-log-vis-tool"
}

variable "app_sa_account_id" {
  type        = string
  description = "Cloud Run実行用サービスアカウントのaccount_id"
  default     = "btlog-cloudrun-app"
}

variable "streamlit_secrets_id" {
  type        = string
  description = "Streamlitのsecrets.toml全体を値として持つSecret Managerシークレットのsecret_id"
  default     = "btlog-streamlit-secrets-toml"
}
