from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb

from scripts.subcontractor.backup_service import (
    BackupResult,
    format_backup_result,
)
from scripts.subcontractor.framework import (
    FrameworkContext,
)


@dataclass(frozen=True)
class StageResult:
    stage_name: str
    status: str
    started_at: datetime
    completed_at: datetime
    elapsed_seconds: float
    details: dict[str, Any]


class Stage(ABC):
    name = "unnamed-stage"
    description = "No description provided."
    writes_database = False
    backup_reason: str | None = None
    verify_backup_checksum = False

    def __init__(
        self,
        context: FrameworkContext | None = None,
    ) -> None:
        self.context = (
            context
            if context is not None
            else FrameworkContext.load()
        )

        self.connection: (
            duckdb.DuckDBPyConnection | None
        ) = None

        self.backup_result: BackupResult | None = None

    def print_header(self) -> None:
        print()
        print(self.name.upper())
        print("=" * 120)
        print(self.description)

    def validate_environment(self) -> None:
        if not self.context.paths.database.exists():
            raise FileNotFoundError(
                "Database not found: "
                f"{self.context.paths.database}"
            )

        if self.writes_database and not self.backup_reason:
            raise RuntimeError(
                f"Stage '{self.name}' writes to the database "
                "but does not define backup_reason."
            )

    def before_execute(self) -> None:
        pass

    @abstractmethod
    def execute(self) -> dict[str, Any] | None:
        raise NotImplementedError

    def after_execute(
        self,
        details: dict[str, Any],
    ) -> None:
        pass

    def validate_result(
        self,
        details: dict[str, Any],
    ) -> None:
        pass

    def open_connection(self) -> None:
        self.connection = self.context.connect(
            read_only=not self.writes_database
        )

    def close_connection(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def create_backup(self) -> None:
        if not self.writes_database:
            return

        if self.backup_reason is None:
            raise RuntimeError(
                "Backup reason is required."
            )

        print()
        print("CREATING DATABASE BACKUP")
        print("-" * 120)

        self.backup_result = (
            self.context.create_backup(
                self.backup_reason,
                verify_checksum=(
                    self.verify_backup_checksum
                ),
            )
        )

        print(
            format_backup_result(
                self.backup_result
            )
        )

    def run(self) -> StageResult:
        started_at = datetime.now().astimezone()
        started_clock = time.perf_counter()

        self.print_header()

        try:
            self.validate_environment()
            self.create_backup()
            self.open_connection()
            self.before_execute()

            raw_details = self.execute()

            details = (
                raw_details
                if raw_details is not None
                else {}
            )

            self.validate_result(details)
            self.after_execute(details)

            completed_at = datetime.now().astimezone()
            elapsed_seconds = (
                time.perf_counter()
                - started_clock
            )

            result = StageResult(
                stage_name=self.name,
                status="PASSED",
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
                details=details,
            )

            print()
            print("STAGE RESULT")
            print("-" * 120)
            print(f"Status: {result.status}")
            print(
                "Elapsed: "
                f"{result.elapsed_seconds:,.2f} seconds"
            )

            return result

        except Exception:
            completed_at = datetime.now().astimezone()
            elapsed_seconds = (
                time.perf_counter()
                - started_clock
            )

            print()
            print("STAGE RESULT")
            print("-" * 120)
            print("Status: FAILED")
            print(
                "Elapsed: "
                f"{elapsed_seconds:,.2f} seconds"
            )
            print()
            traceback.print_exc()

            raise

        finally:
            self.close_connection()


def run_stage(
    stage_type: type[Stage],
) -> int:
    try:
        result = stage_type().run()
    except Exception:
        return 1

    return (
        0
        if result.status == "PASSED"
        else 1
    )
