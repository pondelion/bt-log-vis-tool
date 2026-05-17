# bt-log-vis-tool 仕様書

バックテスト実験の結果を構造化保存し、Streamlit ダッシュボードで可視化するツールの仕様。

---

## 用語定義

| 用語 | 説明 |
|---|---|
| `base_dir` | 実験データの保存ルートディレクトリ |
| `exp_name` | ノートブック（実験テーマ）単位の名前 |
| `run_name` | 同一ノートブック内の各試行の名前 |
| `split` | データ分割区分。`train` / `val` / `test` の3種 |
| `epoch` | 学習エポック番号（整数） |
| `strategy_name` | 戦略名（例: `longshort`, `long_only`） |
| `ticker` | 銘柄コード |
| `non_metric_columns` | 統計メトリクスDFにおける条件カラム（メトリック以外） |

---

## 1. ディレクトリ構造

```
{base_dir}/
└── {exp_name}/
    └── {run_name}/
        ├── pnl_pred_position/
        │   ├── ticker/              # 銘柄別時系列 (optional)
        │   │   ├── data.parquet
        │   │   └── meta.yaml
        │   ├── individual/          # 個別条件別時系列 (optional)
        │   │   ├── data.parquet
        │   │   └── meta.yaml
        │   └── strategy/            # 戦略別時系列 (必須)
        │       ├── data.parquet
        │       └── meta.yaml
        ├── stats_metrics/
        │   ├── strategy/            # 戦略別統計メトリクス (必須)
        │   │   ├── data.parquet
        │   │   └── meta.yaml        # non_metric_columns / metric_columns を記録
        │   └── individual/          # 個別条件別統計メトリクス (optional)
        │       ├── data.parquet
        │       └── meta.yaml
        ├── params/
        │   └── config.yaml          # ハイパーパラメータ (optional)
        └── codes/
            └── {filename}           # 実験コード (optional)
```

---

## 2. 保存データ仕様

### 2.1. PnL / Pred / Position 時系列データ

時系列データは3種類あり、それぞれ独立した parquet ファイルに保存する。
**共通ルール:**
- index: `DatetimeIndex`
- `pnl` / `pred` / `position` 以外のカラムはすべて「条件カラム」として扱う
- 条件カラムの組み合わせでgroupbyしたとき、index（日時）が一意になること（バリデーションあり）

#### 2.1.1. 銘柄別時系列 `pnl_pred_position/ticker` *(optional)*

複数銘柄の予測・ポジション・損益を銘柄単位で保存する。

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `ticker` | ✅ | 銘柄コード |
| `pnl` | ※1 | 損益 |
| `pred` | ※1 | 予測値 |
| `position` | ※1 | ポジション |
| その他 | - | random_seed 等、任意の条件カラム |

※1: `pnl` / `pred` / `position` のうち最低1つは必須

```python
# DataFrame フォーマット例
#   index: DatetimeIndex
#   条件カラムの組み合わせ (split, epoch, ticker) ごとに日時が一意

            split  epoch ticker      pnl     pred  position
2023-01-01  train      0   AAPL   0.005    0.312         1
2023-01-02  train      0   AAPL  -0.002   -0.105         0
2023-01-01  train      0  GOOGL   0.003    0.198         1
...
```

#### 2.1.2. 個別条件別時系列 `pnl_pred_position/individual` *(optional)*

複数の弱学習モデルや乱数シード別など、任意の個別条件ごとの時系列を保存する。

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `pnl` | ※1 | 損益 |
| `pred` | ※1 | 予測値 |
| `position` | ※1 | ポジション |
| その他 | - | `model_id`, `random_seed` 等、任意の条件カラム |

※1: `pnl` / `pred` / `position` のうち最低1つは必須

```python
# DataFrame フォーマット例
#   条件カラムの組み合わせ (split, epoch, model_id) ごとに日時が一意

            split  epoch  model_id      pnl     pred  position
2023-01-01  train      0         0   0.004    0.280         1
2023-01-02  train      0         0  -0.001   -0.090         0
2023-01-01  train      0         1   0.006    0.310         1
...
```

#### 2.1.3. 戦略別時系列 `pnl_pred_position/strategy` *(必須)*

銘柄・個別条件を集約した最終的な戦略単位の損益時系列。
longshort ポートフォリオ・シードアンサンブル等の戦略ごとに保存する。

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `strategy_name` | ✅ | 戦略名 |
| `pnl` | ✅ | 損益 |
| `pred` | - | 予測値 |
| `position` | - | ポジション |
| その他 | - | 任意の条件カラム |

```python
# DataFrame フォーマット例
#   条件カラムの組み合わせ (split, epoch, strategy_name) ごとに日時が一意

            split  epoch strategy_name      pnl     pred  position
2023-01-01  train      0     longshort   0.010    0.123         1
2023-01-02  train      0     longshort   0.005   -0.045         0
2023-01-01  train      0     long_only   0.007    0.089         1
...
```

---

### 2.2. 統計メトリクス

エポックごとのパフォーマンス指標（annual return / sharpe ratio 等）を保存する。
メトリクス名は実験ごとに異なるため、条件カラムを `non_metric_columns` として `meta.yaml` に記録し、残りをメトリクスカラムとして扱う。

#### 2.2.1. 戦略別統計メトリクス `stats_metrics/strategy` *(必須)*

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `strategy_name` | ✅ | 戦略名 |
| メトリクス名 | - | 実験ごとに任意（例: `annual_return`, `sharpe_ratio`） |

- index: 任意（整数でも epoch 値でも可）

```python
# DataFrame フォーマット例

   split strategy_name  epoch  annual_return  annual_risk  sharpe_ratio  max_drawdown
0  train     longshort      0           0.15         0.12           1.2         -0.10
1    val     longshort      0           0.12         0.13           1.0         -0.15
2   test     longshort      0           0.10         0.11           0.9         -0.18
3  train     longshort      1           0.18         0.11           1.5         -0.08
...

# meta.yaml の内容
# non_metric_columns: [split, epoch, strategy_name]
# metric_columns: [annual_return, annual_risk, sharpe_ratio, max_drawdown]
```

#### 2.2.2. 個別条件別統計メトリクス `stats_metrics/individual` *(optional)*

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| その他条件 | - | `model_id`, `random_seed` 等 |
| メトリクス名 | - | 実験ごとに任意 |

---

### 2.3. ハイパーパラメータ `params/config.yaml` *(optional)*

前処理・特徴量・モデル・学習・評価など実験条件をすべて `dict` で渡す。YAML 形式に変換して保存される。

```python
params = {
    "model": {"type": "neural_network", "layers": [128, 64, 32]},
    "training": {"epochs": 10, "learning_rate": 0.001},
    "strategy": {"long_threshold": 0.6, "short_threshold": -0.6},
}
```

---

### 2.4. 実験コード `codes/{filename}` *(optional)*

実験コードを文字列で渡す。拡張子付きのファイル名を指定する。

---

## 3. 保存 API

`ExperimentSaver` を使って Jupyter Notebook から保存する。

### 3.1. 初期化

```python
from bt_log_vis_tool import ExperimentSaver

saver = ExperimentSaver(
    base_dir="./backtest_experiments",   # 保存ルートディレクトリ
    exp_name="my_experiment",            # 実験名
    run_name="run_001",                  # ラン名
)
```

`non_metric_columns` をデフォルト以外にしたい場合:

```python
saver = ExperimentSaver(
    base_dir="./backtest_experiments",
    exp_name="my_experiment",
    run_name="run_001",
    non_metric_columns_stats_strategy=["split", "epoch", "strategy_name", "seed"],
)
```

### 3.2. 一括保存 `save_all()`

すべて省略可能（`None` の場合はスキップ）。

```python
saver.save_all(
    pnl_pred_position_ticker=ticker_df,         # 銘柄別時系列 (optional)
    pnl_pred_position_individual=individual_df, # 個別条件別時系列 (optional)
    pnl_pred_position_strategy=strategy_df,     # 戦略別時系列
    stats_metrics_strategy=stats_df,            # 戦略別統計メトリクス
    stats_metrics_individual=stats_ind_df,      # 個別条件別統計メトリクス (optional)
    params=params_dict,                         # ハイパーパラメータ (optional)
    code=code_string,                           # 実験コード文字列 (optional)
    code_filename="experiment.py",              # コードのファイル名 (optional)
)
```

### 3.3. バリデーション

保存時に以下を自動チェックし、違反があれば `ValidationError` を送出する。

- 必須カラムの存在チェック
- `pnl_pred_position` 系データ: 条件カラムの組み合わせで groupby したとき日時 index が一意であること
- `stats_metrics` 系データ: `non_metric_columns` で指定したカラムがすべて存在すること

---

## 4. 可視化ダッシュボード

Streamlit による Web ダッシュボード。`exp_name` × `run_name` の組み合わせをサイドバーから選択し、詳細を閲覧する。

### 4.1. サイドバー

| UI 要素 | 説明 |
|---|---|
| ベースディレクトリ入力 | データの保存先ルートパス |
| exp_name セレクトボックス | 利用可能な実験一覧から選択 |
| run_name セレクトボックス | 選択した実験内のラン一覧から選択 |
| ベストエポック判定設定 | 判定 split / メトリクス / strategy_name を選択（全タブ共通） |
| ベストエポック表示 | 算出されたベストエポック番号を表示 |

ベストエポック判定のデフォルト: `split=test`, メトリクス=sharpe 系の先頭, strategy=先頭

---

### 4.2. タブ構成

| タブ | 内容 | データ不在時 |
|---|---|---|
| 統計メトリクス | エポック推移グラフ・生データ表 | 警告表示 |
| 戦略時系列（資産曲線・ポジション） | 戦略別の累積PnL・ポジション・予測値 | 警告表示 |
| 銘柄別時系列（資産曲線・ポジション） | 銘柄別の累積PnL・ポジション・予測値 | 「データなし」表示 |
| パラメータ | ハイパーパラメータの JSON 表示 | 警告表示 |
| コード | 実験コードのシンタックスハイライト表示 | 警告表示 |

---

### 4.3. 統計メトリクスタブ

#### グラフ

- **縦方向**: メトリクスごとにグラフを分ける
- **横方向**: split ごとにグラフを並べる
- split はチェックボックスで表示/非表示を選択（デフォルト: 全選択）
- 各 strategy_name は同一グラフ内に複数トレースとして描画
- ベンチマーク戦略はセレクトボックスで選択可能（選択なし可）。選択された系列は赤色・太線で強調表示
- ベストエポックの位置に破線縦線を表示

#### 表

- **describe() などの集計ではなく生データを表示**
- index: epoch（重複なし）
- split ごとに別テーブルとして横並びに表示（チェックボックスで選択可能、デフォルト: 全選択）
- カラム: `{メトリクス名}_{strategy_name}` の形式で横持ちに整形（unstackに相当）

---

### 4.4. 戦略時系列タブ

- エポック選択セレクトボックス（デフォルト: サイドバーのベストエポック）
- split チェックボックス（横並び、デフォルト: 全選択）
- 選択エポックのデータを split ごとに横並びグラフで表示
- 表示する値:
  - 累積 PnL（`pnl` が存在する場合）
  - ポジション時系列（`position` が存在する場合）
  - 予測値時系列（`pred` が存在する場合）
- 各グラフ内で strategy_name を色分けして重ねて表示

---

### 4.5. 銘柄別時系列タブ

- `pnl_pred_position/ticker` データがない場合は「データなし」を表示してタブ終了
- エポック選択セレクトボックス（デフォルト: サイドバーのベストエポック）
- split チェックボックス（横並び、デフォルト: 全選択）
- ticker マルチセレクト（デフォルト: 全選択）
- 表示する値:
  - 累積 PnL（`pnl` が存在する場合）
  - ポジション時系列（`position` が存在する場合）
  - 予測値時系列（`pred` が存在する場合）
- 各グラフ内で選択 ticker を色分けして重ねて表示、split ごとに横並び

---

### 4.6. パラメータタブ

- `params/config.yaml` を読み込み、JSON 形式で表示
- ファイルが存在しない場合は警告を表示

---

### 4.7. コードタブ

- `codes/` ディレクトリ内のファイルを列挙
- ファイルが1つの場合はそのまま表示、複数の場合はセレクトボックスで選択
- 拡張子に応じてシンタックスハイライト（`.py` → Python, `.yaml` → YAML 等）
- ファイルが存在しない場合は警告を表示
