"""実験データ読み込みモジュール

保存された実験データを読み込み、可視化用に処理する
"""

import pandas as pd
import yaml

from bt_log_vis_tool.permissions import is_open
from bt_log_vis_tool.storage import AnyPath as Path


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

        # UPathオブジェクトをそのまま渡すとpyarrowがgs://を認識できずTypeErrorになるため、
        # 文字列化してfsspec URLとして解決させる
        return pd.read_parquet(str(data_path))

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

        with meta_path.open() as f:
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

    def load_metrics_history_strategy(self) -> pd.DataFrame | None:
        """戦略毎メトリクス学習推移（エポック推移）を読み込み

        Returns:
            メトリクス学習推移 DataFrame
        """
        return self._load_dataframe("metrics_history/strategy")

    def load_metrics_history_individual(self) -> pd.DataFrame | None:
        """個別条件毎メトリクス学習推移（エポック推移）を読み込み

        Returns:
            メトリクス学習推移 DataFrame
        """
        return self._load_dataframe("metrics_history/individual")

    def load_params(self, filename: str, can_view_closed: bool = False) -> dict | None:
        """ハイパーパラメータを読み込み

        Args:
            filename: YAMLファイル名（"open/xxx.yaml"、"closed/xxx.yaml"、"xxx.yaml"のいずれか）
            can_view_closed: Trueの場合、closed指定のファイルも読み込める

        Returns:
            ハイパーパラメータ辞書（closed指定でcan_view_closed=Falseの場合、ファイルが存在してもNone）
        """
        if not (can_view_closed or is_open(filename)):
            return None

        params_path = self.run_dir / "params" / filename

        if not params_path.exists():
            return None

        with params_path.open() as f:
            params = yaml.safe_load(f)

        return params

    def list_params_files(self, can_view_closed: bool = False) -> list[str]:
        """保存済みパラメータファイル名の一覧を取得（アルファベット順）

        Args:
            can_view_closed: Trueの場合、closed指定のファイルも一覧に含める

        Returns:
            ファイル名（相対パス）のリスト（paramsディレクトリが無い場合は空リスト）
        """
        return self._list_category_files("params", can_view_closed)

    def _list_category_files(self, category: str, can_view_closed: bool = False) -> list[str]:
        """指定カテゴリ配下のファイル名一覧を取得（アルファベット順）

        <category>/直下のファイルに加え、<category>/open/・<category>/closed/配下のファイルも
        "open/xxx"・"closed/xxx"の形式で含める。can_view_closed=Falseの場合、
        closed指定のファイル（存在自体）は一覧から除外する。

        Args:
            category: データカテゴリ（例: "codes", "report"）
            can_view_closed: Trueの場合、closed指定のファイルも一覧に含める

        Returns:
            ファイル名（相対パス）のリスト（ディレクトリが無い場合は空リスト）
        """
        category_dir = self.run_dir / category
        if not category_dir.exists():
            return []

        relative_paths = []
        for entry in category_dir.iterdir():
            if entry.is_dir():
                if entry.name in ("open", "closed"):
                    relative_paths.extend(f"{entry.name}/{sub.name}" for sub in entry.iterdir() if not sub.is_dir())
                continue
            relative_paths.append(entry.name)

        return sorted(rel for rel in relative_paths if can_view_closed or is_open(rel))

    def _load_category_file(self, category: str, filename: str, can_view_closed: bool = False) -> str | None:
        """指定カテゴリ配下のファイルをテキストとして読み込み

        Args:
            category: データカテゴリ（例: "codes", "report"）
            filename: ファイル名（"open/xxx"、"closed/xxx"、"xxx"のいずれか）
            can_view_closed: Trueの場合、closed指定のファイルも読み込める

        Returns:
            ファイル内容の文字列（closed指定でcan_view_closed=Falseの場合、ファイルが存在してもNone）
        """
        if not (can_view_closed or is_open(filename)):
            return None

        file_path = self.run_dir / category / filename

        if not file_path.exists():
            return None

        return file_path.read_text()

    def load_code(self, filename: str, can_view_closed: bool = False) -> str | None:
        """実験コードを読み込み

        Args:
            filename: コードファイル名（"open/xxx.py"、"closed/xxx.py"、"xxx.py"のいずれか）
            can_view_closed: Trueの場合、closed指定のファイルも読み込める

        Returns:
            コード文字列（closed指定でcan_view_closed=Falseの場合、ファイルが存在してもNone）
        """
        return self._load_category_file("codes", filename, can_view_closed)

    def list_code_files(self, can_view_closed: bool = False) -> list[str]:
        """保存済みコードファイル名の一覧を取得（アルファベット順）

        Args:
            can_view_closed: Trueの場合、closed指定のファイルも一覧に含める

        Returns:
            ファイル名（相対パス）のリスト（コードディレクトリが無い場合は空リスト）
        """
        return self._list_category_files("codes", can_view_closed)

    def load_report(self, filename: str, can_view_closed: bool = False) -> str | None:
        """サマリレポート（markdown、AI生成・手動作成問わず）を読み込み

        Args:
            filename: レポートファイル名（"open/xxx.md"、"closed/xxx.md"、"xxx.md"のいずれか）
            can_view_closed: Trueの場合、closed指定のレポートも読み込める

        Returns:
            レポート文字列（closed指定でcan_view_closed=Falseの場合、ファイルが存在してもNone）
        """
        return self._load_category_file("report", filename, can_view_closed)

    def list_reports(self, can_view_closed: bool = False) -> list[str]:
        """保存済みサマリレポートファイル名の一覧を取得（アルファベット順）

        Args:
            can_view_closed: Trueの場合、closed指定のレポートも一覧に含める

        Returns:
            ファイル名（相対パス）のリスト（reportディレクトリが無い場合は空リスト）
        """
        return self._list_category_files("report", can_view_closed)

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
            "metrics_history/strategy",
            "metrics_history/individual",
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
