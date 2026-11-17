# LoL Draft Simulator

A data pipeline and machine learning model that recommends League of Legends champion picks during draft. Given the picks and bans made so far, it ranks the remaining champions by predicted win probability for your team and explains each pick (synergy with teammates, counters to the enemy).

The pipeline runs on AWS: match data is stored in S3, secrets live in Parameter Store, and access is controlled by a least-privilege IAM user.

> **Status:** In development. Setup (Phase 0) is complete, and AWS storage, secrets, and permissions are configured. Data collection (Phase 1) is next. Sections marked *(planned)* describe work that hasn't been built yet.

---

## The question this project answers

> Given the current state of a draft (picks and bans for both teams), which champion gives my team the highest predicted chance of winning?

**Success criterion:** The model must beat a baseline that recommends champions using only their overall win rates, measured on later matches the model never saw during training.

---

## Data scope

| Setting | Value | Notes |
|---|---|---|
| Game | League of Legends | |
| Queue | Ranked Solo/Duo | Riot queue ID `420` |
| Ranks | Diamond (I–IV), Master, Grandmaster, Challenger | High-elo play, where drafting is more deliberate |
| Regions | North America, Europe West, Korea | Tagged per match so they can be compared |
| Patch | Most recent patch *(exact version set when collection starts)* | Only matches from this patch are kept |
| Target sample | ~2,000 matches per region to start | Increased once the pipeline is stable |
| Minimum games per champion | 30 | Champions below this are excluded from win-rate results |

### Why these choices
- **High elo only:** Players in these ranks draft with more intent, so draft patterns are more meaningful and less noisy.
- **One patch:** Balance changes shift champion strength between patches. Mixing patches would blur the results.
- **Three regions:** Each region has its own meta. Every match is tagged with its region, so the model can be trained per region or across all three, and the results can be compared.

---

## Architecture

```
                    ┌────────────────────────── AWS (us-east-2) ──────────────────────────┐
Riot API ──► Collector ──► S3 raw/ ──► Transform ──► S3 processed/ ──► Model ──► S3 models/
               │                                                                    │
               └── reads Riot key from Parameter Store          Recommender API ◄───┘ (planned)
```

| Piece | AWS service | Status |
|---|---|---|
| Data lake (raw JSON, Parquet tables, model files) | S3 | ✅ Configured |
| Riot API key storage | Systems Manager Parameter Store (`SecureString`) | ✅ Configured |
| Access control | IAM user with a least-privilege policy | ✅ Configured |
| Scheduled data collection | Lambda + EventBridge | *(planned, Phase 5)* |
| Recommendation API | API Gateway + Lambda (container image) | *(planned, Phase 6)* |
| Web front end | S3 static hosting or Amplify | *(planned, Phase 6)* |
| Tests and deployment | GitHub Actions | *(planned, Phase 7)* |

### S3 layout
One bucket, organized by prefix:

```
s3://<bucket>/
├── raw/{region}/{patch}/{match_id}.json   # Unmodified Riot API responses — never edited
├── processed/                              # Cleaned Parquet tables, rebuilt from raw/
└── models/                                 # Trained model files (planned)
```

- **Versioning is on**, so an accidental overwrite or delete can be undone.
- **A lifecycle rule** permanently deletes old (noncurrent) versions after 30 days and cleans up incomplete uploads after 7 days, so storage doesn't grow without limit.
- **Block Public Access is on.** Nothing in the bucket is public.

### Security
- **No secrets in code or in the repo.** The Riot API key is stored in Parameter Store as an encrypted `SecureString` and fetched at runtime with `boto3`.
- **Least privilege.** The project's IAM user (`lds-app`) can only list, read, write, and delete objects in the project bucket and read parameters under `/lds/`. It has no console access. If its keys leaked, nothing else in the account would be reachable.
- **Credentials stay on the machine.** AWS access keys live only in the local AWS CLI credentials file, never in `.env` or source code.
- **Cost guardrails.** A $5 AWS budget alert is set, and every resource is tagged `project = lds` so the project's costs can be tracked.

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
- Development keys **expire every 24 hours**. The new key must be updated in Parameter Store each day until a personal key is approved.
- The collector waits between requests, retries after `429` responses, and stops with a clear message if the key has expired.

---

## Pipeline

1. **Collect players:** Pull high-elo players for each region and tier, and save their PUUIDs.
2. **Collect match IDs:** For each player, pull recent ranked Solo/Duo match IDs.
3. **Fetch matches:** Download each match once and save the raw JSON to `s3://<bucket>/raw/`. Matches already saved are skipped, because the same match appears in up to 10 players' histories.
4. **Filter:** Keep only ranked Solo/Duo matches from the target patch.
5. **Transform:** Flatten each match into one row with picks by role, bans, region, patch, and winner. Run data checks (10 unique champions, valid roles), then save as Parquet to `s3://<bucket>/processed/`.
6. **Model:** Train and compare a win-rate baseline, logistic regression, and XGBoost with synergy and counter features. *(planned)*
7. **Recommend:** For a partial draft, score every legal champion and return the top 5 with reasons. *(planned)*
8. **Automate and serve:** Run collection on a schedule with Lambda + EventBridge, and serve recommendations through API Gateway with a simple web page. *(planned)*

---

## Project structure

```
lol-draft-simulator/
├── data/                   # Local cache of raw/processed data (not committed)
├── infra/                  # AWS setup: IAM policy JSON, deployment config
├── notebooks/              # Exploration and charts
├── src/
│   └── draft_sim/
│       ├── __init__.py
│       ├── config.py       # Region, bucket, and Parameter Store settings; fetches the Riot key
│       ├── riot_client.py  # API requests, rate limiting, and retries (planned)
│       ├── storage.py      # Read/write JSON and Parquet in S3 (planned)
│       ├── ingest.py       # Player, match ID, and match collection (planned)
│       └── transform.py    # Raw JSON → processed tables (planned)
├── tests/                  # pytest tests, using mocked API responses
├── .env                    # Local settings only, e.g. AWS_PROFILE (not committed)
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Setup

### Requirements
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and an AWS account
- A Riot developer account and API key

### 1. Install
```bash
git clone https://github.com/jacedaugherty4/lol-draft-simulator.git
cd lol-draft-simulator
uv sync
```

### 2. Set up AWS
1. **S3:** Create a bucket in `us-east-2` with versioning on, Block Public Access on, and the lifecycle rule described above.
2. **Parameter Store:** Create a `SecureString` parameter named `/lds/riot-api-key` holding your Riot API key.
3. **IAM:** Create a policy from `infra/lds-app-policy.json` (update the bucket name and account ID), attach it to a new IAM user with no console access, and create an access key for local code.
4. **Connect your machine:**
   ```bash
   aws configure --profile lds
   aws sts get-caller-identity --profile lds
   ```

### 3. Configure the project
Create a `.env` file in the project root:
```
AWS_PROFILE=lds
```
Set your bucket name in `src/draft_sim/config.py`. Then check that the key can be read:
```bash
uv run check_key.py
```

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
| `patch` | string | Patch version, such as `25.22` |
| `game_start` | datetime | When the match started (used for the train/test split) |
| `tier` | string | Rank tier of the player the match was collected from |
| `blue_top` … `blue_support` | int | Champion IDs for the blue side, by role |
| `red_top` … `red_support` | int | Champion IDs for the red side, by role |
| `blue_bans`, `red_bans` | list[int] | Banned champion IDs for each side |
| `blue_win` | bool | `True` if the blue side won |

---

## Methodology

- **Train/test split by date:** The model is trained on earlier matches and tested on later ones, which mirrors how it would be used on new games.
- **Models, in order of complexity:**
  1. **Baseline:** predict wins from each champion's overall win rate.
  2. **Logistic regression** on team picks.
  3. **XGBoost** with synergy (champion pairs on the same team) and counter (champion vs. lane opponent) features.
- **Evaluation:** AUC and log loss, plus a calibration check, so that a predicted 60% chance means a team wins about 60% of the time.
- **Recommendations:** For a partial draft, every legal champion is scored and the top 5 are returned with the synergy and counter effects behind each one.

### Avoiding data leakage
Only information known **during the draft** is used as model input: picks, bans, side, region, and patch. In-game stats such as gold, kills, or objectives are excluded, since they wouldn't be known at draft time.

### Setting expectations
Draft alone predicts the winner only a little better than a coin flip in ranked games, because player skill and in-game play matter far more. The goal is a measurable, honest improvement over the baseline, and the results will be reported as they are, including where the model falls short.

---

## Known limitations

- **Rank labels:** A match is labeled with the tier of the player it was collected from. Other players in the lobby may be in different tiers.
- **Sample imbalance:** Challenger has far fewer players than Diamond, so Diamond matches will make up most of the dataset.
- **Patch drift:** Results apply to the collected patch and need retraining after balance updates.
- **Small samples:** Champions below the minimum game count are excluded, so rarely played picks may not be recommended.
- **Draft only:** The model doesn't account for player skill, champion mastery, or team communication.
- **Development key:** Riot dev keys expire every 24 hours, which limits unattended collection until a personal key is approved.

---

## Roadmap

- [x] **Phase 0 – Setup:** repo, folder layout, uv environment, pytest and Ruff, README, AWS account with budget alert, Riot API key
- [x] **AWS foundation:** S3 bucket (versioning, lifecycle rule), Riot key in Parameter Store, least-privilege IAM user
- [ ] **Phase 1 – Data collection:** Riot API client with rate limiting and retries; player lists, match IDs, and match details for NA, EUW, and KR; patch filtering and de-duplication; raw JSON to S3; tests with mocked responses
- [ ] **Phase 2 – Processing:** one row per match, data checks, Parquet tables in S3
- [ ] **Phase 3 – Modeling:** baseline, logistic regression, XGBoost; date-based split; AUC and log loss; results documented
- [ ] **Phase 4 – Recommender:** score legal champions for a partial draft, top 5 with reasons, tests
- [ ] **Phase 5 – AWS automation:** collector in Lambda, scheduled with EventBridge
- [ ] **Phase 6 – API and front end:** model as a Lambda container image, API Gateway, web page on S3 or Amplify
- [ ] **Phase 7 – CI/CD and polish:** GitHub Actions for tests, lint, and deployment; architecture diagram; "what I learned" write-up

---

## Tech stack

**Now:** Python, uv, boto3, requests, pandas, PyArrow, DuckDB, scikit-learn, XGBoost, pytest, Ruff, AWS (S3, IAM, Systems Manager Parameter Store).

**Planned:** AWS Lambda, EventBridge, API Gateway, Docker (Lambda container images), GitHub Actions.

---

## Legal

LoL Draft Simulator isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

This is a personal, non-commercial portfolio project. Raw match data is not redistributed in this repository.

---

## Author

Jace Daugherty — [GitHub](https://github.com/jacedaugherty4) · [LinkedIn](https://www.linkedin.com/in/jacedaugherty/)