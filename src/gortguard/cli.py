import argparse
import sys
from pathlib import Path

from gortguard import __version__
from gortguard import pack as P


def _bundles(_):
    print("Presets (pick the one closest to your bot):")
    for name, p in P.PRESETS.items():
        print(f"  {name:<20} {p['about']}  [{', '.join(p['bundles'])}]")
    print("\nBundles (add or swap with --bundles):")
    for name, b in P.BUNDLES.items():
        n = len(P.bundle_patterns(name))
        print(f"  {name:<20} {n:>3} patterns  {b['about']}")
        print(f"  {'':<20}      also: {', '.join(b['aliases'])}")
    print(f"\nLater (not chat layer): {', '.join(P.LATER)}")
    print('Find a bundle by topic: gort search "transfer to a person"')


def _show(args):
    name = P.resolve_bundle(args.bundle)
    b = P.BUNDLES[name]
    print(f"{name}: {b['about']}\nFamilies: {', '.join(b['families'])}\n")
    for p in P.bundle_patterns(name):
        print(f"  {p['id']:<45} {p['name']}")


def _search(args):
    bundles, patterns = P.search(" ".join(args.words))
    if not bundles:
        print("No bundle or pattern matches. Try fewer or other words, or run `gort bundles`.")
        return 1
    print("Bundles:")
    for name in bundles:
        print(f"  {name:<20} {P.BUNDLES[name]['about']}")
    if patterns:
        print("\nPatterns:")
        for p in patterns[:15]:
            print(f"  {p['id']:<45} in {P.bundle_of(p['family'])}")
        if len(patterns) > 15:
            print(f"  ... and {len(patterns) - 15} more")
    return 0


def _build(args):
    split = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]
    pk = P.pack(args.preset, split(args.bundles), split(args.exclude))
    text = pk.policy()
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        Path(args.checklist).write_text(pk.checklist(), encoding="utf-8")
        n = len(pk.prompt_patterns)
        print(f"Wrote {args.output}: {n} prompt rules from {', '.join(pk.bundles)}.")
        print("Place it in your system prompt with a {{gort_policy}} placeholder.")
        print(f"Wrote {args.checklist}: {len(pk.patterns) - n} fixes for code, the chat widget or your")
        print("process, kept out of the prompt because the model cannot carry them out.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gort", description="GORT: best-practice packs for chat agents.")
    parser.add_argument("--version", action="version", version=f"gort {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("bundles", help="list presets and bundles").set_defaults(fn=_bundles)
    s = sub.add_parser("show", help="list the patterns in one bundle")
    s.add_argument("bundle")
    s.set_defaults(fn=_show)
    s = sub.add_parser("search", help="find bundles and patterns by words")
    s.add_argument("words", nargs="+")
    s.set_defaults(fn=_search)
    s = sub.add_parser("build", help="write the policy block for a preset or bundles")
    s.add_argument("--preset")
    s.add_argument("--bundles", help="comma-separated bundle names or aliases")
    s.add_argument("--exclude", help="comma-separated Pattern IDs to leave out")
    s.add_argument("-o", "--output", default="gort-policy.md", help="policy file to write, or - for stdout")
    s.add_argument("--checklist", default="gort-checklist.md", help="file for fixes that are not prompt text")
    s.set_defaults(fn=_build)
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    try:
        return args.fn(args) or 0
    except ValueError as e:
        print(f"gort: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
