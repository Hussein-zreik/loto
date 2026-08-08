"""
Lebanese LOTO archive — command-line analyser
---------------------------------------------
Mirrors the scoring/rules logic in index.html so a combination can be analysed
without opening the site, and checked against the full historical archive.

USAGE:
    python analyze.py 4 17 23 34 38 41        # analyse one combination
    python analyze.py 4 17 23 34 38 41 --json # machine-readable output
    python analyze.py --stats                 # archive-wide statistics
    python analyze.py --generate 5            # generate sets passing default rules

No third-party dependencies — just Python 3 and data.json.
"""

import argparse
import json
import random
import sys
from collections import Counter
from datetime import date
from math import comb
from pathlib import Path

DATA = Path(__file__).parent / "data.json"
N, K = 42, 6
TOTAL = comb(N, K)


def load():
    d = json.loads(DATA.read_text())
    return d["draws"]


# --- helpers shared with index.html -----------------------------------------

def max_run(s):
    run = mx = 1
    for i in range(1, len(s)):
        run = run + 1 if s[i] == s[i - 1] + 1 else 1
        mx = max(mx, run)
    return mx


def is_arithmetic(s):
    step = s[1] - s[0]
    return step > 0 and all(s[i] - s[i - 1] == step for i in range(1, len(s)))


def crowding(s, draws):
    """Same weights as crowdingScore() in index.html."""
    s = sorted(s)
    score, flags = 0, []
    u32 = len([n for n in s if n <= 31])
    if u32 == 6:
        score += 35
        flags.append("all six <=31 (birthday range) — the most crowded pattern there is")
    elif u32 == 5:
        score += 12
        flags.append("five of six <=31 (birthday range)")
    if len([n for n in s if n <= 12]) >= 5:
        score += 10
        flags.append("five or more <=12 (month numbers)")
    mr = max_run(s)
    if mr >= 4:
        score += 22
        flags.append(f"run of {mr} consecutive numbers")
    elif mr == 3:
        score += 8
        flags.append("three consecutive numbers")
    if is_arithmetic(s):
        score += 25
        flags.append(f"arithmetic sequence (step {s[1] - s[0]})")
    if all(n % 2 == 0 for n in s) or all(n % 2 for n in s):
        score += 8
        flags.append("all even or all odd")
    if all(n % 5 == 0 for n in s):
        score += 12
        flags.append("all multiples of 5")
    if len(set(n % 10 for n in s)) <= 2:
        score += 10
        flags.append("only one or two distinct last digits")
    if sum(s) < 100:
        score += 8
        flags.append(f"low sum ({sum(s)})")
    hit = next((d for d in draws if sorted(d["numbers"]) == s), None)
    if hit:
        score += 15
        flags.append(f"this exact combination was drawn on {hit['date']}")
    if not flags:
        flags.append("no common crowding patterns — a genuinely uncrowded ticket")
    return min(100, score), flags, hit


def word(v):
    return "CROWDED" if v >= 55 else "MODERATE" if v >= 25 else "UNCROWDED"


DEFAULT_RULES = {
    "min numbers >31 (>=2)":       lambda s: len([n for n in s if n > 31]) >= 2,
    "max consecutive run (<=2)":   lambda s: max_run(s) <= 2,
    "odd count between 2 and 4":   lambda s: 2 <= len([n for n in s if n % 2]) <= 4,
    "sum between 110 and 190":     lambda s: 110 <= sum(s) <= 190,
    "spread >= 20":                lambda s: (s[-1] - s[0]) >= 20,
    "no arithmetic sequence":      lambda s: not is_arithmetic(s),
}


def analyse(nums, draws, as_json=False):
    s = sorted(nums)
    score, flags, hit = crowding(s, draws)
    freq = Counter(n for d in draws for n in d["numbers"])
    last_seen = {}
    for d in draws:  # draws are newest-first
        for n in d["numbers"]:
            last_seen.setdefault(n, d["date"])

    # closest historical overlap
    best = []
    for d in draws:
        ov = len(set(d["numbers"]) & set(s))
        if ov >= 4:
            best.append((ov, d["date"], sorted(d["numbers"])))
    best.sort(reverse=True)

    if as_json:
        print(json.dumps({
            "numbers": s, "sum": sum(s), "spread": s[-1] - s[0],
            "odd": len([n for n in s if n % 2]), "above31": len([n for n in s if n > 31]),
            "crowding": score, "verdict": word(score), "flags": flags,
            "drawn_before": hit["date"] if hit else None,
            "rules_failed": [k for k, f in DEFAULT_RULES.items() if not f(s)],
            "odds": {"match6": TOTAL},
        }, indent=2))
        return

    odd = len([n for n in s if n % 2])
    print(f"\n  {'  '.join(f'{n:2d}' for n in s)}")
    print(f"  {'-' * 34}")
    print(f"  sum {sum(s)} · spread {s[-1]-s[0]} · {odd} odd / {6-odd} even · "
          f"{len([n for n in s if n > 31])} above 31")
    print(f"\n  CROWDING: {score}/100 — {word(score)}")
    for f in flags:
        print(f"    · {f}")

    failed = [k for k, f in DEFAULT_RULES.items() if not f(s)]
    print(f"\n  DEFAULT RULES: {len(DEFAULT_RULES)-len(failed)}/{len(DEFAULT_RULES)} passed")
    for k in failed:
        print(f"    x fails: {k}")

    print("\n  PER-NUMBER HISTORY (frequency out of "
          f"{len(draws)} draws, expected {len(draws)*6/42:.0f}):")
    for n in s:
        print(f"    {n:2d}: drawn {freq[n]:3d}x   last seen {last_seen.get(n,'never')}")

    if best:
        print("\n  CLOSEST HISTORICAL DRAWS:")
        for ov, dt, nums2 in best[:3]:
            print(f"    {ov}/6 match on {dt}: {'  '.join(f'{x:2d}' for x in nums2)}")
    else:
        print("\n  CLOSEST HISTORICAL DRAWS: never matched 4+ of these in 2,421 draws")

    print(f"\n  ODDS (unchanged by any of the above): 1 in {TOTAL:,} to match all six.\n")


def stats(draws):
    freq = Counter(n for d in draws for n in d["numbers"])
    exp = len(draws) * 6 / 42
    chi = sum((v - exp) ** 2 / exp for v in freq.values())
    print(f"\n  {len(draws)} draws · {draws[-1]['date']} .. {draws[0]['date']}")
    print(f"  expected per number: {exp:.1f}")
    print(f"  most drawn:  {', '.join(f'{n}({c})' for n,c in freq.most_common(5))}")
    print(f"  least drawn: {', '.join(f'{n}({c})' for n,c in freq.most_common()[-5:])}")
    print(f"\n  chi-square = {chi:.1f} (df=41, 5% critical = 56.9)")
    print("  => " + ("consistent with a FAIR draw — no number has an edge"
                     if chi < 56.9 else "deviation worth a closer look"))
    sums = [sum(d["numbers"]) for d in draws]
    print(f"\n  draw sums: min {min(sums)} · median {sorted(sums)[len(sums)//2]} · max {max(sums)}")
    print(f"  all six <=31: {sum(1 for d in draws if all(n<=31 for n in d['numbers']))} draws "
          f"({comb(31,6)/TOTAL*100:.1f}% of the combination space)\n")


def generate(n, draws):
    out, tries = [], 0
    while len(out) < n and tries < 500000:
        tries += 1
        c = sorted(random.sample(range(1, 43), 6))
        if all(f(c) for f in DEFAULT_RULES.values()) and crowding(c, draws)[0] <= 15:
            out.append(c)
    print()
    for c in out:
        odd = len([x for x in c if x % 2])
        print(f"  {'  '.join(f'{x:2d}' for x in c)}   sum {sum(c):3d} · {odd}odd/{6-odd}even")
    print(f"\n  {len(out)} set(s) from {tries:,} random draws. "
          f"Each has the same 1-in-{TOTAL:,} chance.\n")


def main():
    ap = argparse.ArgumentParser(description="Analyse Lebanese LOTO combinations.")
    ap.add_argument("numbers", nargs="*", type=int, help="six numbers, 1-42")
    ap.add_argument("--stats", action="store_true", help="archive-wide statistics")
    ap.add_argument("--generate", type=int, metavar="N", help="generate N rule-passing sets")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    draws = load()
    if a.stats:
        stats(draws); return
    if a.generate:
        generate(a.generate, draws); return
    if len(a.numbers) != 6:
        ap.error("give exactly six numbers, or use --stats / --generate")
    if len(set(a.numbers)) != 6 or not all(1 <= n <= 42 for n in a.numbers):
        ap.error("numbers must be six different values between 1 and 42")
    analyse(a.numbers, draws, a.json)


if __name__ == "__main__":
    main()
