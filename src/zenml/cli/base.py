#  Copyright (c) ZenML GmbH 2020. All Rights Reserved.
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

from pathlib import Path
from typing import Optional

import click

from zenml.cli.cli import cli
from zenml.cli.utils import confirmation, declare, error, warning
from zenml.config.global_config import GlobalConfiguration
from zenml.console import console
from zenml.constants import REPOSITORY_DIRECTORY_NAME
from zenml.exceptions import InitializationException
from zenml.io import fileio
from zenml.io.utils import get_global_config_directory, is_remote
from zenml.repository import Repository


@cli.command("init", help="Initialize a ZenML repository.")
@click.option(
    "--path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=Path
    ),
)
def init(path: Optional[Path]) -> None:
    """Initialize ZenML on given path.

    Args:
      path: Path to the repository.

    Raises:
        InitializationException: If the repo is already initialized.
    """
    if path is None:
        path = Path.cwd()

    with console.status(f"Initializing ZenML repository at {path}.\n"):
        try:
            Repository.initialize(root=path)
            declare(f"ZenML repository initialized at {path}.")
        except InitializationException as e:
            error(f"{e}")

    cfg = GlobalConfiguration()
    declare(
        f"The local active profile was initialized to "
        f"'{cfg.active_profile_name}' and the local active stack to "
        f"'{cfg.active_stack_name}'. This local configuration will only take "
        f"effect when you're running ZenML from the initialized repository "
        f"root, or from a subdirectory. For more information on profile "
        f"and stack configuration, please visit "
        f"https://docs.zenml.io."
    )


def _delete_local_artifact_metadata(force_delete: bool = False) -> None:
    """Delete local metadata and artifact stores from the active stack."""
    if not force_delete:
        confirm = confirmation(
            "DANGER: This will completely delete anything inside the folders for the following stack components: \n"
            "- local metadata store \n"
            "- local artifact store. \n\n"
            "Are you sure you want to proceed?"
        )
        if not confirm:
            declare("Aborting clean.")
            return

    repo = Repository()
    if repo.active_stack:
        metadata_store_path = (
            Path(repo.active_stack.metadata_store.local_path)
            if repo.active_stack.metadata_store.local_path
            else None
        )
        artifact_store_path = Path(repo.active_stack.artifact_store.path)
        if (
            metadata_store_path
            and not is_remote(str(metadata_store_path))
            and not is_remote(str(artifact_store_path))
        ):
            # delete all files inside those directories
            for path in metadata_store_path.iterdir():
                if fileio.isdir(str(path)):
                    fileio.rmtree(str(path))
                else:
                    fileio.remove(str(path))
            for path in artifact_store_path.iterdir():
                if fileio.isdir(str(path)):
                    fileio.rmtree(str(path))
                else:
                    fileio.remove(str(path))
    declare(
        "Deleted all files from within the local active metadata and artifact store."
    )


@cli.command("clean", hidden=True)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Don't ask for confirmation.",
)
@click.option(
    "--local",
    "-l",
    is_flag=True,
    default=False,
    help="Delete local metadata and artifact stores from the active stack.",
)
def clean(yes: bool = False, local: bool = False) -> None:
    """Delete all ZenML metadata, artifacts, profiles and stacks.

    This is a destructive operation, primarily intended for use in development.

    Args:
      yes (flag; default value = False): If you don't want a confirmation prompt.
      local (flag; default value = False): If you want to delete local metadata and artifact stores from the active stack.
    """
    if local:
        if yes:
            _delete_local_artifact_metadata(True)
        else:
            _delete_local_artifact_metadata()
        return

    if not yes:
        confirm = confirmation(
            "DANGER: This will completely delete all artifacts, metadata, stacks and profiles \n"
            "ever created during the use of ZenML. Pipelines and stack components running non-\n"
            "locally will still exist. Please delete those manually. \n\n"
            "Are you sure you want to proceed?"
        )

    if yes or confirm:
        # delete the .zen folder
        local_zen_repo_config = Path.cwd() / REPOSITORY_DIRECTORY_NAME
        if fileio.exists(str(local_zen_repo_config)):
            fileio.rmtree(str(local_zen_repo_config))
            declare(f"Deleted local ZenML config from {local_zen_repo_config}.")

        # delete the profiles (and stacks)
        global_zen_config = Path(get_global_config_directory())
        if fileio.exists(str(global_zen_config)):
            gc = GlobalConfiguration()
            for dir_name in fileio.listdir(str(global_zen_config)):
                if fileio.isdir(str(global_zen_config / str(dir_name))):
                    warning(
                        f"Deleting '{str(dir_name)}' directory from global config."
                    )
            fileio.rmtree(str(global_zen_config))
            declare(f"Deleted global ZenML config from {global_zen_config}.")
            fresh_gc = GlobalConfiguration(
                user_id=gc.user_id,
                analytics_opt_in=gc.analytics_opt_in,
                version=gc.version,
            )
            fresh_gc._add_and_activate_default_profile()
            declare(f"Reinitialized ZenML global config at {Path.cwd()}.")

    else:
        declare("Aborting clean.")
