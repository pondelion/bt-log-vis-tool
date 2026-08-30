# サンプルコード

このディレクトリには、bt-log-vis-toolの使用例が含まれています。基本的な使い方はPythonスクリプト（.py）を想定していますが、同じAPIをJupyter Notebookから呼び出しても構いません。

## ファイル一覧

### example_save.py

戦略毎のPnL/Pred/Positionデータを保存する基本的なサンプルです。

実行方法:

```bash
python examples/example_save.py
```

### example_save_with_ticker.py

銘柄毎のpnl/pred/positionと、それを集約した戦略毎データをあわせて保存するサンプルです。

実行方法:

```bash
python examples/example_save_with_ticker.py
```

### example_notebook.ipynb

同じ内容をJupyter Notebook形式で行うサンプルです（任意。上記の.pyスクリプトと内容は同等）。

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
saver.save_all(
    pnl_pred_position_strategy=strategy_df,
    stats_metrics_strategy=stats_df,
    params=params_dict,
)
```

### 2. ダッシュボード起動

```bash
streamlit run bt_log_vis_tool/app.py
```

ブラウザで http://localhost:8501 にアクセスして、保存したデータを可視化できます。

## データフォーマット

保存ディレクトリ構造・DataFrameフォーマット・open/closed閲覧権限モデルの詳細は [docs/specification.md](../docs/specification.md) を参照してください。
