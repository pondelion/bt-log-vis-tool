"""ディレクトリ構造ベースのopen/closed判定

設定ファイルは使わず、ディレクトリ構造だけで公開状態を判定する:
  <category>/open/<file...>    -> open
  <category>/closed/<file...>  -> closed
  <category>/<file...>         -> closed（サブディレクトリ未指定はfail-closedで非公開扱い）

全カテゴリ（codes, params, report）で共通のルール。カテゴリ毎のデフォルトは持たず、
必ず`open/`または`closed/`のどちらかに明示的に置く運用とする。
"""


def is_open(relative_path: str) -> bool:
    """相対パスから公開状態を判定

    Args:
        relative_path: カテゴリディレクトリからの相対パス（例: "open/x.py", "closed/x.py", "x.py"）

    Returns:
        先頭セグメントが"open"の場合のみTrue。それ以外（"closed"・サブディレクトリ未指定含む）はFalse
    """
    first_part = relative_path.split("/", 1)[0]
    return first_part == "open"
