# bt-log-vis-tool 仕様書

バックテスト実験の結果を構造化保存し、Streamlit ダッシュボードで可視化するツールの仕様。
ローカルファイルシステムと GCS のどちらもデータソースとして使え、クラウド利用時はログイン・閲覧権限の仕組みを備える。

デプロイ手順（Cloud Run / Terraform）は [docs/deploy.md](deploy.md) を参照。本書はツール自体の機能仕様を扱う。

---

## 用語定義

| 用語 | 説明 |
|---|---|
| `base_dir` | 実験データの保存ルートディレクトリ。ローカルパスまたは`gs://bucket/prefix`形式のGCSパス |
| `exp_name` | 実験テーマ単位の名前（1つの実験スクリプトやノートブックに対応することが多い） |
| `run_name` | 同一テーマ内の各試行の名前 |
| `split` | データ分割区分。`train` / `val` / `test` の3種 |
| `epoch` | 学習エポック番号（整数） |
| `strategy_name` | 戦略名（例: `longshort`, `long_only`）。ベンチマーク系列（buy&hold等、モデル予測に依存しない参照系列）は `bm_` プレフィックスを付ける（例: `bm_buy_and_hold`） |
| `ticker` | 銘柄コード |
| `non_metric_columns` | 統計メトリクスDFにおける条件カラム（メトリック以外） |
| open / closed | ファイル単位の公開区分。openは誰でも閲覧可、closedはログイン済み・許可リスト登録者のみ閲覧可 |

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
        ├── params/                  # ハイパーパラメータ (optional, open/closed対応)
        │   ├── open/{filename}.yaml
        │   ├── closed/{filename}.yaml
        │   └── {filename}.yaml      # サブディレクトリ無し = closed扱い
        ├── codes/                   # 実験コード (optional, open/closed対応)
        │   ├── open/{filename}
        │   ├── closed/{filename}
        │   └── {filename}           # サブディレクトリ無し = closed扱い
        └── report/                  # サマリレポート (optional, open/closed対応)
            ├── open/{filename}.md
            ├── closed/{filename}.md
            └── {filename}.md        # サブディレクトリ無し = closed扱い
```

`pnl_pred_position/` と `stats_metrics/` にはopen/closedの区分は無く、存在すれば常に誰でも閲覧できる（実験の性能データ自体は公開してよい、コード・パラメータ・レポートだけを機密扱いできる、という想定）。

---

## 2. 保存データ仕様

### 2.1. PnL / Pred / Position 時系列データ

時系列データは3種類あり、それぞれ独立した parquet ファイルに保存する。
**共通ルール:**
- index: `DatetimeIndex`
- `pnl` / `pred` / `position` / `pnl_abs` 以外のカラムはすべて「条件カラム」として扱う
- 条件カラムの組み合わせでgroupbyしたとき、index（日時）が一意になること（バリデーションあり）
- `pnl` は率（リターン）、`pnl_abs` は絶対損益（価格差分の合算値。通貨単位はデータ依存でtool側は関知しない）。両方保存してもよい

**ウォークフォワード等、期間間で日時が重複しうる場合**は、任意カラム`period_start`/`period_end`を追加できる（`strategy`/`ticker`両方対応、意味・ペア必須の制約は2.2節の`stats_metrics`と同じ）。条件カラムの一意性チェックは全カラムを対象に自動で行われる汎用的な仕組みのため、`period_start`/`period_end`を含めるだけで「同じ`split`/`epoch`/`strategy_name`でも期間が違えば日時重複してよい」という判定になる（保存側の追加実装は不要）。**期間を跨いで日時が重複しうるのに`period_start`/`period_end`を付け忘れた場合は、従来通り`ValidationError`になる**（気付かず不正なデータを保存する事故を防ぐため、明示的にエラーで落とす）。

#### 2.1.1. 銘柄別時系列 `pnl_pred_position/ticker` *(optional)*

複数銘柄の予測・ポジション・損益を銘柄単位で保存する。

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `ticker` | ✅ | 銘柄コード |
| `pnl` | ※1 | 損益（率） |
| `pred` | ※1 | 予測値 |
| `position` | ※1 | ポジション |
| `pnl_abs` | ※1 | 絶対損益（価格差分。1単位保有等、実験側が定義した数量ベース） |
| `period_start` / `period_end` | - | ウォークフォワード等の期間区別用（両方揃えて指定。2.1節参照） |
| その他 | - | random_seed 等、任意の条件カラム |

※1: `pnl` / `pred` / `position` / `pnl_abs` のうち最低1つは必須

```python
# DataFrame フォーマット例
#   index: DatetimeIndex
#   条件カラムの組み合わせ (split, epoch, ticker) ごとに日時が一意

            split  epoch ticker      pnl     pred  position  pnl_abs
2023-01-01  train      0   AAPL   0.005    0.312         1     0.85
2023-01-02  train      0   AAPL  -0.002   -0.105         0     0.00
2023-01-01  train      0  GOOGL   0.003    0.198         1     4.20
...
```

#### 2.1.2. 個別条件別時系列 `pnl_pred_position/individual` *(optional)*

複数の弱学習モデルや乱数シード別など、任意の個別条件ごとの時系列を保存する。

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `pnl` | ※1 | 損益（率） |
| `pred` | ※1 | 予測値 |
| `position` | ※1 | ポジション |
| `pnl_abs` | ※1 | 絶対損益 |
| `period_start` / `period_end` | - | ウォークフォワード等の期間区別用（両方揃えて指定。2.1節参照） |
| その他 | - | `model_id`, `random_seed` 等、任意の条件カラム |

※1: `pnl` / `pred` / `position` / `pnl_abs` のうち最低1つは必須

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
| `pnl` | ✅ | 損益（率） |
| `pred` | - | 予測値 |
| `position` | - | ポジション |
| `pnl_abs` | - | 絶対損益（各銘柄の絶対損益を集計した値） |
| `period_start` / `period_end` | - | ウォークフォワード等の期間区別用（両方揃えて指定。2.1節参照） |
| その他 | - | 任意の条件カラム |

```python
# DataFrame フォーマット例
#   条件カラムの組み合わせ (split, epoch, strategy_name) ごとに日時が一意

            split  epoch strategy_name      pnl     pred  position  pnl_abs
2023-01-01  train      0     longshort   0.010    0.123         1     12.5
2023-01-02  train      0     longshort   0.005   -0.045         0      6.1
2023-01-01  train      0     long_only   0.007    0.089         1      8.9
...
```

---

### 2.2. 統計メトリクス

エポックごとのパフォーマンス指標（annual return / sharpe ratio 等）を保存する。
メトリクス名は実験ごとに異なるため、条件カラムを `non_metric_columns` として `meta.yaml` に記録し、残りをメトリクスカラムとして扱う。

**ウォークフォワード等、複数期間を区別したい場合**は、任意カラム`period_start`/`period_end`を追加できる（`strategy`/`individual`両方対応、必ず両方揃えて指定する。片方だけは`ValidationError`）。値は「そのepoch行が属する期間全体（学習開始日〜テスト終了日）」を表す文字列。epoch番号は期間毎に1から振り直してよい（`period_start`/`period_end`の組で期間を区別するため、`split`/`epoch`/`strategy_name`だけでは複数期間間で衝突しても問題ない）。指定すると、ダッシュボードの統計メトリクスタブ内に期間選択UIが表示される（4.3節参照）。指定しない場合は単一期間の実験として今まで通り扱われる（後方互換）。

#### 2.2.1. 戦略別統計メトリクス `stats_metrics/strategy` *(必須)*

| カラム | 必須 | 説明 |
|---|---|---|
| `split` | ✅ | `train` / `val` / `test` |
| `epoch` | ✅ | エポック番号 |
| `strategy_name` | ✅ | 戦略名 |
| `period_start` / `period_end` | - | ウォークフォワード等の期間区別用（両方揃えて指定） |
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
| `period_start` / `period_end` | - | ウォークフォワード等の期間区別用（両方揃えて指定。2.2節参照） |
| その他条件 | - | `model_id`, `random_seed` 等 |
| メトリクス名 | - | 実験ごとに任意 |

---

### 2.3. open/closed 権限モデル（`params` / `codes` / `report` 共通）

3カテゴリとも、ファイル名（`filename`引数）の**先頭サブディレクトリ**で公開状態が決まる。設定ファイルは無く、ディレクトリ構造だけで判定する（`bt_log_vis_tool/permissions.py`の`is_open()`）。

| filenameの指定 | 実際の保存先 | 公開状態 |
|---|---|---|
| `"open/xxx"` | `{category}/open/xxx` | open（誰でも閲覧可） |
| `"closed/xxx"` | `{category}/closed/xxx` | closed（ログイン済み・許可リスト登録者のみ） |
| `"xxx"`（サブディレクトリ無し） | `{category}/xxx` | **closed**（fail-closed。明示的にopenと指定しない限り非公開） |

同一カテゴリ内で複数ファイルを持て、openとclosedを混在させられる（例: `codes/open/public_summary.py`と`codes/closed/model.py`を同時に保存可能）。

閲覧側は、ローカルデータソース利用時は常にopen扱い（無条件で全部見える）。クラウド(GCS)データソース利用時のみ、ログイン＋許可リストで判定される（詳細は4章）。

---

### 2.4. 実験コード `codes/{filename}` *(optional, 複数可)*

実験コードを文字列で渡す。拡張子付きのファイル名を指定する。open/closedの指定方法は2.3節参照。

---

### 2.5. ハイパーパラメータ `params/{filename}` *(optional, 複数可)*

前処理・特徴量・モデル・学習・評価など実験条件をすべて `dict` で渡す。YAML 形式に変換して保存される。open/closedの指定方法は2.3節参照。デフォルトファイル名は`config.yaml`。

```python
params = {
    "model": {"type": "neural_network", "layers": [128, 64, 32]},
    "training": {"epochs": 10, "learning_rate": 0.001},
    "strategy": {"long_threshold": 0.6, "short_threshold": -0.6},
}
```

---

### 2.6. サマリレポート `report/{filename}` *(optional, 複数可)*

結果のサマリレポートをmarkdown文字列で渡す（AI生成・手動作成問わず）。デフォルトファイル名は`report.md`。open/closedの指定方法は2.3節参照。ダッシュボードの「サマリレポート」タブでプレビュー表示される。

---

## 3. 保存 API

`ExperimentSaver` を使って学習スクリプト（.py）から保存する（Jupyter Notebookからも同様に利用可）。`base_dir`にはローカルパスと`gs://bucket/prefix`形式のGCSパスのどちらも渡せる（詳細は5章）。

### 3.1. 初期化

```python
from bt_log_vis_tool import ExperimentSaver

saver = ExperimentSaver(
    base_dir="./backtest_experiments",   # 保存ルートディレクトリ（ローカル or gs://...）
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

すべて省略可能（`None` の場合はスキップ）。`code_filename` / `report_filename` はデフォルトで`closed/`配下（非公開）になる。openにしたい場合は明示的に`"open/xxx"`を指定する。

```python
saver.save_all(
    pnl_pred_position_ticker=ticker_df,         # 銘柄別時系列 (optional)
    pnl_pred_position_individual=individual_df, # 個別条件別時系列 (optional)
    pnl_pred_position_strategy=strategy_df,     # 戦略別時系列
    stats_metrics_strategy=stats_df,            # 戦略別統計メトリクス
    stats_metrics_individual=stats_ind_df,      # 個別条件別統計メトリクス (optional)
    params=params_dict,                         # ハイパーパラメータ (optional)
    code=code_string,                           # 実験コード文字列 (optional)
    code_filename="closed/experiment.py",       # コードのファイル名（デフォルトclosed）
    report=report_markdown,                  # サマリレポート文字列 (optional)
    report_filename="closed/report.md",      # レポートのファイル名（デフォルトclosed）
)
```

個別に保存したい場合は `save_code(code, filename)` / `save_params(params, filename)` / `save_report(content, filename)` をそれぞれ直接呼んでもよい。

### 3.3. バリデーション

保存時に以下を自動チェックし、違反があれば `ValidationError` を送出する。

- 必須カラムの存在チェック
- `pnl_pred_position` 系データ: 条件カラムの組み合わせで groupby したとき日時 index が一意であること（`period_start`/`period_end`を含めれば期間を跨いだ日時重複も許容される。2.1節参照）
- `stats_metrics` 系データ: `non_metric_columns` で指定したカラムがすべて存在すること

---

## 4. 可視化ダッシュボード

Streamlit による Web ダッシュボード。`exp_name` × `run_name` の組み合わせをサイドバーから選択し、詳細を閲覧する。

### 4.1. サイドバー

| UI 要素 | 説明 |
|---|---|
| データソース選択（ローカル/クラウド） | ローカル実行時のみ表示。Cloud Run上ではクラウド固定で選択肢自体が非表示になる |
| ベースディレクトリ / GCSパス入力 | データの保存先ルートパス。クラウドモードではCloud Run環境変数`GCS_BASE_DIR`があればデフォルト値として自動入力される |
| ログインUI | クラウドデータソース選択時のみ表示（4.1.1参照） |
| exp_name セレクトボックス | 利用可能な実験一覧から選択 |
| run_name セレクトボックス | 選択した実験内のラン一覧から選択 |
| ベストエポック判定設定 | 判定 split / メトリクス / strategy_name を選択（全タブ共通のデフォルトエポックとして使う） |

ベストエポック判定のデフォルト: `split=val`, メトリクス=sharpe 系の先頭, strategy=`long_short`優先。判定設定は統計メトリクス・戦略時系列・銘柄別時系列の全タブで共通のため、ここではサイドバーに置く。算出されたベストエポック番号自体はサイドバーには表示せず、各タブ（統計メトリクスタブのグラフの破線縦線、戦略/銘柄別時系列タブのエポック選択セレクトボックスのラベル）で個別に表示する（サイドバーに単独で出しても現在どのタブ・どの期間に対する値か分かりづらいため）。`period_start`/`period_end`がある場合、この判定設定は全期間それぞれに独立して適用され、期間ごとのベストエポックの辞書（`{(period_start, period_end): best_epoch}`）を算出する（ベストエポックは各期間に1対1で紐づくため）。一方、**期間選択**（ウォークフォワード用、統計メトリクスタブでどの期間を表示するかの絞り込み）は期間という概念自体が統計メトリクスタブにしか無い（他タブは全期間を跨いで表示する。4.3〜4.5節参照）ため、ウィジェット自体は統計メトリクスタブの中に配置している。

#### 4.1.1. ログイン（クラウドデータソース選択時のみ）

- Googleアカウントでのログイン（Streamlitネイティブ認証, `st.login()`）
- ログイン自体は任意のGoogleアカウントで可能。**closedコンテンツの閲覧可否は、`{バケットルート}/_admin/allowlist.yaml`に登録された許可メールアドレスかどうかで判定する**（アプリ側の許可リストが実効的なアクセス制御。GoogleのOAuth同意画面のTesting/Test Users設定は、実際には非機密スコープのみの場合アクセス制限として機能しないことを確認済みのため、当てにしない）
- 許可リストの読み込みに失敗した場合はfail-closed（closedコンテンツは一切表示しない）
- ローカルデータソース選択時はログイン機構自体を使わず、常にフルオープン（openもclosedも区別なく全部閲覧可能）

---

### 4.2. タブ構成

| タブ | 内容 | データ不在時 |
|---|---|---|
| 統計メトリクス | エポック推移グラフ・生データ表 | 警告表示 |
| 戦略時系列（資産曲線・ポジション） | 戦略別の累積PnL・ポジション・予測値 | 警告表示 |
| 銘柄別時系列（資産曲線・ポジション） | 銘柄別の累積PnL・ポジション・予測値 | 「データなし」表示 |
| パラメータ | ハイパーパラメータの JSON 表示 | 警告表示 |
| コード | 実験コードのシンタックスハイライト表示 | 警告表示 |
| サマリレポート | サマリレポートのMarkdownプレビュー | 案内表示 |

パラメータ・コード・サマリレポートの3タブは、closedなファイルしか無く閲覧権限が無い場合、「🔒 ログインが必要です」という案内を表示する（ファイルの存在自体を隠す。fail-closed）。

---

### 4.3. 統計メトリクスタブ

#### 期間選択（ウォークフォワード等、`period_start`/`period_end`がある場合のみ）

- `stats_metrics/strategy`（無ければ`individual`）に`period_start`/`period_end`があれば、タブ内にセレクトボックスを表示し、その一意な組み合わせを期間一覧として選べる（ラベルは`{period_start} 〜 {period_end}`、`period_start`昇順）。デフォルトは最新（最後）の期間
- 選択した期間で、サイドバーのベストエポック判定設定（4.1節）が対象とするデータが絞り込まれる（ベストエポックは各期間に1対1で紐づくため、期間を選ばずに全期間まとめて判定すると意味を成さない）。判定設定のセレクトボックス自体はサイドバーにあり、統計メトリクス・戦略時系列・銘柄別時系列の全タブで共通のベストエポックとして使われる
- 戦略時系列タブ・銘柄別時系列タブには「どの期間を表示するか」という絞り込みの概念自体が無く、常に全期間を対象に表示する（期間を跨いだ表示が目的の別タブに、本タブの期間選択を持ち込むと意味が繋がらない）。ただし各期間ごとのベストエポック（best_epoch_by_period）は共通して使い、両タブの期間ごとのエポック選択セレクトボックスのデフォルト値になる（4.4/4.5節参照）
- `period_start`/`period_end`が無い実験では、このUI自体が表示されず、今まで通り全epochが対象になる

#### グラフ

- **縦方向**: メトリクスごとにグラフを分ける
- **横方向**: split ごとにグラフを並べる
- split はチェックボックスで表示/非表示を選択（デフォルト: `train`のみ非選択、他は全選択）
- 各 strategy_name は同一グラフ内に複数トレースとして描画
- ベンチマーク戦略はセレクトボックスで選択可能（選択なし可）。選択された系列は赤色・太線で強調表示
  - デフォルト選択: `strategy_name` が `bm_` で始まる戦略のうち最初のもの（存在しない場合は選択なし）
- ベストエポックの位置に破線縦線を表示

#### 表

- **describe() などの集計ではなく生データを表示**
- index: epoch（重複なし）
- split ごとに別テーブルとして横並びに表示（チェックボックスで選択可能、デフォルト: `train`のみ非選択、他は全選択）
- 各split列内では、strategy_name毎にさらに別テーブルとして縦に並べる（横持ち化はしない。カラムはmetric_colsそのまま）

---

### 4.4. 戦略時系列タブ

- `period_start`/`period_end`が無い場合: エポック選択セレクトボックスを1つ表示（デフォルト: サイドバーのベストエポック）
- `period_start`/`period_end`がある場合: **期間ごとに個別のエポック選択セレクトボックスを横並びで表示する**（ベストエポックは各期間に1対1で紐づき、期間によって異なりうるため、単一のエポック選択を全期間へ一律適用するのは不適切。各セレクトボックスのラベルは`{period_start} 〜 {period_end} (best:N)`、デフォルトはその期間自身のベストエポック）。期間そのものによる絞り込み（どの期間を表示するか）は行わず、常に全期間を対象に表示する（4.3参照）
- split チェックボックス（横並び、デフォルト: `train`のみ非選択、他は全選択）
- 選択エポックのデータを split ごとに横並びグラフで表示
- 表示する値:
  - 累積リターン（`pnl` が存在する場合）
  - 累積損益・絶対値（`pnl_abs` が存在する場合）
  - ポジション時系列（`position` が存在する場合）
  - 予測値時系列（`pred` が存在する場合）
- 各グラフ内で strategy_name を色分けして重ねて表示
- **期間アウェアな描画（`period_start`/`period_end`がある場合のみ）**: `test`以外のsplit（`train`/`val`等）は期間間で日時が重複しうるため、期間ごとに別トレースへ分けて同一グラフに重ねる（トレース名に期間開始日を付与）。`test`は期間を跨いで重複が無い前提で日時順に連結してから単一トレースにまとめ、その連結後の系列に対して累積（cumsum）を計算する

---

### 4.5. 銘柄別時系列タブ

- `pnl_pred_position/ticker` データがない場合は「データなし」を表示してタブ終了
- **「グラフを表示する」チェックボックス（デフォルトOFF）**: 銘柄数が多いとダウンロード・描画が重いため、チェックを入れるまではデータの読み込み自体を行わない（チェックボックスより後ろの処理は一切実行されない）
- チェックを入れた場合のみ、以下を表示:
  - エポック選択セレクトボックス（`period_start`/`period_end`が無ければ1つ、あれば期間ごとに個別。戦略時系列タブと同じ方式）
  - split チェックボックス（横並び、デフォルト: `train`のみ非選択、他は全選択）
  - ticker マルチセレクト（デフォルト: 全選択）
  - 累積リターン（`pnl` が存在する場合）
  - 累積損益・絶対値（`pnl_abs` が存在する場合）
  - ポジション時系列（`position` が存在する場合）
  - 予測値時系列（`pred` が存在する場合）
  - 各グラフ内で選択 ticker を色分けして重ねて表示、split ごとに横並び
  - 期間アウェアな描画は4.4節の戦略時系列タブと同じ方式（`test`以外は期間毎に別トレース、`test`は連結後cumsum）

---

### 4.6. パラメータタブ

- `params/` 配下のopen（+ログイン済みならclosedも）なファイルを列挙
- ファイルが1つの場合はそのまま表示、複数の場合はセレクトボックスで選択
- 選択したファイルをJSON形式で表示
- 閲覧可能なファイルが無い場合は警告（またはログイン案内）を表示

---

### 4.7. コードタブ

- `codes/` 配下のopen（+ログイン済みならclosedも）なファイルを列挙
- ファイルが1つの場合はそのまま表示、複数の場合はセレクトボックスで選択
- 拡張子に応じてシンタックスハイライト（`.py` → Python, `.yaml` → YAML 等）
- 閲覧可能なファイルが無い場合は警告（またはログイン案内）を表示

---

### 4.8. サマリレポートタブ

- `report/` 配下のopen（+ログイン済みならclosedも）なファイルを列挙
- ファイルが1つの場合はそのまま表示、複数の場合はセレクトボックスで選択
- 選択したファイルをMarkdownとしてプレビュー表示（`st.markdown()`）
- 閲覧可能なファイルが無い場合は案内を表示

---

## 5. ストレージ・実行環境

### 5.1. ローカル / GCS 切り替え

`bt_log_vis_tool/storage.py`の`AnyPath`（`universal_pathlib.UPath`）により、`ExperimentSaver`/`ExperimentLoader`とも`base_dir`にローカルパスと`gs://bucket/prefix`形式のGCSパスのどちらも透過的に渡せる。ダッシュボード側はサイドバーの「データソース」選択で切り替える（ローカル実行時のみ選択可、Cloud Run上ではGCS固定）。

### 5.2. キャッシュ

ダッシュボードの主要なデータ読み込み（`stats_metrics`系・`pnl_pred_position`系・メタデータ・データ型一覧）は`@st.cache_data`でキャッシュされる（TTL 24時間、キー毎最大8件のLRU）。Streamlitはウィジェット操作の度にスクリプト全体を再実行するため、無関係な操作でも毎回GCSから再ダウンロードしないようにするための措置。実験結果は保存後に更新されない運用を前提としている。

### 5.3. Cloud Run実行時の環境変数

| 環境変数 | 用途 |
|---|---|
| `K_SERVICE` | Cloud Runが自動設定。存在すればクラウド実行と判定し、データソース選択肢からローカルを隠す |
| `GCS_BASE_DIR` | 設定されていれば、GCSパス入力欄のデフォルト値として使う |

---

## 6. 関連ドキュメント

- [docs/deploy.md](deploy.md) — GCP Cloud Runへのデプロイ手順（Terraform, Docker, Google OAuth設定, 許可リスト運用）
