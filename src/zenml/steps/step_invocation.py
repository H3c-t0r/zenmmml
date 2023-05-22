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
"""Step invocation class definition."""
from typing import TYPE_CHECKING, Any, Dict, Sequence, Set

if TYPE_CHECKING:
    from zenml.config.step_configurations import StepConfiguration
    from zenml.new.pipelines.pipeline import Pipeline
    from zenml.steps import BaseStep
    from zenml.steps.entrypoint_function_utils import (
        ExternalArtifact,
        StepArtifact,
    )


class StepInvocation:
    """Step invocation class."""

    def __init__(
        self,
        id: str,
        step: "BaseStep",
        input_artifacts: Dict[str, "StepArtifact"],
        external_artifacts: Dict[str, "ExternalArtifact"],
        parameters: Dict[str, Any],
        upstream_steps: Sequence[str],
        pipeline: "Pipeline",
    ) -> None:
        """Initialize a step invocation.

        Args:
            id: The invocation ID.
            step: The step that is represented by the invocation.
            input_artifacts: The input artifacts for the invocation.
            external_artifacts: The external artifacts for the invocation.
            parameters: The parameters for the invocation.
            upstream_steps: The upstream steps for the invocation.
            pipeline: The parent pipeline of the invocation.
        """
        self.id = id
        self.step = step
        self.input_artifacts = input_artifacts
        self.external_artifacts = external_artifacts
        self.parameters = parameters
        self.invocation_upstream_steps = upstream_steps
        self.pipeline = pipeline

    @property
    def upstream_steps(self) -> Set[str]:
        """The upstream steps of the invocation.

        Returns:
            The upstream steps of the invocation.
        """
        return set(self.invocation_upstream_steps).union(
            self._get_and_validate_step_upstream_steps()
        )

    def _get_and_validate_step_upstream_steps(self) -> Set[str]:
        """Validates the upstream steps defined on the step instance.

        This is only allowed in legacy pipelines when calling `step.after(...)`
        and we need to make sure that both the upstream and downstream steps
        of such a relationship are only invoked once inside a pipeline.

        Raises:
            RuntimeError: If either the upstream or downstream step of a
                `.after(...)` call got invoked multiple times in a pipeline.

        Returns:
            The upstream steps defined on the step instance.
        """
        if self.step.upstream_steps:
            # If the step has upstream steps, it can only be part of a single
            # invocation, otherwise it's not clear which invocation should come
            # after the upstream steps
            invocations = {
                invocation
                for invocation in self.pipeline.steps.values()
                if invocation.step is self.step
            }

            if len(invocations) > 1:
                raise RuntimeError(
                    "Setting upstream steps for a step using the `.after(...) "
                    "method is not allowed in combination with calling the "
                    "step multiple times."
                )

        upstream_steps = set()

        for step in self.step.upstream_steps:
            upstream_steps_invocations = {
                invocation.id
                for invocation in self.pipeline.steps.values()
                if invocation.step is step
            }

            if len(upstream_steps_invocations) == 1:
                upstream_steps.add(upstream_steps_invocations.pop())
            elif len(upstream_steps_invocations) > 1:
                raise RuntimeError(
                    "Setting upstream steps for a step using the `.after(...) "
                    "method is not allowed in combination with calling the "
                    "step multiple times."
                )

        return upstream_steps

    def finalize(self) -> "StepConfiguration":
        """Finalizes a step invocation.

        The will validate the upstream steps and run final configurations on the
        step that is represented by the invocation.

        Returns:
            The finalized step configuration.
        """
        # Validate the upstream steps for legacy .after() calls
        self._get_and_validate_step_upstream_steps()
        self.step.configure(parameters=self.parameters)

        external_artifact_ids = {}
        for key, artifact in self.external_artifacts.items():
            external_artifact_ids[key] = artifact.upload_if_necessary()

        return self.step._finalize_configuration(
            input_artifacts=self.input_artifacts,
            external_artifacts=external_artifact_ids,
        )
