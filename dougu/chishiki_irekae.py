#!/usr/bin/env python3
"""大きな知識DBを安全に準備・切替・復帰する。元DBは junbi 中に変更しない。"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import sqlite3
import sys
from pathlib import Path


def _progress(status, remaining, total):
    done = total - remaining
    print(f"複写: {done:,}/{total:,} pages ({100 * done // max(total, 1)}%)", flush=True)


def _connect(path, readonly=False):
    path = Path(path).resolve()
    uri = f"file:{path.as_posix()}?mode=ro" if readonly else str(path)
    return sqlite3.connect(uri, uri=readonly, timeout=60)


def _prepare_indexes(db):
    db.execute("CREATE TABLE IF NOT EXISTS chishiki_meta(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS tsunagari(moto TEXT NOT NULL,saki TEXT NOT NULL,shurui TEXT NOT NULL,UNIQUE(moto,saki,shurui))")
    db.execute("CREATE TABLE IF NOT EXISTS daimei(title TEXT PRIMARY KEY,id INTEGER NOT NULL)")
    db.execute("INSERT OR IGNORE INTO daimei(title,id) SELECT title,rowid FROM chishiki")
    db.execute("CREATE INDEX IF NOT EXISTS tsunagari_saki ON tsunagari(saki)")
    for key, value in (("枝再構築", "1"), ("取り直し不要", "1"), ("題索引", "1")):
        db.execute("INSERT OR REPLACE INTO chishiki_meta(k,v) VALUES(?,?)", (key, value))
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daimei_trigram'").fetchone() is None:
        try:
            db.execute("CREATE VIRTUAL TABLE daimei_trigram USING fts5(title, tokenize='trigram')")
            db.execute("INSERT INTO daimei_trigram(rowid,title) SELECT id,title FROM daimei")
        except sqlite3.OperationalError:
            pass


def junbi(source, production):
    source, production = Path(source).resolve(), Path(production).resolve()
    stage = Path(str(production) + ".irekae")
    if not source.is_file() or not production.parent.is_dir():
        raise FileNotFoundError("新旧DBと本番フォルダを確認してください")
    if stage.exists():
        raise FileExistsError(f"準備先が既にあります: {stage}")
    print(f"準備: {source} → {stage}", flush=True)
    try:
        with _connect(source, readonly=True) as src, sqlite3.connect(stage, timeout=60) as dst:
            src.backup(dst, pages=4096, progress=_progress)
            _prepare_indexes(dst)
        print(f"準備完了: {stage} ({stage.stat().st_size:,} bytes)", flush=True)
    except Exception:
        stage.unlink(missing_ok=True)
        raise
    return stage


def _server_running():
    """カーネルの server.py（窓の裏）が動いているか。8080 は llama-server なので見ない。"""
    import subprocess
    out = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True).stdout
    # 10/5: 文字列の部分一致だと、"server.py" を含むシェルのコマンド自体に当たった。最初の語が Python のものだけ見る。
    for line in out.splitlines():
        words = line.split()
        if len(words) >= 2 and Path(words[0]).name.lower().startswith("python") and Path(words[1]).name == "server.py":
            return True
    return False


def _merge_table(db, table, conflict="IGNORE"):
    source = db.execute("SELECT sql FROM old.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not source:
        return
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not exists:
        db.execute(source[0])
    columns = [r[1] for r in db.execute(f"PRAGMA old.table_info([{table}])")]
    col_sql = ",".join('"' + col.replace('"', '""') + '"' for col in columns)
    db.execute(f"INSERT OR {conflict} INTO main.[{table}]({col_sql}) SELECT {col_sql} FROM old.[{table}]")


def _merge_teian(db):
    source = db.execute("SELECT sql FROM old.sqlite_master WHERE type='table' AND name='teian'").fetchone()
    if not source:
        return
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='teian'").fetchone():
        db.execute(source[0])
    old_cols = [r[1] for r in db.execute("PRAGMA old.table_info(teian)")]
    new_cols = {r[1] for r in db.execute("PRAGMA main.table_info(teian)")}
    columns = [name for name in old_cols if name in new_cols]
    quoted = ",".join('"' + col.replace('"', '""') + '"' for col in columns)
    rows = db.execute(f"SELECT {quoted} FROM old.teian").fetchall()
    if "id" not in columns:
        db.execute(f"INSERT OR REPLACE INTO main.teian({quoted}) SELECT {quoted} FROM old.teian")
        return
    offset = columns.index("id")
    for row in rows:
        exists = db.execute("SELECT 1 FROM main.teian WHERE id=?", (row[offset],)).fetchone()
        if not exists:
            db.execute(f"INSERT INTO main.teian({quoted}) VALUES({','.join('?' for _ in row)})", row)
        else:
            values = db.execute(f"SELECT {quoted} FROM main.teian WHERE id=?", (row[offset],)).fetchone()
            if values != row:
                other_cols = [c for c in columns if c != "id"]
                other_quoted = ",".join('"' + col.replace('"', '""') + '"' for col in other_cols)
                other_values = tuple(value for name, value in zip(columns, row) if name != "id")
                db.execute(f"INSERT INTO main.teian({other_quoted}) VALUES({','.join('?' for _ in other_values)})", other_values)


def _merge_data(stage, production):
    db = sqlite3.connect(f"file:{Path(stage).resolve().as_posix()}?mode=rw", uri=True, timeout=60)
    try:
        old_uri = f"file:{Path(production).resolve().as_posix()}?mode=ro"
        db.execute("ATTACH DATABASE ? AS old", (old_uri,))
        old_tables = {r[0] for r in db.execute("SELECT name FROM old.sqlite_master WHERE type='table'")}
        _merge_table(db, "nooto", "REPLACE")
        _merge_teian(db)
        if "chishiki" in old_tables:
            old_cols = [r[1] for r in db.execute("PRAGMA old.table_info(chishiki)")]
            cols = ",".join('"' + col.replace('"', '""') + '"' for col in old_cols)
            rows = db.execute(f"SELECT {cols} FROM old.chishiki").fetchall()
            for row in rows:
                title = row[0]
                if db.execute("SELECT 1 FROM daimei WHERE title=?", (title,)).fetchone():
                    continue
                cur = db.execute(f"INSERT INTO chishiki({cols}) VALUES({','.join('?' for _ in row)})", row)
                rid = cur.lastrowid
                db.execute("INSERT INTO daimei(title,id) VALUES(?,?)", (title, rid))
                source = row[2] if len(row) > 2 else ""
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chishiki_trigram'").fetchone():
                    db.execute("INSERT INTO chishiki_trigram(rowid,title,text,source) VALUES(?,?,?,?)", (rid, row[0], row[1], source))
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daimei_trigram'").fetchone():
                    db.execute("INSERT INTO daimei_trigram(rowid,title) VALUES(?,?)", (rid, title))
                if rid % 500 == 0:
                    print(f"記事を補完: {rid:,}", flush=True)
        _merge_table(db, "tsunagari", "IGNORE")
        _prepare_indexes(db)
        db.commit()
    finally:
        db.close()


def _sidecars(path):
    path = Path(path)
    return [Path(str(path) + suffix) for suffix in ("", "-wal", "-shm")]


def _move_sidecars(source, destination):
    for suffix in ("", "-wal", "-shm"):
        src, dst = Path(str(source) + suffix), Path(str(destination) + suffix)
        if src.exists():
            os.replace(src, dst)


def i_rekae(production):
    production = Path(production).resolve()
    stage = Path(str(production) + ".irekae")
    backup = Path(str(production) + ".mae_1005")
    if _server_running():
        raise RuntimeError("server.py が動作中のため中止しました")
    if not stage.is_file():
        raise FileNotFoundError(f"準備DBがありません: {stage}")
    if backup.exists():
        raise FileExistsError(f"退避先が既にあります: {backup}")
    print("古いDBの不足記事・ノート・提案・枝を取り込みます", flush=True)
    _merge_data(stage, production)
    with sqlite3.connect(stage, timeout=60) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        size = sum(p.stat().st_size for p in _sidecars(stage) if p.exists())
        db.execute("INSERT OR REPLACE INTO chishiki_meta(k,v) VALUES('取り込み時の大きさ',?)", (str(size),))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    try:
        _move_sidecars(production, backup)
        _move_sidecars(stage, production)
    except Exception:
        if not production.exists() and backup.exists():
            _move_sidecars(backup, production)
        raise
    print(f"切替完了: {production} / 旧版保存: {backup}", flush=True)
    return production


def modosu(production):
    production = Path(production).resolve()
    backup = Path(str(production) + ".mae_1005")
    failed = Path(str(production) + ".irekae_shippai")
    if not backup.is_file():
        raise FileNotFoundError(f"旧DBの退避がありません: {backup}")
    if _server_running():
        raise RuntimeError("server.py が動作中のため復帰を中止しました")
    if failed.exists():
        raise FileExistsError(f"失敗DBの保存先が既にあります: {failed}")
    _move_sidecars(production, failed)
    _move_sidecars(backup, production)
    print(f"復帰完了: {production} / 切替後DB保存: {failed}", flush=True)
    return production


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("junbi")
    prepare.add_argument("new_db")
    prepare.add_argument("production_db")
    switch = sub.add_parser("irekae")
    switch.add_argument("production_db")
    restore = sub.add_parser("modosu")
    restore.add_argument("production_db")
    args = parser.parse_args(argv)
    if args.command == "junbi":
        junbi(args.new_db, args.production_db)
    elif args.command == "irekae":
        i_rekae(args.production_db)
    else:
        modosu(args.production_db)


if __name__ == "__main__":
    main()
