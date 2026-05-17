"""ユーティリティ関数モジュール

データ処理や可視化に使用する共通関数
"""

import pandas as pd


def calculate_cumulative_pnl(pnl_series: pd.Series) -> pd.Series:
    """累積PnLを計算

    Args:
        pnl_series: PnL系列

    Returns:
        累積PnL系列
    """
    return pnl_series.cumsum()


def calculate_stats(pnl_series: pd.Series, periods_per_year: int = 252) -> dict:
    """パフォーマンス統計を計算

    Args:
        pnl_series: PnL時系列（日次等）
        periods_per_year: 年あたりの期間数（日次なら252等）

    Returns:
        統計値の辞書
    """
    total_return = pnl_series.sum()
    mean_return = pnl_series.mean()
    std_return = pnl_series.std()

    annual_return = mean_return * periods_per_year
    annual_risk = std_return * (periods_per_year**0.5)

    sharpe_ratio = annual_return / annual_risk if annual_risk > 0 else 0.0

    cumsum_pnl = pnl_series.cumsum()
    max_drawdown = (cumsum_pnl - cumsum_pnl.cummax()).min()

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_risk": annual_risk,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
    }


def find_best_epoch(
    stats_df: pd.DataFrame,
    metric_column: str,
    split: str = "val",
    split_column: str = "split",
    ascending: bool = False,
) -> int:
    """ベストエポックを見つける

    Args:
        stats_df: 統計メトリクスDataFrame
        metric_column: 評価に使用するメトリック列名
        split: 評価に使用するsplit
        split_column: split列名
        ascending: 昇順でベストを選ぶ場合True（デフォルトは降順）

    Returns:
        ベストエポック番号
    """
    if split_column in stats_df.columns:
        split_data = stats_df[stats_df[split_column] == split]
    else:
        split_data = stats_df

    if metric_column not in split_data.columns:
        return stats_df.index[0] if len(stats_df) > 0 else 0

    if ascending:
        best_idx = split_data[metric_column].idxmin()
    else:
        best_idx = split_data[metric_column].idxmax()

    return best_idx


def filter_by_conditions(df: pd.DataFrame, **conditions) -> pd.DataFrame:
    """条件カラムでフィルタリング

    Args:
        df: DataFrame
        **conditions: 条件カラムと値のペア（例: epoch=0, split="train"）

    Returns:
        フィルタリングされたDataFrame
    """
    filtered = df.copy()
    for column, value in conditions.items():
        if column in filtered.columns:
            filtered = filtered[filtered[column] == value]
    return filtered
