
import csv

def inspect_file(filename):
    with open(filename, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    games = {
        (row["session_id"], row["game_id"])
        for row in rows
        if row.get("session_id") and row.get("game_id")
    }

    print(f"\n{filename}")
    print("Total records:", len(rows))
    print("Unique games:", len(games))
    print("Unique sessions:", len({g[0] for g in games}))

    return games

gameplay_games = inspect_file("human_gameplay.csv")
decision_games = inspect_file("human_decisions.csv")

print("\nDataset comparison")
print("Games with no decision records:",
      len(gameplay_games - decision_games))
print("Games with decision records:",
      len(gameplay_games & decision_games))
