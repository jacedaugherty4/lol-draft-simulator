# LoL Draft Simulator

A data pipeline and machine learning model that recommends League of Legends champion picks during draft. Given the picks and bans made so far, it ranks the remaining champions by predicted win probability for your team.

> **Status:** In development. Setup is complete. Data ingestion is in progress. Sections marked *(planned)* describe work that hasn't been built yet.

---

## The question this project answers

> Given the current state of a draft (picks and bans for both teams), which champion gives my team the highest predicted chance of winning?

**Success criterion:** The model must beat a baseline that recommends champions using only their overall win rates, measured on matches the model never saw during training.

---

## Data scope

| Setting | Value | Notes |
|---|---|---|
| Game | League of Legends | |
| Queue | Ranked Solo/Duo | Riot queue ID `420` |
| Ranks | Diamond (I–IV), Master, Grandmaster, Challenger | High-elo play, where drafting is more deliberate |
| Regions | North America, Europe West, Korea | Tagged per match so they can be compared |
| Patch | `XX.XX` *(update when collection starts)* | Only matches from this patch are kept |
| Target sample | ~2,000 matches per region to start | Increased once the pipeline is stable |
| Minimum games per champion | 30 | Champions below this are excluded from win-rate results |

### Why these choices
- **High elo only:** Players in these ranks draft with more intent, so draft patterns are more meaningful and less noisy.
- **One patch:** Balance changes shift champion strength between patches. Mixing patches would blur the results.
- **Three regions:** Each region has its own meta. Every match is tagged with its region, so the model can be trained per region or across all three, and the results can be compared.

---

## Data sources

All data comes from the official [Riot Games API](https://developer.riotgames.com/).

### Region routing
Riot splits its API across two kinds of servers: **platform** hosts (player and rank data) and **regional routing** hosts (match data).

| Region | Platform host | Routing host | Match ID prefix |
|---|---|---|---|
| North America | `na1` | `americas` | `NA1_` |
| Europe West | `euw1` | `europe` | `EUW1_` |
| Korea | `kr` | `asia` | `KR_` |

### Endpoints used
| Purpose | Endpoint | Host type |
|---|---|---|
| Challenger players | `/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5` | Platform |
| Grandmaster players | `/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5` | Platform |
| Master players | `/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5` | Platform |
| Diamond players | `/lol/league/v4/entries/RANKED_SOLO_5x5/DIAMOND/{division}` | Platform |
| Match IDs for a player | `/lol/match/v5/matches/by-puuid/{puuid}/ids` | Routing |
| Match details | `/lol/match/v5/matches/{matchId}` | Routing |

Master, Grandmaster, and Challenger each have their own endpoint. Diamond is split into four divisions (I–IV) and is paged.

Champion names and IDs come from Riot's static data (Data Dragon), not hard-coded values.

### API limits
- Development and personal keys allow roughly **20 requests per second** and **100 requests per 2 minutes**, enforced **per region**.
- Development keys **expire every 24 hours** and must be regenerated in the developer portal.
- The collector waits between requests, retries after `429` responses, and stops with a clear message if the key has expired.

---

## Pipeline

```
Riot API → Ingestion → Raw JSON → Transform → Processed tables → Model → Recommendations
```

1. **Collect players:** Pull high-elo players for each region and tier, and save their PUUIDs.
2. **Collect match IDs:** For each player, pull recent ranked Solo/Duo match IDs.
3. **Fetch matches:** Download each match once and save the raw JSON. Matches already saved are skipped, because the same match appears in up to 10 players' histories.
4. **Filter:** Keep only matches from the target patch.
5. **Transform:** Flatten each match into one row with picks, bans, region, patch, and winner. Save as Parquet.
6. **Baseline:** Compute champion and matchup win rates.
7. **Model:** Train an XGBoost classifier to predict the winner from the draft. *(planned)*
8. **Recommend:** For a partial draft, score each available champion and return a ranked list. *(planned)*

---

## Project structure

```
lol-draft-simulator/
├── api/                    # FastAPI service (planned)
├── data/
│   ├── raw/                # Unmodified JSON from Riot, by region (not committed)
│   └── processed/          # Cleaned Parquet tables (not committed)
├── notebooks/              # Exploration and charts
├── src/
│   └── draft_sim/
│       ├── __init__.py
│       ├── riot_client.py  # API requests and error handling
│       ├── ingest.py       # Player, match ID, and match collection
│       └── transform.py    # Raw JSON → processed tables
├── tests/                  # pytest tests
├── .env                    # Riot API key (not committed)
├── .gitignore
├── notes.md                # Development log
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Setup

### Requirements
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A Riot developer account and API key

### Install
```bash
git clone https://github.com/jacedaugherty4/lol-draft-simulator.git
cd lol-draft-simulator
uv sync
```

### Add your API key
Create a `.env` file in the project root:
```
RIOT_API_KEY=RGAPI-your-key-here
```
Never commit this file. It's already listed in `.gitignore`.

---

## Usage

### Collect data *(planned)*
```bash
uv run python -m draft_sim.ingest --region na1 --matches 2000
uv run python -m draft_sim.ingest --region euw1 --matches 2000
uv run python -m draft_sim.ingest --region kr --matches 2000
```

### Build the processed tables *(planned)*
```bash
uv run python -m draft_sim.transform
```

### Run tests and linting
```bash
uv run pytest
uv run ruff check .
```

---

## Processed data schema *(planned)*

One row per match.

| Column | Type | Description |
|---|---|---|
| `match_id` | string | Riot match ID, such as `NA1_1234567890` |
| `region` | string | `na1`, `euw1`, or `kr` |
| `patch` | string | Patch version, such as `14.22` |
| `tier` | string | Rank tier of the player the match was collected from |
| `blue_top` … `blue_support` | int | Champion IDs for the blue side, by role |
| `red_top` … `red_support` | int | Champion IDs for the red side, by role |
| `blue_bans`, `red_bans` | list[int] | Banned champion IDs for each side |
| `blue_win` | bool | `True` if the blue side won |

---

## Methodology

- **Train/test split:** Matches are split so that the model is always evaluated on matches it hasn't seen.
- **Baseline:** Recommend the champion with the highest overall win rate for the open role.
- **Model:** XGBoost classifier on draft features. *(planned)*
- **Evaluation:** Accuracy, log loss, and a calibration check, so that a predicted 60% chance means a team wins about 60% of the time.
- **Explainability:** SHAP values to show which picks drive each prediction. *(planned)*

### Avoiding data leakage
Only information known **during the draft** is used as model input: picks, bans, side, region, and patch. In-game stats such as gold, kills, or objectives are excluded, since they wouldn't be known at draft time.

---

## Known limitations

- **Rank labels:** A match is labeled with the tier of the player it was collected from. Other players in the lobby may be in different tiers.
- **Sample imbalance:** Challenger has far fewer players than Diamond, so Diamond matches will make up most of the dataset.
- **Patch drift:** Results apply to the collected patch and need retraining after balance updates.
- **Small samples:** Champions below the minimum game count are excluded, so rarely played picks may not be recommended.
- **Draft only:** The model doesn't account for player skill, champion mastery, or team communication.

---

## Roadmap

- [x] Project setup and environment
- [ ] Riot API client with error handling
- [ ] Player and match ingestion for NA, EUW, and KR
- [ ] Transform raw matches into Parquet tables
- [ ] Champion and matchup win-rate baseline
- [ ] XGBoost model and evaluation
- [ ] Draft recommendation function
- [ ] FastAPI service and Docker container
- [ ] Streamlit interface
- [ ] GitHub Actions for tests
- [ ] Deployment
- [ ] Region comparison analysis

---

## Tech stack

Python, uv, requests, pandas, PyArrow, DuckDB, XGBoost, scikit-learn, pytest, Ruff. Planned: MLflow, SHAP, FastAPI, Docker, Streamlit, GitHub Actions.

---

## Legal

LoL Draft Simulator isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

This is a personal, non-commercial portfolio project. Raw match data is not redistributed in this repository.

---

## Author

Jace Daugherty — [GitHub](https://github.com/jacedaugherty4) · [LinkedIn](https://www.linkedin.com/in/jacedaugherty/)