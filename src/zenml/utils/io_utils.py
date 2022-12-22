#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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
"""Various utility functions for the io module."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

from zenml.constants import APP_NAME, ENV_ZENML_CONFIG_PATH
from zenml.io.fileio import (
    copy,
    create_dir_recursive_if_not_exists,
    exists,
    isdir,
    listdir,
    open,
)

if TYPE_CHECKING:
    from zenml.io.filesystem import PathType


def get_global_config_directory() -> str:
    """Gets the global config directory for ZenML.

    Returns:
        The global config directory for ZenML.
    """
    env_var_path = os.getenv(ENV_ZENML_CONFIG_PATH)
    if env_var_path:
        return str(Path(env_var_path).resolve())
    return click.get_app_dir(APP_NAME)


def write_file_contents_as_string(file_path: str, content: str) -> None:
    """Writes contents of file.

    Args:
        file_path: Path to file.
        content: Contents of file.

    Raises:
        ValueError: If content is not of type str.
    """
    if not isinstance(content, str):
        raise ValueError(f"Content must be of type str, got {type(content)}")
    with open(file_path, "w") as f:
        f.write(content)


def read_file_contents_as_string(file_path: str) -> str:
    """Reads contents of file.

    Args:
        file_path: Path to file.

    Returns:
        Contents of file.

    Raises:
        FileNotFoundError: If file does not exist.
    """
    if not exists(file_path):
        raise FileNotFoundError(f"{file_path} does not exist!")
    with open(file_path) as f:
        return f.read()  # type: ignore[no-any-return]


# def resolve_relative_path(path: str) -> str:
#     """Takes relative path and resolves it absolutely.

#     Args:
#         path: Local path in filesystem.

#     Returns:
#         Resolved path.
#     """
#     if is_remote(path):
#         return path
#     return str(Path(path).resolve())


def copy_dir(
    source_dir: str, destination_dir: str, overwrite: bool = False
) -> None:
    """Copies dir from source to destination.

    Args:
        source_dir: Path to copy from.
        destination_dir: Path to copy to.
        overwrite: Boolean. If false, function throws an error before overwrite.
    """
    for source_file in listdir(source_dir):
        source_path = os.path.join(source_dir, convert_to_str(source_file))
        destination_path = os.path.join(
            destination_dir, convert_to_str(source_file)
        )
        if isdir(source_path):
            if source_path == destination_dir:
                # if the destination is a subdirectory of the source, we skip
                # copying it to avoid an infinite loop.
                continue
            copy_dir(source_path, destination_path, overwrite)
        else:
            create_dir_recursive_if_not_exists(
                os.path.dirname(destination_path)
            )
            copy(str(source_path), str(destination_path), overwrite)


def get_grandparent(dir_path: str) -> str:
    """Get grandparent of dir.

    Args:
        dir_path: Path to directory.

    Returns:
        Directory name of the input path's parent's parent.

    Raises:
        ValueError: If dir_path does not exist.
    """
    if not os.path.exists(dir_path):
        raise ValueError(f"Path '{dir_path}' does not exist.")
    return Path(dir_path).parent.parent.stem


def get_parent(dir_path: str) -> str:
    """Get parent of dir.

    Args:
        dir_path: Path to directory.

    Returns:
        Parent (stem) of the dir as a string.

    Raises:
        ValueError: If dir_path does not exist.
    """
    if not os.path.exists(dir_path):
        raise ValueError(f"Path '{dir_path}' does not exist.")
    return Path(dir_path).parent.stem


def convert_to_str(path: "PathType") -> str:
    """Converts a PathType to a str using UTF-8.

    Args:
        path: Path to convert.

    Returns:
        Converted path.
    """
    if isinstance(path, str):
        return path
    else:
        return path.decode("utf-8")


def is_root(path: str) -> bool:
    """Returns true if path has no parent in local filesystem.

    Args:
        path: Local path in filesystem.

    Returns:
        True if root, else False.
    """
    return Path(path).parent == Path(path)
