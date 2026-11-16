"""Run the textbook reproduction and UK month-end experiment. 运行教材复现与英国月末实验。"""

import argparse
from pathlib import Path

from experiment import write_results
from run_route_b import SOURCE_DIR, publish_results, run_route_b
from textbook import reproduce_examples


def main():
    """Generate both sets of results under one output root. 为一个输出根目录生成两部分结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    textbook = reproduce_examples()
    sources, uk_tables = run_route_b(SOURCE_DIR)

    # Publish the verified UK results before writing the textbook examples.
    # 先发布已验证的英国结果，再写教材算例。
    publish_results(args.output_dir / "uk", sources, uk_tables)
    write_results(args.output_dir / "textbook", textbook)
    print(f"Textbook: {len(textbook['textbook.csv'])} rows. UK: {len(uk_tables['metrics.csv'])} fits.")
    print(f"结果目录 / Results: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
