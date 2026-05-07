"""M2 (2026-05-07) — local perf-baseline regression checks.

Frozen synthetic 5k-artist corpus. Per-stage millisecond budgets that fail
loud if a refactor regresses an O(n) hotspot to O(n log n) or O(n²) — the
class of bug the eval harness wouldn't surface (eval runs use the real
corpus and the per-run variance hides single-stage regressions).

Marked ``@pytest.mark.perf`` so the default test suite skips them. Run on
demand::

    python -m pytest core/tests/test_perf_baseline.py -m perf -v

Budgets are conservative — each is roughly 5× the wall-clock observed on
the dev machine on 2026-05-07 with Python 3.13 on Windows. They exist to
catch *order-of-magnitude* regressions, not to enforce micro-budgets.
"""

from __future__ import annotations

import random
import time
from dataclasses import replace

import pytest

from core.src.rag.corpus import ArtistRow, RagCorpus
from core.src.rag.retrieval import retrieve_candidates


pytestmark = pytest.mark.perf


_CORPUS_SIZE = 5_000


def _build_synthetic_corpus(n: int = _CORPUS_SIZE) -> list[ArtistRow]:
    """Generate a deterministic *n*-artist corpus.

    Tag vocabulary mirrors the real corpus's coarse shape (~120 distinct
    tags, Zipf-ish frequency, ~3 tags per artist). Last.fm listener data
    populated on ~80 % of rows so the precedence path is exercised.
    """
    rng = random.Random(20260507)
    tags_pool = [
        f"tag_{i:03d}" for i in range(120)
    ]
    artists: list[ArtistRow] = []
    for i in range(n):
        n_tags = rng.choice([2, 3, 3, 4])
        # Zipf-bias the picks so a few tags dominate (matches reality).
        picks = rng.sample(tags_pool[: max(40, n_tags * 8)], n_tags)
        weights = [rng.randint(30, 100) for _ in picks]
        has_lfm = rng.random() < 0.80
        artists.append(
            ArtistRow(
                mbid=f"mbid-{i:06d}",
                name=f"Artist {i:05d}",
                sort_name=f"Artist {i:05d}",
                country=rng.choice(["US", "GB", "DE", "JP", "BR", ""]),
                begin_year=rng.randint(1965, 2020),
                tags=list(picks),
                tag_weights=list(weights),
                listener_popularity=rng.random(),
                lastfm_listeners=(rng.randint(50, 5_000_000) if has_lfm else None),
                lastfm_playcount=(rng.randint(1_000, 200_000_000) if has_lfm else None),
                lastfm_tags=list(picks[:2]),
                lastfm_tag_weights=[rng.randint(50, 100) for _ in picks[:2]],
            )
        )
    return artists


@pytest.fixture(scope="module")
def synthetic_corpus() -> RagCorpus:
    return RagCorpus(_build_synthetic_corpus(_CORPUS_SIZE))


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


class TestPerfBaseline:
    """Per-stage budgets. Increase only after a deliberate trade-off."""

    def test_index_build_under_budget(self):
        # Construction runs ``_build_indices`` once; covers the inverted
        # tag index + TF-IDF pass (the O(n × tags-per-row) hotspot).
        artists = _build_synthetic_corpus(_CORPUS_SIZE)
        t0 = time.perf_counter()
        RagCorpus(artists)
        elapsed = _ms(t0)
        assert elapsed < 1500.0, (
            f"_build_indices on {_CORPUS_SIZE} rows took {elapsed:.1f}ms "
            f"(budget 1500ms). Likely an O(n²) regression."
        )

    def test_retrieve_candidates_under_budget(self, synthetic_corpus):
        profile = {
            "preferences": {
                "user_prose": "moody synthwave with retrowave influences",
                "tags": ["tag_001", "tag_002", "tag_005"],
                "avoid": ["tag_099"],
            },
            "history": {"confirmed": [], "rejected": []},
        }
        # Warm up — first call may JIT-touch caches.
        retrieve_candidates(synthetic_corpus, profile, target_size=50)

        t0 = time.perf_counter()
        for _ in range(3):
            retrieve_candidates(synthetic_corpus, profile, target_size=50)
        avg = _ms(t0) / 3.0
        assert avg < 600.0, (
            f"retrieve_candidates avg {avg:.1f}ms (budget 600ms). "
            f"Stage 1 retrieval is on the user-perceived critical path — "
            f"check for accidental O(n²) on the candidate pool."
        )

    def test_artist_popularity_hot_path_under_budget(self, synthetic_corpus):
        # Popularity scoring is called inside the candidate pool sort; a
        # regression here cascades through every retrieval call.
        from core.src.rag.retrieval import _artist_popularity

        artists = synthetic_corpus.artists
        t0 = time.perf_counter()
        for _ in range(20):
            for a in artists:
                _artist_popularity(a)
        elapsed = _ms(t0)
        # 20 × 5k = 100k calls; budget is loose because the function is
        # O(1) per call — this catches a regression to repeated math
        # imports or attribute lookups in a hot inner loop.
        assert elapsed < 800.0, (
            f"100k _artist_popularity calls took {elapsed:.1f}ms "
            f"(budget 800ms). Likely a per-call import or attr-lookup "
            f"regression."
        )
