from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class QualityStep:
    name: str
    module: str
    arguments: tuple[str, ...] = ()


CHECK_STEPS: tuple[QualityStep, ...] = (
    QualityStep(
        name="Framework verification",
        module="scripts.subcontractor.verify_framework",
    ),
    QualityStep(
        name="Framework doctor",
        module="scripts.subcontractor.doctor",
    ),
)


def discover_test_modules() -> list[str]:
    tests_directory = (
        PROJECT_ROOT
        / "scripts/subcontractor/tests"
    )

    if not tests_directory.exists():
        return []

    modules: list[str] = []

    for path in sorted(
        tests_directory.glob("test_*.py")
    ):
        if path.name == "__init__.py":
            continue

        modules.append(
            "scripts.subcontractor.tests."
            + path.stem
        )

    return modules


def run_module(
    module: str,
    arguments: Sequence[str] = (),
    dry_run: bool = False,
) -> int:
    command = [
        sys.executable,
        "-m",
        module,
        *arguments,
    ]

    print(" ".join(command))

    if dry_run:
        return 0

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    return completed.returncode


def run_tests(
    dry_run: bool,
    stop_on_failure: bool,
) -> int:
    test_modules = discover_test_modules()

    print()
    print("SUBCONTRACTOR TEST SUITE")
    print("=" * 100)

    if not test_modules:
        print("No test modules found.")
        return 0

    failures: list[tuple[str, int]] = []

    for index, module in enumerate(
        test_modules,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(test_modules)}] "
            f"{module}"
        )
        print("-" * 100)

        return_code = run_module(
            module=module,
            dry_run=dry_run,
        )

        if return_code != 0:
            failures.append(
                (
                    module,
                    return_code,
                )
            )

            if stop_on_failure:
                break

    print()
    print("=" * 100)

    if failures:
        print(
            f"TEST SUITE FAILED: "
            f"{len(failures)} failure(s)"
        )

        for module, return_code in failures:
            print(
                f"- {module}: exit code "
                f"{return_code}"
            )

        return 1

    if dry_run:
        print("TEST SUITE DRY RUN COMPLETED")
    else:
        print(
            f"TEST SUITE PASSED: "
            f"{len(test_modules)} test module(s)"
        )

    return 0


def run_check(
    dry_run: bool,
) -> int:
    print()
    print("SUBCONTRACTOR QUALITY GATE")
    print("=" * 100)

    for index, step in enumerate(
        CHECK_STEPS,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(CHECK_STEPS) + 1}] "
            f"{step.name.upper()}"
        )
        print("-" * 100)

        return_code = run_module(
            module=step.module,
            arguments=step.arguments,
            dry_run=dry_run,
        )

        if return_code != 0:
            print()
            print(
                f"QUALITY GATE FAILED: "
                f"{step.name}",
                file=sys.stderr,
            )
            return return_code

    print()
    print(
        f"[{len(CHECK_STEPS) + 1}/"
        f"{len(CHECK_STEPS) + 1}] TESTS"
    )
    print("-" * 100)

    return_code = run_tests(
        dry_run=dry_run,
        stop_on_failure=True,
    )

    if return_code != 0:
        print()
        print(
            "QUALITY GATE FAILED: tests",
            file=sys.stderr,
        )
        return return_code

    print()
    print("=" * 100)

    if dry_run:
        print("QUALITY GATE DRY RUN COMPLETED")
    else:
        print("QUALITY GATE PASSED")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Quality and test commands for the "
            "subcontractor-processing framework."
        )
    )

    subparsers = parser.add_subparsers(
        dest="operation",
        required=True,
    )

    test_parser = subparsers.add_parser(
        "test",
        help="Run all subcontractor test modules.",
    )

    test_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print test commands without running them.",
    )

    test_parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Run all tests even after a test fails.",
    )

    check_parser = subparsers.add_parser(
        "check",
        help=(
            "Run framework verification, doctor, "
            "and the complete test suite."
        ),
    )

    check_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print quality-gate commands without running them.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.operation == "test":
        return run_tests(
            dry_run=arguments.dry_run,
            stop_on_failure=(
                not arguments.continue_on_failure
            ),
        )

    if arguments.operation == "check":
        return run_check(
            dry_run=arguments.dry_run,
        )

    parser.error(
        f"Unsupported operation: "
        f"{arguments.operation}"
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
