from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def configure_logging(
    log_directory: Path,
    command_name: str,
) -> tuple[logging.Logger, Path]:
    log_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    log_path = (
        log_directory
        / f"{command_name}_{timestamp}.log"
    )

    logger_name = (
        f"subcontractor.{command_name}"
    )

    logger = logging.getLogger(
        logger_name
    )

    logger.setLevel(
        logging.INFO
    )

    logger.propagate = False
    logger.handlers.clear()

    file_formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )

    console_formatter = logging.Formatter(
        "%(message)s"
    )

    file_handler = logging.FileHandler(
        log_path,
        encoding="utf-8",
    )

    file_handler.setLevel(
        logging.INFO
    )

    file_handler.setFormatter(
        file_formatter
    )

    console_handler = logging.StreamHandler()

    console_handler.setLevel(
        logging.INFO
    )

    console_handler.setFormatter(
        console_formatter
    )

    logger.addHandler(
        file_handler
    )

    logger.addHandler(
        console_handler
    )

    return logger, log_path


def log_section(
    logger: logging.Logger,
    title: str,
    *,
    width: int = 120,
) -> None:
    logger.info("")
    logger.info(title)
    logger.info("=" * width)


def log_subsection(
    logger: logging.Logger,
    title: str,
    *,
    width: int = 120,
) -> None:
    logger.info("")
    logger.info(title)
    logger.info("-" * width)


def log_key_value(
    logger: logging.Logger,
    label: str,
    value: object,
) -> None:
    logger.info(
        "%s: %s",
        label,
        value,
    )
