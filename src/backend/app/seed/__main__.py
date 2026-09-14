"""app/seed/__main__.py — allows python -m app.seed to invoke seed.py."""
import asyncio
import argparse

from app.seed import _run_seed


def main():
    parser = argparse.ArgumentParser(description="Seed the supply chain database.")
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )
    args = parser.parse_args()
    asyncio.run(_run_seed(args.seed))


if __name__ == "__main__":
    main()
