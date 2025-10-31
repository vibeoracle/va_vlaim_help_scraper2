# Reddit Veterans Subreddits Rhetorical Strategy Scraper

**VA Claim Help Scraper 2** is a Python-based research tool that collects and tags Reddit posts and comments from veteran-focused communities (*r/Veterans*, *r/VeteransBenefits*, and *r/VAClaims*). Unlike typical keyword scrapers, it links search terms to **rhetorical strategies**—such as procedural discourse, affective protest, and moral legitimacy—allowing posts to be automatically flagged for how veterans express frustration, identity, and institutional critique. The script performs authenticated Reddit API searches, saves results in structured JSON and CSV formats, and supports transparent, reproducible analysis of online veteran discourse.

---

## Purpose

This project extends the original *VA Claim Help Scraper* by introducing rhetorical strategy tagging as part of a hybrid methodology for studying digital veteran discourse. It supports a **qualitative–quantitative workflow** in which Reddit data is collected ethically and transparently, stored locally in structured formats, and annotated for later qualitative analysis.

---

## Rhetorical Framework

The scraping logic is organized around a set of **rhetorical strategies**, not just topical categories. Keywords are grouped into strategies in a `strategy_keywords.json` file and loaded by the script at runtime. Each keyword is a short phrase chosen for its thematic relevance and colloquial presence in veteran communities.

### Example strategies

* **Procedural Discourse** – institutional language and bureaucratic mimicry (e.g., “evidence insufficient,” “effective date,” “service connected”).
* **Affective Protest** – expressions of frustration, burnout, or solidarity (e.g., “can’t take it anymore,” “not worth it,” “hang in there”).
* **Moral Legitimacy** – claims to credibility, service, or fairness (e.g., “real vet,” “earned it,” “deserve better”).

Each post or comment is evaluated for **all** keywords, not just the one that triggered the search. This allows multi-strategy tagging and supports rhetorical network analysis.

### Why rhetorical strategies?

Sorting by rhetorical strategy (rather than topic or sentiment) aligns with a **qualitative research agenda** centered on *how* veterans express institutional frustration, identity, and irony—not just *what* they talk about, but how they frame their claims. Examples include:

* **Framing anxiety:** “I could lose my house if this doesn’t come through” vs. “Just the VA, nothing new.”
* **Stance toward the institution:** mocking, pleading, instructing, or warning.
* **Tactical expression:** using official VA terminology vs. plain-language translation.
* **Affective motion:** spreading reassurance, cynicism, panic, or solidarity.

These rhetorical moves are what give discourse its social and affective force.

---

## How the Script Works

1. **Keyword-Strategy Mapping** – loads `strategy_keywords.json` and builds a reverse lookup mapping each keyword to one or more strategies.
2. **API Authentication** – authenticates with Reddit using credentials stored in `.env` or environment variables.
3. **Target Subreddits** – scrapes posts and comments from `r/Veterans`, `r/VeteransBenefits`, and `r/VAClaims`.
4. **Search & Tagging Loop** – performs full-text search for each keyword, flags posts and comments, and saves results to JSON and CSV.
5. **Output Metadata** – includes strategy tags, post/comment metadata, timestamps, and counts in summary files. Deduplication is handled globally through `seen_ids.json`.

---

## ⚙️ Setup & Installation

### Requirements

Python 3.10 or newer

Install dependencies:

```bash
pip install -r requirements.txt
```

### .env file

Create a `.env` file in your project root:

```bash
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
USER_AGENT=va_claim_help_scraper2 by u/<your_username> (contact: you@example.com)
# Optional if using password grant (2FA must be off):
REDDIT_USERNAME=your_username
REDDIT_PASSWORD=your_password
```

### Strategy Keywords

Create `strategy_keywords.json` in the project directory:

```json
{
  "procedural_discourse": ["service connected", "evidence insufficient", "effective date"],
  "affective_protest": ["can't take it anymore", "not worth it", "hang in there"],
  "moral_legitimacy": ["real vet", "earned it", "deserve better"]
}
```

---

## 🚀 Preflight / First-Run Checklist

Before your first scrape, run these checks to avoid setup issues:

```bash
python va_claim_help_scraper2.py --dotenv --doctor
```

This verifies:

* Python version ≥ 3.10
* Required libraries installed (`praw`, `python-dotenv`)
* Reddit credentials valid and API reachable
* `strategy_keywords.json` present
* Results directory writable

If all checks pass, start a quick test run:

```bash
python va_claim_help_scraper2.py --dotenv --skip-comments --verbose
```

When ready for a full scrape:

```bash
python va_claim_help_scraper2.py --dotenv --verbose
```

---

## Outputs

| File                                 | Description                           |
| ------------------------------------ | ------------------------------------- |
| `results/<subreddit>_<keyword>.json` | All posts/comments matching a keyword |
| `results/<subreddit>_<keyword>.csv`  | Flat version of the same data         |
| `summary_log_<subreddit>.csv`        | Per-run statistics and timestamps     |
| `seen_ids.json`                      | Deduplication record across runs      |

Each record includes: post/comment ID, type, title, body, score, timestamp, matched keyword(s), and corresponding rhetorical strategy(ies).

---

## Methodological Context

This scraper is part of a dissertation data collection and analysis workflow exploring **veteran discourse, affect, and institutional rhetoric**. Its methodological premise is that scraping can reveal recurring rhetorical patterns but also **miss affective nuance**—tone, irony, or embodied frustration that operate below keyword thresholds.

By embedding rhetorical tagging at the scraping stage, this tool bridges computational scale with qualitative sensitivity, laying groundwork for later interpretive analysis.

---

## Dependencies

* `praw` – Reddit API wrapper (BSD-2-Clause)
* `prawcore` – Reddit API utilities (BSD-2-Clause)
* `python-dotenv` – Environment variable loader (MIT)
* `pandas`, `matplotlib`, `gspread`, `oauth2client` – optional for downstream reporting

---

## Ethics & License

Released under the MIT License.

This project interacts with Reddit’s API via PRAW. This project complies with [Reddit’s Data API Terms of Use](https://www.redditinc.com/policies/data-api-terms). Users are responsible for following Reddit’s API Terms of Use, including restrictions on rate limits, data storage, and redistribution. No scraped data is included in this repository. No personally identifying information (usernames, URLs, or IDs) should be redistributed or published in research outputs. This script is intended for academic research on discourse patterns, not for surveillance or moderation.

---

## Citation

*VibeOracle. VA Claim Help Scraper 2: Strategy-Aware Reddit Data Collector* (2025).
Unpublished research tool for rhetorical analysis of veteran discourse.
Developed for a dissertation-related project in rhetoric and composition.

---

## Acknowledgment

Developed collaboratively with **ChatGPT-5** for debugging, documentation, and accessibility enhancements. Designed as part of a broader effort toward transparent, rhetorically informed digital research methodologies.

---
