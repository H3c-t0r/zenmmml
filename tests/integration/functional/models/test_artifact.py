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
"""Integration tests for artifact models."""


from typing import TYPE_CHECKING, Dict, List, Optional

from tests.integration.functional.conftest import (
    constant_int_output_test_step,
    visualizable_step,
)
from zenml.enums import ExecutionStatus
from zenml.models import (
    ArtifactResponse,
    ArtifactVisualizationResponse,
    RunMetadataResponse,
)
from zenml.pipelines.base_pipeline import BasePipeline
from zenml.utils.artifact_utils import load_artifact_visualization

if TYPE_CHECKING:
    from zenml.client import Client


def test_artifact_step_run_linkage(
    clean_workspace: "Client", one_step_pipeline
):
    """Integration test for `artifact.step` and `artifact.run` properties."""
    step_ = constant_int_output_test_step()
    pipe: BasePipeline = one_step_pipeline(step_)
    pipe.run()

    # Non-cached run: producer step is the step that was just run
    pipeline_run = pipe.model.last_run
    step_run = pipeline_run.steps["step_"]
    artifact = step_run.output
    assert artifact.step == step_run
    assert artifact.run == pipeline_run

    # Cached run: producer step is the step that was cached
    pipe.run()
    step_run_2 = pipe.model.last_run.steps["step_"]
    assert step_run_2.status == ExecutionStatus.CACHED
    assert step_run_2.original_step_run_id == step_run.id
    artifact_2 = step_run_2.output
    assert artifact_2.step == step_run
    assert artifact_2.run == pipeline_run


def test_disabling_artifact_visualization(
    clean_workspace: "Client", one_step_pipeline
):
    """Test that disabling artifact visualization works."""

    # By default, artifact visualization should be enabled
    step_ = visualizable_step()
    pipe: BasePipeline = one_step_pipeline(step_)
    pipe.configure(enable_cache=False)
    pipe.run(unlisted=True)
    _assert_visualization_enabled(clean_workspace)

    # Test disabling artifact visualization on pipeline level
    pipe.configure(enable_artifact_visualization=False)
    pipe.run(unlisted=True)
    _assert_visualization_disabled(clean_workspace)

    pipe.configure(enable_artifact_visualization=True)
    pipe.run(unlisted=True)
    _assert_visualization_enabled(clean_workspace)

    # Test disabling artifact visualization on step level
    # This should override the pipeline level setting
    step_.configure(enable_artifact_visualization=False)
    pipe.run(unlisted=True)
    _assert_visualization_disabled(clean_workspace)

    step_.configure(enable_artifact_visualization=True)
    pipe.run(unlisted=True)
    _assert_visualization_enabled(clean_workspace)

    # Test disabling artifact visualization on run level
    # This should override both the pipeline and step level setting
    pipe.run(unlisted=True, enable_artifact_visualization=False)
    _assert_visualization_disabled(clean_workspace)

    pipe.configure(enable_artifact_visualization=False)
    step_.configure(enable_artifact_visualization=False)
    pipe.run(unlisted=True, enable_artifact_visualization=True)
    _assert_visualization_enabled(clean_workspace)


def test_load_artifact_visualization(clean_workspace, one_step_pipeline):
    """Integration test for loading artifact visualizations."""
    step_ = visualizable_step()
    pipe: BasePipeline = one_step_pipeline(step_)
    pipe.configure(enable_cache=False)
    pipe.run(unlisted=True)

    artifact = _get_output_of_last_run(clean_workspace)
    assert artifact.visualizations
    for i in range(len(artifact.visualizations)):
        load_artifact_visualization(
            artifact=artifact, index=i, zen_store=clean_workspace.zen_store
        )


def test_disabling_artifact_metadata(clean_workspace, one_step_pipeline):
    """Test that disabling artifact metadata works."""

    # By default, artifact metadata should be enabled
    step_ = visualizable_step()
    pipe: BasePipeline = one_step_pipeline(step_)
    pipe.configure(enable_cache=False)
    pipe.run(unlisted=True)
    _assert_metadata_enabled(clean_workspace)

    # Test disabling artifact metadata on pipeline level
    pipe.configure(enable_artifact_metadata=False)
    pipe.run(unlisted=True)
    _assert_metadata_disabled(clean_workspace)

    pipe.configure(enable_artifact_metadata=True)
    pipe.run(unlisted=True)
    _assert_metadata_enabled(clean_workspace)

    # Test disabling artifact metadata on step level
    # This should override the pipeline level setting
    step_.configure(enable_artifact_metadata=False)
    pipe.run(unlisted=True)
    _assert_metadata_disabled(clean_workspace)

    step_.configure(enable_artifact_metadata=True)
    pipe.run(unlisted=True)
    _assert_metadata_enabled(clean_workspace)

    # Test disabling artifact metadata on run level
    # This should override both the pipeline and step level setting
    pipe.run(unlisted=True, enable_artifact_metadata=False)
    _assert_metadata_disabled(clean_workspace)

    pipe.configure(enable_artifact_metadata=False)
    step_.configure(enable_artifact_metadata=False)
    pipe.run(unlisted=True, enable_artifact_metadata=True)
    _assert_metadata_enabled(clean_workspace)


def _get_output_of_last_run(clean_workspace: "Client") -> ArtifactResponse:
    """Get the output of the last run."""
    return list(clean_workspace.list_pipeline_runs()[0].steps.values())[
        0
    ].output


def _get_visualizations_of_last_run(
    clean_workspace: "Client",
) -> Optional[List[ArtifactVisualizationResponse]]:
    """Get the artifact visualizations of the last run."""
    return _get_output_of_last_run(clean_workspace).visualizations


def _get_metadata_of_last_run(
    clean_workspace: "Client",
) -> Dict[str, "RunMetadataResponse"]:
    """Get the artifact metadata of the last run."""
    return _get_output_of_last_run(clean_workspace).run_metadata


def _assert_visualization_enabled(clean_workspace: "Client"):
    """Assert that artifact visualization was enabled in the last run."""
    assert _get_visualizations_of_last_run(clean_workspace)


def _assert_visualization_disabled(clean_workspace: "Client"):
    """Assert that artifact visualization was disabled in the last run."""
    assert not _get_visualizations_of_last_run(clean_workspace)


def _assert_metadata_enabled(clean_workspace: "Client"):
    """Assert that artifact metadata was enabled in the last run."""
    assert _get_metadata_of_last_run(clean_workspace)


def _assert_metadata_disabled(clean_workspace: "Client"):
    """Assert that artifact metadata was disabled in the last run."""
    assert not _get_metadata_of_last_run(clean_workspace)
