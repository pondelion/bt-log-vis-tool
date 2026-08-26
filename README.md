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
)
```

### 2. ダッシュボードの起動

```bash
streamlit run bt_log_vis_tool/app.py
```

ブラウザで http://localhost:8501 にアクセスして可視化

## データ仕様

詳細は [specification.md](specification.md) を参照してください。

### 保存ディレクトリ構造

```
{base_dir}/
└── {exp_name}/
    └── {run_name}/
        ├── pnl_pred_position/
        │   ├── ticker/
        │   │   ├── data.parquet
        │   │   └── meta.yaml
        │   ├── individual/
        │   │   ├── data.parquet
        │   │   └── meta.yaml
        │   └── strategy/
        │       ├── data.parquet
        │       └── meta.yaml
        ├── stats_metrics/
        │   ├── strategy/
        │   │   ├── data.parquet
        │   │   └── meta.yaml
        │   └── individual/
        │       ├── data.parquet
        │       └── meta.yaml
        ├── params/
        │   └── config.yaml
        └── codes/
            └── experiment.py
```

### DataFrame フォーマット例

#### PnL/Pred/Position DataFrame (戦略毎)

```python
# index: DatetimeIndex
# 必須カラム: pnl, split, epoch, strategy_name
# 任意カラム: pred, position, その他条件カラム

            split  epoch strategy_name    pnl   pred  position
2023-01-01  train      0     longshort  0.010  0.123         1
2023-01-02  train      0     longshort  0.005 -0.045         0
2023-01-03  train      0     longshort -0.002  0.234        -1
...
```

#### 統計メトリクス DataFrame (戦略毎)

```python
# index: epoch番号
# 必須カラム: split, strategy_name
# その他: メトリック名（実験毎に任意）

       split strategy_name  annual_return  sharpe_ratio  max_drawdown
0      train     longshort           0.15           1.2         -0.10
0        val     longshort           0.12           1.0         -0.15
1      train     longshort           0.18           1.5         -0.08
...
```

## ダッシュボード機能

- **統計メトリクス**: Split毎の統計値表示とエポック推移グラフ
- **資産曲線**: 戦略毎の累積PnL時系列（エポック選択可能、ベストエポック自動検出）
- **ポジション**: 戦略毎のポジション時系列
- **パラメータ**: ハイパーパラメータの確認

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