#!/bin/bash
# tf_infra_phase_outputs_to_env.sh
#
# deploy/terraform/infra の出力（apply後にしか値が決まらないもの: SAメール等）を
# TF_VAR_* 環境変数に変換してexportする。app フェーズで terraform.tfvars を
# 手で書き写す必要がなくなる。
#
# 使い方（infra apply後に一度）:
#   source tf_infra_phase_outputs_to_env.sh
#
# 要 jq。

outputs_json=$(terraform -chdir=deploy/terraform/infra output -json)

for key in $(echo "$outputs_json" | jq -r 'keys[]'); do
  value=$(echo "$outputs_json" | jq -r ".\"$key\".value")
  var_name="TF_VAR_${key}"
  export "$var_name=$value"
  echo "Exported $var_name=$value"
done
