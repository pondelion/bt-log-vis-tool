output "app_sa_email" {
  value = google_service_account.app_sa.email
}

output "artifact_repo_name" {
  value = google_artifact_registry_repository.docker_repo.repository_id
}

output "bucket_name" {
  value = google_storage_bucket.results_bucket.name
}

output "streamlit_secrets_id" {
  value = google_secret_manager_secret.streamlit_secrets.secret_id
}
