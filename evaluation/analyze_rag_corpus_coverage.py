"""Analyze whether the RAG corpus covers evaluation scenarios.

Diagnostic only: no OpenAI/Spotify calls. It loads the same RagCorpus and
retrieval code used in production, extracts scenario tags, measures tag/avoid
coverage, and checks candidate pool sizes.

Usage:
    python evaluation/analyze_rag_corpus_coverage.py
    python evaluation/analyze_rag_corpus_coverage.py --json --output coverage.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

from core.src.rag.corpus import RagCorpus, normalise_tag  # noqa: E402
from core.src.rag.retrieval import (  # noqa: E402
    _apply_aliases,
    _avoid_traits_coverage,
    _build_facet_query,
    _extract_text_tokens,
    build_query_tags,
    retrieve_candidates,
    score_artists_stratified,
)
from evaluation.scenario import SCENARIOS, Scenario  # noqa: E402


MARKER_TAG_GROUPS = {
    "japanese_or_j_music": ["japanese", "japan", "j-pop", "j-rock"],
    "american": ["american", "american artists"],
    "80s": ["80s"],
    "classic_vintage_arena": ["classic rock", "vintage", "arena rock", "60s", "70s"],
    "electronic_edm_synthwave": ["electronic", "electronic music", "edm", "synthwave"],
    "theatrical_quirky": ["theatrical", "quirky"],
    "uplifting": ["uplifting"],
}


def pct(n: int | float, d: int | float) -> float:
    return 0.0 if not d else round(100.0 * float(n) / float(d), 2)


def split_section(text: str) -> list[str]:
    parts = [p.strip() for p in (text or "").replace("\n", ";").split(";")]
    return [p for p in parts if p]


def profile_from_sections(sections: dict[str, str]) -> dict[str, Any]:
    return {
        "preferences": {
            "core_description": sections.get("core_description", ""),
            "must_have": split_section(sections.get("must_have", "")),
            "soft_preferences": split_section(sections.get("soft_preferences", "")),
            "avoid": split_section(sections.get("avoid", "")),
        }
    }


def tag_freq(corpus: RagCorpus, tag: str) -> int:
    return len(corpus.tag_index.get(tag, ()))


def token_report(corpus: RagCorpus, raw_query: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for raw_tag, weight in sorted(raw_query.items(), key=lambda kv: (-kv[1], kv[0])):
        canon = corpus.resolve_alias(raw_tag)
        freq = tag_freq(corpus, canon)
        rows.append({
            "token": raw_tag,
            "canonical": canon,
            "weight": round(weight, 3),
            "artist_frequency": freq,
            "covered": freq > 0,
            "passes_production_min_frequency": freq >= (3 if len(corpus.artists) >= 100 else 1),
        })
    return rows


def item_coverage(corpus: RagCorpus, profile: dict[str, Any]) -> dict[str, Any]:
    prefs = profile.get("preferences", {}) or {}
    out = {}
    for field in ("core_description", "must_have", "soft_preferences", "avoid"):
        src = prefs.get(field)
        items = src if isinstance(src, list) else ([src] if src else [])
        field_rows = []
        for item in items:
            toks = []
            for tok in _extract_text_tokens(str(item)):
                canon = corpus.resolve_alias(normalise_tag(tok))
                freq = tag_freq(corpus, canon)
                toks.append({"token": tok, "canonical": canon, "artist_frequency": freq})
            covered = [t for t in toks if t["artist_frequency"] > 0]
            field_rows.append({"text": item, "covered_token_count": len(covered), "covered_tokens": covered})
        out[field] = field_rows
    return out


def artist_has_any_marker(artist, marker_tags: list[str]) -> bool:
    artist_tags = {normalise_tag(t) for t in artist.tags}
    artist_tags.update(normalise_tag(g) for g in artist.spotify_genres)
    return any(normalise_tag(tag) in artist_tags for tag in marker_tags)


def marker_counts(rows) -> dict[str, int]:
    return {
        label: sum(1 for artist in rows if artist_has_any_marker(artist, tags))
        for label, tags in MARKER_TAG_GROUPS.items()
    }


def corpus_report(corpus: RagCorpus) -> dict[str, Any]:
    tag_freqs = Counter({tag: len(rows) for tag, rows in corpus.tag_index.items()})
    special_terms = [
        "japanese", "japan", "j-pop", "j-rock", "anime", "anime soundtrack",
        "theatrical", "cinematic", "uplifting", "harmonized vocals",
        "american", "80s", "classic rock", "edm", "synthwave", "electronic",
    ]
    return {
        "artist_count": len(corpus.artists),
        "tag_count": len(corpus.tag_index),
        "spotify_enriched_artist_count": sum(1 for a in corpus.artists if a.spotify_id),
        "spotify_enriched_percent": pct(sum(1 for a in corpus.artists if a.spotify_id), len(corpus.artists)),
        "with_spotify_genres_count": sum(1 for a in corpus.artists if a.spotify_genres),
        "with_spotify_genres_percent": pct(sum(1 for a in corpus.artists if a.spotify_genres), len(corpus.artists)),
        "with_country_count": sum(1 for a in corpus.artists if a.country),
        "with_country_percent": pct(sum(1 for a in corpus.artists if a.country), len(corpus.artists)),
        "with_top_tracks_count": sum(1 for a in corpus.artists if a.top_tracks),
        "with_top_tracks_percent": pct(sum(1 for a in corpus.artists if a.top_tracks), len(corpus.artists)),
        "top_tags": [{"tag": t, "artist_frequency": f} for t, f in tag_freqs.most_common(40)],
        "special_term_frequencies": {
            term: tag_freq(corpus, corpus.resolve_alias(normalise_tag(term)))
            for term in special_terms
        },
    }


def scenario_report(corpus: RagCorpus, scenario: Scenario, targets: list[int]) -> dict[str, Any]:
    profile = profile_from_sections(scenario.seed_sections)
    primary_reference = {
        "name": scenario.analysis_artist,
        "analysis": f"{scenario.analysis_artist} {scenario.analysis_track}",
        "genres": [],
        "moods": [],
    }
    raw_query = build_query_tags(profile, primary_reference=primary_reference)
    mapped_query = _apply_aliases(corpus, raw_query)
    token_rows = token_report(corpus, raw_query)
    mapped_freqs = [tag_freq(corpus, t) for t in mapped_query]

    prefs = profile.get("preferences", {}) or {}
    facets = {}
    for facet in ("must_have", "soft_preferences", "primary_reference", "tags"):
        mapped = _apply_aliases(corpus, _build_facet_query(prefs, facet, primary_reference))
        union = set()
        for tag in mapped:
            union.update(corpus.tag_index.get(tag, ()))
        facets[facet] = {
            "mapped_token_count": len(mapped),
            "matching_artist_union": len(union),
            "tokens": [
                {"token": tag, "artist_frequency": tag_freq(corpus, tag)}
                for tag in sorted(mapped, key=lambda t: (-tag_freq(corpus, t), t))
            ],
        }

    avoid_tags, avoid_total, avoid_covered = _avoid_traits_coverage(corpus, profile)
    retrieval = {}
    for target in targets:
        rows = retrieve_candidates(corpus, profile, target_size=target, primary_reference=primary_reference)
        broad = score_artists_stratified(corpus, profile, pool_size=target * 3, primary_reference=primary_reference)
        retrieval[str(target)] = {
            "requested": target,
            "broad_pool_before_filters": len(broad),
            "returned_after_filters": len(rows),
            "marker_counts_after_filters": marker_counts(rows),
            "marker_counts_before_filters": marker_counts(broad),
            "top_artists_after_filters": [a.name for a in rows[:15]],
            "top_artists_before_filters": [a.name for a in broad[:15]],
        }

    return {
        "name": scenario.name,
        "description": scenario.description,
        "analysis_reference": {
            "artist": scenario.analysis_artist,
            "track": scenario.analysis_track,
            "artist_in_corpus": any(a.name.lower() == scenario.analysis_artist.lower() for a in corpus.artists),
        },
        "query": {
            "raw_token_count": len(raw_query),
            "mapped_token_count": len(mapped_query),
            "covered_raw_tokens": sum(1 for r in token_rows if r["covered"]),
            "covered_raw_token_percent": pct(sum(1 for r in token_rows if r["covered"]), len(token_rows)),
            "mapped_artist_frequency_min": min(mapped_freqs) if mapped_freqs else 0,
            "mapped_artist_frequency_median": statistics.median(mapped_freqs) if mapped_freqs else 0,
            "mapped_artist_frequency_max": max(mapped_freqs) if mapped_freqs else 0,
            "tokens": token_rows,
        },
        "fields": item_coverage(corpus, profile),
        "facets": facets,
        "avoid": {
            "traits_total": avoid_total,
            "traits_covered": avoid_covered,
            "traits_fully_covered": bool(avoid_total and avoid_total == avoid_covered),
            "resolved_avoid_tags": [
                {"tag": tag, "artist_frequency": tag_freq(corpus, tag)}
                for tag in sorted(avoid_tags, key=lambda t: (-tag_freq(corpus, t), t))
            ],
        },
        "retrieval": retrieval,
    }


def print_text(report: dict[str, Any]) -> None:
    c = report["corpus"]
    print("RAG corpus coverage analysis")
    print("=" * 72)
    print(f"Corpus: {report['corpus_path']}")
    print(
        f"Artists: {c['artist_count']:,} | tags: {c['tag_count']:,} | "
        f"Spotify enriched: {c['spotify_enriched_artist_count']:,} ({c['spotify_enriched_percent']}%) | "
        f"Spotify genres: {c['with_spotify_genres_count']:,} ({c['with_spotify_genres_percent']}%) | "
        f"country: {c['with_country_count']:,} ({c['with_country_percent']}%) | "
        f"top_tracks: {c['with_top_tracks_count']:,} ({c['with_top_tracks_percent']}%)"
    )
    print("\nSpecial term frequencies:")
    for term, freq in c["special_term_frequencies"].items():
        print(f"  {term:22s} {freq:6d}")

    for scn in report["scenarios"]:
        q = scn["query"]
        print("\n" + "-" * 72)
        print(f"Scenario: {scn['name']}")
        print(f"Query coverage: {q['covered_raw_tokens']}/{q['raw_token_count']} ({q['covered_raw_token_percent']}%), mapped={q['mapped_token_count']}")
        print(f"Mapped frequencies: min={q['mapped_artist_frequency_min']}, median={q['mapped_artist_frequency_median']}, max={q['mapped_artist_frequency_max']}")
        ref = scn["analysis_reference"]
        print(f"Reference in corpus: {ref['artist']} -> {ref['artist_in_corpus']}")
        a = scn["avoid"]
        print(f"Avoid coverage: {a['traits_covered']}/{a['traits_total']} fully_covered={a['traits_fully_covered']}")
        if a["resolved_avoid_tags"]:
            print("  Avoid tags: " + ", ".join(f"{x['tag']}({x['artist_frequency']})" for x in a["resolved_avoid_tags"][:12]))
        print("Facet support:")
        for facet, data in scn["facets"].items():
            print(f"  {facet:18s} tokens={data['mapped_token_count']:2d} artist_union={data['matching_artist_union']:5d}")
            if data["tokens"]:
                print("    " + ", ".join(f"{x['token']}({x['artist_frequency']})" for x in data["tokens"][:8]))
        print("Retrieval pool sizes:")
        for target, data in scn["retrieval"].items():
            print(f"  target={target:>3s}: broad={data['broad_pool_before_filters']:3d}, after_filters={data['returned_after_filters']:3d}")
            print("    markers: " + ", ".join(
                f"{label}={count}" for label, count in data["marker_counts_after_filters"].items()
            ))
            print("    top: " + "; ".join(data["top_artists_after_filters"][:10]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=REPO_ROOT / "context" / "artists.enriched.jsonl")
    parser.add_argument("--aliases", type=Path, default=None)
    parser.add_argument("--scenario", action="append", choices=sorted(SCENARIOS), help="Scenario(s) to analyze; default: all")
    parser.add_argument("--target-size", action="append", type=int, default=None, help="Candidate target size(s); default: 20, 50, 100")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--output", type=Path, help="Optional output path")
    args = parser.parse_args()

    corpus = RagCorpus.load(args.corpus, args.aliases)
    scenario_names = args.scenario or sorted(SCENARIOS)
    targets = args.target_size or [20, 50, 100]
    report = {
        "corpus_path": str(args.corpus),
        "corpus": corpus_report(corpus),
        "scenarios": [scenario_report(corpus, SCENARIOS[name], targets) for name in scenario_names],
    }

    if args.json:
        text = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        import io
        old_stdout = sys.stdout
        buf = io.StringIO()
        try:
            sys.stdout = buf
            print_text(report)
        finally:
            sys.stdout = old_stdout
        text = buf.getvalue()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
