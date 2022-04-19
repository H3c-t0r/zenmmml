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

import pytest
from click.testing import CliRunner

from zenml.artifact_stores import LocalArtifactStore
from zenml.cli.stack import describe_stack, update_stack
from zenml.orchestrators import LocalOrchestrator
from zenml.secrets_managers.local.local_secrets_manager import (
    LocalSecretsManager,
)
from zenml.stack import Stack

NOT_STACKS = ["abc", "my_other_cat_is_called_blupus", "stack123"]

# TODO [HIGH]: Add tests for these commands using REST, SQL and local options


def test_stack_describe_contains_local_stack() -> None:
    """Test that the stack describe command contains the default local stack"""
    runner = CliRunner()
    result = runner.invoke(describe_stack)
    assert result.exit_code == 0
    assert "default" in result.output


@pytest.mark.parametrize("not_a_stack", NOT_STACKS)
def test_stack_describe_fails_for_bad_input(
    not_a_stack: str,
) -> None:
    """Test that the stack describe command fails when passing in bad parameters"""
    runner = CliRunner()
    result = runner.invoke(describe_stack, [not_a_stack])
    assert result.exit_code == 1


def test_updating_active_stack_succeeds(clean_repo) -> None:
    """Test stack update of active stack succeeds."""
    new_artifact_store = LocalArtifactStore(name="arias_store", path="/meow")
    clean_repo.register_stack_component(new_artifact_store)

    runner = CliRunner()
    result = runner.invoke(update_stack, ["default", "-a", "arias_store"])
    assert result.exit_code == 0
    assert clean_repo.active_stack.artifact_store == new_artifact_store


def test_updating_non_active_stack_succeeds(clean_repo) -> None:
    """Test stack update of pre-existing component of non-active stack succeeds."""
    new_orchestrator = LocalOrchestrator(name="arias_orchestrator")
    clean_repo.register_stack_component(new_orchestrator)

    registered_stack = clean_repo.active_stack
    new_stack = Stack(
        name="arias_new_stack",
        orchestrator=registered_stack.orchestrator,
        metadata_store=registered_stack.metadata_store,
        artifact_store=registered_stack.artifact_store,
    )
    clean_repo.register_stack(new_stack)

    runner = CliRunner()
    result = runner.invoke(
        update_stack, ["arias_new_stack", "-o", "arias_orchestrator"]
    )
    assert result.exit_code == 0
    assert (
        clean_repo.get_stack("arias_new_stack").orchestrator == new_orchestrator
    )


def test_adding_to_stack_succeeds(clean_repo) -> None:
    """Test stack update by adding a new component to a stack
    succeeds."""
    local_secrets_manager = LocalSecretsManager(name="arias_secrets_manager")
    clean_repo.register_stack_component(local_secrets_manager)

    runner = CliRunner()
    result = runner.invoke(
        update_stack, ["default", "-x", "arias_secrets_manager"]
    )

    assert result.exit_code == 0
    assert clean_repo.get_stack("default").secrets_manager is not None
    assert (
        clean_repo.get_stack("default").secrets_manager == local_secrets_manager
    )


def test_updating_nonexistent_stack_fails(clean_repo) -> None:
    """Test stack update of nonexistent stack fails."""
    local_secrets_manager = LocalSecretsManager(name="arias_secrets_manager")
    clean_repo.register_stack_component(local_secrets_manager)

    runner = CliRunner()
    result = runner.invoke(
        update_stack, ["not_a_stack", "-x", "arias_secrets_manager"]
    )

    assert result.exit_code == 1
    assert clean_repo.get_stack("default").secrets_manager is None


def test_renaming_nonexistent_stack_fails(clean_repo) -> None:
    """Test stack rename of nonexistent stack fails."""
    CliRunner()
