from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from .config import AppConfig, default_paths
from .pipeline import Pipeline
from .storage import db as dbmod


def semi_auto_review(text: str) -> Optional[str]:
    print("\nCandidate:")
    print("-" * 60)
    print(text)
    print("-" * 60)
    print("[y] send  [n] skip  [e] edit  [q] quit")
    while True:
        try:
            choice = input("> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "__QUIT__"
        if choice == "y":
            return text
        if choice == "n":
            return None
        if choice == "e":
            print("Edit. End with Enter.")
            try:
                text = input("new> ")
            except (KeyboardInterrupt, EOFError):
                return "__QUIT__"
            return text
        if choice == "q":
            return "__QUIT__"


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI Danmaku Assistant (offline-first)")
    parser.add_argument("--live-url", type=str, default="", help="Live room URL (open and login manually)")
    parser.add_argument("--semi", action="store_true", help="Enable semi-auto review mode")
    parser.add_argument("--interval", type=int, default=45, help="Generation interval (sec)")
    args = parser.parse_args(argv)

    # Use project root detected from package location
    paths = default_paths()
    cfg = AppConfig.load(paths["config"])  # load if exists
    if args.live_url:
        cfg.live_url = args.live_url
    if args.interval:
        cfg.loop.gen_interval_sec = args.interval
    cfg.save(paths["config"])  # persist updates

    pl = Pipeline(cfg, paths)

    print("Starting Safari. Ensure Develop -> Allow Remote Automation is enabled.")
    pl.start()
    print("Safari started. Please login if required and keep the room open.")

    try:
        last = 0.0
        while True:
            pl._update_recent()
            now = time.time()
            if now - last >= cfg.loop.gen_interval_sec:
                last = now
                cand = pl.generate_candidate()
                if args.semi:
                    reviewed = semi_auto_review(cand)
                    if reviewed == "__QUIT__":
                        print("Exiting by user.")
                        break
                    if reviewed is None:
                        continue
                    cand = reviewed
                # store message and tts
                msg_id = dbmod.insert_message(pl.conn, int(now), "ai", cand, source="generator", extra_json="")
                try:
                    audio = pl.tts_and_archive(cand, msg_id)
                    dbmod.insert_action(pl.conn, int(time.time()), "tts", msg_id, "ok", str(audio))
                except Exception as e:
                    dbmod.insert_action(pl.conn, int(time.time()), "tts", msg_id, "error", str(e))
                # send
                ok = pl.send(cand)
                dbmod.insert_action(pl.conn, int(time.time()), "send", msg_id, "ok" if ok else "fail", "")
                print(f"Sent: {ok} - {cand}")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nExiting by user (Ctrl+C).")
    finally:
        pl.stop()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        # As an extra guard; main already handles it.
        pass
