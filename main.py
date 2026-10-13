#!/usr/bin/env python3
"""APEX OVERDRIVE - retro pixel street racer with police pursuit. Run with `make run`."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="APEX OVERDRIVE")
    ap.add_argument("--bot", action="store_true", help="autopilot demo")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--shot", metavar="PNG", help="autopilot, save a screenshot and exit")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--title", action="store_true", help="with --shot: capture the title screen")
    args = ap.parse_args()
    if args.shot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from apex.game import Game
    game = Game(bot=args.bot or (bool(args.shot) and not args.title), mute=args.mute)
    if args.shot:
        game.screenshot(args.shot, args.frames)
    else:
        game.run()


if __name__ == "__main__":
    main()
