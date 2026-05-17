# サンプルコード

このディレクトリには、bt-log-vis-toolの使用例が含まれています。

## ファイル一覧

### example_save.py

Pythonスクリプトとして実験データを保存するサンプルです。

実行方法:

```bash
python examples/example_save.py
```

### example_notebook.ipynb

Jupyter Notebook形式のサンプルです。バックテスト実験をノートブックで行い、結果を保存する典型的なワークフローを示しています。

使用方法:

```bash
jupyter notebook examples/example_notebook.ipynb
```

## 基本的な使い方

### 1. データ保存

```python
from bt_log_vis_tool import ExperimentSaver

# Saver初期化
saver = ExperimentSaver(
    base_dir="~/backtest_experiments",
    exp_name="my_experiment",
    run_name="run_001"
)

# データ保存
saver.save_pnl_strategy(pnl_df)
saver.save_stats_metrics(stats_df)
saver.save_params(params_dict)
```

### 2. ダッシュボード起動

```bash
streamlit run bt_log_vis_tool/app.py
```

ブラウザで http://localhost:8501 にアクセスして、保存したデータを可視化できます。

## データフォーマット

詳細は[ai_coding_prompt.md](../ai_coding_prompt.md)を参照してください。

### PnL DataFrame例

```python
import pandas as pd

# 戦略毎PnL
pnl_df = pd.DataFrame({
    'strategy_long': [...],      # 戦略1のPnL
    'strategy_short': [...],     # 戦略2のPnL
    'split': ['train', 'val', 'test', ...],  # データ分割
    'run_id': ['epoch_0', 'epoch_0', ...],   # エポック等の識別ID
}, index=pd.date_range('2023-01-01', periods=100))
```

### 統計メトリクス DataFrame例

```python
# 統計メトリクス
stats_df = pd.DataFrame({
    'annual_return': [...],
    'sharpe_ratio': [...],
    'split': ['train', 'val', 'test', ...],
    'run_id': ['epoch_0', 'epoch_1', ...],
}, index=range(10))  # epoch番号
```

### パラメータ辞書例

```python
params = {
    'model': {
        'type': 'neural_network',
        'layers': [128, 64, 32],
    },
    'training': {
        'epochs': 10,
        'learning_rate': 0.001,
    }
}
```
