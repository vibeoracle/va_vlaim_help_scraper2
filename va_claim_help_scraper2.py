#!/usr/bin/env python3
"""
va_claim_help_scraper2.py — Strategy‑aware Reddit scraper
---------------------------------------------------------
Collects posts and comments from multiple veteran‑related subreddits and
flags occurrences of strategy keywords (loaded from a JSON file). Designed
for transparent, reproducible use by non‑experts with built‑in preflight
checks and plain‑English troubleshooting.

# INSTALLATION
    python --version         # requires 3.10 or newer
    pip install praw python-dotenv

# SETUP
1) Create a Reddit 'script' app at https://www.reddit.com/prefs/apps
   and copy its client_id and client_secret.
2) Create a `.env` file in this folder (or set environment variables):
       CLIENT_ID=your_client_id
       CLIENT_SECRET=your_client_secret
       USER_AGENT=va_claim_help_scraper2 by u/<your_username> (contact: you@example.com)
       # Optional if using password grant (2FA must be OFF):
       REDDIT_USERNAME=your_username
       REDDIT_PASSWORD=your_password
3) Prepare input files in the project folder:
       strategy_keywords.json   # {"strategy_name": ["keyword1", "keyword2", ...], ...}

# FIRST RUN
    python va_claim_help_scraper2.py --dotenv --doctor \
        --subreddits VeteransBenefits Veterans VAClaims \
        --strategy-keywords strategy_keywords.json
    # Fix any issues it reports.

# TYPICAL RUN (fast test)
    python va_claim_help_scraper2.py --dotenv --skip-comments --verbose

# FULL RUN (scan comments too)
    python va_claim_help_scraper2.py --dotenv --verbose

# OUTPUT
    results/<subreddit>_<keyword>.json  # all matched records (posts + comments)
    results/<subreddit>_<keyword>.csv   # flat export
    summary_log_<subreddit>.csv         # one row per keyword per run
    seen_ids.json                       # global dedupe across runs

# TROUBLESHOOTING
    * Missing praw →  pip install praw
    * OAuthException → check CLIENT_ID/SECRET and app type ('script')
    * FileNotFoundError on strategy_keywords.json → provide the file path or use --strategy-keywords
    * PermissionError → choose a writable directory or use --results <path>
    * Rate limit (429) → rerun with higher --sleep or --max-retries

# ETHICS & TERMS
    Use in accordance with Reddit Data API Terms. Do not publish PII or raw URLs
    in venues where it would identify users. This script was written for research
    on digital veteran discourse and emphasizes transparency over opacity.
---------------------------------------------------------
"""
from __future__ import annotations
import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Optional .env support
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

# Third‑party deps
try:
    import praw  # type: ignore
    import prawcore  # type: ignore
except Exception:
    praw = None  # type: ignore
    prawcore = None  # type: ignore

APP_NAME = "va_claim_help_scraper2"
DEFAULT_RESULTS_DIR = "results"
DEFAULT_SEEN_IDS_FILE = "seen_ids.json"
DEFAULT_STRATEGY_KEYWORDS = "strategy_keywords.json"
DEFAULT_SUBREDDITS = ["VeteransBenefits", "Veterans", "VAClaims"]

# ------------------------- helpers -------------------------

def sanitize_filename(name: str, maxlen: int = 120) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return safe[:maxlen] or "untitled"


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def append_csv_row(path: Path, header: List[str], row: List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(header)
        w.writerow(row)


def utc_date(ts: float | int | None) -> str:
    if ts is None:
        return "N/A"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "N/A"


def periodic_save_seen(seen_ids: set[str], seen_path: Path, counter: int, every: int = 3) -> None:
    if counter % every == 0:
        try:
            save_json(seen_path, sorted(seen_ids))
        except Exception:
            logging.warning("Could not save seen IDs (periodic). Continuing…")


# ------------------------- preflight doctor -------------------------

def create_reddit(client_id: str, client_secret: str, user_agent: str,
                  username: str | None, password: str | None):
    if username and password:
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            username=username,
            password=password,
            ratelimit_seconds=5,
        )
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        ratelimit_seconds=5,
    )


def run_doctor(args) -> int:
    print("\n=== Preflight: first‑run checks ===")

    # Python version
    py_ok = sys.version_info >= (3, 10)
    print(f"Python version: {sys.version.split()[0]} — {'OK' if py_ok else 'Needs 3.10+'}")

    # dotenv
    if args.dotenv:
        if load_dotenv is None:
            print("python-dotenv not installed. Run: pip install python-dotenv")
        else:
            load_dotenv()
            print("Loaded .env (if present).")

    # PRAW import
    if praw is None:
        print("PRAW not installed. Run: pip install praw")
        return 1

    # Credentials
    cid = os.getenv("CLIENT_ID")
    csec = os.getenv("CLIENT_SECRET")
    uagent = os.getenv("USER_AGENT", f"{APP_NAME} by u/your_username (contact: email)")
    ruser = os.getenv("REDDIT_USERNAME")
    rpass = os.getenv("REDDIT_PASSWORD")

    if not (cid and csec and uagent):
        print("Missing credentials. Set CLIENT_ID, CLIENT_SECRET, and USER_AGENT in env or .env.")
        print("If using password grant, also set REDDIT_USERNAME and REDDIT_PASSWORD (2FA must be off).")
        return 1
    else:
        print("Found Reddit app credentials.")

    # Strategy keywords file
    sk_path = Path(args.strategy_keywords)
    if not sk_path.exists():
        print(f"strategy_keywords file not found at: {sk_path}. Provide it or pass --strategy-keywords <path>.")
        return 1
    else:
        print(f"Found strategy keywords file: {sk_path}")

    # Results dir writable
    results_dir = Path(args.results)
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        test = results_dir / ".writetest"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        print(f"Results directory writable: {results_dir}")
    except Exception:
        print(f"Cannot write to results directory: {results_dir}. Choose another with --results.")
        return 1

    # API touch + subreddit visibility check
    try:
        reddit = create_reddit(cid, csec, uagent, ruser, rpass)
        _ = reddit.read_only
        # ping first subreddit
        first = args.subreddits[0] if args.subreddits else DEFAULT_SUBREDDITS[0]
        _ = reddit.subreddit(first).display_name  # resolves if accessible
        print(f"Reddit API reachable. Subreddit looks accessible: r/{first}")
    except prawcore.exceptions.OAuthException:
        print("OAuth error. Ensure your Reddit app is type 'script' and secrets are correct.")
        return 1
    except prawcore.exceptions.Forbidden:
        print("Access forbidden to target subreddit(s). Is one private/banned?")
        return 1
    except Exception as e:
        print(f"General API/network error: {e}\nCheck network, proxies, or try again later.")
        return 1

    print("\nAll essential checks passed. You can run the scraper now.")
    return 0


# ------------------------- core scraping -------------------------

def build_keyword_maps(strategy_keywords: Dict[str, List[str]]) -> Dict[str, List[str]]:
    kw_to_strats: Dict[str, List[str]] = defaultdict(list)
    for strat, kws in strategy_keywords.items():
        for kw in kws:
            if not isinstance(kw, str):
                continue
            kw_to_strats[kw.lower()].append(strat)
    return kw_to_strats


def flag_strategies(text: str, kw_to_strats: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    text_lower = text.lower() if text else ""
    matched_keywords = []
    matched_strategies = set()
    for kw, strategies in kw_to_strats.items():
        if kw and kw in text_lower:
            matched_keywords.append(kw)
            matched_strategies.update(strategies)
    return matched_keywords, sorted(matched_strategies)


def scrape(reddit, subreddits: List[str], kw_to_strats: Dict[str, List[str]], results_dir: Path,
           summary_prefix: str, seen_ids_path: Path, limit_posts: int,
           sleep_s: int, max_retries: int, include_comments: bool, verbose: bool) -> None:
    log = logging.getLogger("scraper")

    # seen ids
    seen_ids: set[str] = set()
    try:
        if seen_ids_path.exists():
            data = load_json(seen_ids_path)
            if isinstance(data, list):
                seen_ids = set(map(str, data))
    except Exception:
        log.warning("seen_ids.json is corrupt; starting fresh.")

    for subreddit_name in subreddits:
        sub = reddit.subreddit(subreddit_name)
        summary_csv = Path(f"{summary_prefix}{subreddit_name}.csv")
        header = [
            "subreddit", "keyword", "post_count", "comment_count",
            "oldest_date", "newest_date", "json_filename", "skipped_duplicates"
        ]

        for idx, search_phrase in enumerate(kw_to_strats.keys(), start=1):
            safe_kw = sanitize_filename(search_phrase)
            prefix = f"{subreddit_name}_{safe_kw}"
            json_file = results_dir / f"{prefix}.json"
            csv_file = results_dir / f"{prefix}.csv"

            results: List[Dict[str, Any]] = []
            post_count = 0
            comment_count = 0
            skipped = 0
            oldest_ts = None
            newest_ts = None

            def update_dates(ts):
                nonlocal oldest_ts, newest_ts
                if ts is None:
                    return
                oldest_ts = ts if oldest_ts is None else min(oldest_ts, ts)
                newest_ts = ts if newest_ts is None else max(newest_ts, ts)

            # --- search posts for exact phrase ---
            q = f'"{search_phrase}"'
            if verbose:
                log.info(f"[{subreddit_name}] [{idx}/{len(kw_to_strats)}] Searching posts for: {q}")

            for attempt in range(1, max_retries + 1):
                try:
                    for post in sub.search(q, sort="new", time_filter="all", limit=200):
                        if post.id in seen_ids:
                            skipped += 1
                            continue
                        seen_ids.add(post.id)
                        matched_keywords, matched_strategies = flag_strategies(
                            f"{getattr(post,'title','')} {getattr(post,'selftext','')}", kw_to_strats
                        )
                        results.append({
                            "subreddit": subreddit_name,
                            "type": "post",
                            "id": post.id,
                            "title": getattr(post, "title", ""),
                            "body": getattr(post, "selftext", ""),
                            "url": f"https://reddit.com{getattr(post, 'permalink', '')}",
                            "score": getattr(post, "score", 0),
                            "created_utc": getattr(post, "created_utc", None),
                            "matched_keyword": search_phrase,
                            "matched_keywords": matched_keywords,
                            "matched_strategies": matched_strategies
                        })
                        post_count += 1
                        update_dates(getattr(post, "created_utc", None))
                    break
                except prawcore.exceptions.TooManyRequests:
                    wait = sleep_s * attempt
                    log.warning(f"Rate limited. Sleeping {wait}s (attempt {attempt}/{max_retries})…")
                    time.sleep(wait)
                except prawcore.exceptions.ServerError:
                    wait = sleep_s * attempt
                    log.warning(f"Server error. Sleeping {wait}s (attempt {attempt}/{max_retries})…")
                    time.sleep(wait)
                except Exception as e:
                    log.error(f"Unexpected error while searching posts: {e}")
                    break

            # --- scan hot posts & comments ---
            if include_comments:
                if verbose:
                    log.info(f"[{subreddit_name}] Scanning hot posts & comments for: {search_phrase}")
                try:
                    for post in sub.hot(limit=limit_posts):
                        try:
                            post.comments.replace_more(limit=0)
                            for c in post.comments.list():
                                body = getattr(c, "body", "")
                                if body and search_phrase.lower() in body.lower():
                                    cid = getattr(c, "id", None)
                                    if not cid or cid in seen_ids:
                                        skipped += 1
                                        continue
                                    seen_ids.add(cid)
                                    matched_keywords, matched_strategies = flag_strategies(body, kw_to_strats)
                                    results.append({
                                        "subreddit": subreddit_name,
                                        "type": "comment",
                                        "id": cid,
                                        "post_title": getattr(post, "title", ""),
                                        "comment_body": body,
                                        "url": f"https://reddit.com{getattr(c, 'permalink', '')}",
                                        "score": getattr(c, "score", 0),
                                        "created_utc": getattr(c, "created_utc", None),
                                        "matched_keyword": search_phrase,
                                        "matched_keywords": matched_keywords,
                                        "matched_strategies": matched_strategies
                                    })
                                    comment_count += 1
                                    update_dates(getattr(c, "created_utc", None))
                        except Exception as e:
                            log.warning(f"Skipping one hot post due to error: {e}")
                except Exception as e:
                    log.warning(f"Hot listing failed: {e}")

            # --- persist per‑keyword outputs ---
            # merge with existing JSON if present
            existing = load_json(json_file) or []
            if not isinstance(existing, list):
                existing = []
            save_json(json_file, existing + results)

            # write CSV (append with header if new)
            fieldnames = [
                "subreddit", "type", "id", "title", "body", "post_title",
                "comment_body", "url", "score", "created_utc",
                "matched_keyword", "matched_keywords", "matched_strategies"
            ]
            is_new = not csv_file.exists() or csv_file.stat().st_size == 0
            with csv_file.open("a", encoding="utf-8", newline="") as cf:
                w = csv.DictWriter(cf, fieldnames=fieldnames)
                if is_new:
                    w.writeheader()
                for row in results:
                    w.writerow({k: row.get(k, "") for k in fieldnames})

            # summary row
            timestamps = [r.get("created_utc") for r in results if r.get("created_utc") is not None]
            oldest_date = utc_date(min(timestamps)) if timestamps else "N/A"
            newest_date = utc_date(max(timestamps)) if timestamps else "N/A"
            append_csv_row(
                summary_csv,
                header,
                [subreddit_name, search_phrase, post_count, comment_count,
                 oldest_date, newest_date, json_file.name, skipped],
            )

            periodic_save_seen(seen_ids, seen_ids_path, idx, every=3)

            if sleep_s > 0:
                time.sleep(sleep_s)

    # final save of seen ids
    try:
        save_json(seen_ids_path, sorted(seen_ids))
    except Exception:
        logging.warning("Could not save final seen IDs.")


# ------------------------- main -------------------------

def main():
    p = argparse.ArgumentParser(description="Strategy‑aware Reddit scraper with preflight doctor & guards.")
    p.add_argument("--dotenv", action="store_true", help="Load a .env file from the project root if present.")
    p.add_argument("--doctor", action="store_true", help="Run preflight checks and exit.")

    p.add_argument("--subreddits", nargs="*", default=DEFAULT_SUBREDDITS,
                   help="Space‑separated list of subreddits (default: VeteransBenefits Veterans VAClaims)")
    p.add_argument("--strategy-keywords", default=DEFAULT_STRATEGY_KEYWORDS,
                   help="Path to strategy_keywords.json")

    p.add_argument("--results", default=DEFAULT_RESULTS_DIR, help="Directory to write results.")
    p.add_argument("--seen-ids", default=DEFAULT_SEEN_IDS_FILE, help="Path to seen IDs JSON.")
    p.add_argument("--summary-prefix", default="summary_log_", help="Prefix for per‑subreddit summary CSV files.")

    p.add_argument("--limit-posts", type=int, default=100, help="Number of hot posts to scan for comments.")
    p.add_argument("--sleep", type=int, default=5, help="Seconds to sleep between keywords and on backoff.")
    p.add_argument("--max-retries", type=int, default=3, help="Retries for rate‑limit/server errors.")
    p.add_argument("--skip-comments", action="store_true", help="Do not scan comments (faster).")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")

    args = p.parse_args()

    if args.dotenv and load_dotenv is not None:
        load_dotenv()

    logging.basicConfig(level=(logging.INFO if args.verbose else logging.WARNING),
                        format="%(levelname)s: %(message)s")

    if args.doctor:
        if praw is None:
            print("PRAW not installed. Run: pip install praw")
            sys.exit(1)
        rc = run_doctor(args)
        sys.exit(rc)

    if praw is None:
        raise SystemExit("PRAW is not installed. Run: pip install praw")

    # creds
    cid = os.getenv("CLIENT_ID")
    csec = os.getenv("CLIENT_SECRET")
    uagent = os.getenv("USER_AGENT", f"{APP_NAME} by u/your_username (contact: email)")
    ruser = os.getenv("REDDIT_USERNAME")
    rpass = os.getenv("REDDIT_PASSWORD")

    if not (cid and csec):
        raise SystemExit("Missing CLIENT_ID/CLIENT_SECRET. Set them in env or .env (use --dotenv).")

    reddit = create_reddit(cid, csec, uagent, ruser, rpass)

    # strategy keywords
    sk_path = Path(args.strategy_keywords)
    sk_obj = load_json(sk_path)
    if not isinstance(sk_obj, dict):
        raise SystemExit(
            f"strategy_keywords file missing or invalid JSON map. Provide a file like: {{'strategy': ['kw', ...]}}\nPath: {sk_path}"
        )
    kw_to_strats = build_keyword_maps(sk_obj)

    scrape(
        reddit=reddit,
        subreddits=args.subreddits,
        kw_to_strats=kw_to_strats,
        results_dir=Path(args.results),
        summary_prefix=args.summary_prefix,
        seen_ids_path=Path(args.seen_ids),
        limit_posts=args.limit_posts,
        sleep_s=args.sleep,
        max_retries=args.max_retries,
        include_comments=not args.skip_comments,
        verbose=args.verbose,
    )

    print("\nDone. Outputs in:", Path(args.results).resolve())
    print("Seen IDs:", Path(args.seen_ids).resolve())


if __name__ == "__main__":
    main()
