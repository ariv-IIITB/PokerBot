"""Action profile: per bot and street, what it does when checked to vs facing a bet.
Usage: python3 -m lab.opps.profile tier2 opp3 3 [--variant SPEC]   (3 duplicate pairs, locks off)
A thin front for `python -m lab.eval BRAIN --pool OPP --report profile --locks off`."""
import argparse

from lab.eval import DEFAULT_VARIANT, main as eval_main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brain")
    ap.add_argument("opponent")
    ap.add_argument("pairs", type=int)
    ap.add_argument("--variant", default=DEFAULT_VARIANT)
    args = ap.parse_args(argv)
    return eval_main([args.brain, "--pool", args.opponent, "--pairs", str(args.pairs),
                      "--locks", "off", "--report", "profile", "--variant", args.variant])


if __name__ == "__main__":
    raise SystemExit(main())
