import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
import gakushuu
import kazoeru


def make_box(path, article):
    with sqlite3.connect(path) as db:
        db.execute("CREATE VIRTUAL TABLE chishiki USING fts5(title,text,source UNINDEXED,url UNINDEXED,added UNINDEXED)")
        db.execute("CREATE TABLE tsunagari(moto TEXT NOT NULL,saki TEXT NOT NULL,shurui TEXT NOT NULL,UNIQUE(moto,saki,shurui))")
        db.execute("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)", (article, article + " 本文", "test", "", "now"))


class BigKnowledgeTests(unittest.TestCase):
    def test_title_index_edges_and_refetch_skip(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": tmp}):
            with gakushuu._db() as db:
                for title, body in (("銀河系", "渦巻き星雲の本文"), ("青色星", "銀河系と宇宙の本文")):
                    cur = db.execute("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)", (title, body, "test", "", "now"))
                    db.execute("INSERT INTO daimei(title,id) VALUES(?,?)", (title, cur.lastrowid))
                    gakushuu._add_trigram(db, cur.lastrowid, title, body, "test")
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='daimei_trigram'").fetchone():
                        db.execute("INSERT INTO daimei_trigram(rowid,title) VALUES(?,?)", (cur.lastrowid, title))
                    gakushuu._add_article_edges(db, title, body)
                self.assertTrue(db.execute("SELECT 1 FROM tsunagari WHERE moto='青色星' AND saki='銀河系'").fetchone())
                self.assertTrue(db.execute("SELECT 1 FROM tsunagari WHERE moto='青色星' AND saki='銀河系' AND shurui='本文'").fetchone())
                db.execute("INSERT OR REPLACE INTO chishiki_meta(k,v) VALUES('取り直し不要','1')")
            self.assertEqual(gakushuu._names(), {"青色星", "銀河系"})
            self.assertFalse(gakushuu._refetch_one({}, object()))
            with gakushuu._db() as db:
                self.assertTrue(gakushuu._delete_article(db, "青色星"))
                self.assertFalse(db.execute("SELECT 1 FROM daimei WHERE title='青色星'").fetchone())
                self.assertFalse(db.execute("SELECT 1 FROM tsunagari WHERE moto='青色星' OR saki='青色星'").fetchone())

    def test_large_unmarked_box_gets_deferred_full_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": tmp}):
            with gakushuu._db() as db:
                db.executemany("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)",
                               ((f"題{i}", "本文", "test", "", "now") for i in range(20001)))
                db.execute("DELETE FROM chishiki_meta WHERE k='枝再構築'")
                gakushuu._ensure_knowledge_indexes(db)
                marker = db.execute("SELECT v FROM chishiki_meta WHERE k='枝再構築'").fetchone()[0]
                self.assertEqual(marker, "省略:20000超")

    def test_imported_bytes_are_not_charged_as_growth(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": tmp}):
            with gakushuu._db() as db:
                db.execute("INSERT OR REPLACE INTO chishiki_meta(k,v) VALUES('取り込み時の大きさ','999999999')")
            self.assertEqual(gakushuu.used_bytes(), 0)

    def test_count_or_calculation_signal_exists(self):
        self.assertTrue(kazoeru.aizu("このフォルダのファイルを何個数えて"))
        self.assertTrue(kazoeru.aizu("12 * 8 を計算して"))
        self.assertFalse(kazoeru.aizu("おはよう"))

    def test_prepare_switch_restore_round_trip(self):
        import importlib.util
        script = Path(__file__).resolve().parents[2] / "dougu" / "chishiki_irekae.py"
        spec = importlib.util.spec_from_file_location("chishiki_irekae_test", script)
        swap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(swap)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new, prod = root / "new.sqlite3", root / "chishiki.sqlite3"
            make_box(new, "新しい記事")
            make_box(prod, "古い記事")
            with sqlite3.connect(new) as db:
                db.execute("CREATE TABLE teian(id INTEGER PRIMARY KEY,題 TEXT)")
                db.execute("INSERT INTO teian VALUES(1,'新提案')")
            with sqlite3.connect(prod) as db:
                db.execute("CREATE TABLE nooto(title TEXT PRIMARY KEY,youten TEXT NOT NULL,omoshirosa INTEGER NOT NULL,tsunagari TEXT NOT NULL,model TEXT NOT NULL,added TEXT NOT NULL)")
                db.execute("INSERT INTO nooto VALUES('古い記事','要点',4,'枝','m','now')")
                db.execute("CREATE TABLE teian(id INTEGER PRIMARY KEY,題 TEXT)")
                db.execute("INSERT INTO teian VALUES(1,'提案')")
                db.execute("INSERT INTO tsunagari VALUES('古い記事','新しい記事','test')")
            swap.junbi(new, prod)
            with mock.patch.object(swap, "_server_running", return_value=False):
                swap.i_rekae(prod)
            with sqlite3.connect(prod) as db:
                titles = {row[0] for row in db.execute("SELECT title FROM chishiki")}
                self.assertEqual(titles, {"新しい記事", "古い記事"})
                self.assertEqual(db.execute("SELECT youten FROM nooto WHERE title='古い記事'").fetchone()[0], "要点")
                self.assertEqual({r[0] for r in db.execute("SELECT 題 FROM teian")}, {"新提案", "提案"})
                self.assertGreater(int(db.execute("SELECT v FROM chishiki_meta WHERE k='取り込み時の大きさ'").fetchone()[0]), 0)
            with mock.patch.object(swap, "_server_running", return_value=False):
                swap.modosu(prod)
            with sqlite3.connect(prod) as db:
                self.assertEqual(db.execute("SELECT title FROM chishiki").fetchone()[0], "古い記事")
            self.assertTrue(Path(str(prod) + ".irekae_shippai").is_file())


if __name__ == "__main__":
    unittest.main()
