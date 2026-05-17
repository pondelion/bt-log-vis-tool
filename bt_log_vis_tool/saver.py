"""実験データ保存モジュール

バックテスト実験のデータを指定フォーマットで保存する
"""

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


class ValidationError(Exception):
    """データバリデーションエラー"""

    pass


class ExperimentSaver:
    """実験データ保存クラス

    Jupyter上でのバックテスト実験結果を指定されたディレクトリ構造で保存する
    """

    # 固定カラム名
    PNL_COLUMN = "pnl"
    PRED_COLUMN = "pred"
    POSITION_COLUMN = "position"

    # 必須その他条件カラム
    REQUIRED_COLUMNS_TICKER = ["split", "epoch", "ticker"]
    REQUIRED_COLUMNS_INDIVIDUAL = ["split", "epoch"]
    REQUIRED_COLUMNS_STRATEGY = ["split", "epoch", "strategy_name"]

    # 統計メトリクスの必須条件カラム
    REQUIRED_STATS_COLUMNS_STRATEGY = ["split", "epoch", "strategy_name"]
    REQUIRED_STATS_COLUMNS_INDIVIDUAL = ["split", "epoch"]

    def __init__(
        self,
        base_dir: str | Path,
        exp_name: str,
        run_name: str,
        non_metric_columns_stats_strategy: list[str] | None = None,
        non_metric_columns_stats_individual: list[str] | None = None,
    ):
        """
        Args:
            base_dir: 保存先のベースディレクトリ
            exp_name: 実験名（ノートブック単位）
            run_name: ラン名（ノートブック内の各実験）
            non_metric_columns_stats_strategy: 戦略毎統計メトリクスの非メトリックカラム
                                              指定しない場合は["split", "epoch", "strategy_name"]
            non_metric_columns_stats_individual: 個別条件毎統計メトリクスの非メトリックカラム
                                                指定しない場合は["split", "epoch"]
        """
        self.base_dir = Path(base_dir).expanduser()
        self.exp_name = exp_name
        self.run_name = run_name
        self.run_dir = self.base_dir / exp_name / run_name

        # 戦略毎統計メトリクスのnon_metric_columns設定
        if non_metric_columns_stats_strategy is None:
            self.non_metric_columns_stats_strategy = self.REQUIRED_STATS_COLUMNS_STRATEGY.copy()
        else:
            # 必須カラムを含める
            self.non_metric_columns_stats_strategy = list(
                set(non_metric_columns_stats_strategy) | set(self.REQUIRED_STATS_COLUMNS_STRATEGY)
            )

        # 個別条件毎統計メトリクスのnon_metric_columns設定
        if non_metric_columns_stats_individual is None:
            self.non_metric_columns_stats_individual = self.REQUIRED_STATS_COLUMNS_INDIVIDUAL.copy()
        else:
            # 必須カラムを含める
            self.non_metric_columns_stats_individual = list(
                set(non_metric_columns_stats_individual) | set(self.REQUIRED_STATS_COLUMNS_INDIVIDUAL)
            )

    def _get_data_dir(self, data_type: str) -> Path:
        """データタイプに応じた保存ディレクトリを取得

        Args:
            data_type: データタイプ

        Returns:
            保存先ディレクトリパス
        """
        return self.run_dir / data_type

    def _get_condition_columns(self, df: pd.DataFrame) -> list[str]:
        """その他条件カラムを取得（pnl/pred/position以外）

        Args:
            df: DataFrame

        Returns:
            条件カラムのリスト
        """
        value_columns = {self.PNL_COLUMN, self.PRED_COLUMN, self.POSITION_COLUMN}
        condition_columns = [col for col in df.columns if col not in value_columns]
        return condition_columns

    def _validate_pnl_pred_position(
        self, df: pd.DataFrame, data_type: str, required_columns: list[str], required_value_columns: list[str], at_least_one_value: bool = False
    ) -> None:
        """PnL/Pred/Position DataFrameのバリデーション

        Args:
            df: 検証するDataFrame
            data_type: データタイプ
            required_columns: 必須その他条件カラム
            required_value_columns: 必須値カラム（pnl, pred, position）
            at_least_one_value: Trueの場合、pnl/pred/positionの内最低1つは存在すること

        Raises:
            ValidationError: バリデーションエラー
        """
        # 必須値カラムの存在チェック
        if at_least_one_value:
            # pnl/pred/positionの内最低1つは存在すること
            available_value_columns = {self.PNL_COLUMN, self.PRED_COLUMN, self.POSITION_COLUMN}
            existing_value_columns = available_value_columns & set(df.columns)
            if not existing_value_columns:
                raise ValidationError(
                    f"{data_type}: pnl/pred/positionの内、最低1つはカラムに存在する必要があります\n"
                    f"存在するカラム: {list(df.columns)}"
                )
        else:
            # 必須値カラムがすべて存在すること
            missing_value_cols = set(required_value_columns) - set(df.columns)
            if missing_value_cols:
                raise ValidationError(
                    f"{data_type}: 必須値カラムが不足しています: {missing_value_cols}\n"
                    f"必要なカラム: {required_value_columns}\n"
                    f"存在するカラム: {list(df.columns)}"
                )

        # 必須その他条件カラムの存在チェック
        missing_condition_cols = set(required_columns) - set(df.columns)
        if missing_condition_cols:
            raise ValidationError(
                f"{data_type}: 必須その他条件カラムが不足しています: {missing_condition_cols}\n"
                f"必要なカラム: {required_columns}\n"
                f"存在するカラム: {list(df.columns)}"
            )

        # その他条件カラムを取得
        condition_columns = self._get_condition_columns(df)

        # その他条件カラムでgroupbyした際にindexが一意になることをチェック
        grouped = df.groupby(condition_columns)
        duplicated_indices = []

        for group_keys, group_df in grouped:
            if group_df.index.duplicated().any():
                duplicated_indices.append((group_keys, group_df.index[group_df.index.duplicated()].tolist()))

        if duplicated_indices:
            error_msg = f"{data_type}: その他条件カラム={condition_columns} でgroupbyした際にindexが重複しています:\n"
            for group_keys, dup_idx in duplicated_indices[:5]:  # 最初の5件のみ表示
                error_msg += f"  グループ {group_keys}: 重複index {dup_idx}\n"
            if len(duplicated_indices) > 5:
                error_msg += f"  ... 他 {len(duplicated_indices) - 5} グループ\n"
            raise ValidationError(error_msg)

    def _save_dataframe(self, df: pd.DataFrame, data_type: str, filename: str = "data.parquet") -> None:
        """DataFrameを保存

        Args:
            df: 保存するDataFrame
            data_type: データタイプ
            filename: ファイル名
        """
        save_dir = self._get_data_dir(data_type)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        df.to_parquet(save_path)
        print(f"Saved: {save_path}")

    def _save_meta(self, df: pd.DataFrame, data_type: str) -> None:
        """メタデータ（条件カラム情報）を保存

        Args:
            df: DataFrame
            data_type: データタイプ
        """
        save_dir = self._get_data_dir(data_type)
        save_dir.mkdir(parents=True, exist_ok=True)
        meta_path = save_dir / "meta.yaml"

        condition_columns = self._get_condition_columns(df)
        value_columns = [col for col in [self.PNL_COLUMN, self.PRED_COLUMN, self.POSITION_COLUMN] if col in df.columns]

        meta = {"condition_columns": condition_columns, "value_columns": value_columns}

        with open(meta_path, "w") as f:
            yaml.dump(meta, f, default_flow_style=False, allow_unicode=True)

        print(f"Saved meta: {meta_path}")

    def _save_stats_meta(self, df: pd.DataFrame, data_type: str, non_metric_columns: list[str]) -> None:
        """統計メトリクス用メタデータを保存

        Args:
            df: 統計メトリクスDataFrame
            data_type: データタイプ
            non_metric_columns: 非メトリックカラムのリスト
        """
        save_dir = self._get_data_dir(data_type)
        save_dir.mkdir(parents=True, exist_ok=True)
        meta_path = save_dir / "meta.yaml"

        metric_columns = self._get_metric_columns(df, non_metric_columns)

        meta = {"non_metric_columns": non_metric_columns, "metric_columns": metric_columns}

        with open(meta_path, "w") as f:
            yaml.dump(meta, f, default_flow_style=False, allow_unicode=True)

        print(f"Saved meta: {meta_path}")

    def save_pnl_pred_position_ticker(self, df: pd.DataFrame) -> None:
        """銘柄毎PnL/Pred/Position時系列を保存

        Args:
            df: データフレーム
                - index: datetime
                - 必須カラム: split, epoch, ticker
                - 任意カラム: pnl, pred, position, その他条件カラム（random_seed等）
                - ※ただしpnl/pred/positionの内最低1つはカラムに存在すること
        """
        data_type = "pnl_pred_position/ticker"
        self._validate_pnl_pred_position(df, data_type, self.REQUIRED_COLUMNS_TICKER, [], at_least_one_value=True)
        self._save_dataframe(df, data_type)
        self._save_meta(df, data_type)

    def save_pnl_pred_position_individual(self, df: pd.DataFrame) -> None:
        """個別条件毎PnL/Pred/Position時系列を保存

        Args:
            df: データフレーム
                - index: datetime
                - 必須カラム: split, epoch
                - 任意カラム: pnl, pred, position, その他条件カラム（model_id, random_seed等）
                - ※ただしpnl/pred/positionの内最低1つはカラムに存在すること
        """
        data_type = "pnl_pred_position/individual"
        self._validate_pnl_pred_position(df, data_type, self.REQUIRED_COLUMNS_INDIVIDUAL, [], at_least_one_value=True)
        self._save_dataframe(df, data_type)
        self._save_meta(df, data_type)

    def save_pnl_pred_position_strategy(self, df: pd.DataFrame) -> None:
        """戦略毎PnL/Pred/Position時系列を保存

        Args:
            df: データフレーム
                - index: datetime
                - 必須カラム: pnl, split, epoch, strategy_name
                - 任意カラム: pred, position, その他条件カラム
        """
        required_value_columns = [self.PNL_COLUMN]
        data_type = "pnl_pred_position/strategy"
        self._validate_pnl_pred_position(df, data_type, self.REQUIRED_COLUMNS_STRATEGY, required_value_columns)
        self._save_dataframe(df, data_type)
        self._save_meta(df, data_type)

    def _validate_stats_metrics(self, df: pd.DataFrame, data_type: str, non_metric_columns: list[str]) -> None:
        """統計メトリクスのバリデーション

        Args:
            df: 統計メトリクスDataFrame
            data_type: データタイプ
            non_metric_columns: 非メトリックカラムのリスト

        Raises:
            ValidationError: バリデーションエラー
        """
        # non_metric_columnsの存在チェック
        missing_cols = set(non_metric_columns) - set(df.columns)
        if missing_cols:
            raise ValidationError(
                f"{data_type}: 必須non_metric_columnsが不足しています: {missing_cols}\n"
                f"必要なカラム: {non_metric_columns}\n"
                f"存在するカラム: {list(df.columns)}"
            )

    def _get_metric_columns(self, df: pd.DataFrame, non_metric_columns: list[str]) -> list[str]:
        """メトリックカラムを取得（non_metric_columns以外）

        Args:
            df: DataFrame
            non_metric_columns: 非メトリックカラムのリスト

        Returns:
            メトリックカラムのリスト
        """
        metric_columns = [col for col in df.columns if col not in non_metric_columns]
        return metric_columns

    def save_stats_metrics_strategy(self, df: pd.DataFrame) -> None:
        """戦略毎統計メトリクス（エポック推移）を保存

        Args:
            df: 統計メトリクスデータフレーム
                - index: epoch
                - 必須カラム: split, epoch, strategy_name
                - その他: メトリック名（任意）+ 任意条件カラム
        """
        data_type = "stats_metrics/strategy"
        self._validate_stats_metrics(df, data_type, self.non_metric_columns_stats_strategy)
        self._save_dataframe(df, data_type)
        self._save_stats_meta(df, data_type, self.non_metric_columns_stats_strategy)

    def save_stats_metrics_individual(self, df: pd.DataFrame) -> None:
        """個別条件毎統計メトリクス（エポック推移）を保存

        Args:
            df: 統計メトリクスデータフレーム
                - index: epoch
                - 必須カラム: split, epoch
                - その他: メトリック名（任意）+ 任意条件カラム（model_id, random_seed等）
        """
        data_type = "stats_metrics/individual"
        self._validate_stats_metrics(df, data_type, self.non_metric_columns_stats_individual)
        self._save_dataframe(df, data_type)
        self._save_stats_meta(df, data_type, self.non_metric_columns_stats_individual)

    def save_code(self, code: str, filename: str) -> None:
        """実験コードを保存

        Args:
            code: 保存するコード文字列
            filename: ファイル名（例: "experiment.py"）
        """
        save_dir = self._get_data_dir("codes")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        save_path.write_text(code)
        print(f"Saved: {save_path}")

    def save_params(self, params: dict[str, Any], filename: str = "config.yaml") -> None:
        """ハイパーパラメータをYAML形式で保存

        Args:
            params: ハイパーパラメータ辞書
            filename: ファイル名（例: "config.yaml"）
        """
        save_dir = self._get_data_dir("params")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename

        with open(save_path, "w") as f:
            yaml.dump(params, f, default_flow_style=False, allow_unicode=True)

        print(f"Saved: {save_path}")

    def save_all(
        self,
        pnl_pred_position_ticker: pd.DataFrame | None = None,
        pnl_pred_position_individual: pd.DataFrame | None = None,
        pnl_pred_position_strategy: pd.DataFrame | None = None,
        stats_metrics_strategy: pd.DataFrame | None = None,
        stats_metrics_individual: pd.DataFrame | None = None,
        params: dict[str, Any] | None = None,
        code: str | None = None,
        code_filename: str = "experiment.py",
    ) -> None:
        """全データを一括保存

        Args:
            pnl_pred_position_ticker: 銘柄毎データ
            pnl_pred_position_individual: 個別条件毎データ
            pnl_pred_position_strategy: 戦略毎データ
            stats_metrics_strategy: 戦略毎統計メトリクス
            stats_metrics_individual: 個別条件毎統計メトリクス
            params: ハイパーパラメータ
            code: 実験コード
            code_filename: コードのファイル名
        """
        if pnl_pred_position_ticker is not None:
            self.save_pnl_pred_position_ticker(pnl_pred_position_ticker)

        if pnl_pred_position_individual is not None:
            self.save_pnl_pred_position_individual(pnl_pred_position_individual)

        if pnl_pred_position_strategy is not None:
            self.save_pnl_pred_position_strategy(pnl_pred_position_strategy)

        if stats_metrics_strategy is not None:
            self.save_stats_metrics_strategy(stats_metrics_strategy)

        if stats_metrics_individual is not None:
            self.save_stats_metrics_individual(stats_metrics_individual)

        if params is not None:
            self.save_params(params)

        if code is not None:
            self.save_code(code, code_filename)

        print(f"\nAll data saved to: {self.run_dir}")
