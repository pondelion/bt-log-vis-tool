"""Streamlit可視化ダッシュボードアプリ

バックテスト実験結果を可視化するWebダッシュボード
"""

from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bt_log_vis_tool.loader import ExperimentLoader
from bt_log_vis_tool.utils import calculate_cumulative_pnl, filter_by_conditions


def main():
    """メイン関数"""
    st.set_page_config(page_title="Backtest Dashboard", layout="wide")

    st.title("バックテスト実験ダッシュボード")

    with st.sidebar:
        st.header("設定")

        base_dir = st.text_input(
            "ベースディレクトリ",
            # value=str(Path.home() / "backtest_experiments"),
            value=str(Path('.') / "backtest_experiments"),
            help="実験データが保存されているディレクトリ",
        )

        base_path = Path(base_dir)
        if not base_path.exists():
            st.warning(f"ディレクトリが存在しません: {base_dir}")
            st.info("データを保存してから実行してください")
            return

        experiments = ExperimentLoader.list_experiments(base_dir)
        if not experiments:
            st.warning("実験データが見つかりません")
            return

        exp_name = st.selectbox("実験名 (exp_name)", experiments)

        runs = ExperimentLoader.list_runs(base_dir, exp_name)
        if not runs:
            st.warning(f"実験 '{exp_name}' にランが見つかりません")
            return

        run_name = st.selectbox("ラン名 (run_name)", runs)

    loader = ExperimentLoader(base_dir, exp_name, run_name)

    if not loader.exists():
        st.error(f"データが見つかりません: {exp_name}/{run_name}")
        return

    st.header(f"実験: {exp_name} / ラン: {run_name}")

    available_types = loader.get_available_data_types()
    st.sidebar.info(f"利用可能なデータ: {', '.join(available_types)}")

    # --- サイドバーにベストエポック判定設定（全タブ共通） ---
    best_epoch = _setup_best_epoch_sidebar(loader)

    tabs = st.tabs(["統計メトリクス", "戦略時系列（資産曲線・ポジション）", "銘柄別時系列（資産曲線・ポジション）", "パラメータ", "コード"])

    with tabs[0]:
        render_stats_tab(loader, best_epoch)

    with tabs[1]:
        render_timeseries_tab(loader, best_epoch)

    with tabs[2]:
        render_ticker_tab(loader, best_epoch)

    with tabs[3]:
        render_params_tab(loader)

    with tabs[4]:
        render_code_tab(loader)


def _setup_best_epoch_sidebar(loader: ExperimentLoader) -> int | None:
    """サイドバーにベストエポック判定設定を追加し、best_epochを返す"""
    stats_df = loader.load_stats_metrics_strategy()
    stats_type = "stats_metrics/strategy"
    if stats_df is None:
        stats_df = loader.load_stats_metrics_individual()
        stats_type = "stats_metrics/individual"
    if stats_df is None:
        return None

    if stats_df.index.name == "epoch":
        stats_df = stats_df.reset_index(drop="epoch" in stats_df.columns)

    meta = loader.load_meta(stats_type)
    if meta is not None:
        non_metric_columns = meta.get("non_metric_columns", ["split"])
        metric_cols = meta.get("metric_columns", [])
    else:
        non_metric_columns = ["split"]
        metric_cols = [c for c in stats_df.columns if c not in non_metric_columns]

    has_strategy = "strategy_name" in non_metric_columns and "strategy_name" in stats_df.columns
    splits = sorted(stats_df["split"].unique().tolist()) if "split" in stats_df.columns else []
    strategies = sorted(stats_df["strategy_name"].unique().tolist()) if has_strategy else []

    if not splits or not metric_cols:
        return None

    with st.sidebar:
        st.markdown("---")
        st.subheader("ベストエポック判定設定")

        default_split_idx = splits.index("test") if "test" in splits else 0
        best_split = st.selectbox("判定 split", splits, index=default_split_idx, key="best_split")

        sharpe_cols = [c for c in metric_cols if "sharpe" in c.lower()]
        default_metric = sharpe_cols[0] if sharpe_cols else metric_cols[0]
        best_metric = st.selectbox(
            "判定 メトリクス", metric_cols, index=metric_cols.index(default_metric), key="best_metric"
        )

        if has_strategy:
            best_strategy = st.selectbox("判定 strategy", strategies, key="best_strategy")
        else:
            best_strategy = None

    best_epoch = None
    if "epoch" in stats_df.columns:
        filtered = filter_by_conditions(stats_df, split=best_split)
        if has_strategy and best_strategy:
            filtered = filter_by_conditions(filtered, strategy_name=best_strategy)
        if len(filtered) > 0:
            epoch_means = filtered.groupby("epoch")[best_metric].mean()
            best_epoch = int(epoch_means.idxmax())

    st.sidebar.info(
        f"ベストエポック: {best_epoch}\n"
        f"(split={best_split}, {best_metric}"
        + (f", {best_strategy}" if best_strategy else "")
        + ")"
    )
    return best_epoch


def render_stats_tab(loader: ExperimentLoader, best_epoch: int | None):
    """統計メトリクスタブを描画"""
    st.subheader("統計メトリクス")

    stats_df = loader.load_stats_metrics_strategy()
    data_type = "stats_metrics/strategy"
    if stats_df is None:
        stats_df = loader.load_stats_metrics_individual()
        data_type = "stats_metrics/individual"
    if stats_df is None:
        st.warning("統計メトリクスデータが見つかりません")
        return

    meta = loader.load_meta(data_type)
    if meta is not None:
        non_metric_columns = meta.get("non_metric_columns", ["split"])
        metric_cols = meta.get("metric_columns", [])
    else:
        non_metric_columns = ["split"]
        metric_cols = [col for col in stats_df.columns if col not in non_metric_columns]

    if stats_df.index.name == "epoch":
        stats_df = stats_df.reset_index(drop="epoch" in stats_df.columns)

    has_strategy = "strategy_name" in non_metric_columns and "strategy_name" in stats_df.columns
    splits = sorted(stats_df["split"].unique().tolist()) if "split" in stats_df.columns else []
    strategies = sorted(stats_df["strategy_name"].unique().tolist()) if has_strategy else []

    if not splits:
        st.warning("split列が見つかりません")
        return
    if not metric_cols:
        st.warning("メトリクス列が見つかりません")
        return

    # --- Split選択チェックボックス ---
    st.markdown("**表示するSplit:**")
    split_check_cols = st.columns(max(len(splits), 1))
    selected_splits = []
    for i, split in enumerate(splits):
        with split_check_cols[i]:
            if st.checkbox(split, value=True, key=f"stats_split_check_{split}"):
                selected_splits.append(split)

    if not selected_splits:
        st.info("表示するsplitを選択してください")
        return

    # --- ベンチマーク戦略選択 ---
    benchmark_strategy = None
    if has_strategy:
        benchmark_options = ["(なし)"] + strategies
        default_bm_idx = next(
            (i + 1 for i, s in enumerate(strategies) if any(k in s.lower() for k in ["buy", "hold", "benchmark"])),
            0,
        )
        benchmark_strategy_sel = st.selectbox(
            "ベンチマーク戦略（赤色強調）", benchmark_options, index=default_bm_idx, key="stats_benchmark"
        )
        if benchmark_strategy_sel != "(なし)":
            benchmark_strategy = benchmark_strategy_sel

    # === テーブル表示（生データ、split横並び） ===
    st.markdown("### 統計メトリクス表")
    table_cols_ui = st.columns(len(selected_splits))
    for i, split in enumerate(selected_splits):
        with table_cols_ui[i]:
            st.markdown(f"**Split: {split}**")
            split_data = filter_by_conditions(stats_df, split=split)
            if len(split_data) == 0:
                st.info("データなし")
                continue

            if has_strategy and "epoch" in split_data.columns:
                # {メトリクス名}_{strategy_name} の横持ちテーブル
                pivot_df = split_data.pivot_table(
                    index="epoch",
                    columns="strategy_name",
                    values=metric_cols,
                    aggfunc="mean",
                )
                pivot_df.columns = [f"{m}_{s}" for m, s in pivot_df.columns]
                pivot_df.index.name = "epoch"
                st.dataframe(pivot_df, use_container_width=True)
            elif "epoch" in split_data.columns:
                st.dataframe(split_data.set_index("epoch")[metric_cols], use_container_width=True)
            else:
                st.dataframe(split_data[metric_cols], use_container_width=True)

    # === グラフ表示（メトリック毎に縦並び、split毎に横並び） ===
    st.markdown("### エポック推移グラフ")

    if "epoch" not in stats_df.columns:
        st.info("epoch列がないためグラフを表示できません")
        return

    colors = px.colors.qualitative.Plotly

    for metric in metric_cols:
        st.markdown(f"#### {metric}")
        graph_cols_ui = st.columns(len(selected_splits))

        for i, split in enumerate(selected_splits):
            with graph_cols_ui[i]:
                split_data = filter_by_conditions(stats_df, split=split)
                fig = go.Figure()

                if has_strategy:
                    for j, strategy in enumerate(strategies):
                        strat_data = filter_by_conditions(split_data, strategy_name=strategy)
                        if len(strat_data) == 0 or metric not in strat_data.columns:
                            continue
                        epoch_agg = strat_data.groupby("epoch")[metric].mean().reset_index()
                        is_bm = strategy == benchmark_strategy
                        fig.add_trace(
                            go.Scatter(
                                x=epoch_agg["epoch"],
                                y=epoch_agg[metric],
                                mode="lines+markers",
                                name=strategy,
                                line=dict(
                                    color="red" if is_bm else colors[j % len(colors)],
                                    width=3 if is_bm else 1.5,
                                ),
                            )
                        )
                else:
                    if metric in split_data.columns:
                        epoch_agg = split_data.groupby("epoch")[metric].mean().reset_index()
                        fig.add_trace(
                            go.Scatter(
                                x=epoch_agg["epoch"],
                                y=epoch_agg[metric],
                                mode="lines+markers",
                                name=metric,
                            )
                        )

                if best_epoch is not None:
                    fig.add_vline(
                        x=best_epoch,
                        line_dash="dash",
                        line_color="gray",
                        annotation_text=f"best:{best_epoch}",
                    )

                fig.update_layout(
                    title=f"{metric} ({split})",
                    xaxis_title="epoch",
                    yaxis_title=metric,
                    hovermode="x unified",
                    height=350,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)


def render_timeseries_tab(loader: ExperimentLoader, best_epoch: int | None):
    """時系列（資産曲線・ポジション）タブを描画"""
    st.subheader("時系列データ可視化")

    strategy_df = loader.load_pnl_pred_position_strategy()

    if strategy_df is None:
        st.warning("戦略データが見つかりません")
        return

    # メタデータ読み込み
    meta = loader.load_meta("pnl_pred_position/strategy")
    if meta is None:
        st.warning("メタデータが見つかりません")
        return

    condition_columns = meta.get("condition_columns", [])
    value_columns = meta.get("value_columns", [])

    # エポック選択（サイドバーで算出されたベストエポックをデフォルトに）
    if "epoch" in condition_columns:
        available_epochs = sorted(strategy_df["epoch"].unique().tolist())
    else:
        available_epochs = []

    if available_epochs:
        default_idx = available_epochs.index(best_epoch) if best_epoch in available_epochs else 0
        epoch = st.selectbox("表示エポック", available_epochs, index=default_idx)
    else:
        epoch = None

    # エポックでフィルタリング
    if "epoch" in condition_columns:
        epoch_data = filter_by_conditions(strategy_df, epoch=epoch)
    else:
        epoch_data = strategy_df.copy()

    if len(epoch_data) == 0:
        st.warning(f"エポック {epoch} のデータが見つかりません")
        return

    # 資産曲線の描画
    if "pnl" in value_columns:
        st.markdown("### 資産曲線（累積PnL）")
        render_equity_curve(epoch_data, epoch, condition_columns)

    # ポジションの描画
    if "position" in value_columns:
        st.markdown("### ポジション時系列")
        render_position(epoch_data, epoch, condition_columns)


def render_equity_curve(df, epoch, condition_columns):
    """資産曲線を描画

    Args:
        df: データフレーム
        epoch: 選択されたエポック
        condition_columns: 条件カラムのリスト
    """
    if "strategy_name" not in condition_columns:
        st.warning("strategy_nameカラムが見つかりません")
        return

    # strategy_name毎にグループ化
    strategies = df["strategy_name"].unique()
    splits = df["split"].unique() if "split" in df.columns else ["all"]

    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    for i, split in enumerate(splits):
        split_data = filter_by_conditions(df, split=split) if "split" in df.columns else df

        for strategy in strategies:
            strategy_data = filter_by_conditions(split_data, strategy_name=strategy)

            if len(strategy_data) > 0 and "pnl" in strategy_data.columns:
                cum_pnl = calculate_cumulative_pnl(strategy_data["pnl"])

                fig.add_trace(
                    go.Scatter(
                        x=strategy_data.index,
                        y=cum_pnl,
                        mode="lines",
                        name=f"{strategy} ({split})",
                        line=dict(color=colors[i % len(colors)]),
                    )
                )

    fig.update_layout(
        title=f"累積PnL - エポック {epoch}",
        xaxis_title="日時",
        yaxis_title="累積PnL",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_position(df, epoch, condition_columns):
    """ポジション時系列を描画

    Args:
        df: データフレーム
        epoch: 選択されたエポック
        condition_columns: 条件カラムのリスト
    """
    if "strategy_name" not in condition_columns:
        st.warning("strategy_nameカラムが見つかりません")
        return

    if "position" not in df.columns:
        st.info("positionカラムが存在しません")
        return

    # strategy_name毎にグループ化
    strategies = df["strategy_name"].unique()
    splits = df["split"].unique() if "split" in df.columns else ["all"]

    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    for i, split in enumerate(splits):
        split_data = filter_by_conditions(df, split=split) if "split" in df.columns else df

        for strategy in strategies:
            strategy_data = filter_by_conditions(split_data, strategy_name=strategy)

            if len(strategy_data) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=strategy_data.index,
                        y=strategy_data["position"],
                        mode="lines",
                        name=f"{strategy} ({split})",
                        line=dict(color=colors[i % len(colors)]),
                    )
                )

    fig.update_layout(
        title=f"ポジション - エポック {epoch}",
        xaxis_title="日時",
        yaxis_title="ポジション",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_ticker_tab(loader: ExperimentLoader, best_epoch: int | None):
    """銘柄別時系列タブを描画"""
    st.subheader("銘柄別時系列")

    ticker_df = loader.load_pnl_pred_position_ticker()
    if ticker_df is None:
        st.info("銘柄別データ（pnl_pred_position/ticker）が見つかりません")
        return

    meta = loader.load_meta("pnl_pred_position/ticker")
    if meta is None:
        st.warning("メタデータが見つかりません")
        return

    condition_columns = meta.get("condition_columns", [])
    value_columns = meta.get("value_columns", [])

    # エポック選択
    if "epoch" in condition_columns:
        available_epochs = sorted(ticker_df["epoch"].unique().tolist())
        default_idx = available_epochs.index(best_epoch) if best_epoch in available_epochs else 0
        epoch = st.selectbox("表示エポック", available_epochs, index=default_idx, key="ticker_epoch")
        epoch_df = filter_by_conditions(ticker_df, epoch=epoch)
    else:
        epoch_df = ticker_df.copy()
        epoch = None

    if len(epoch_df) == 0:
        st.warning(f"エポック {epoch} のデータが見つかりません")
        return

    # Split チェックボックス（横並び）
    splits = sorted(epoch_df["split"].unique().tolist()) if "split" in epoch_df.columns else []
    selected_splits = []
    if splits:
        st.markdown("**表示するSplit:**")
        split_cols = st.columns(max(len(splits), 1))
        for i, split in enumerate(splits):
            with split_cols[i]:
                if st.checkbox(split, value=True, key=f"ticker_split_{split}"):
                    selected_splits.append(split)
    else:
        selected_splits = []

    if splits and not selected_splits:
        st.info("表示するsplitを選択してください")
        return

    # Ticker 選択
    tickers = sorted(epoch_df["ticker"].unique().tolist()) if "ticker" in epoch_df.columns else []
    if not tickers:
        st.warning("ticker列が見つかりません")
        return

    selected_tickers = st.multiselect("表示するTicker", tickers, default=tickers, key="ticker_select")
    if not selected_tickers:
        st.info("表示するtickerを選択してください")
        return

    colors = px.colors.qualitative.Plotly
    display_splits = selected_splits if selected_splits else [None]

    # === 資産曲線（累積PnL）===
    if "pnl" in value_columns:
        st.markdown("### 資産曲線（累積PnL）")
        graph_cols = st.columns(len(display_splits))
        for i, split in enumerate(display_splits):
            with graph_cols[i]:
                split_df = filter_by_conditions(epoch_df, split=split) if split else epoch_df
                fig = go.Figure()
                for j, ticker in enumerate(selected_tickers):
                    t_df = filter_by_conditions(split_df, ticker=ticker)
                    if len(t_df) == 0:
                        continue
                    cum_pnl = calculate_cumulative_pnl(t_df["pnl"])
                    fig.add_trace(go.Scatter(
                        x=t_df.index,
                        y=cum_pnl,
                        mode="lines",
                        name=ticker,
                        line=dict(color=colors[j % len(colors)]),
                    ))
                fig.update_layout(
                    title=f"累積PnL ({split})" if split else "累積PnL",
                    xaxis_title="日時",
                    yaxis_title="累積PnL",
                    hovermode="x unified",
                    height=400,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)

    # === ポジション ===
    if "position" in value_columns:
        st.markdown("### ポジション時系列")
        graph_cols = st.columns(len(display_splits))
        for i, split in enumerate(display_splits):
            with graph_cols[i]:
                split_df = filter_by_conditions(epoch_df, split=split) if split else epoch_df
                fig = go.Figure()
                for j, ticker in enumerate(selected_tickers):
                    t_df = filter_by_conditions(split_df, ticker=ticker)
                    if len(t_df) == 0:
                        continue
                    fig.add_trace(go.Scatter(
                        x=t_df.index,
                        y=t_df["position"],
                        mode="lines",
                        name=ticker,
                        line=dict(color=colors[j % len(colors)]),
                    ))
                fig.update_layout(
                    title=f"ポジション ({split})" if split else "ポジション",
                    xaxis_title="日時",
                    yaxis_title="ポジション",
                    hovermode="x unified",
                    height=400,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)

    # === 予測値 ===
    if "pred" in value_columns:
        st.markdown("### 予測値時系列")
        graph_cols = st.columns(len(display_splits))
        for i, split in enumerate(display_splits):
            with graph_cols[i]:
                split_df = filter_by_conditions(epoch_df, split=split) if split else epoch_df
                fig = go.Figure()
                for j, ticker in enumerate(selected_tickers):
                    t_df = filter_by_conditions(split_df, ticker=ticker)
                    if len(t_df) == 0:
                        continue
                    fig.add_trace(go.Scatter(
                        x=t_df.index,
                        y=t_df["pred"],
                        mode="lines",
                        name=ticker,
                        line=dict(color=colors[j % len(colors)]),
                    ))
                fig.update_layout(
                    title=f"予測値 ({split})" if split else "予測値",
                    xaxis_title="日時",
                    yaxis_title="pred",
                    hovermode="x unified",
                    height=400,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)


def render_params_tab(loader: ExperimentLoader):
    """パラメータタブを描画"""
    st.subheader("ハイパーパラメータ")

    params = loader.load_params()

    if params is None:
        st.warning("パラメータファイルが見つかりません")
        return

    st.json(params)


def render_code_tab(loader: ExperimentLoader):
    """コードタブを描画"""
    st.subheader("実験コード")

    codes_dir = loader.run_dir / "codes"
    if not codes_dir.exists():
        st.warning("コードファイルが見つかりません")
        return

    code_files = sorted(codes_dir.iterdir())
    if not code_files:
        st.warning("コードファイルが見つかりません")
        return

    ext_to_language = {
        ".py": "python",
        ".ipynb": "json",
        ".r": "r",
        ".sql": "sql",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".txt": "text",
    }

    if len(code_files) == 1:
        f = code_files[0]
        lang = ext_to_language.get(f.suffix.lower(), "text")
        st.markdown(f"**{f.name}**")
        st.code(loader.load_code(f.name) or "", language=lang)
    else:
        selected = st.selectbox("ファイル選択", [f.name for f in code_files], key="code_file_select")
        suffix = Path(selected).suffix.lower()
        lang = ext_to_language.get(suffix, "text")
        st.code(loader.load_code(selected) or "", language=lang)


if __name__ == "__main__":
    main()
