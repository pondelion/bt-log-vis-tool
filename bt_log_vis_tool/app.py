"""Streamlit可視化ダッシュボードアプリ

バックテスト実験結果を可視化するWebダッシュボード
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bt_log_vis_tool.auth import render_auth_sidebar
from bt_log_vis_tool.loader import ExperimentLoader
from bt_log_vis_tool.storage import AnyPath as Path
from bt_log_vis_tool.utils import calculate_cumulative_pnl, filter_by_conditions

SPLIT_ORDER = ["train", "val", "test"]

# Cloud Runは全コンテナにK_SERVICEを自動設定するため、これでクラウド実行かどうかを判定できる
# （デプロイ済み環境ではローカルデータソースを選択する意味が無いため選択肢自体を隠す）
IS_CLOUD_RUN = bool(os.environ.get("K_SERVICE"))

# データ取得のキャッシュTTL（秒）。Streamlitはウィジェット操作の度にスクリプト全体を
# 再実行するため、キャッシュ無しだと無関係なウィジェット操作（例: コードタブでの
# ファイル切替）でもGCS上の重いparquetを毎回re-fetchしてしまい重くなる。
# 実験結果は一度保存された後は更新されない運用のため、TTLは長め（24時間）にしている
# （0にする＝無期限も検討したが、万一の更新に対する自己修復のため一応上限は設ける）。
_CACHE_TTL_SECONDS = 60 * 60 * 24

# ExperimentLoaderはbase_dir/exp_name/run_nameで一意に定まるが、st.cache_dataの
# デフォルトハッシュではオブジェクトそのものを見てしまいキャッシュが効かないため、
# 意味のあるキー（3つの文字列）でハッシュするよう明示する。
_LOADER_HASH_FUNCS = {ExperimentLoader: lambda loader: (str(loader.base_dir), loader.exp_name, loader.run_name)}


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_stats_metrics_strategy(loader: ExperimentLoader) -> pd.DataFrame | None:
    return loader.load_stats_metrics_strategy()


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_stats_metrics_individual(loader: ExperimentLoader) -> pd.DataFrame | None:
    return loader.load_stats_metrics_individual()


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_pnl_pred_position_strategy(loader: ExperimentLoader) -> pd.DataFrame | None:
    return loader.load_pnl_pred_position_strategy()


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_pnl_pred_position_ticker(loader: ExperimentLoader) -> pd.DataFrame | None:
    return loader.load_pnl_pred_position_ticker()


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_meta(loader: ExperimentLoader, data_type: str) -> dict | None:
    return loader.load_meta(data_type)


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _get_available_data_types(loader: ExperimentLoader) -> list[str]:
    return loader.get_available_data_types()


def sort_splits(splits: list[str]) -> list[str]:
    """splitをtrain/val/testの順に並べる（未知のsplit値はアルファベット順で末尾に追加）"""
    known = [s for s in SPLIT_ORDER if s in splits]
    unknown = sorted(s for s in splits if s not in SPLIT_ORDER)
    return known + unknown


def main():
    """メイン関数"""
    st.set_page_config(page_title="Backtest Dashboard", page_icon="💹", layout="wide")

    st.title("バックテスト実験ダッシュボード")

    with st.sidebar:
        st.header("設定")

        if IS_CLOUD_RUN:
            data_source = "クラウド (GCS)"
        else:
            data_source = st.radio("データソース", ["ローカル", "クラウド (GCS)"], horizontal=True)

        if data_source == "クラウド (GCS)":
            base_dir = st.text_input(
                "GCSパス",
                value=os.environ.get("GCS_BASE_DIR", "gs://"),
                help="実験データが保存されているGCSバケット/プレフィックス（例: gs://my-bucket/backtest_experiments/results）",
            )
        else:
            base_dir = st.text_input(
                "ベースディレクトリ",
                value=str(Path('.') / "backtest_experiments/results"),
                help="実験データが保存されているディレクトリ",
            )

        if data_source == "クラウド (GCS)":
            auth_state = render_auth_sidebar(base_dir)
            can_view_closed = auth_state.is_authorized
        else:
            # ローカルデータソースは権限判定なし・常にフルオープン（今まで通りの挙動）
            can_view_closed = True

        if data_source == "クラウド (GCS)" and base_dir.strip() in ("", "gs://"):
            st.info("GCSパスを入力してください（例: gs://my-bucket/backtest_experiments/results）")
            return

        base_path = Path(base_dir)
        try:
            base_dir_exists = base_path.exists()
        except Exception as e:
            st.error(f"ディレクトリへのアクセスに失敗しました: {e}")
            if data_source == "クラウド (GCS)":
                st.info("GCS利用時はGoogle Cloudの認証情報（Application Default Credentials）が設定されているか確認してください")
            return

        if not base_dir_exists:
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

    available_types = _get_available_data_types(loader)
    st.sidebar.info(f"利用可能なデータ: {', '.join(available_types)}")

    # --- サイドバーにベストエポック判定設定（全タブ共通） ---
    best_epoch = _setup_best_epoch_sidebar(loader)

    tabs = st.tabs(["統計メトリクス", "戦略時系列（資産曲線・ポジション）", "銘柄別時系列（資産曲線・ポジション）", "パラメータ", "コード", "サマリレポート"])

    with tabs[0]:
        render_stats_tab(loader, best_epoch)

    with tabs[1]:
        render_timeseries_tab(loader, best_epoch)

    with tabs[2]:
        render_ticker_tab(loader, best_epoch)

    with tabs[3]:
        render_params_tab(loader, can_view_closed)

    with tabs[4]:
        render_code_tab(loader, can_view_closed)

    with tabs[5]:
        render_report_tab(loader, can_view_closed)


def _setup_best_epoch_sidebar(loader: ExperimentLoader) -> int | None:
    """サイドバーにベストエポック判定設定を追加し、best_epochを返す"""
    stats_df = _load_stats_metrics_strategy(loader)
    stats_type = "stats_metrics/strategy"
    if stats_df is None:
        stats_df = _load_stats_metrics_individual(loader)
        stats_type = "stats_metrics/individual"
    if stats_df is None:
        return None

    if stats_df.index.name == "epoch":
        stats_df = stats_df.reset_index(drop="epoch" in stats_df.columns)

    meta = _load_meta(loader, stats_type)
    if meta is not None:
        non_metric_columns = meta.get("non_metric_columns", ["split"])
        metric_cols = meta.get("metric_columns", [])
    else:
        non_metric_columns = ["split"]
        metric_cols = [c for c in stats_df.columns if c not in non_metric_columns]

    has_strategy = "strategy_name" in non_metric_columns and "strategy_name" in stats_df.columns
    splits = sort_splits(stats_df["split"].unique().tolist()) if "split" in stats_df.columns else []
    strategies = sorted(stats_df["strategy_name"].unique().tolist()) if has_strategy else []

    if not splits or not metric_cols:
        return None

    with st.sidebar:
        st.markdown("---")
        st.subheader("ベストエポック判定設定")

        default_split_idx = splits.index("val") if "val" in splits else 0
        best_split = st.selectbox("判定 split", splits, index=default_split_idx, key="best_split")

        sharpe_cols = [c for c in metric_cols if "sharpe" in c.lower()]
        default_metric = sharpe_cols[0] if sharpe_cols else metric_cols[0]
        best_metric = st.selectbox(
            "判定 メトリクス", metric_cols, index=metric_cols.index(default_metric), key="best_metric"
        )

        if has_strategy:
            default_strategy_idx = strategies.index("long_short") if "long_short" in strategies else 0
            best_strategy = st.selectbox("判定 strategy", strategies, index=default_strategy_idx, key="best_strategy")
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

    stats_df = _load_stats_metrics_strategy(loader)
    data_type = "stats_metrics/strategy"
    if stats_df is None:
        stats_df = _load_stats_metrics_individual(loader)
        data_type = "stats_metrics/individual"
    if stats_df is None:
        st.warning("統計メトリクスデータが見つかりません")
        return

    meta = _load_meta(loader, data_type)
    if meta is not None:
        non_metric_columns = meta.get("non_metric_columns", ["split"])
        metric_cols = meta.get("metric_columns", [])
    else:
        non_metric_columns = ["split"]
        metric_cols = [col for col in stats_df.columns if col not in non_metric_columns]

    if stats_df.index.name == "epoch":
        stats_df = stats_df.reset_index(drop="epoch" in stats_df.columns)

    has_strategy = "strategy_name" in non_metric_columns and "strategy_name" in stats_df.columns
    splits = sort_splits(stats_df["split"].unique().tolist()) if "split" in stats_df.columns else []
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
        default_bm_idx = next((i + 1 for i, s in enumerate(strategies) if s.startswith("bm_")), 0)
        benchmark_strategy_sel = st.selectbox(
            "ベンチマーク戦略（赤色強調）", benchmark_options, index=default_bm_idx, key="stats_benchmark"
        )
        if benchmark_strategy_sel != "(なし)":
            benchmark_strategy = benchmark_strategy_sel

    # === グラフ表示（メトリック毎に縦並び、split毎に横並び） ===
    st.markdown("### エポック推移グラフ")

    if "epoch" not in stats_df.columns:
        st.info("epoch列がないためグラフを表示できません")
    else:
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
                # strategy_name毎に別テーブルとして縦に並べる
                for strategy in strategies:
                    strategy_data = filter_by_conditions(split_data, strategy_name=strategy)
                    if len(strategy_data) == 0:
                        continue
                    st.markdown(f"*{strategy}*")
                    st.dataframe(strategy_data.set_index("epoch")[metric_cols], use_container_width=True)
            elif "epoch" in split_data.columns:
                st.dataframe(split_data.set_index("epoch")[metric_cols], use_container_width=True)
            else:
                st.dataframe(split_data[metric_cols], use_container_width=True)


def render_timeseries_tab(loader: ExperimentLoader, best_epoch: int | None):
    """時系列（資産曲線・ポジション）タブを描画"""
    st.subheader("時系列データ可視化")

    strategy_df = _load_pnl_pred_position_strategy(loader)

    if strategy_df is None:
        st.warning("戦略データが見つかりません")
        return

    # メタデータ読み込み
    meta = _load_meta(loader, "pnl_pred_position/strategy")
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
        epoch_label = f"表示エポック (ベストエポック: {best_epoch})" if best_epoch is not None else "表示エポック"
        epoch = st.selectbox(epoch_label, available_epochs, index=default_idx)
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
        st.markdown("### 資産曲線（累積リターン）")
        render_equity_curve(epoch_data, epoch, condition_columns)

    # 絶対損益の描画
    if "pnl_abs" in value_columns:
        st.markdown("### 資産曲線（累積損益・絶対値）")
        render_equity_curve(epoch_data, epoch, condition_columns, pnl_column="pnl_abs", chart_title="累積損益(絶対値)")

    # ポジションの描画
    if "position" in value_columns:
        st.markdown("### ポジション時系列")
        pos_cumsum = st.checkbox("cumsum表示", value=True, key="strategy_pos_cumsum")
        render_position(epoch_data, epoch, condition_columns, cumsum=pos_cumsum)


def render_equity_curve(df, epoch, condition_columns, pnl_column: str = "pnl", chart_title: str = "累積PnL"):
    """資産曲線を描画（split毎に列を分けてy軸スケールを独立させる）

    Args:
        df: データフレーム
        epoch: 選択されたエポック
        condition_columns: 条件カラムのリスト
        pnl_column: 累積対象のカラム名（"pnl"=率、"pnl_abs"=絶対損益）
        chart_title: グラフタイトルに使う名称
    """
    if "strategy_name" not in condition_columns:
        st.warning("strategy_nameカラムが見つかりません")
        return

    # strategy_name毎にグループ化
    strategies = df["strategy_name"].unique()
    splits = sort_splits(df["split"].unique().tolist()) if "split" in df.columns else ["all"]
    colors = px.colors.qualitative.Plotly

    columns = st.columns(len(splits))
    for col, split in zip(columns, splits):
        split_data = filter_by_conditions(df, split=split) if "split" in df.columns else df

        fig = go.Figure()
        for j, strategy in enumerate(strategies):
            strategy_data = filter_by_conditions(split_data, strategy_name=strategy)

            if len(strategy_data) > 0 and pnl_column in strategy_data.columns:
                cum_pnl = calculate_cumulative_pnl(strategy_data[pnl_column])

                fig.add_trace(
                    go.Scatter(
                        x=strategy_data.index,
                        y=cum_pnl,
                        mode="lines",
                        name=strategy,
                        line=dict(color=colors[j % len(colors)]),
                    )
                )

        fig.update_layout(
            title=f"{chart_title} ({split}) - エポック {epoch}",
            xaxis_title="日時",
            yaxis_title=chart_title,
            hovermode="x unified",
        )

        with col:
            st.plotly_chart(fig, use_container_width=True)


def render_position(df, epoch, condition_columns, cumsum: bool = False):
    """ポジション時系列を描画（split毎に列を分けてy軸スケールを独立させる）"""
    if "strategy_name" not in condition_columns:
        st.warning("strategy_nameカラムが見つかりません")
        return

    if "position" not in df.columns:
        st.info("positionカラムが存在しません")
        return

    strategies = df["strategy_name"].unique()
    splits = sort_splits(df["split"].unique().tolist()) if "split" in df.columns else ["all"]
    colors = px.colors.qualitative.Plotly
    ylabel = "ポジション累積" if cumsum else "ポジション"

    columns = st.columns(len(splits))
    for col, split in zip(columns, splits):
        split_data = filter_by_conditions(df, split=split) if "split" in df.columns else df

        fig = go.Figure()
        for j, strategy in enumerate(strategies):
            strategy_data = filter_by_conditions(split_data, strategy_name=strategy)

            if len(strategy_data) > 0:
                y = strategy_data["position"].cumsum() if cumsum else strategy_data["position"]
                fig.add_trace(
                    go.Scatter(
                        x=strategy_data.index,
                        y=y,
                        mode="lines",
                        name=strategy,
                        line=dict(color=colors[j % len(colors)]),
                    )
                )

        fig.update_layout(
            title=f"{ylabel} ({split}) - エポック {epoch}",
            xaxis_title="日時",
            yaxis_title=ylabel,
            hovermode="x unified",
        )

        with col:
            st.plotly_chart(fig, use_container_width=True)


def render_ticker_equity_curve(epoch_df, display_splits, selected_tickers, colors, pnl_column: str = "pnl", chart_title: str = "累積PnL"):
    """銘柄別の累積損益曲線を描画（split毎に列を分ける）"""
    graph_cols = st.columns(len(display_splits))
    for i, split in enumerate(display_splits):
        with graph_cols[i]:
            split_df = filter_by_conditions(epoch_df, split=split) if split else epoch_df
            fig = go.Figure()
            for j, ticker in enumerate(selected_tickers):
                t_df = filter_by_conditions(split_df, ticker=ticker)
                if len(t_df) == 0 or pnl_column not in t_df.columns:
                    continue
                cum_pnl = calculate_cumulative_pnl(t_df[pnl_column])
                fig.add_trace(go.Scatter(
                    x=t_df.index,
                    y=cum_pnl,
                    mode="lines",
                    name=ticker,
                    line=dict(color=colors[j % len(colors)]),
                ))
            fig.update_layout(
                title=f"{chart_title} ({split})" if split else chart_title,
                xaxis_title="日時",
                yaxis_title=chart_title,
                hovermode="x unified",
                height=400,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)


def render_ticker_tab(loader: ExperimentLoader, best_epoch: int | None):
    """銘柄別時系列タブを描画"""
    st.subheader("銘柄別時系列")

    # 銘柄別データはファイルサイズが大きくGCSからのダウンロードも重いため、
    # チェックボックスで明示的に選択されるまではロード自体を行わない
    show_charts = st.checkbox("グラフを表示する（銘柄数が多いとダウンロード・描画が重くなります）", value=False, key="ticker_show_charts")
    if not show_charts:
        st.info("上のチェックボックスをオンにするとグラフが表示されます")
        return

    ticker_df = _load_pnl_pred_position_ticker(loader)
    if ticker_df is None:
        st.info("銘柄別データ（pnl_pred_position/ticker）が見つかりません")
        return

    meta = _load_meta(loader, "pnl_pred_position/ticker")
    if meta is None:
        st.warning("メタデータが見つかりません")
        return

    condition_columns = meta.get("condition_columns", [])
    value_columns = meta.get("value_columns", [])

    # エポック選択
    if "epoch" in condition_columns:
        available_epochs = sorted(ticker_df["epoch"].unique().tolist())
        default_idx = available_epochs.index(best_epoch) if best_epoch in available_epochs else 0
        epoch_label = f"表示エポック (ベストエポック: {best_epoch})" if best_epoch is not None else "表示エポック"
        epoch = st.selectbox(epoch_label, available_epochs, index=default_idx, key="ticker_epoch")
        epoch_df = filter_by_conditions(ticker_df, epoch=epoch)
    else:
        epoch_df = ticker_df.copy()
        epoch = None

    if len(epoch_df) == 0:
        st.warning(f"エポック {epoch} のデータが見つかりません")
        return

    # Split チェックボックス（横並び）
    splits = sort_splits(epoch_df["split"].unique().tolist()) if "split" in epoch_df.columns else []
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

    # === 資産曲線（累積リターン）===
    if "pnl" in value_columns:
        st.markdown("### 資産曲線（累積リターン）")
        render_ticker_equity_curve(epoch_df, display_splits, selected_tickers, colors)

    # === 絶対損益 ===
    if "pnl_abs" in value_columns:
        st.markdown("### 資産曲線（累積損益・絶対値）")
        render_ticker_equity_curve(epoch_df, display_splits, selected_tickers, colors, pnl_column="pnl_abs", chart_title="累積損益(絶対値)")

    # === ポジション ===
    if "position" in value_columns:
        st.markdown("### ポジション時系列")
        ticker_pos_cumsum = st.checkbox("cumsum表示", value=True, key="ticker_pos_cumsum")
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
                        y=t_df["position"].cumsum() if ticker_pos_cumsum else t_df["position"],
                        mode="lines",
                        name=ticker,
                        line=dict(color=colors[j % len(colors)]),
                    ))
                pos_ylabel = "ポジション累積" if ticker_pos_cumsum else "ポジション"
                pos_title = f"{pos_ylabel} ({split})" if split else pos_ylabel
                fig.update_layout(
                    title=pos_title,
                    xaxis_title="日時",
                    yaxis_title=pos_ylabel,
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


def render_params_tab(loader: ExperimentLoader, can_view_closed: bool):
    """パラメータタブを描画

    Args:
        loader: ExperimentLoader
        can_view_closed: Trueの場合closed指定のパラメータファイルも表示する
    """
    st.subheader("ハイパーパラメータ")

    params_files = loader.list_params_files(can_view_closed=can_view_closed)
    if not params_files:
        if can_view_closed:
            st.warning("パラメータファイルが見つかりません")
        else:
            st.info("🔒 閲覧可能なパラメータファイルがありません。closedなパラメータを見るにはログインが必要です。")
        return

    if len(params_files) == 1:
        filename = params_files[0]
    else:
        filename = st.selectbox("ファイル選択", params_files, key="params_file_select")

    params = loader.load_params(filename, can_view_closed=can_view_closed)
    st.json(params)


def render_code_tab(loader: ExperimentLoader, can_view_closed: bool):
    """コードタブを描画

    Args:
        loader: ExperimentLoader
        can_view_closed: Trueの場合closed指定のコードも表示する
    """
    st.subheader("実験コード")

    code_files = loader.list_code_files(can_view_closed=can_view_closed)
    if not code_files:
        if can_view_closed:
            st.warning("コードファイルが見つかりません")
        else:
            st.info("🔒 閲覧可能なコードファイルがありません。closedなコードを見るにはログインが必要です。")
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
        filename = code_files[0]
        lang = ext_to_language.get(Path(filename).suffix.lower(), "text")
        st.markdown(f"**{filename}**")
        st.code(loader.load_code(filename, can_view_closed=can_view_closed) or "", language=lang)
    else:
        selected = st.selectbox("ファイル選択", code_files, key="code_file_select")
        lang = ext_to_language.get(Path(selected).suffix.lower(), "text")
        st.code(loader.load_code(selected, can_view_closed=can_view_closed) or "", language=lang)


def render_report_tab(loader: ExperimentLoader, can_view_closed: bool):
    """サマリレポートタブを描画

    Args:
        loader: ExperimentLoader
        can_view_closed: Trueの場合closed指定のレポートも表示する
    """
    st.subheader("サマリレポート")

    report_files = loader.list_reports(can_view_closed=can_view_closed)
    if not report_files:
        if can_view_closed:
            st.info("サマリレポートはまだありません")
        else:
            st.info("🔒 閲覧可能なサマリレポートがありません。closedなレポートを見るにはログインが必要です。")
        return

    if len(report_files) == 1:
        filename = report_files[0]
        content = loader.load_report(filename, can_view_closed=can_view_closed) or ""
        st.markdown(content)
    else:
        selected = st.selectbox("レポート選択", report_files, key="report_file_select")
        content = loader.load_report(selected, can_view_closed=can_view_closed) or ""
        st.markdown(content)


if __name__ == "__main__":
    main()
