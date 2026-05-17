"""実験データ読み込みモジュール

保存された実験データを読み込み、可視化用に処理する
"""

from pathlib import Path

import pandas as pd
import yaml


class ExperimentLoader:
    """実験データ読み込みクラス

    保存された実験データを読み込み、分析・可視化用に提供する
    """

    def __init__(
        self,
        base_dir: str | Path,
        exp_name: str,
        run_name: str,
    ):
        """
        Args:
            base_dir: 保存先のベースディレクトリ
            exp_name: 実験名
            run_name: ラン名
        """
        self.base_dir = Path(base_dir).expanduser()
        self.exp_name = exp_name
        self.run_name = run_name
        self.run_dir = self.base_dir / exp_name / run_name

    @staticmethod
    def list_experiments(base_dir: str | Path) -> list[str]:
        """利用可能な実験名のリストを取得

        Args:
            base_dir: ベースディレクトリ

        Returns:
            実験名のリスト
        """
        base_path = Path(base_dir).expanduser()
        if not base_path.exists():
            return []

        experiments = [d.name for d in base_path.iterdir() if d.is_dir()]
        return sorted(experiments)

    @staticmethod
    def list_runs(base_dir: str | Path, exp_name: str) -> list[str]:
        """指定実験の利用可能なラン名のリストを取得

        Args:
            base_dir: ベースディレクトリ
            exp_name: 実験名

        Returns:
            ラン名のリスト
        """
        exp_path = Path(base_dir).expanduser() / exp_name
        if not exp_path.exists():
            return []

        runs = [d.name for d in exp_path.iterdir() if d.is_dir()]
        return sorted(runs)

    def _get_data_path(self, data_type: str, filename: str = "data.parquet") -> Path:
        """データファイルのパスを取得

        Args:
            data_type: データタイプ
            filename: ファイル名

        Returns:
            データファイルパス
        """
        return self.run_dir / data_type / filename

    def _load_dataframe(
        self,
        data_type: str,
        filename: str = "data.parquet",
    ) -> pd.DataFrame | None:
        """DataFrameを読み込み

        Args:
            data_type: データタイプ
            filename: ファイル名

        Returns:
            読み込んだDataFrame、存在しない場合はNone
        """
        data_path = self._get_data_path(data_type, filename)
        if not data_path.exists():
            return None

        return pd.read_parquet(data_path)

    def load_meta(self, data_type: str) -> dict | None:
        """メタデータを読み込み

        Args:
            data_type: データタイプ

        Returns:
            メタデータ辞書、存在しない場合はNone
        """
        meta_path = self.run_dir / data_type / "meta.yaml"
        if not meta_path.exists():
            return None

        with open(meta_path) as f:
            return yaml.safe_load(f)

    def load_pnl_pred_position_ticker(self) -> pd.DataFrame | None:
        """銘柄毎PnL/Pred/Position時系列を読み込み

        Returns:
            DataFrame
        """
        return self._load_dataframe("pnl_pred_position/ticker")

    def load_pnl_pred_position_individual(self) -> pd.DataFrame | None:
        """個別条件毎PnL/Pred/Position時系列を読み込み

        Returns:
            DataFrame
        """
        return self._load_dataframe("pnl_pred_position/individual")

    def load_pnl_pred_position_strategy(self) -> pd.DataFrame | None:
        """戦略毎PnL/Pred/Position時系列を読み込み

        Returns:
            DataFrame
        """
        return self._load_dataframe("pnl_pred_position/strategy")

    def load_stats_metrics_strategy(self) -> pd.DataFrame | None:
        """戦略毎統計メトリクス（エポック推移）を読み込み

        Returns:
            統計メトリクス DataFrame
        """
        return self._load_dataframe("stats_metrics/strategy")

    def load_stats_metrics_individual(self) -> pd.DataFrame | None:
        """個別条件毎統計メトリクス（エポック推移）を読み込み

        Returns:
            統計メトリクス DataFrame
        """
        return self._load_dataframe("stats_metrics/individual")

    def load_params(self, filename: str = "config.yaml") -> dict | None:
        """ハイパーパラメータを読み込み

        Args:
            filename: YAMLファイル名

        Returns:
            ハイパーパラメータ辞書
        """
        params_dir = self.run_dir / "params"
        params_path = params_dir / filename

        if not params_path.exists():
            return None

        with open(params_path) as f:
            params = yaml.safe_load(f)

        return params

    def load_code(self, filename: str) -> str | None:
        """実験コードを読み込み

        Args:
            filename: コードファイル名

        Returns:
            コード文字列
        """
        code_dir = self.run_dir / "codes"
        code_path = code_dir / filename

        if not code_path.exists():
            return None

        return code_path.read_text()

    def get_available_data_types(self) -> list[str]:
        """利用可能なデータタイプのリストを取得

        Returns:
            データタイプのリスト
        """
        data_types = []
        for data_type in [
            "pnl_pred_position/ticker",
            "pnl_pred_position/individual",
            "pnl_pred_position/strategy",
            "stats_metrics/strategy",
            "stats_metrics/individual",
        ]:
            if self._get_data_path(data_type).exists():
                data_types.append(data_type)

        return data_types

    def exists(self) -> bool:
        """このラン用のデータが存在するかチェック

        Returns:
            存在する場合True
        """
        return self.run_dir.exists()
