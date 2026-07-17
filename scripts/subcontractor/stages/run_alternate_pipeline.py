from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PipelineStage:
    name: str
    module: str
    description: str


STAGES: tuple[PipelineStage, ...] = (
    PipelineStage(
        name="validate",
        module="scripts.subcontractor.stages.validate_stage1",
        description="Validate Stage 1 inputs.",
    ),
    PipelineStage(
        name="detect",
        module="scripts.subcontractor.stages.parse_alternate_layout",
        description="Detect alternate-layout pages.",
    ),
    PipelineStage(
        name="group",
        module="scripts.subcontractor.stages.group_alternate_layout",
        description="Group pages into bidder blocks.",
    ),
    PipelineStage(
        name="reconcile",
        module="scripts.subcontractor.stages.reconcile_alternate_blocks",
        description="Reconcile blocks with bidder ranks.",
    ),
    PipelineStage(
        name="parse",
        module="scripts.subcontractor.stages.stage2_alternate_parser",
        description="Parse subcontractor disclosures.",
    ),
    PipelineStage(
        name="certify",
        module="scripts.subcontractor.stages.certify_alternate_stage2",
        description="Certify parsed disclosures.",
    ),
    PipelineStage(
        name="identity",
        module="scripts.subcontractor.stages.build_identity_overlay",
        description="Build prime-bidder identity overlay.",
    ),
    PipelineStage(
        name="promote",
        module="scripts.subcontractor.stages.promote_alternate_disclosures",
        description="Promote certified disclosures.",
    ),
)


STAGE_INDEX = {
    stage.name: index
    for index, stage in enumerate(STAGES)
}


def select_stages(
    from_stage: str | None,
    through_stage: str | None,
) -> tuple[PipelineStage, ...]:
    start_index = 0
    end_index = len(STAGES) - 1

    if from_stage is not None:
        start_index = STAGE_INDEX[from_stage]

    if through_stage is not None:
        end_index = STAGE_INDEX[through_stage]

    if start_index > end_index:
        raise ValueError(
            "--from-stage must occur before "
            "--through-stage."
        )

    return STAGES[start_index : end_index + 1]


def print_stage_list() -> None:
    print()
    print("ALTERNATE PIPELINE STAGES")
    print("=" * 100)

    for index, stage in enumerate(
        STAGES,
        start=1,
    ):
        print(
            f"{index:>2}. "
            f"{stage.name:<12} "
            f"{stage.description}"
        )

    print()


def run_stage(
    stage: PipelineStage,
    extra_arguments: Sequence[str],
    dry_run: bool,
) -> int:
    command = [
        sys.executable,
        "-m",
        stage.module,
        *extra_arguments,
    ]

    print("COMMAND")
    print(" ".join(command))
    print()

    if dry_run:
        return 0

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the 2025 alternate-layout "
            "subcontractor pipeline."
        )
    )

    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="List available pipeline stages and exit.",
    )

    parser.add_argument(
        "--from-stage",
        choices=tuple(STAGE_INDEX),
        help="Begin execution at this stage.",
    )

    parser.add_argument(
        "--through-stage",
        choices=tuple(STAGE_INDEX),
        help="Stop after this stage.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )

    parser.add_argument(
        "extra_arguments",
        nargs=argparse.REMAINDER,
        help=(
            "Arguments following -- are passed "
            "to every selected stage."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.list_stages:
        print_stage_list()
        return 0

    try:
        selected_stages = select_stages(
            arguments.from_stage,
            arguments.through_stage,
        )
    except ValueError as error:
        parser.error(str(error))

    extra_arguments = list(
        arguments.extra_arguments
    )

    if (
        extra_arguments
        and extra_arguments[0] == "--"
    ):
        extra_arguments = extra_arguments[1:]

    print()
    print("2025 ALTERNATE SUBCONTRACTOR PIPELINE")
    print("=" * 100)
    print(
        "Selected stages: "
        + " -> ".join(
            stage.name
            for stage in selected_stages
        )
    )
    print(
        f"Dry run: {arguments.dry_run}"
    )

    for index, stage in enumerate(
        selected_stages,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(selected_stages)}] "
            f"{stage.name.upper()}"
        )
        print("-" * 100)
        print(stage.description)
        print()

        return_code = run_stage(
            stage,
            extra_arguments,
            arguments.dry_run,
        )

        if return_code != 0:
            print()
            print(
                f"PIPELINE FAILED AT STAGE: "
                f"{stage.name}",
                file=sys.stderr,
            )
            print(
                f"Exit code: {return_code}",
                file=sys.stderr,
            )
            return return_code

    print()
    print("=" * 100)

    if arguments.dry_run:
        print("ALTERNATE PIPELINE DRY RUN COMPLETED")
    else:
        print("ALTERNATE PIPELINE COMPLETED SUCCESSFULLY")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
