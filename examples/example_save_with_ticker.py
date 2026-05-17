"""サンプル: 銘柄毎データ + 戦略データの保存

銘柄毎のpnl/pred/positionと、それを集約した戦略毎データを
あわせて保存するサンプルコード
"""

import numpy as np
import pandas as pd

from bt_log_vis_tool import ExperimentSaver

# 設定
BASE_DIR = "./backtest_experiments"
EXP_NAME = "mock_experiment_with_ticker"
RUN_NAME = "run_001"

# サンプルデータの作成
dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
n_dates = len(dates)
n_epochs = 10
tickers = ["AAPL", "GOOGL", "MSFT", "AMZN"]
strategies = ["longshort", "long_only"]

# train/val/test は境界日付を共有する連続した期間
# max(train) == min(val), max(val) == min(test)
n_per_split = n_dates // 3
split_dates = {
    "train": dates[: n_per_split + 1],
    "val":   dates[n_per_split : 2 * n_per_split + 1],
    "test":  dates[2 * n_per_split :],
}

# ------------------------------------------------------------------ #
# 銘柄毎 PnL/Pred/Position データ
# 必須カラム: split, epoch, ticker
# ------------------------------------------------------------------ #
ticker_data_list = []
ticker_date_idx = []

for epoch in range(n_epochs):
    for split in ["train", "val", "test"]:
        for ticker in tickers:
            for date in split_dates[split]:
                ticker_data_list.append(
                    {
                        "split": split,
                        "epoch": epoch,
                        "ticker": ticker,
                    }
                )
                ticker_date_idx.append(date)

pnl_pred_position_ticker_df = pd.DataFrame(ticker_data_list, index=ticker_date_idx)
pnl_pred_position_ticker_df["pnl"] = np.random.randn(len(pnl_pred_position_ticker_df)) * 0.005
pnl_pred_position_ticker_df["pred"] = np.random.randn(len(pnl_pred_position_ticker_df)) * 0.5
pnl_pred_position_ticker_df["position"] = np.random.choice(
    [-1, 0, 1], size=len(pnl_pred_position_ticker_df)
)

print("Ticker DataFrame:")
print(pnl_pred_position_ticker_df.head(10))
print(f"Shape: {pnl_pred_position_ticker_df.shape}")
print(f"Columns: {pnl_pred_position_ticker_df.columns.tolist()}")

# ------------------------------------------------------------------ #
# 戦略毎 PnL/Pred/Position データ（銘柄を集約した最終戦略）
# 必須カラム: split, epoch, strategy_name
# ------------------------------------------------------------------ #
strategy_data_list = []
strategy_date_idx = []

for epoch in range(n_epochs):
    for split in ["train", "val", "test"]:
        for strategy in strategies:
            for date in split_dates[split]:
                strategy_data_list.append(
                    {
                        "split": split,
                        "epoch": epoch,
                        "strategy_name": strategy,
                    }
                )
                strategy_date_idx.append(date)

pnl_pred_position_strategy_df = pd.DataFrame(strategy_data_list, index=strategy_date_idx)
pnl_pred_position_strategy_df["pnl"] = np.random.randn(len(pnl_pred_position_strategy_df)) * 0.01
pnl_pred_position_strategy_df["pred"] = np.random.randn(len(pnl_pred_position_strategy_df)) * 0.5
pnl_pred_position_strategy_df["position"] = np.random.choice(
    [-1, 0, 1], size=len(pnl_pred_position_strategy_df)
)

print("\nStrategy DataFrame:")
print(pnl_pred_position_strategy_df.head(10))
print(f"Shape: {pnl_pred_position_strategy_df.shape}")

# ------------------------------------------------------------------ #
# 統計メトリクス（戦略毎）
# ------------------------------------------------------------------ #
stats_data = []
for epoch in range(n_epochs):
    for split in ["train", "val", "test"]:
        for strategy in strategies:
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
stats_strategy_df = stats_strategy_df.set_index(stats_strategy_df["epoch"])
stats_strategy_df.index.name = "epoch"

# ------------------------------------------------------------------ #
# ハイパーパラメータ
# ------------------------------------------------------------------ #
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
        "tickers": tickers,
    },
}

code = '''
# バックテスト実験コード（銘柄毎 + 戦略集約）
import pandas as pd
import numpy as np

tickers = ["AAPL", "GOOGL", "MSFT", "AMZN"]

# 銘柄毎に予測・ポジション算出
ticker_results = {}
for ticker in tickers:
    data = load_data(ticker)
    pred = model.predict(data)
    position = compute_position(pred)
    pnl = compute_pnl(position, data["returns"])
    ticker_results[ticker] = {"pred": pred, "position": position, "pnl": pnl}

# 銘柄集約して戦略PnL算出
strategy_pnl = aggregate_to_strategy(ticker_results)
'''


def main():
    """メイン処理"""
    saver = ExperimentSaver(BASE_DIR, EXP_NAME, RUN_NAME)

    print("\n実験データを保存中...")

    saver.save_all(
        pnl_pred_position_ticker=pnl_pred_position_ticker_df,
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
