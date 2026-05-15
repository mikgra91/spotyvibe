"""OpenRouter free-tier smoke screen — quick cull of bad model candidates.

5 probes × N models. Tests JSON compliance + basic grounding/constraint
following. NOT a full quality eval — just "horrible vs okay" filter.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("SV_TEST_KEY")
if not KEY:
    print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
    sys.exit(2)

OUT_DIR = Path(__file__).parent / "results" / "openrouter_smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)
JSONL = OUT_DIR / "responses.jsonl"

MODELS = [
    "deepseek/deepseek-v4-flash:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "z-ai/glm-4.5-air:free",
]


def _system(rationale_required: bool = False) -> str:
    extra = "" if not rationale_required else ""
    return (
        "You are a music recommendation engine.\n"
        "OUTPUT: valid JSON object only, no prose. Schema: "
        '{"playlist":[{"artist":"...","track":"..."}]}.\n'
        "Pick ONLY real, released tracks you can recall by name. "
        "Never invent track titles. Never put the artist name in the track field. "
        "If unsure, return fewer entries — empty playlist is preferred over invention." + extra
    )


PROBES = [
    {
        "id": "p1_cold_schema",
        "system": _system(),
        "user": (
            "Suggest UP TO 3 real released tracks by Tally Hall. "
            'Output JSON: {"playlist":[{"artist":"...","track":"..."}]}.'
        ),
    },
    {
        "id": "p2_refusal",
        "system": _system(),
        "user": (
            "Approved artists:\n- zzzfake-artist-nonexistent\n\n"
            "Suggest UP TO 3 real released tracks by approved artists ONLY. "
            "If no real tracks can be cited, return empty playlist. "
            'Output JSON: {"playlist":[...]}.'
        ),
    },
    {
        "id": "p3_must_avoid",
        "system": _system(),
        "user": (
            "Taste: Must: female vocalist. Avoid: heavy metal.\n\n"
            "Approved artists:\n- Beyonce\n- Metallica\n- Adele\n\n"
            "Suggest UP TO 4 tracks satisfying ALL Must traits and NONE of Avoid traits. "
            "Pick from approved artists ONLY. "
            'Output JSON: {"playlist":[{"artist":"...","track":"..."}]}.'
        ),
    },
    {
        "id": "p4_pool_grounding",
        "system": _system(),
        "user": (
            "Approved artists:\n"
            "- Tally Hall\n  known: Banana Man, Good Day, Hidden in the Sand\n"
            "- Bear Ghost\n  known: Necromancin Dancin, Funeral March of Old Friends\n"
            "\nSuggest UP TO 4 tracks. Prefer titles from the `known:` lines. "
            'Output JSON: {"playlist":[{"artist":"...","track":"..."}]}.'
        ),
    },
    {
        "id": "p5_scale_cap",
        "system": _system(),
        "user": (
            "Approved artists:\n- The Beatles\n- Queen\n- David Bowie\n- Pink Floyd\n- Fleetwood Mac\n\n"
            "Suggest UP TO 10 real released tracks. Max 2 per artist. From approved artists ONLY. "
            'Output JSON: {"playlist":[{"artist":"...","track":"..."}]}.'
        ),
    },
]


def call(model: str, system: str, user: str, retries: int = 2) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    last_err = None
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = json.loads(r.read())
            resp["_wall_s"] = round(time.monotonic() - t0, 2)
            return resp
        except urllib.error.HTTPError as e:
            body_str = e.read()[:500].decode(errors="replace")
            last_err = f"HTTP {e.code} {body_str}"
            if e.code == 429 and attempt < retries:
                time.sleep(8 * (attempt + 1))
                continue
            break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            break
    return {"_error": last_err, "_wall_s": round(time.monotonic() - t0, 2)}


def parse_playlist(content: str) -> tuple[list, str | None]:
    """Return (playlist_list_or_empty, error_str_or_None)."""
    if not content:
        return [], "empty content"
    s = content.strip()
    # strip code fences
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        return [], f"json_decode: {e}"
    if not isinstance(obj, dict):
        return [], f"not_object: {type(obj).__name__}"
    pl = obj.get("playlist")
    if pl is None:
        return [], "missing_playlist_key"
    if not isinstance(pl, list):
        return [], f"playlist_not_list: {type(pl).__name__}"
    return pl, None


def score(probe_id: str, playlist: list) -> dict:
    """Per-probe pass/fail + diagnostics."""
    out = {"count": len(playlist)}
    # generic check: each entry has artist+track, track != artist (case-insensitive)
    well_formed = 0
    echoes = 0
    for entry in playlist:
        if not isinstance(entry, dict):
            continue
        a = (entry.get("artist") or "").strip().lower()
        t = (entry.get("track") or "").strip().lower()
        if a and t:
            well_formed += 1
            if a == t:
                echoes += 1
    out["well_formed"] = well_formed
    out["echoes"] = echoes

    if probe_id == "p1_cold_schema":
        out["pass"] = well_formed >= 1 and echoes == 0
    elif probe_id == "p2_refusal":
        out["pass"] = well_formed == 0  # must NOT hallucinate
    elif probe_id == "p3_must_avoid":
        metallica = sum(1 for e in playlist if isinstance(e, dict)
                        and "metallica" in (e.get("artist") or "").lower())
        out["metallica_count"] = metallica
        out["pass"] = metallica == 0 and well_formed >= 1
    elif probe_id == "p4_pool_grounding":
        pool = {"tally hall", "bear ghost"}
        in_pool = sum(1 for e in playlist if isinstance(e, dict)
                      and (e.get("artist") or "").strip().lower() in pool)
        known = {
            "banana man", "good day", "hidden in the sand",
            "necromancin dancin", "funeral march of old friends",
        }
        from_known = sum(1 for e in playlist if isinstance(e, dict)
                         and (e.get("track") or "").strip().lower().replace("'", "") in known)
        out["in_pool"] = in_pool
        out["from_known"] = from_known
        out["pass"] = in_pool == len(playlist) and from_known >= 1
    elif probe_id == "p5_scale_cap":
        pool = {"the beatles", "beatles", "queen", "david bowie", "pink floyd", "fleetwood mac"}
        in_pool = sum(1 for e in playlist if isinstance(e, dict)
                      and (e.get("artist") or "").strip().lower() in pool)
        # per-artist count
        from collections import Counter
        counts = Counter((e.get("artist") or "").strip().lower()
                         for e in playlist if isinstance(e, dict))
        max_per = max(counts.values()) if counts else 0
        out["in_pool"] = in_pool
        out["max_per_artist"] = max_per
        out["pass"] = in_pool == len(playlist) and max_per <= 2 and well_formed >= 5
    else:
        out["pass"] = False
    return out


def main():
    print(f"Probing {len(MODELS)} models × {len(PROBES)} probes = {len(MODELS) * len(PROBES)} calls\n")
    rows = []
    with JSONL.open("w", encoding="utf-8") as fh:
        for mi, model in enumerate(MODELS, 1):
            print(f"[{mi}/{len(MODELS)}] {model}")
            for pi, probe in enumerate(PROBES, 1):
                print(f"  probe {pi}/5 {probe['id']}", end=" ", flush=True)
                resp = call(model, probe["system"], probe["user"])
                row = {"model": model, "probe": probe["id"], "wall_s": resp.get("_wall_s")}
                if "_error" in resp:
                    row["error"] = resp["_error"]
                    row["pass"] = False
                    print(f"ERR {resp['_error'][:80]}")
                elif "choices" not in resp or not resp["choices"]:
                    row["error"] = f"no_choices: {json.dumps(resp)[:300]}"
                    row["pass"] = False
                    print(f"ERR no choices: {json.dumps(resp)[:120]}")
                else:
                    content = resp["choices"][0].get("message", {}).get("content") or ""
                    usage = resp.get("usage") or {}
                    row["usage_in"] = usage.get("prompt_tokens", 0)
                    row["usage_out"] = usage.get("completion_tokens", 0)
                    pl, parse_err = parse_playlist(content)
                    if parse_err:
                        row["parse_error"] = parse_err
                        row["content_head"] = content[:200]
                        row["pass"] = False
                        print(f"PARSE-FAIL {parse_err}")
                    else:
                        s = score(probe["id"], pl)
                        row.update(s)
                        print(f"{'PASS' if s['pass'] else 'FAIL'} (n={s['count']})")
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                rows.append(row)
                time.sleep(3)  # pace at <20 RPM
            print()

    # Build summary
    summary_lines = [
        "# OpenRouter free-tier smoke screen — results",
        f"\nDate: 2026-05-14",
        f"\nModels: {len(MODELS)}. Probes: {len(PROBES)}. Total calls: {len(rows)}.",
        f"\nCost: $0 (free tier).",
        "\n## Probe pass matrix\n",
        "| Model | p1 cold | p2 refuse | p3 must/avoid | p4 grounding | p5 scale | Pass rate |",
        "|---|:-:|:-:|:-:|:-:|:-:|---:|",
    ]
    by_model: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_model.setdefault(r["model"], {})[r["probe"]] = r
    for m in MODELS:
        cells = []
        passes = 0
        total = 0
        for p in PROBES:
            r = by_model.get(m, {}).get(p["id"])
            if r is None:
                cells.append("—")
                continue
            total += 1
            if r.get("error"):
                cells.append("ERR")
            elif r.get("parse_error"):
                cells.append("PARSE")
            elif r.get("pass"):
                cells.append("✅")
                passes += 1
            else:
                cells.append("❌")
        rate = f"{passes}/{total}" if total else "—"
        summary_lines.append(f"| `{m}` | " + " | ".join(cells) + f" | **{rate}** |")

    summary_lines += [
        "\n## Token + wall per model (mean across probes)\n",
        "| Model | mean tokens out | mean wall s |",
        "|---|---:|---:|",
    ]
    for m in MODELS:
        rs = [by_model.get(m, {}).get(p["id"]) for p in PROBES]
        out_tokens = [r["usage_out"] for r in rs if r and r.get("usage_out") is not None]
        walls = [r["wall_s"] for r in rs if r and r.get("wall_s") is not None and not r.get("error")]
        if out_tokens:
            summary_lines.append(
                f"| `{m}` | {sum(out_tokens)//len(out_tokens)} | {sum(walls)/len(walls):.1f} |"
            )
        else:
            summary_lines.append(f"| `{m}` | — | — |")

    summary_lines += [
        "\n## Verdict",
        "",
        "Survivors (≥ 4/5 pass) advance to Phase 2 paid eval. Models < 3/5 dropped.",
        "Models with ERR on ≥ 3 probes = retry next session (likely upstream rate-limit).",
        "",
        "## Files",
        "",
        "- `responses.jsonl` — full per-call records",
        "- `openrouter_smoke.py` — probe script",
    ]
    (OUT_DIR / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\nWrote {OUT_DIR / 'SUMMARY.md'}")
    print(f"Raw: {JSONL}")


if __name__ == "__main__":
    main()
