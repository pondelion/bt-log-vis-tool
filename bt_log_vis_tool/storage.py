"""ストレージ抽象化モジュール

ローカルファイルシステムとGCS（`gs://bucket/prefix`）を同じAPIで扱うための薄いラッパー。
`upath.UPath`は`pathlib.Path`互換のインターフェースをfsspec経由で提供するため、
ローカル/GCSどちらのパスも同じコードで扱える。

使い方: `pathlib.Path`の代わりに`AnyPath`を使うだけでよい。
GCS利用時は`AnyPath("gs://bucket/prefix")`のように渡す（実際のGCSアクセスは
Application Default Credentials経由。鍵ファイルはコード側で扱わない）。
"""

from upath import UPath as AnyPath

__all__ = ["AnyPath"]
