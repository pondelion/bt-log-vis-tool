"""Streamlit可視化ダッシュボードアプリ

バックテスト実験結果を可視化するWebダッシュボード
"""

import math
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bt_log_vis_tool.auth import render_auth_sidebar
from bt_log_vis_tool.loader import ExperimentLoader
from bt_log_vis_tool.storage import AnyPath as Path
from bt_log_vis_tool.utils import calculate_stats, filter_by_conditions

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


@st.cache_data(ttl=_CACHE_TTL_SECONDS, max_entries=8, show_spinner=False, hash_funcs=_LOADER_HASH_FUNCS)
def _load_backtest_config_params(loader: ExperimentLoader, can_view_closed: bool) -> dict | None:
    """paramsファイル群から、`target_horizon`・`backtest_entry_interval_days`をトップレベルキーとして
    持つファイルを探し、その2値の辞書を返す（bt-log-vis-tool仕様書2.5.1節の共通バックテスト設定
    パラメータ参照）。複数ファイルがある場合は両キーを持つ最初のものを使う。見つからなければNone
    （closed指定でcan_view_closed=Falseの場合、読めるファイルが無ければNone＝機能ごと非表示になる）"""
    for filename in loader.list_params_files(can_view_closed=can_view_closed):
        params = loader.load_params(filename, can_view_closed=can_view_closed)
        if params and "target_horizon" in params and "backtest_entry_interval_days" in params:
            return {"target_horizon": params["target_horizon"], "backtest_entry_interval_days": params["backtest_entry_interval_days"]}
    return None


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

    tabs = st.tabs(
        ["成績サマリ", "メトリクス学習推移", "戦略時系列（資産曲線・ポジション）", "銘柄別時系列（資産曲線・ポジション）", "パラメータ", "コード", "サマリレポート"]
    )

    # メトリクス学習推移タブ内の期間選択（該当する場合）を先に描画し、その選択結果をサイドバーの
    # ベストエポック判定設定（判定 split/メトリクス/strategy。全タブ共通）に反映する
    best_epoch, selected_period, best_epoch_by_period = _setup_best_epoch_sidebar(loader, tabs[1])

    with tabs[0]:
        render_summary_tab(loader, best_epoch, best_epoch_by_period, can_view_closed)

    with tabs[1]:
        render_stats_tab(loader, best_epoch, selected_period)

    with tabs[2]:
        render_timeseries_tab(loader, best_epoch, best_epoch_by_period, can_view_closed)

    with tabs[3]:
        render_ticker_tab(loader, best_epoch, best_epoch_by_period)

    with tabs[4]:
        render_params_tab(loader, can_view_closed)

    with tabs[5]:
        render_code_tab(loader, can_view_closed)

    with tabs[6]:
        render_report_tab(loader, can_view_closed)


def _render_period_selector_in_tab(stats_df: pd.DataFrame, container) -> tuple[pd.DataFrame, tuple | None]:
    """stats_dfにperiod_start/period_endがあれば期間選択UIをcontainer（メトリクス学習推移タブ）内に
    描画し、選択期間で絞り込んだstats_dfと選択期間(period_start, period_end)のタプルを返す
    （period_start/period_endが無い場合は絞り込みせずそのまま返し、選択期間はNone）。

    ベストエポック判定はこの期間選択の結果を使うが、判定 split/メトリクス/strategy 自体は
    時系列タブとも共通のためサイドバーに残す（`_setup_best_epoch_sidebar`参照）。期間選択の
    概念自体はメトリクス学習推移タブにしか無いため、ウィジェットの描画先だけをこのタブ内にする。
    """
    has_period = "period_start" in stats_df.columns and "period_end" in stats_df.columns

    with container:
        st.subheader("メトリクス学習推移")
        if not has_period:
            return stats_df, None

        unique_periods = stats_df[["period_start", "period_end"]].drop_duplicates().sort_values("period_start")
        period_list = list(zip(unique_periods["period_start"], unique_periods["period_end"], strict=True))
        period_labels = [f"{pd.Timestamp(p[0]).date()} 〜 {pd.Timestamp(p[1]).date()}" for p in period_list]
        selected_label = st.selectbox("期間（ウォークフォワード）", period_labels, index=len(period_labels) - 1, key="wf_period_select")

    selected_period = period_list[period_labels.index(selected_label)]
    filtered_df = stats_df[(stats_df["period_start"] == selected_period[0]) & (stats_df["period_end"] == selected_period[1])]
    return filtered_df, selected_period


def _compute_pnl_abs_sharpe(loader: ExperimentLoader) -> pd.DataFrame | None:
    """pnl_pred_position/strategyの`pnl_abs`（絶対損益）から、stats_metricsと同じ
    epoch/split/strategy_name（・period_start/period_end）粒度で年率Sharpe比を算出し、
    `sharpe_ratio_abs`列を持つDataFrameを返す（stats_dfへの左結合用）。

    既存のstats_metricsの`sharpe_ratio`は学習時に`pnl`（率）から計算されたもので、絶対損益
    ベースの評価軸を持たない。絶対損益（`pnl_abs`）を目的変数として最適化する実験
    （run0001_7等）では判定指標側もそれに揃えられないと、ベストエポック判定が実際の最適化対象と
    ずれてしまう。stats_metrics側の再保存（学習スクリプトの再実行）無しに使えるよう、
    pnl_pred_position側の生データから都度計算する。`pnl_abs`列が無ければNoneを返す。
    """
    strategy_df = _load_pnl_pred_position_strategy(loader)
    if strategy_df is None or "pnl_abs" not in strategy_df.columns:
        return None

    group_cols = [c for c in ["period_start", "period_end", "split", "strategy_name", "epoch"] if c in strategy_df.columns]
    if "epoch" not in group_cols or "split" not in group_cols:
        return None

    records = []
    for keys, group in strategy_df.groupby(group_cols, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        record = dict(zip(group_cols, keys, strict=True))
        record["sharpe_ratio_abs"] = calculate_stats(group["pnl_abs"])["sharpe_ratio"]
        records.append(record)
    return pd.DataFrame(records)


def _load_stats_with_derived_metrics(loader: ExperimentLoader) -> tuple[pd.DataFrame, str, list[str], list[str]] | None:
    """stats_metrics/strategy（無ければindividual）を読み込み、`_compute_pnl_abs_sharpe`で
    算出した`sharpe_ratio_abs`（絶対損益ベースの年率Sharpe比）を追加でマージした上で
    (stats_df, stats_type, non_metric_columns, metric_cols) を返す。stats_metricsデータが
    無ければNone。stats_metrics/individualはstrategy_name粒度が無く、strategy粒度のpnl_abs由来
    指標とは結合できないためマージ対象外（stats_metrics/strategyの場合のみ結合する）。"""
    stats_df = _load_stats_metrics_strategy(loader)
    stats_type = "stats_metrics/strategy"
    if stats_df is None:
        stats_df = _load_stats_metrics_individual(loader)
        stats_type = "stats_metrics/individual"
    if stats_df is None:
        return None

    meta = _load_meta(loader, stats_type)
    if meta is not None:
        non_metric_columns = meta.get("non_metric_columns", ["split"])
        metric_cols = list(meta.get("metric_columns", []))
    else:
        non_metric_columns = ["split"]
        metric_cols = [c for c in stats_df.columns if c not in non_metric_columns]

    if stats_df.index.name == "epoch":
        stats_df = stats_df.reset_index(drop="epoch" in stats_df.columns)

    if stats_type == "stats_metrics/strategy":
        derived_df = _compute_pnl_abs_sharpe(loader)
        if derived_df is not None:
            merge_keys = [c for c in ["period_start", "period_end", "split", "strategy_name", "epoch"] if c in stats_df.columns and c in derived_df.columns]
            if merge_keys:
                stats_df = stats_df.merge(derived_df, on=merge_keys, how="left")
                if "sharpe_ratio_abs" not in metric_cols:
                    metric_cols = [*metric_cols, "sharpe_ratio_abs"]

    return stats_df, stats_type, non_metric_columns, metric_cols


def _setup_best_epoch_sidebar(loader: ExperimentLoader, period_container) -> tuple[int | None, tuple | None, dict]:
    """メトリクス学習推移タブ内の期間選択（該当する場合）と、サイドバーのベストエポック判定設定
    （判定 split/メトリクス/strategy。全タブ共通）から (best_epoch, selected_period, best_epoch_by_period)
    を算出する。

    Returns:
        best_epoch: メトリクス学習推移タブで選択中の期間（該当する場合）のベストエポック
        selected_period: メトリクス学習推移タブで選択中の期間 (period_start, period_end)。期間の概念が
            無ければNone
        best_epoch_by_period: 全期間ぶんの {(period_start, period_end): best_epoch} 辞書
            （ベストエポックは各期間に1対1で紐づくため。期間の概念が無い場合は {None: best_epoch}
            の1エントリ辞書。時系列/銘柄別時系列タブが期間ごとに個別のデフォルトエポックを
            出せるようにするために使う）
    """
    loaded = _load_stats_with_derived_metrics(loader)
    if loaded is None:
        return None, None, {}
    stats_df, _stats_type, non_metric_columns, metric_cols = loaded

    full_stats_df = stats_df
    _, selected_period = _render_period_selector_in_tab(full_stats_df, period_container)

    has_strategy = "strategy_name" in non_metric_columns and "strategy_name" in full_stats_df.columns
    splits = sort_splits(full_stats_df["split"].unique().tolist()) if "split" in full_stats_df.columns else []
    strategies = sorted(full_stats_df["strategy_name"].unique().tolist()) if has_strategy else []

    if not splits or not metric_cols:
        return None, selected_period, {}

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

    def _compute_best_epoch(df: pd.DataFrame) -> int | None:
        if "epoch" not in df.columns:
            return None
        filtered = filter_by_conditions(df, split=best_split)
        if has_strategy and best_strategy:
            filtered = filter_by_conditions(filtered, strategy_name=best_strategy)
        if len(filtered) == 0:
            return None
        epoch_means = filtered.groupby("epoch")[best_metric].mean()
        return int(epoch_means.idxmax())

    has_period = "period_start" in full_stats_df.columns and "period_end" in full_stats_df.columns
    best_epoch_by_period: dict = {}
    if has_period:
        unique_periods = full_stats_df[["period_start", "period_end"]].drop_duplicates().sort_values("period_start")
        for p_start, p_end in zip(unique_periods["period_start"], unique_periods["period_end"], strict=True):
            period_df = full_stats_df[(full_stats_df["period_start"] == p_start) & (full_stats_df["period_end"] == p_end)]
            best_epoch_by_period[(p_start, p_end)] = _compute_best_epoch(period_df)
        best_epoch = best_epoch_by_period.get(selected_period)
    else:
        best_epoch = _compute_best_epoch(full_stats_df)
        best_epoch_by_period = {None: best_epoch}

    return best_epoch, selected_period, best_epoch_by_period


def render_summary_tab(
    loader: ExperimentLoader, best_epoch: int | None, best_epoch_by_period: dict | None = None, can_view_closed: bool = False
):
    """成績サマリタブを描画（全タブの先頭）。

    testデータ（複数期間がある場合は連結したOOS実績。train/valは期間間で日時が重複するため
    対象外）を「全体通算」＋「年毎」の単位で集計する。指標（リターン・Sharpe Ratio・リスク・
    Max Drawdown。`pnl`から算出）ごとに表を分け、**列をstrategy_nameにして全戦略を横並びで
    比較できる**ようにする（strategy選択式にはしない）。条件が揃う場合は「最大所要資金に対する
    利益率」（戦略時系列タブの必要資金セクションと同じロジック）の表も追加する。年次推移は
    棒グラフで、strategy毎に色分けしたグループ棒グラフとして示す。エポック選択は戦略時系列タブと
    同じ方式（_select_period_aware_epoch参照）。
    """
    st.subheader("成績サマリ")

    strategy_df = _load_pnl_pred_position_strategy(loader)
    if strategy_df is None:
        st.warning("戦略データが見つかりません")
        return

    meta = _load_meta(loader, "pnl_pred_position/strategy")
    if meta is None:
        st.warning("メタデータが見つかりません")
        return
    condition_columns = meta.get("condition_columns", [])
    value_columns = meta.get("value_columns", [])

    if "pnl" not in value_columns:
        st.info("pnl列が見つかりません")
        return

    epoch_data, chosen_epoch_by_period, _epoch_label = _select_period_aware_epoch(
        strategy_df, condition_columns, best_epoch, best_epoch_by_period, key_prefix="summary"
    )
    if len(epoch_data) == 0:
        st.warning("選択したエポックのデータが見つかりません")
        return

    has_strategy = "strategy_name" in condition_columns and "strategy_name" in epoch_data.columns
    strategies = sorted(epoch_data["strategy_name"].unique().tolist()) if has_strategy else ["(all)"]

    if "split" not in epoch_data.columns or "test" not in epoch_data["split"].unique():
        st.info("test splitのデータが見つかりません（本タブはtest期間の連結実績を対象とします）")
        return
    test_df = filter_by_conditions(epoch_data, split="test").sort_index()
    st.caption("test（複数期間がある場合は連結したOOS実績）を対象に、strategy毎に集計しています")

    # === 全体通算 + 年毎 × strategy毎の指標テーブル（指標ごとに表を分け、列=strategy） ===
    periods = ["全体通算"] + [str(y) for y in sorted(test_df.index.year.unique())]
    metric_keys = {"リターン": "total_return", "Sharpe Ratio": "sharpe_ratio", "リスク": "annual_risk", "Max Drawdown": "max_drawdown"}
    metric_tables = {m: pd.DataFrame(index=periods, columns=strategies, dtype=float) for m in metric_keys}
    has_pnl_abs = "pnl_abs" in test_df.columns
    return_abs_table = pd.DataFrame(index=periods, columns=strategies, dtype=float) if has_pnl_abs else None

    for strategy in strategies:
        strat_df = filter_by_conditions(test_df, strategy_name=strategy) if has_strategy else test_df
        stats = calculate_stats(strat_df["pnl"])
        for m, key in metric_keys.items():
            metric_tables[m].loc["全体通算", strategy] = stats[key]
        if has_pnl_abs:
            return_abs_table.loc["全体通算", strategy] = strat_df["pnl_abs"].sum()
        for year, year_df in strat_df.groupby(strat_df.index.year):
            year_stats = calculate_stats(year_df["pnl"])
            for m, key in metric_keys.items():
                metric_tables[m].loc[str(year), strategy] = year_stats[key]
            if has_pnl_abs:
                return_abs_table.loc[str(year), strategy] = year_df["pnl_abs"].sum()

    # リターン表は「率 | 絶対額」を1セルにまとめた表示用DataFrameを別途作る（pnl_absが無い実験では率のみ）
    if has_pnl_abs:
        return_display_table = pd.DataFrame(index=periods, columns=strategies, dtype=object)
        for p in periods:
            for s in strategies:
                rate = metric_tables["リターン"].loc[p, s]
                if pd.isna(rate):
                    return_display_table.loc[p, s] = "-"
                    continue
                abs_v = return_abs_table.loc[p, s]
                abs_str = f"{abs_v:,.0f}" if pd.notna(abs_v) else "-"
                return_display_table.loc[p, s] = f"{rate:.2%} | {abs_str}"

    # === 最大所要資金に対する利益率（entry_price・target_horizon/backtest_entry_interval_daysが
    # 揃う場合のみ。戦略時系列タブの必要資金セクションと同じロジック）。銘柄別のposition列は
    # long_short戦略のtop_k/bottom_k選択をそのまま反映しているため、long_only→ロング必要現金、
    # short_only→ショート想定評価額、long_short→グロス合計にそれぞれ対応させる。
    # ベンチマーク等それ以外のstrategyは対応する資金概念が無いため対象外（NaNのまま）
    ticker_meta = _load_meta(loader, "pnl_pred_position/ticker")
    has_entry_price = ticker_meta is not None and (
        "entry_price" in ticker_meta.get("value_columns", []) or "entry_price" in ticker_meta.get("condition_columns", [])
    )
    backtest_config = _load_backtest_config_params(loader, can_view_closed) if has_entry_price else None
    strategy_cash_column = {"long_only": "long_cash", "short_only": "short_cash", "long_short": "gross_cash"}

    profit_rate_table = None
    if has_entry_price and backtest_config is not None and "pnl_abs" in test_df.columns:
        show_capital = st.checkbox(
            "資金効率も計算する（銘柄別データの読み込みが必要なため重い場合があります）", value=False, key="summary_show_capital"
        )
        if show_capital:
            ticker_df = _load_pnl_pred_position_ticker(loader)
            if ticker_df is not None and "entry_price" in ticker_df.columns and "position" in ticker_df.columns:
                target_horizon = backtest_config["target_horizon"]
                entry_interval = backtest_config["backtest_entry_interval_days"]
                window = max(1, math.ceil(target_horizon / max(entry_interval, 1)))

                ticker_frames = []
                for (p_start, p_end), chosen_epoch in chosen_epoch_by_period.items():
                    sub = ticker_df[ticker_df["epoch"] == chosen_epoch] if "epoch" in ticker_df.columns else ticker_df
                    if p_start is not None and "period_start" in sub.columns:
                        sub = sub[(sub["period_start"] == p_start) & (sub["period_end"] == p_end)]
                    ticker_frames.append(sub)
                ticker_epoch_df = pd.concat(ticker_frames) if ticker_frames else ticker_df.iloc[0:0]
                ticker_test_df = filter_by_conditions(ticker_epoch_df, split="test") if "split" in ticker_epoch_df.columns else ticker_epoch_df

                cash_df = _compute_required_cash_df(ticker_test_df, window).sort_index()
                if len(cash_df) > 0:
                    profit_rate_table = pd.DataFrame(index=periods, columns=strategies, dtype=float)
                    max_cash_table = pd.DataFrame(index=periods, columns=strategies, dtype=float)
                    for strategy in strategies:
                        cash_col = strategy_cash_column.get(strategy)
                        if cash_col is None:
                            continue
                        strat_test_df = filter_by_conditions(test_df, strategy_name=strategy) if has_strategy else test_df
                        overall_max = cash_df[cash_col].max()
                        max_cash_table.loc["全体通算", strategy] = overall_max
                        if overall_max > 0:
                            profit_rate_table.loc["全体通算", strategy] = strat_test_df["pnl_abs"].sum() / overall_max
                        for year, year_cash in cash_df.groupby(cash_df.index.year):
                            year_max = year_cash[cash_col].max()
                            max_cash_table.loc[str(year), strategy] = year_max
                            if year_max > 0:
                                year_pnl_abs = strat_test_df.loc[strat_test_df.index.year == year, "pnl_abs"].sum()
                                profit_rate_table.loc[str(year), strategy] = year_pnl_abs / year_max

                    # 表示用: 「率 | 最大所要資金」を1セルにまとめた文字列表（リターン表と同じ方式）
                    profit_rate_display_table = pd.DataFrame(index=periods, columns=strategies, dtype=object)
                    for p in periods:
                        for s in strategies:
                            rate = profit_rate_table.loc[p, s]
                            if pd.isna(rate):
                                profit_rate_display_table.loc[p, s] = "-"
                                continue
                            max_cash = max_cash_table.loc[p, s]
                            max_cash_str = f"{max_cash:,.0f}" if pd.notna(max_cash) else "-"
                            profit_rate_display_table.loc[p, s] = f"{rate:.1%} | {max_cash_str}"
            else:
                st.info("銘柄別データ（entry_price）が見つかりません")

    # === テーブル表示（指標ごとに表を分け、列=strategy。2列グリッドで配置） ===
    st.markdown("### 成績サマリ表")
    table_specs: list[tuple[str, object, str | None]] = []
    if has_pnl_abs:
        table_specs.append(("リターン（率 | 絶対額）", return_display_table, None))
    else:
        table_specs.append(("リターン", metric_tables["リターン"].style.format("{:.2%}", na_rep="-"), None))
    table_specs.append(("Sharpe Ratio", metric_tables["Sharpe Ratio"].style.format("{:.2f}", na_rep="-"), None))
    table_specs.append(("リスク", metric_tables["リスク"].style.format("{:.2%}", na_rep="-"), None))
    table_specs.append(("Max Drawdown", metric_tables["Max Drawdown"].style.format("{:.2%}", na_rep="-"), None))
    if profit_rate_table is not None:
        table_specs.append(
            (
                "最大所要資金に対する利益率（率 | 最大所要資金）",
                profit_rate_display_table,
                "long_only/short_only/long_shortのみ算出可能（ベンチマーク等は対応する銘柄別ポジションが無いため対象外）",
            )
        )

    for i in range(0, len(table_specs), 2):
        row_specs = table_specs[i : i + 2]
        row_cols = st.columns(2)
        for col, (title, tbl, caption) in zip(row_cols, row_specs, strict=False):
            with col:
                st.markdown(f"**{title}**")
                if caption:
                    st.caption(caption)
                st.dataframe(tbl, use_container_width=True)

    # === 年次推移の棒グラフ（strategy毎に色分けしたグループ棒グラフ） ===
    yearly_periods = [p for p in periods if p != "全体通算"]
    if yearly_periods:
        st.markdown("### 年次推移")
        colors = px.colors.qualitative.Plotly
        chart_specs = [("リターン", metric_tables["リターン"], ".1%"), ("Sharpe Ratio", metric_tables["Sharpe Ratio"], ".2f")]
        if profit_rate_table is not None:
            chart_specs.append(("最大所要資金に対する利益率", profit_rate_table, ".1%"))
        chart_cols = st.columns(len(chart_specs))
        for col, (title, table, tick_format) in zip(chart_cols, chart_specs, strict=True):
            with col:
                fig = go.Figure()
                for j, strategy in enumerate(strategies):
                    fig.add_trace(
                        go.Bar(x=yearly_periods, y=table.loc[yearly_periods, strategy], name=strategy, marker_color=colors[j % len(colors)])
                    )
                fig.update_layout(
                    title=f"年次{title}",
                    barmode="group",
                    xaxis=dict(type="category"),  # 年ラベル("2024"等)が数値と誤認され軸が連続数値化される(=2024.5等の中間目盛が出る)のを防ぐ
                    yaxis_tickformat=tick_format,
                    hovermode="x unified",
                    height=350,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)


def render_stats_tab(loader: ExperimentLoader, best_epoch: int | None, selected_period: tuple | None = None):
    """メトリクス学習推移タブを描画

    Args:
        selected_period: 指定時、(period_start, period_end) のタプルでそのウォークフォワード
            期間のデータのみに絞り込む（メトリクス学習推移タブ内の期間選択UIの結果。
            `_setup_best_epoch_sidebar`/`_render_period_selector_in_tab`参照）
    """
    loaded = _load_stats_with_derived_metrics(loader)
    if loaded is None:
        st.warning("メトリクス学習推移データが見つかりません")
        return
    stats_df, _data_type, non_metric_columns, metric_cols = loaded

    if selected_period is not None:
        stats_df = stats_df[(stats_df["period_start"] == selected_period[0]) & (stats_df["period_end"] == selected_period[1])]

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
            if st.checkbox(split, value=(split != "train"), key=f"stats_split_check_{split}"):
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
    st.markdown("### メトリクス学習推移表")
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


def _select_period_aware_epoch(
    df: pd.DataFrame, condition_columns: list, best_epoch: int | None, best_epoch_by_period: dict | None, key_prefix: str
) -> tuple[pd.DataFrame, dict, str | int | None]:
    """period_start/period_end列の有無に応じて、期間ごとの個別エポック選択（無ければ単一の
    エポック選択）UIを描画し、(絞り込んだdf, chosen_epoch_by_period, 表示用epochラベル) を返す。
    render_timeseries_tab/render_summary_tabで共通利用する（元はrender_timeseries_tab内に
    inlineで実装していたものを共通化）。

    chosen_epoch_by_period: 期間の概念が無い場合は{(None, None): epoch}の1エントリ辞書になる
    （render_timeseries_tabの必要資金セクション等、期間の有無を問わず同じ形で扱うため）。

    key_prefix: ウィジェットkeyの重複を避けるための呼び出し元ごとのプレフィックス（Streamlitは
    全タブの中身を毎回まとめて実行するため、複数タブから呼ぶ場合はprefixを分ける必要がある）。
    """
    best_epoch_by_period = best_epoch_by_period or {}
    has_period = "period_start" in df.columns and "period_end" in df.columns

    if has_period and "epoch" in condition_columns:
        unique_periods = df[["period_start", "period_end"]].drop_duplicates().sort_values("period_start")
        period_list = list(zip(unique_periods["period_start"], unique_periods["period_end"], strict=True))

        st.markdown("**期間ごとの表示エポック:**")
        epoch_cols = st.columns(len(period_list))
        chosen_epoch_by_period: dict = {}
        for col, (p_start, p_end) in zip(epoch_cols, period_list, strict=True):
            with col:
                period_df = df[(df["period_start"] == p_start) & (df["period_end"] == p_end)]
                period_epochs = sorted(period_df["epoch"].unique().tolist())
                period_best = best_epoch_by_period.get((p_start, p_end))
                default_idx = period_epochs.index(period_best) if period_best in period_epochs else 0
                label = f"{pd.Timestamp(p_start).date()} 〜 {pd.Timestamp(p_end).date()}"
                if period_best is not None:
                    label += f" (best:{period_best})"
                # keyにperiod_bestを含めることで、判定設定変更でおすすめエポックが変わった際に
                # ウィジェットを再生成させ、新しいデフォルトへ追従させる（Streamlitはkeyが同じだと
                # indexを無視してsession_stateの古い選択値を保持し続けるため）
                chosen_epoch_by_period[(p_start, p_end)] = st.selectbox(
                    label, period_epochs, index=default_idx, key=f"{key_prefix}_epoch_{p_start}_{p_end}_{period_best}"
                )

        epoch_data = pd.concat(
            [
                df[(df["period_start"] == p_start) & (df["period_end"] == p_end) & (df["epoch"] == chosen_epoch)]
                for (p_start, p_end), chosen_epoch in chosen_epoch_by_period.items()
            ]
        )
        epoch_label = " / ".join(f"{pd.Timestamp(p_start).date()}:{e}" for (p_start, p_end), e in chosen_epoch_by_period.items())
    else:
        if "epoch" in condition_columns:
            available_epochs = sorted(df["epoch"].unique().tolist())
        else:
            available_epochs = []

        if available_epochs:
            default_idx = available_epochs.index(best_epoch) if best_epoch in available_epochs else 0
            epoch_selectbox_label = f"表示エポック (ベストエポック: {best_epoch})" if best_epoch is not None else "表示エポック"
            epoch = st.selectbox(epoch_selectbox_label, available_epochs, index=default_idx, key=f"{key_prefix}_epoch_single_{best_epoch}")
        else:
            epoch = None

        epoch_data = filter_by_conditions(df, epoch=epoch) if "epoch" in condition_columns else df.copy()
        chosen_epoch_by_period = {(None, None): epoch}
        epoch_label = epoch

    return epoch_data, chosen_epoch_by_period, epoch_label


def render_timeseries_tab(
    loader: ExperimentLoader, best_epoch: int | None, best_epoch_by_period: dict | None = None, can_view_closed: bool = False
):
    """時系列（資産曲線・ポジション）タブを描画

    ウォークフォワード等でperiod_start/period_end列がある場合、期間ごとに個別のエポック選択
    セレクトボックスを並べる（ベストエポックは各期間に1対1で紐づき、期間によって異なりうるため、
    単一のエポック選択を全期間へ一律適用するのは不適切）。各セレクトボックスのデフォルトは
    その期間自身のベストエポック（best_epoch_by_period）。期間選択の概念（どの期間を表示するか
    の絞り込み）自体はメトリクス学習推移タブ側にのみ存在し、本タブは常に全期間を表示する。

    can_view_closed: 末尾の「必要資金・利益率」セクションが参照する`params`（closed指定のことが
    多い）の閲覧権限判定に使う（仕様書2.5.1節参照）。
    """
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

    epoch_data, chosen_epoch_by_period, epoch = _select_period_aware_epoch(
        strategy_df, condition_columns, best_epoch, best_epoch_by_period, key_prefix="ts"
    )

    if len(epoch_data) == 0:
        st.warning(f"エポック {epoch} のデータが見つかりません")
        return

    # Split選択チェックボックス（train系はデフォルト非表示）
    selected_splits = []
    if "split" in epoch_data.columns:
        splits_all = sort_splits(epoch_data["split"].unique().tolist())
        st.markdown("**表示するSplit:**")
        split_check_cols = st.columns(max(len(splits_all), 1))
        selected_splits = []
        for i, split in enumerate(splits_all):
            with split_check_cols[i]:
                if st.checkbox(split, value=(split != "train"), key=f"ts_split_check_{split}"):
                    selected_splits.append(split)
        if not selected_splits:
            st.info("表示するsplitを選択してください")
            return
        epoch_data = epoch_data[epoch_data["split"].isin(selected_splits)]

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

    # 必要資金・利益率（pnl_pred_position/ticker の entry_price と、paramsの
    # target_horizon/backtest_entry_interval_days（仕様書2.5.1節）が両方揃う場合のみ表示）
    ticker_meta = _load_meta(loader, "pnl_pred_position/ticker")
    # entry_priceはsaver.py側でvalue_columnsに分類されるべきだが（bt-log-vis-tool側のバージョンにより
    # condition_columns側に入っている過去データもありうるため）、両方をチェックする
    has_entry_price = ticker_meta is not None and (
        "entry_price" in ticker_meta.get("value_columns", []) or "entry_price" in ticker_meta.get("condition_columns", [])
    )
    backtest_config = _load_backtest_config_params(loader, can_view_closed) if has_entry_price else None

    if has_entry_price and backtest_config is not None and selected_splits:
        st.markdown("### 必要資金・利益率")
        show_capital = st.checkbox(
            "必要資金・利益率を計算する（銘柄別データの読み込みが必要なため重い場合があります）", value=False, key="ts_show_capital"
        )
        if show_capital:
            ticker_df = _load_pnl_pred_position_ticker(loader)
            if ticker_df is None or "entry_price" not in ticker_df.columns or "position" not in ticker_df.columns:
                st.info("銘柄別データ（entry_price）が見つかりません")
            else:
                target_horizon = backtest_config["target_horizon"]
                entry_interval = backtest_config["backtest_entry_interval_days"]
                window = max(1, math.ceil(target_horizon / max(entry_interval, 1)))
                st.caption(
                    f"target_horizon={target_horizon}, backtest_entry_interval_days={entry_interval} "
                    f"→ 同時保有コホート数(window)={window}"
                    + ("（重複無し・正確な値）" if window == 1 else "（重複あり・シグナル日ベースの近似値）")
                )

                # 戦略時系列タブと同じ選択エポックをticker側でも再現する（period_start/period_end +
                # epochで絞り込み、chosen_epoch_by_periodは期間概念が無い場合 {None: epoch} になっている）
                ticker_frames = []
                for (p_start, p_end), chosen_epoch in chosen_epoch_by_period.items():
                    sub = ticker_df[ticker_df["epoch"] == chosen_epoch] if "epoch" in ticker_df.columns else ticker_df
                    if p_start is not None and "period_start" in sub.columns:
                        sub = sub[(sub["period_start"] == p_start) & (sub["period_end"] == p_end)]
                    ticker_frames.append(sub)
                ticker_epoch_df = pd.concat(ticker_frames) if ticker_frames else ticker_df.iloc[0:0]
                ticker_epoch_df = ticker_epoch_df[ticker_epoch_df["split"].isin(selected_splits)] if "split" in ticker_epoch_df.columns else ticker_epoch_df

                colors = px.colors.qualitative.Plotly
                cash_cols = st.columns(len(selected_splits))
                for i, split in enumerate(selected_splits):
                    with cash_cols[i]:
                        split_ticker_df = filter_by_conditions(ticker_epoch_df, split=split)
                        cash_df = _compute_required_cash_df(split_ticker_df, window)
                        fig = go.Figure()
                        for j, (col_name, label) in enumerate([("long_cash", "ロング"), ("short_cash", "ショート"), ("gross_cash", "グロス合計")]):
                            for x, y, period_label in _build_period_traces(cash_df, split, col_name, cumsum=False):
                                fig.add_trace(
                                    go.Scatter(x=x, y=y, mode="lines", name=f"{label}{period_label}", line=dict(color=colors[j % len(colors)]))
                                )
                        fig.update_layout(
                            title=f"必要資金 ({split})", xaxis_title="日時", yaxis_title="必要資金", hovermode="x unified", height=400, margin=dict(t=40, b=40)
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        if split == "test" and len(cash_df) > 0:
                            max_cash = cash_df["gross_cash"].max()
                            mean_cash = cash_df["gross_cash"].mean()
                            total_pnl_abs = filter_by_conditions(epoch_data, split=split, strategy_name="long_short")["pnl_abs"].sum()
                            if max_cash > 0:
                                st.metric("最大所要資金に対する利益率", f"{total_pnl_abs / max_cash:.1%}", help=f"最大所要資金: {max_cash:,.0f} / 総損益: {total_pnl_abs:,.0f}")
                            if mean_cash > 0:
                                st.metric("平均所要資金に対する利益率", f"{total_pnl_abs / mean_cash:.1%}", help=f"平均所要資金: {mean_cash:,.0f} / 総損益: {total_pnl_abs:,.0f}")


def _build_period_traces(entity_df: pd.DataFrame, split: str | None, value_column: str, cumsum: bool) -> list[tuple]:
    """splitとperiod_start/period_end列の有無に応じて描画用トレース群 (x, y, ラベル接尾辞) を構築する。

    period_start/period_end列が無い場合は従来通り単一トレース。ある場合、train/val（≒非test）は
    期間間で日付が重複しうるため期間毎に別トレースへ分け、testは重複が無い前提で期間を跨いで
    日時順に連結してから単一トレースにまとめる（cumsumはこの連結後の系列に対して行う）。
    """
    if len(entity_df) == 0 or value_column not in entity_df.columns:
        return []

    has_period = "period_start" in entity_df.columns and "period_end" in entity_df.columns
    if not has_period or split == "test":
        sorted_df = entity_df.sort_index()
        y = sorted_df[value_column].cumsum() if cumsum else sorted_df[value_column]
        return [(sorted_df.index, y, "")]

    traces = []
    period_starts = sorted(entity_df["period_start"].unique())
    multiple = len(period_starts) > 1
    for p_start in period_starts:
        p_df = entity_df[entity_df["period_start"] == p_start].sort_index()
        if len(p_df) == 0:
            continue
        y = p_df[value_column].cumsum() if cumsum else p_df[value_column]
        label = f" [{pd.Timestamp(p_start).date()}〜]" if multiple else ""
        traces.append((p_df.index, y, label))
    return traces


def _compute_required_cash_df(ticker_split_df: pd.DataFrame, window: int) -> pd.DataFrame:
    """ticker_split_df（1つのsplitの銘柄別データ。period_start/period_end列がある場合は複数期間分を
    含みうる）から、必要資金（ロング必要現金・ショート想定評価額・グロス合計）の日次時系列を返す
    （index=Date, columns=[long_cash, short_cash, gross_cash]、period_start/period_endがあれば
    それも保持する）。

    window: 同時に保有されうる最大コホート数（ceil(target_horizon / backtest_entry_interval_days)）。
    エントリー間隔で間引かれた各シグナル日を1コホートの代表点とみなし、直近window個ぶんの
    エントリー総額を合算することで重複保有時の必要資金を近似する（正確な暦日ベースの重複判定では
    ない近似値である点に注意。backtest_entry_interval_days >= target_horizonなら重複が無いため
    window=1となり、この場合は正確な値になる）。

    期間をまたいで日付が重複しうるため、rolling計算は必ず期間ごとに独立して行う（scaler等と同じ、
    期間をまたいで統計量を混ぜない方針）。
    """
    has_period = "period_start" in ticker_split_df.columns and "period_end" in ticker_split_df.columns
    period_keys = (
        list(ticker_split_df[["period_start", "period_end"]].drop_duplicates().itertuples(index=False, name=None)) if has_period else [(None, None)]
    )

    frames = []
    for p_start, p_end in period_keys:
        period_df = (
            ticker_split_df[(ticker_split_df["period_start"] == p_start) & (ticker_split_df["period_end"] == p_end)] if has_period else ticker_split_df
        )
        held = period_df[period_df["position"] != 0]
        all_index = period_df.index.unique().sort_values()
        long_held = held[held["position"] == 1]
        short_held = held[held["position"] == -1]
        long_daily = long_held.groupby(long_held.index)["entry_price"].sum().reindex(all_index, fill_value=0.0).sort_index()
        short_daily = short_held.groupby(short_held.index)["entry_price"].sum().reindex(all_index, fill_value=0.0).sort_index()
        long_cash = long_daily.rolling(window, min_periods=1).sum()
        short_cash = short_daily.rolling(window, min_periods=1).sum()
        cash_df = pd.DataFrame({"long_cash": long_cash, "short_cash": short_cash, "gross_cash": long_cash + short_cash})
        if has_period:
            cash_df["period_start"], cash_df["period_end"] = p_start, p_end
        frames.append(cash_df)
    return pd.concat(frames) if frames else pd.DataFrame(columns=["long_cash", "short_cash", "gross_cash"])


def render_equity_curve(df, epoch, condition_columns, pnl_column: str = "pnl", chart_title: str = "累積PnL"):
    """資産曲線を描画（split毎に列を分けてy軸スケールを独立させる）

    Args:
        df: データフレーム
        epoch: 選択されたエポック
        condition_columns: 条件カラムのリスト
        pnl_column: 累積対象のカラム名（"pnl"=率、"pnl_abs"=絶対損益）
        chart_title: グラフタイトルに使う名称

    period_start/period_end列がある場合、test以外のsplitは期間毎に別トレースとして重ねて表示し、
    testは期間を跨いで連結してから単一トレースでcumsumする。
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

            for x, y, label in _build_period_traces(strategy_data, split, pnl_column, cumsum=True):
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines",
                        name=f"{strategy}{label}",
                        legendgroup=strategy,
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
    """ポジション時系列を描画（split毎に列を分けてy軸スケールを独立させる）

    period_start/period_end列がある場合、test以外のsplitは期間毎に別トレースとして重ねて表示し、
    testは期間を跨いで連結してから単一トレースにする。
    """
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

            for x, y, label in _build_period_traces(strategy_data, split, "position", cumsum=cumsum):
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=y,
                        mode="lines",
                        name=f"{strategy}{label}",
                        legendgroup=strategy,
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
    """銘柄別の累積損益曲線を描画（split毎に列を分ける）

    period_start/period_end列がある場合、test以外のsplitは期間毎に別トレースとして重ねて表示し、
    testは期間を跨いで連結してから単一トレースでcumsumする。
    """
    graph_cols = st.columns(len(display_splits))
    for i, split in enumerate(display_splits):
        with graph_cols[i]:
            split_df = filter_by_conditions(epoch_df, split=split) if split else epoch_df
            fig = go.Figure()
            for j, ticker in enumerate(selected_tickers):
                t_df = filter_by_conditions(split_df, ticker=ticker)
                for x, y, label in _build_period_traces(t_df, split, pnl_column, cumsum=True):
                    fig.add_trace(go.Scatter(
                        x=x,
                        y=y,
                        mode="lines",
                        name=f"{ticker}{label}",
                        legendgroup=ticker,
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


def render_ticker_tab(loader: ExperimentLoader, best_epoch: int | None, best_epoch_by_period: dict | None = None):
    """銘柄別時系列タブを描画

    ウォークフォワード等でperiod_start/period_end列がある場合、期間ごとに個別のエポック選択
    セレクトボックスを並べる（render_timeseries_tabと同じ方針。ベストエポックは期間毎に異なりうる）。
    """
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
    best_epoch_by_period = best_epoch_by_period or {}

    has_period = "period_start" in ticker_df.columns and "period_end" in ticker_df.columns

    if has_period and "epoch" in condition_columns:
        unique_periods = ticker_df[["period_start", "period_end"]].drop_duplicates().sort_values("period_start")
        period_list = list(zip(unique_periods["period_start"], unique_periods["period_end"], strict=True))

        st.markdown("**期間ごとの表示エポック:**")
        epoch_cols = st.columns(len(period_list))
        chosen_epoch_by_period: dict = {}
        for col, (p_start, p_end) in zip(epoch_cols, period_list, strict=True):
            with col:
                period_df = ticker_df[(ticker_df["period_start"] == p_start) & (ticker_df["period_end"] == p_end)]
                period_epochs = sorted(period_df["epoch"].unique().tolist())
                period_best = best_epoch_by_period.get((p_start, p_end))
                default_idx = period_epochs.index(period_best) if period_best in period_epochs else 0
                label = f"{pd.Timestamp(p_start).date()} 〜 {pd.Timestamp(p_end).date()}"
                if period_best is not None:
                    label += f" (best:{period_best})"
                # keyにperiod_bestを含める理由はrender_timeseries_tabと同じ（判定設定変更への追従）
                chosen_epoch_by_period[(p_start, p_end)] = st.selectbox(
                    label, period_epochs, index=default_idx, key=f"ticker_epoch_{p_start}_{p_end}_{period_best}"
                )

        epoch_df = pd.concat(
            [
                ticker_df[(ticker_df["period_start"] == p_start) & (ticker_df["period_end"] == p_end) & (ticker_df["epoch"] == chosen_epoch)]
                for (p_start, p_end), chosen_epoch in chosen_epoch_by_period.items()
            ]
        )
        epoch = " / ".join(f"{pd.Timestamp(p_start).date()}:{e}" for (p_start, p_end), e in chosen_epoch_by_period.items())
    else:
        # エポック選択
        if "epoch" in condition_columns:
            available_epochs = sorted(ticker_df["epoch"].unique().tolist())
            if not available_epochs:
                st.warning("エポックが見つかりません")
                return
            default_idx = available_epochs.index(best_epoch) if best_epoch in available_epochs else 0
            epoch_label = f"表示エポック (ベストエポック: {best_epoch})" if best_epoch is not None else "表示エポック"
            epoch = st.selectbox(epoch_label, available_epochs, index=default_idx, key=f"ticker_epoch_single_{best_epoch}")
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
                if st.checkbox(split, value=(split != "train"), key=f"ticker_split_{split}"):
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
                    for x, y, label in _build_period_traces(t_df, split, "position", cumsum=ticker_pos_cumsum):
                        fig.add_trace(go.Scatter(
                            x=x,
                            y=y,
                            mode="lines",
                            name=f"{ticker}{label}",
                            legendgroup=ticker,
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
                    for x, y, label in _build_period_traces(t_df, split, "pred", cumsum=False):
                        fig.add_trace(go.Scatter(
                            x=x,
                            y=y,
                            mode="lines",
                            name=f"{ticker}{label}",
                            legendgroup=ticker,
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
    has_hidden_closed = not can_view_closed and len(loader.list_params_files(can_view_closed=True)) > len(params_files)

    if not params_files:
        if has_hidden_closed:
            st.info("🔒 closedなパラメータファイルが存在します。閲覧するにはログインが必要です。")
        else:
            st.warning("パラメータファイルが見つかりません")
        return

    if has_hidden_closed:
        st.caption("🔒 このほかに、ログインが必要な非公開のパラメータファイルがあります")

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
    has_hidden_closed = not can_view_closed and len(loader.list_code_files(can_view_closed=True)) > len(code_files)

    if not code_files:
        if has_hidden_closed:
            st.info("🔒 closedなコードファイルが存在します。閲覧するにはログインが必要です。")
        else:
            st.warning("コードファイルが見つかりません")
        return

    if has_hidden_closed:
        st.caption("🔒 このほかに、ログインが必要な非公開のコードファイルがあります")

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
    has_hidden_closed = not can_view_closed and len(loader.list_reports(can_view_closed=True)) > len(report_files)

    if not report_files:
        if has_hidden_closed:
            st.info("🔒 closedなサマリレポートが存在します。閲覧するにはログインが必要です。")
        else:
            st.info("サマリレポートはまだありません")
        return

    if has_hidden_closed:
        st.caption("🔒 このほかに、ログインが必要な非公開のレポートがあります")

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
