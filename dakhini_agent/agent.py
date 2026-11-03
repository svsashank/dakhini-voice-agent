"""Orchestrator. Runs locally (yt-dlp/ffmpeg from your own IP); calls Modal for LLM, GPU and HF."""
import argparse
import json
from pathlib import Path

from . import config, filters, sources, download
from .modal_app import app, generate_queries, Transcriber, judge_dakhini, upload_to_hf

STATE = Path("state.json")


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"queries": [], "seen": [], "accepted": []}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


def discover(queries, per_query, state):
    cands, seen = [], set(state["seen"])
    for q in queries:
        print(f"[search] {q}")
        found = sources.search_youtube(q, per_query) + sources.search_podcasts(q)
        sources.polite_sleep()
        for c in found:
            if c.key() in seen:
                continue
            seen.add(c.key())
            # YouTube flat results have no description: pre-filter by title, then enrich
            if c.source == "youtube" and not c.description:
                if filters.score(c) < 0:
                    continue
                c = sources.enrich_youtube(c)
            if filters.keep(c):
                print(f"  + keep ({c.score}) [{c.source}] {c.title[:80]}")
                cands.append(c)
    state["seen"] = sorted(seen)
    return cands


def run(args):
    work = Path("work")
    state = load_state()
    with app.run():
        queries = generate_queries.remote(args.num_queries, state["queries"])
        print("queries:", queries)
        state["queries"] += queries
        cands = discover(queries, args.per_query, state)[: args.max_candidates]
        print(f"\n{len(cands)} candidates passed title/description filter\n")

        transcriber = Transcriber()
        accepted = []
        for c in cands:
            print(f"[sample] {c.key()} {c.title[:70]}")
            sample = download.download_sample(c, work / "samples")
            if not sample:
                continue
            tr = transcriber.transcribe.remote(sample.read_bytes())
            verdict = judge_dakhini.remote(c.title, tr)
            print(f"  lang={tr['language']} dakhini={verdict.get('is_dakhini')} "
                  f"conf={verdict.get('confidence')} markers={verdict.get('markers')}")
            sample.unlink(missing_ok=True)
            if verdict.get("is_dakhini") and verdict.get("confidence", 0) >= args.min_confidence:
                accepted.append((c, tr, verdict))

        print(f"\n{len(accepted)} clips judged Dakhini")
        for c, tr, verdict in accepted:
            if args.dry_run:
                print(f"  (dry-run) would download+upload {c.title}")
                continue
            full = download.download_full(c, work / "full")
            if not full:
                continue
            meta = {**c.to_dict(), "sample_transcript": tr, "judgement": verdict}
            path = upload_to_hf.remote(args.repo, full.name, full.read_bytes(), meta)
            print(f"  uploaded {path}")
            full.unlink(missing_ok=True)
            state["accepted"].append(c.key())
    save_state(state)


def main():
    p = argparse.ArgumentParser(description="Dakhini speech audio collection agent")
    p.add_argument("--repo", required=True, help="HF dataset id, e.g. user/dakhini-audio (created private)")
    p.add_argument("--num-queries", type=int, default=5)
    p.add_argument("--per-query", type=int, default=10)
    p.add_argument("--max-candidates", type=int, default=20)
    p.add_argument("--min-confidence", type=float, default=0.6)
    p.add_argument("--dry-run", action="store_true", help="stop before full download/upload")
    run(p.parse_args())


if __name__ == "__main__":
    main()
