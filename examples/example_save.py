"""サンプル: 実験データの保存

Jupyter Notebookからバックテスト実験の結果を保存するサンプルコード
"""

import numpy as np
import pandas as pd

from bt_log_vis_tool import ExperimentSaver

# 設定
BASE_DIR = "./backtest_experiments"
EXP_NAME = "mock_experiment"
RUN_NAME = "run_001"

# サンプルデータの作成
dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
n_dates = len(dates)

# エポック数
n_epochs = 10

# train/val/test は境界日付を共有する連続した期間
# max(train) == min(val), max(val) == min(test)
n_per_split = n_dates // 3
split_dates = {
    "train": dates[: n_per_split + 1],
    "val":   dates[n_per_split : 2 * n_per_split + 1],
    "test":  dates[2 * n_per_split :],
}

# 戦略毎PnL/Pred/Positionデータの作成例
strategy_data_list = []
date_idx = []

for epoch in range(n_epochs):
    for split in ["train", "val", "test"]:
        for strategy in ["longshort", "long_only", "short_only"]:
            for date in split_dates[split]:
                strategy_data_list.append(
                    {
                        "split": split,
                        "epoch": epoch,
                        "strategy_name": strategy,
                    }
                )
                date_idx.append(date)

pnl_pred_position_strategy_df = pd.DataFrame(strategy_data_list, index=date_idx)

# 値カラムの追加
pnl_pred_position_strategy_df["pnl"] = np.random.randn(len(pnl_pred_position_strategy_df)) * 0.01
pnl_pred_position_strategy_df["pred"] = np.random.randn(len(pnl_pred_position_strategy_df)) * 0.5
pnl_pred_position_strategy_df["position"] = np.random.choice(
    [-1, 0, 1], size=len(pnl_pred_position_strategy_df)
)

print("Strategy DataFrame:")
print(pnl_pred_position_strategy_df.head(10))
print(f"\nShape: {pnl_pred_position_strategy_df.shape}")
print(f"Columns: {pnl_pred_position_strategy_df.columns.tolist()}")


# 統計メトリクスデータの作成例（戦略毎）
stats_data = []
for epoch in range(n_epochs):
    for split in ["train", "val", "test"]:
        for strategy in ["longshort", "long_only", "short_only"]:
            stats_data.append(
                {
                    "epoch": epoch,
                    "split": split,
                    "strategy_name": strategy,
                    "annual_return": np.random.uniform(0.05, 0.20),
                    "annual_risk": np.random.uniform(0.10, 0.25),
                    "sharpe_ratio": np.random.uniform(0.5, 2.0),
                    "max_drawdown": -np.random.uniform(0.05, 0.15),
                }
            )

stats_strategy_df = pd.DataFrame(stats_data)
# epochをindexに設定しつつ、カラムとしても保持
stats_strategy_df = stats_strategy_df.set_index(stats_strategy_df["epoch"])
stats_strategy_df.index.name = "epoch"

print("\nStats Strategy DataFrame:")
print(stats_strategy_df.head(10))


# ハイパーパラメータの例
params = {
    "model": {
        "type": "neural_network",
        "layers": [128, 64, 32],
        "activation": "relu",
        "dropout": 0.2,
    },
    "training": {
        "epochs": n_epochs,
        "batch_size": 256,
        "learning_rate": 0.001,
        "optimizer": "adam",
    },
    "strategy": {
        "long_threshold": 0.6,
        "short_threshold": -0.6,
        "rebalance_freq": "daily",
    },
}


# 実験コードの例
code = '''
# バックテスト実験コード
import pandas as pd
import numpy as np

# データ読み込み
data = load_data()

# モデル学習
model = train_model(data)

# 予測
predictions = model.predict(data)

# 戦略実行
pnl = execute_strategy(predictions)
'''


# 保存実行
def main():
    """メイン処理"""
    # Saver初期化
    saver = ExperimentSaver(BASE_DIR, EXP_NAME, RUN_NAME)

    print("\n実験データを保存中...")

    # 全データを一括保存
    saver.save_all(
        pnl_pred_position_strategy=pnl_pred_position_strategy_df,
        stats_metrics_strategy=stats_strategy_df,
        params=params,
        code=code,
        code_filename="experiment.py",
    )

    print("\n保存完了!")
    print(f"保存先: {saver.run_dir}")
    print("\n次のコマンドでダッシュボードを起動:")
    print("  streamlit run bt_log_vis_tool/app.py")


if __name__ == "__main__":
    main()
