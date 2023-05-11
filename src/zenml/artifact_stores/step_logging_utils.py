#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Utilities for step logs."""

import logging
import os
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from zenml.artifact_stores.base_artifact_store_logging_handler import (
    ArtifactStoreLoggingHandler,
)
from zenml.io import fileio
from zenml.logger import get_logger

if TYPE_CHECKING:
    from zenml.artifact_stores import BaseArtifactStore


logger = get_logger(__name__)


def prepare_logs_uri(
    artifact_store: "BaseArtifactStore",
    pipeline_run_id: UUID,
    step_name: str,
    log_key: Optional[str] = None,
) -> str:
    """Generates and prepares a URI for the log file for a step.

    Args:
        artifact_store: The artifact store on which the artifact will be stored.
        pipeline_run_id: The id of the pipeline run.
        step_name: Name of the step.
        log_key: The unique identification key of the log file.

    Returns:
        The URI of the output artifact.
    """
    if log_key is None:
        log_key = str(uuid4())

    logs_base_uri = os.path.join(
        artifact_store.path,
        str(pipeline_run_id),
        step_name,
    )

    # Create the dir
    if not fileio.exists(logs_base_uri):
        fileio.makedirs(logs_base_uri)

    # Delete the file if it already exists
    logs_uri = os.path.join(logs_base_uri, f"{log_key}.log")
    if fileio.exists(logs_uri):
        logger.warning(
            f"Logs file {logs_uri} already exists! Removing old log file..."
        )
        fileio.remove(logs_uri)
    return logs_uri


def get_step_logging_handler(
    artifact_store: "BaseArtifactStore",
    logs_uri: str,
    max_messages: int = 20,
    when: str = "s",
    interval: int = 2,
    backup_count: int = 0,
) -> ArtifactStoreLoggingHandler:
    """Sets up a logging handler for the artifact store.

    Args:
        artifact_store: The artifact store on which the artifact will be stored.
        logs_uri: The URI of the output artifact.
        max_messages: The maximum number of messages before logs are uploaded.
        when: The unit of time to wait between logging.
        interval: The interval of time to wait between logging.
        backup_count: The number of backups to keep.

    Returns:
        The logging handler.
    """
    log_format = "%(asctime)s - %(message)s"
    date_format = "%Y-%m-%dT%H:%M:%S"  # ISO 8601 format
    formatter = logging.Formatter(log_format, datefmt=date_format)

    handler = ArtifactStoreLoggingHandler(
        artifact_store,
        logs_uri,
        max_messages=max_messages,
        when=when,
        interval=interval,
        backupCount=backup_count,
    )
    handler.setFormatter(formatter)
    return handler
