# bt-log-vis-tool

バックテスト実験管理・可視化ツール

バックテスト実験の結果を構造化して保存し、Streamlitダッシュボードで可視化するためのPythonパッケージです。

## 特徴

- Jupyter Notebookからの簡単なデータ保存API
- 実験結果の構造化保存（PnL、ポジション、統計メトリクス等）
- Streamlitベースのインタラクティブなダッシュボード
- エポック毎のパフォーマンス追跡
- ベストエポックの自動検出
- Train/Val/Test split毎の可視化
- データソースをローカル/GCSで切り替え可能
- クラウド(GCS)利用時のGoogleログイン＋ファイル単位のopen/closed閲覧権限
- GCP Cloud Runへのデプロイに対応（Terraform）

詳細な仕様は [docs/specification.md](docs/specification.md)、デプロイ手順は [docs/deploy.md](docs/deploy.md) を参照してください。

## インストール

### uvを使用する場合（推奨）

```bash
# 依存関係のインストール
uv sync

# 開発用パッケージも含める場合
uv sync --all-extras
```

### pipを使用する場合

```bash
pip install -e .

# 開発用パッケージも含める場合
pip install -e ".[dev]"
```

## クイックスタート

### 1. 実験データの保存

Jupyter Notebookまたはスクリプトから:

```python
from bt_log_vis_tool import ExperimentSaver
import pandas as pd

# Saver初期化
saver = ExperimentSaver(
    base_dir="~/backtest_experiments",
    exp_name="momentum_strategy",
    run_name="run_001"
)

# データ保存
saver.save_all(
    pnl_pred_position_strategy=strategy_df,  # 戦略毎PnL/Pred/Position DataFrame
    stats_metrics_strategy=stats_df,         # 戦略毎統計メトリクス DataFrame
    params=params_dict,                      # ハイパーパラメータ辞書
    code=code_string,                        # 実験コード（文字列）
    code_filename="closed/experiment.py",    # デフォルトclosed。open/closedの詳細は仕様書参照
)
```

`base_dir`にはローカルパスの他、`gs://bucket/prefix`形式のGCSパスも渡せます。

### 2. ダッシュボードの起動

```bash
streamlit run bt_log_vis_tool/app.py
```

ブラウザで http://localhost:8501 にアクセスして可視化。サイドバーからデータソース（ローカル/GCS）を切り替えられます。

## データ仕様・ダッシュボード機能

保存ディレクトリ構造、DataFrameフォーマット、open/closed閲覧権限モデル、ダッシュボードの各タブの詳細仕様は [docs/specification.md](docs/specification.md) を参照してください。

## サンプルコード

[examples/](examples/) ディレクトリにサンプルコードがあります:

- [example_save.py](examples/example_save.py): Pythonスクリプト例
実行例:

```bash
# uvを使用する場合
PYTHONPATH=. uv run python examples/example_save.py

# pipでインストールした場合
python examples/example_save.py
```

## 開発

### テスト実行

```bash
pytest
```

### コードフォーマット

```bash
ruff check .
ruff format .
```