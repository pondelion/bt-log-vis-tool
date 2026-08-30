"""認証・許可リスト管理モジュール

クラウド(GCS)データソース使用時のみ有効なログインゲート。
ローカルデータソース使用時はこのモジュールは呼び出されない（今まで通り無認証・フル公開）。

ログイン自体はStreamlitのネイティブOIDC認証（st.login/st.user/st.logout、Googleを
[auth]セクションでデフォルトプロバイダとして設定）を使う。

当初はGoogleのOAuth同意画面をTesting状態＋Test Usersのみに限定することで
「管理者発行アカウントのみ」を実現する設計だったが、実際にはTest User未登録の
アカウントでもログインできてしまうことを確認した（非機密スコープ(openid/email/profile)
のみの場合、Google側のTesting/Test Users制限が有効に機能しないと見られる）。
そのため、Google側の設定には依存せず、**アプリ側の許可リスト**（_admin/allowlist.yaml）
を実効的なアクセス制御として使う。

許可リストの読み込みに失敗した場合は必ず「非許可」に倒す（fail-closed）。

許可リストは`base_dir`（実験名一覧を走査する場所）の**外**、バケットルート直下の
`_admin/allowlist.yaml`に置く。base_dir配下に置くと、ExperimentLoader.list_experiments()が
`_admin`を実験名として誤検出してしまう（実際に事故った）ため。
"""

from dataclasses import dataclass

import streamlit as st
import yaml

from bt_log_vis_tool.storage import AnyPath

ALLOWLIST_RELATIVE_PATH = "_admin/allowlist.yaml"


def _bucket_root(base_dir: str) -> str:
    """base_dirからGCSバケットルート（gs://bucket-name）を取り出す

    Args:
        base_dir: 実験データのベースディレクトリ（例: "gs://my-bucket/backtest_experiments/results"）

    Returns:
        バケットルート（例: "gs://my-bucket"）。gs://で始まらない場合はbase_dirをそのまま返す
    """
    if not base_dir.startswith("gs://"):
        return base_dir
    bucket_name = base_dir[len("gs://") :].split("/", 1)[0]
    return f"gs://{bucket_name}"


@dataclass
class AuthState:
    """認証状態

    Attributes:
        is_logged_in: Googleログイン済みか（本人確認のみ、認可は別）
        email: ログイン済みの場合のメールアドレス
        is_authorized: ログイン済みかつ許可リストに存在する場合のみTrue
                       （closedコンテンツを見せてよいかの判定に使う）
    """

    is_logged_in: bool
    email: str | None
    is_authorized: bool


def _load_allowlist(base_dir: str) -> set[str] | None:
    """許可emailの集合を読み込む

    Args:
        base_dir: 実験データのベースディレクトリ（許可リストはこのバケットのルート直下の
                  _admin/allowlist.yamlから読む。base_dir配下ではない点に注意）

    Returns:
        許可email（小文字化）の集合。読み込みに失敗した場合はNone（fail-closed用の区別）
    """
    allowlist_path = AnyPath(_bucket_root(base_dir)).expanduser() / ALLOWLIST_RELATIVE_PATH
    try:
        if not allowlist_path.exists():
            return None
        with allowlist_path.open() as f:
            data = yaml.safe_load(f) or {}
        emails = data.get("allowed_emails", [])
        return {e.strip().lower() for e in emails if isinstance(e, str) and e.strip()}
    except Exception:
        return None


def is_authorized(email: str | None, allowlist: set[str] | None) -> bool:
    """emailが許可リストに含まれるか判定する純粋ロジック（UI/Streamlitに非依存）

    バックエンド実装への移行時にそのまま流用できるよう、Streamlitのセッション状態や
    I/Oから切り離してある（許可リストの読み込みは_load_allowlist()側の責務）。

    Args:
        email: 判定対象のメールアドレス
        allowlist: _load_allowlist()が返す許可email集合

    Returns:
        許可されている場合True。allowlistがNone（読み込み失敗）またはemail未所属ならFalse（fail-closed）
    """
    if allowlist is None or email is None:
        return False
    return email.lower() in allowlist


def render_auth_sidebar(base_dir: str) -> AuthState:
    """クラウドデータソース用の認証UIをサイドバーに描画し、認証状態を返す

    Args:
        base_dir: 実験データのベースディレクトリ（GCSパス想定）

    Returns:
        AuthState。認証設定が無い/許可リストが読めない等のエラー時は
        is_authorized=Falseに倒す（fail-closed）。
    """
    st.sidebar.divider()
    st.sidebar.subheader("ログイン")

    try:
        is_logged_in = bool(st.user.is_logged_in)
    except Exception:
        st.sidebar.error("認証設定が見つかりません。.streamlit/secrets.tomlの[auth]セクションを設定してください。")
        return AuthState(is_logged_in=False, email=None, is_authorized=False)

    if not is_logged_in:
        st.sidebar.caption("openなデータはログイン不要で閲覧できます。closedなデータを見るにはログインが必要です。")
        if st.sidebar.button("Googleでログイン"):
            st.login()
        return AuthState(is_logged_in=False, email=None, is_authorized=False)

    email = st.user.email
    allowlist = _load_allowlist(base_dir)
    authorized = is_authorized(email, allowlist)

    if allowlist is None:
        st.sidebar.warning(f"{email} としてログイン済みですが、許可リストを読み込めませんでした。closedデータは表示されません。")
    elif not authorized:
        st.sidebar.warning(f"{email} はアクセス権がありません。管理者に連絡してください。")
    else:
        st.sidebar.success(f"{email} としてログイン中")

    if st.sidebar.button("ログアウト"):
        st.logout()

    return AuthState(is_logged_in=True, email=email, is_authorized=authorized)
