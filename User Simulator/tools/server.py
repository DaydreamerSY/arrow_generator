"""
HTTP API server for the simulator UI.

Usage:
    cd "User Simulator"
    python tools/server.py [--port 8080]

Then open http://localhost:8080 in browser.
Serves ui.html and provides /api/simulate endpoint with progress logging.
"""

import argparse
import copy
import csv
import http.server
import json
import os
import random
import statistics
import sys
import threading
import time
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import (
    PLAYER_MIX,
    PLAYER_PROFILES,
    BoosterConfig,
    LevelOverheadConfig,
    PlayerProfile,
    SimulationConfig,
    SkillConfig,
)
from engine import Board, load_level, compute_level_metrics
from game_adapter import ArrowEscapeAdapter
from user_model import UserModel


PROJECT_ROOT = Path(__file__).parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
#  Dataset Discovery & Feed Data
# ═══════════════════════════════════════════════════════════════════════════════

def list_datasets():
    """Scan data/versions/ — each version folder has test_data/ and feed_data/ inside."""
    versions_dir = PROJECT_ROOT / "data" / "versions"
    versions = []

    if versions_dir.exists():
        for d in sorted(versions_dir.iterdir()):
            if not d.is_dir():
                continue

            info = {"name": d.name, "test_levels": 0, "has_feed": False, "glossary": "", "reports": []}

            # Count test data levels
            td = d / "test_data"
            if td.exists():
                info["test_levels"] = len(list(td.glob("*.json")))

            # Check feed data
            fd = d / "feed_data"
            if fd.exists() and list(fd.glob("*.csv")):
                info["has_feed"] = True
                gpath = fd / "Glossary.md"
                if gpath.exists():
                    info["glossary"] = gpath.read_text(encoding="utf-8")

            # List report files
            rd = d / "report"
            if rd.exists():
                info["reports"] = sorted(f.name for f in rd.iterdir() if f.is_file())

            # Only include versions that have at least test data
            if info["test_levels"] > 0:
                versions.append(info)

    return {"versions": versions}


# Cache keyed by folder name to support multiple datasets
_feed_cache = {}

def load_feed_data(folder_name="current"):
    """Load feed data from data/versions/<folder_name>/feed_data/."""
    if folder_name in _feed_cache:
        return _feed_cache[folder_name]

    feed_dir = PROJECT_ROOT / "data" / "versions" / folder_name / "feed_data"
    pt, eng = {}, {}

    pt_path = feed_dir / "Level playtime.csv"
    if pt_path.exists():
        with open(pt_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lvl = int(row["level"])
                pt[lvl] = {
                    "avg_time": float(row["Avg time spent (minutes)"]),
                    "med_time": float(row["Median time spent (minutes)"]),
                    "avg_attempts": float(row["avg attempts"]),
                }

    eng_path = feed_dir / "Level engagement.csv"
    if eng_path.exists():
        with open(eng_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lvl = int(row["level"])
                eng[lvl] = {
                    "start": int(row["start"]),
                    "win_rate": float(row["Win Rate %"]),
                    "fail_rate": float(row["fail rate %"]),
                }

    _feed_cache[folder_name] = (pt, eng)
    return pt, eng


# ═══════════════════════════════════════════════════════════════════════════════
#  Per-Level Simulation
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_level(board, sim_config, n_players, seed, profiles, mix):
    """Run per-level simulation with LOCAL copies of profiles/mix (no global mutation)."""
    rng = random.Random(seed)
    acfg = sim_config.attempt
    all_times_ms, all_attempts = [], []
    wins, total_matches, total_wins = 0, 0, 0

    profiles_list = list(profiles.keys())
    weights = [mix[p] for p in profiles_list]

    for ui in range(n_players):
        chosen = rng.choices(profiles_list, weights=weights, k=1)[0]
        user = UserModel(ui + seed, profiles[chosen], sim_config)
        adapter = ArrowEscapeAdapter(board, user, sim_config)
        total_time, won = 0.0, False

        for att_num in range(acfg.max_attempts):
            result = adapter.simulate_attempt(att_num)
            total_time += result.time_ms
            total_matches += 1
            if result.won:
                won = True
                total_wins += 1
                break
            if user.should_give_up(att_num + 1):
                break

        if won:
            wins += 1
        all_times_ms.append(total_time)
        all_attempts.append(att_num + 1)

    times_min = [t / 60_000.0 for t in all_times_ms]
    return {
        "avg_time": statistics.mean(times_min) if times_min else 0,
        "med_time": statistics.median(times_min) if times_min else 0,
        "avg_attempts": statistics.mean(all_attempts) if all_attempts else 1,
        "win_rate": wins / n_players if n_players > 0 else 0,
        "fail_rate": 1 - (total_wins / total_matches) if total_matches > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  API Handler
# ═══════════════════════════════════════════════════════════════════════════════

def handle_simulate(body):
    """Handle /api/simulate POST — returns JSON results."""
    config = json.loads(body)
    t_start = time.time()

    sim_config = SimulationConfig(
        cohort_size=config.get("cohort", 500),
        random_seed=config.get("seed", 42),
    )

    # Apply booster config
    bcfg = config.get("booster", {})
    sim_config.booster.enabled = bcfg.get("enabled", True)
    sim_config.booster.hint_per_attempt = bcfg.get("hint_per_attempt", 5)
    sim_config.booster.scissors_per_attempt = bcfg.get("scissors_per_attempt", 5)
    sim_config.booster.wand_per_attempt = bcfg.get("wand_per_attempt", 5)

    # Apply overhead
    ocfg = config.get("overhead", {})
    sim_config.overhead.level_load_time_ms = ocfg.get("level_load_time_ms", 1500)
    sim_config.overhead.win_celebration_ms = ocfg.get("win_celebration_ms", 2000)

    # Build LOCAL profile copies (never mutate globals)
    profiles = copy.deepcopy(PLAYER_PROFILES)
    mix = copy.deepcopy(PLAYER_MIX)

    pcfg = config.get("profiles", {})
    for key, overrides in pcfg.items():
        if key in profiles:
            p = profiles[key]
            if "scan" in overrides: p.scan_time_per_arrow = overrides["scan"]
            if "decision" in overrides: p.decision_time_base = overrides["decision"]
            if "tap" in overrides: p.tap_time = overrides["tap"]
            if "miss" in overrides: p.miss_probability = overrides["miss"]
            if "mistake" in overrides: p.mistake_rate = overrides["mistake"]
            if "fatigue" in overrides: p.fatigue_factor = overrides["fatigue"]
            if "frustration" in overrides: p.frustration_buildup_rate = overrides["frustration"]
            if "booster" in overrides: p.booster_willingness = overrides["booster"]

    mcfg = config.get("mix", {})
    for key, weight in mcfg.items():
        if key in mix:
            mix[key] = weight

    # Load levels from selected version folder
    version = config.get("version", "current")
    levels_dir = PROJECT_ROOT / "data" / "versions" / version / "test_data"
    # Fallback to old path if new structure not found
    if not levels_dir.exists():
        levels_dir = PROJECT_ROOT / "data" / "levels"
    level_files = list(levels_dir.glob("*.json"))

    def eid(p):
        try: return int(p.stem.split("_")[1])
        except: return 0
    level_files.sort(key=eid)

    # Load feed data from the same version folder
    feed_pt, feed_eng = load_feed_data(version)
    feed_ids = set(feed_pt.keys())
    level_files = [f for f in level_files if eid(f) in feed_ids]

    # Filter by level range (from/to) instead of maxLevels
    level_from = config.get("levelFrom", 1)
    level_to = config.get("levelTo", 9999)
    level_files = [f for f in level_files if level_from <= eid(f) <= level_to]

    cohort = config.get("cohort", 500)
    total = len(level_files)
    print(f"\n[SIM] Starting: {total} levels (L{level_from}–L{level_to}) × {cohort} players (seed={config.get('seed', 42)})")

    # Simulate each level with progress logging
    results = []
    for i, lf in enumerate(level_files):
        board = load_level(str(lf))
        lvl = board.level_id
        metrics = compute_level_metrics(board)

        t0 = time.time()
        sr = simulate_level(board, sim_config, cohort, config.get("seed", 42) + lvl, profiles, mix)
        dt = time.time() - t0

        fp = feed_pt.get(lvl, {})
        fe = feed_eng.get(lvl, {})

        results.append({
            "level": lvl,
            "board": f"{board.width}x{board.height}",
            "arrows": len(board.arrows),
            "difficulty": round(metrics.difficulty_score, 3),
            "sim_avg": round(sr["avg_time"], 3),
            "feed_avg": round(fp.get("avg_time", 0), 3),
            "sim_wr": round(sr["win_rate"], 4),
            "feed_wr": round(fe.get("win_rate", 0), 4),
            "sim_att": round(sr["avg_attempts"], 4),
            "feed_att": round(fp.get("avg_attempts", 0), 4),
        })

        # Progress log every 10 levels or if a level takes >1s
        if (i + 1) % 10 == 0 or dt > 1.0:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"[SIM] {i+1}/{total} levels | L{lvl} {dt:.1f}s | "
                  f"elapsed {elapsed:.0f}s | ETA {eta:.0f}s")

    elapsed = time.time() - t_start
    print(f"[SIM] Done: {total} levels in {elapsed:.1f}s\n")

    # ── Auto-save CSVs to version's report/ folder ──────────────────────────
    report_dir = PROJECT_ROOT / "data" / "versions" / version / "report"
    report_dir.mkdir(exist_ok=True)

    playtime_path = report_dir / "Sim_Level_playtime.csv"
    with open(playtime_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["level", "board", "arrows", "difficulty",
                         "sim_avg_min", "feed_avg_min", "ratio",
                         "sim_med_min", "feed_med_min"])
        for r in results:
            ratio = round(r["sim_avg"] / r["feed_avg"], 4) if r["feed_avg"] > 0 else ""
            writer.writerow([r["level"], r["board"], r["arrows"], r["difficulty"],
                             r["sim_avg"], r["feed_avg"], ratio, "", ""])

    engagement_path = report_dir / "Sim_Level_engagement.csv"
    with open(engagement_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["level", "sim_win_rate", "feed_win_rate", "wr_diff_pp",
                         "sim_attempts", "feed_attempts", "att_diff"])
        for r in results:
            wr_diff = round((r["sim_wr"] - r["feed_wr"]) * 100, 3)
            att_diff = round(r["sim_att"] - r["feed_att"], 4)
            writer.writerow([r["level"], r["sim_wr"], r["feed_wr"], wr_diff,
                             r["sim_att"], r["feed_att"], att_diff])

    print(f"[SIM] Reports saved to {report_dir}/")

    return json.dumps({"levels": results})


# ═══════════════════════════════════════════════════════════════════════════════
#  HTTP Server
# ═══════════════════════════════════════════════════════════════════════════════

class SimHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/ui.html"
        elif self.path == "/api/datasets":
            # Return available test_data and feed_data folders
            try:
                result = list_datasets()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return
        elif self.path == "/favicon.ico":
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return super().do_GET()

    def log_message(self, format, *args):
        msg = format % args
        if "/favicon.ico" in msg:
            return
        super().log_message(format, *args)

    def do_POST(self):
        if self.path == "/api/simulate":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                result = handle_simulate(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(result.encode("utf-8"))
            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="Simulator UI Server")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    os.chdir(str(PROJECT_ROOT))

    server = http.server.HTTPServer(("0.0.0.0", args.port), SimHandler)
    print(f"Server running at http://localhost:{args.port}")
    print(f"Open in browser to use the simulator UI")
    print(f"Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
