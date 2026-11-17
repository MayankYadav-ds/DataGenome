import argparse
import csv
from pathlib import Path
from random import Random


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    random = Random(42)
    rows = [
        (
            index,
            "" if index in {3, 8} else random.randrange(100),
            "batch_a",
            "minority" if index == 19 else "majority",
        )
        for index in range(20)
    ]
    rows.append(rows[0])
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("id", "measurement", "batch", "label"))
        writer.writerows(rows)


if __name__ == "__main__":
    main()
