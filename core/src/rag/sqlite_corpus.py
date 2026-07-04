"""On-disk SQLite corpus — the "installed" corpus for packaged runtimes.

The in-memory :class:`RagCorpus` re-parses a ~180k-artist ``.jsonl.gz`` and
rebuilds an inverted index on every launch (~6-9s). Packaged apps (the Windows
EXE and the macOS/Linux wheel) instead build this SQLite database once and then
open it in ~20ms on every subsequent launch.

Layout::

    tags(tag PK, idf, idxs BLOB, ws BLOB)   -- posting list + PRECOMPUTED weights
    artists(idx PK, blob)                   -- zlib(pickle(ArtistRow)), lazy-fetched
    names(nkey PK, idx) / mbids(mbid PK, idx)
    aliases(k PK, v)
    meta(key PK, value)                     -- schema version + source signature

Every lookup key is a PRIMARY KEY, so SQLite maintains a B-tree index on it and
lookups are O(log n). The posting ``idxs``/``ws`` blobs are packed ``array('i')``
(int32) — the DB is built on the user's own machine, so native endianness is
consistent between build and read.

Design mirror of :meth:`RagCorpus.postings`: the scoring hot loop reads only the
precomputed ``(idf, idxs, weights)`` per tag — no ArtistRow is materialised until
the small rerank pool. See ``core/src/rag/retrieval.py``.

Stability notes:
- Read-only, thread-local connections (Flask serves requests on many threads;
  a single sqlite3 connection is not safe for concurrent use).
- Callers fall back to the in-memory corpus on ANY error here (see
  ``app._load_rag_corpus_if_enabled``), so a corrupt/locked DB never breaks boot.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pickle
import sqlite3
import threading
import zlib
from array import array
from pathlib import Path

from .corpus import ArtistRow, RagCorpus, normalise_tag

logger = logging.getLogger(__name__)

# Bump when the DB layout, the ArtistRow schema, or the posting-weight semantics
# change — any stored DB with a different version is treated as stale and rebuilt.
_SCHEMA_VERSION = 1

# Input files whose contents affect the built corpus. The overlays live beside
# the corpus file (auto-detected by RagCorpus.load); include them in the
# signature so an overlay refresh invalidates the DB.
_OVERLAY_NAMES = ("top_tracks_overlay.json", "ai_tags_overlay.json")


# Files at or below this size are signed by content hash rather than mtime.
# The tag-alias map is bundled in the EXE and re-extracted to a fresh temp dir
# on every launch, so its mtime is volatile even though its content is stable —
# hashing keeps the signature (and thus the cached DB) stable across launches.
# The large corpus/overlays live in the user data dir with stable mtimes, so we
# avoid hashing 100+ MB on every startup.
_HASH_MAX_BYTES = 2_000_000


def _file_signature(p: Path) -> str:
    """Size + (content hash for small files | mtime for large files)."""
    try:
        st = p.stat()
    except OSError:
        return f"{p.name}:-"
    if st.st_size <= _HASH_MAX_BYTES:
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            return f"{p.name}:{st.st_size}:{digest}"
        except OSError:
            return f"{p.name}:-"
    return f"{p.name}:{st.st_size}:{st.st_mtime_ns}"


def corpus_signature(corpus_path, aliases_path=None) -> str:
    """Return a signature over every input that affects the built corpus.

    Combines the schema version with each input file's identity (see
    :func:`_file_signature`). If any input changes (corpus refresh, overlay
    update, aliases edit), the signature changes and the DB is rebuilt.
    """
    corpus_path = Path(corpus_path)
    parts = [f"v{_SCHEMA_VERSION}"]
    paths = [corpus_path]
    if aliases_path:
        paths.append(Path(aliases_path))
    paths.extend(corpus_path.parent / name for name in _OVERLAY_NAMES)
    return "|".join([parts[0]] + [_file_signature(p) for p in paths])


def is_sqlite_corpus_valid(db_path, signature: str) -> bool:
    """True if *db_path* exists and its stored signature matches *signature*."""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
        finally:
            con.close()
        return bool(row) and row[0] == signature
    except sqlite3.Error:
        return False


def build_sqlite_corpus(ram: RagCorpus, db_path, signature: str) -> None:
    """Build the SQLite corpus from an in-memory :class:`RagCorpus`.

    Writes to a temp file and atomically renames, so a crash (or the
    single-instance kill) never leaves a half-built DB in place.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    con = sqlite3.connect(str(tmp))
    try:
        con.execute("PRAGMA journal_mode=OFF")
        con.execute("PRAGMA synchronous=OFF")
        con.executescript(
            """
            CREATE TABLE tags(tag TEXT PRIMARY KEY, idf REAL, idxs BLOB, ws BLOB);
            CREATE TABLE artists(idx INTEGER PRIMARY KEY, blob BLOB);
            CREATE TABLE names(nkey TEXT PRIMARY KEY, idx INTEGER);
            CREATE TABLE mbids(mbid TEXT PRIMARY KEY, idx INTEGER);
            CREATE TABLE aliases(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            """
        )

        def _tag_rows():
            for tag in ram.tag_index:
                idf, idxs, weights = ram.postings(tag)  # precomputed, exact
                yield (tag, float(idf),
                       array('i', idxs).tobytes(),
                       array('i', (int(w) for w in weights)).tobytes())

        con.executemany("INSERT INTO tags VALUES(?,?,?,?)", _tag_rows())
        con.executemany(
            "INSERT INTO artists VALUES(?,?)",
            ((i, zlib.compress(pickle.dumps(a, protocol=pickle.HIGHEST_PROTOCOL), 6))
             for i, a in enumerate(ram.artists)),
        )
        con.executemany("INSERT INTO names VALUES(?,?)", ram.by_name_normalised.items())
        con.executemany("INSERT INTO mbids VALUES(?,?)", ram.by_mbid.items())
        con.executemany("INSERT INTO aliases VALUES(?,?)", ram.aliases.items())
        con.executemany(
            "INSERT INTO meta VALUES(?,?)",
            [("signature", signature),
             ("count", str(len(ram.artists))),
             ("schema_version", str(_SCHEMA_VERSION))],
        )
        con.commit()
    finally:
        con.close()

    os.replace(tmp, db_path)
    logger.info("Built SQLite corpus: %d artists, %d tags -> %s (%.0f MB)",
                len(ram.artists), len(ram.tag_index), db_path,
                db_path.stat().st_size / 1e6)


# ── lazy views mimicking the RagCorpus dict/list attributes ──────────────

class _TagIndexView:
    """Lazy ``tag -> array('i')`` mapping. Supports the access patterns the
    retriever uses on ``corpus.tag_index``: ``in``, ``.get(tag, default)``."""

    def __init__(self, conn_getter):
        self._conn = conn_getter

    def __contains__(self, tag) -> bool:
        return self._conn().execute(
            "SELECT 1 FROM tags WHERE tag=?", (tag,)).fetchone() is not None

    def get(self, tag, default=None):
        row = self._conn().execute(
            "SELECT idxs FROM tags WHERE tag=?", (tag,)).fetchone()
        if row is None:
            return default
        a = array('i'); a.frombytes(row[0])
        return a

    def __len__(self) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM tags").fetchone()[0]


class _KeyToIntView:
    """Lazy ``key -> int`` mapping (tag_idf, by_name_normalised, by_mbid)."""

    def __init__(self, conn_getter, sql):
        self._conn = conn_getter
        self._sql = sql

    def get(self, key, default=None):
        row = self._conn().execute(self._sql, (key,)).fetchone()
        return row[0] if row is not None else default


class _ArtistsView:
    """Lazy random-access sequence of ArtistRow, backed by the artists table.

    Only the ~200-candidate rerank pool is ever materialised per retrieval, so
    a small per-thread cache keeps repeat accesses cheap without holding all
    180k rows in memory."""

    def __init__(self, conn_getter, count):
        self._conn = conn_getter
        self._count = count
        self._local = threading.local()

    def _cache(self):
        c = getattr(self._local, "cache", None)
        if c is None:
            c = self._local.cache = {}
        return c

    def __len__(self) -> int:
        return self._count

    def __bool__(self) -> bool:
        return self._count > 0

    def __getitem__(self, idx) -> ArtistRow:
        cache = self._cache()
        art = cache.get(idx)
        if art is None:
            row = self._conn().execute(
                "SELECT blob FROM artists WHERE idx=?", (int(idx),)).fetchone()
            if row is None:
                raise IndexError(idx)
            art = pickle.loads(zlib.decompress(row[0]))
            if len(cache) < 8192:
                cache[idx] = art
        return art


class SqliteCorpus:
    """Read-only, disk-backed corpus with the same surface the retriever and
    verifier use on :class:`RagCorpus` (``tag_index``, ``tag_idf``, ``artists``,
    ``by_name_normalised``, ``by_mbid``, ``resolve_alias``, ``postings``, ``len``).
    """

    def __init__(self, db_path, aliases, count):
        self._db_path = str(db_path)
        self._local = threading.local()
        self.aliases = aliases
        self._count = count
        self.tag_index = _TagIndexView(self._conn)
        self.tag_idf = _KeyToIntView(self._conn, "SELECT idf FROM tags WHERE tag=?")
        self.by_name_normalised = _KeyToIntView(self._conn, "SELECT idx FROM names WHERE nkey=?")
        self.by_mbid = _KeyToIntView(self._conn, "SELECT idx FROM mbids WHERE mbid=?")
        self.artists = _ArtistsView(self._conn, count)

    @classmethod
    def open(cls, db_path) -> "SqliteCorpus":
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            count = int(con.execute("SELECT value FROM meta WHERE key='count'").fetchone()[0])
            aliases = dict(con.execute("SELECT k, v FROM aliases"))
        finally:
            con.close()
        return cls(db_path, aliases, count)

    def _conn(self) -> sqlite3.Connection:
        """Return this thread's read-only connection (opened lazily)."""
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(f"file:{self._db_path}?mode=ro",
                                  uri=True, check_same_thread=False)
            con.execute("PRAGMA query_only=1")
            con.execute("PRAGMA mmap_size=268435456")  # 256 MB
            self._local.con = con
        return con

    def resolve_alias(self, tag: str) -> str:
        nt = normalise_tag(tag)
        return self.aliases.get(nt, nt)

    def postings(self, tag: str) -> tuple[float, "array", "array"]:
        row = self._conn().execute(
            "SELECT idf, idxs, ws FROM tags WHERE tag=?", (tag,)).fetchone()
        if row is None:
            return 1.0, array('i'), array('i')
        idf, ib, wb = row
        ia = array('i'); ia.frombytes(ib)
        wa = array('i'); wa.frombytes(wb)
        return idf, ia, wa

    def __len__(self) -> int:
        return self._count
