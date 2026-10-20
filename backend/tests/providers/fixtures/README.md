# Chess.com provider fixtures

All fixtures are **synthetic**. They follow the response formats documented at
<https://www.chess.com/news/view/published-data-api> (checked 2026-10-20) but contain
invented usernames, ids, ratings and games. They are not recordings of real responses:
the live API could not be called from the development sandbox. Before release, compare
one real response per endpoint with these fixtures and update them if fields differ.

| File | Endpoint | Scenario |
| ---- | -------- | -------- |
| `profile_full.json` | `/pub/player/{u}` | all documented profile fields |
| `profile_minimal.json` | `/pub/player/{u}` | only `username` and `player_id` |
| `stats_rapid.json` | `/pub/player/{u}/stats` | Rapid section present |
| `stats_no_rapid.json` | `/pub/player/{u}/stats` | player never rated in Rapid |
| `archives.json` | `/pub/player/{u}/games/archives` | valid and invalid archive URLs |
| `archive_empty.json` | `/pub/player/{u}/games/{YYYY}/{MM}` | confirmed empty month |
| `archive_mixed.json` | `/pub/player/{u}/games/{YYYY}/{MM}` | valid, partial and malformed games |
| `not_found.json` | any | documented 404 body |
