# Copyright 2020 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This module defines a generic Launcher for all TFleX nodes."""

import json
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Dict

from tfx.dsl.io import fileio

from zenml.artifacts.base_artifact import BaseArtifact
from zenml.client import Client
from zenml.config.step_configurations import Step
from zenml.enums import ExecutionStatus
from zenml.logger import get_logger
from zenml.models.pipeline_models import ArtifactModel, StepRunModel
from zenml.steps.utils import StepExecutor
from zenml.utils import string_utils

if TYPE_CHECKING:
    from zenml.artifact_stores import BaseArtifactStore
    from zenml.config.pipeline_configurations import PipelineConfiguration
    from zenml.stack import Stack

logger = get_logger(__name__)


def generate_cache_key(
    step: Step, input_artifacts: Dict[str, ArtifactModel]
) -> str:
    return json.dumps(step.config.parameters, sort_keys=True)


def generate_artifact_uri(
    artifact_store: "BaseArtifactStore",
    step_run: "StepRunModel",
    output_name: str,
) -> str:
    return os.path.join(
        artifact_store.path,
        step_run.entrypoint_name,
        output_name,
        str(step_run.id),
    )


class Launcher:
    def __init__(
        self,
        step: Step,
        step_name: str,
        run_name: str,
        pipeline_config: "PipelineConfiguration",
        stack: "Stack",
    ):
        self._step = step
        self._step_name = step_name
        self._run_name = run_name
        self._pipeline_config = pipeline_config
        self._stack = stack

    def launch(self) -> None:
        # TODO: Create run here instead
        start_time = time.time()
        logger.info(f"Step `{self._step_name}` has started.")

        run = Client().zen_store.get_run(self._run_name)
        current_run_steps = Client().zen_store.list_run_steps(run_id=run.id)

        # Z1) Get input artifacts of current run
        current_run_input_artifacts: Dict[str, ArtifactModel] = {}
        for name, inp_ in self._step.spec.inputs.items():
            for s in current_run_steps:
                if s.entrypoint_name == inp_.step_name:
                    for (
                        artifact_name,
                        artifact_id,
                    ) in s.output_artifacts.items():
                        if artifact_name == inp_.output_name:
                            artifact = Client().zen_store.get_artifact(
                                artifact_id
                            )
                            current_run_input_artifacts[name] = artifact
                            break

                    break
            else:
                assert False

        # Z2) generate cache key for current step
        cache_key = generate_cache_key(
            step=self._step, input_artifacts=current_run_input_artifacts
        )

        # Z3) Register step run
        parent_step_ids = []

        for upstream_step in self._step.spec.upstream_steps:
            for run_step in current_run_steps:
                if run_step.entrypoint_name == upstream_step:
                    parent_step_ids.append(run_step.id)

        # RMTFX: Get parent step names from pipeline spec, get their IDs from the run model
        input_artifact_ids = {
            k: a.id for k, a in current_run_input_artifacts.items()
        }
        current_step_run = StepRunModel(
            name=self._step_name,
            pipeline_run_id=run.id,
            parent_step_ids=parent_step_ids,
            input_artifacts=input_artifact_ids,
            status=ExecutionStatus.RUNNING,
            entrypoint_name=self._step.config.name,
            parameters=self._step.config.parameters,
            step_configuration=self._step.dict(),
            mlmd_parent_step_ids=[],
            cache_key=cache_key,
            output_artifacts={},
            caching_parameters={},
            start_time=datetime.now(),
            enable_cache=self._step.config.enable_cache,
        )
        Client().zen_store.create_run_step(current_step_run)

        # Z4) query zen store for all step runs with same cache key

        all_step_runs = Client().zen_store.list_run_steps()
        cache_candidates = [
            step_run
            for step_run in all_step_runs
            if step_run.id != current_step_run.id
            and step_run.cache_key == cache_key
        ]

        if cache_candidates:
            # if exists, use latest run and do the following:
            #   - Set status to cached
            #   - Update with output artifacts of the existing step run
            cache_candidates.sort(key=lambda s: s.created)
            cached_step_run = cache_candidates[-1]
            current_step_run.output_artifacts = cached_step_run.output_artifacts
            current_step_run.status = ExecutionStatus.CACHED
            current_step_run.end_time = current_step_run.start_time
            Client().zen_store.update_run_step(current_step_run)

            logger.info(f"Using cached version of `{self._step_name}`.")
        else:
            # if no step run exists:
            #   - Run code
            #   - Register the new output artifacts
            input_artifacts: Dict[str, BaseArtifact] = {}
            for name, artifact_model in current_run_input_artifacts.items():
                artifact = BaseArtifact()
                artifact.name = name
                artifact.uri = artifact_model.uri
                artifact.materializer = artifact_model.materializer
                artifact.datatype = artifact_model.data_type
                input_artifacts[name] = artifact

            output_artifacts: Dict[str, BaseArtifact] = {}
            for name, _ in self._step.config.outputs.items():
                artifact = BaseArtifact()
                artifact.name = name
                artifact.uri = generate_artifact_uri(
                    artifact_store=self._stack.artifact_store,
                    step_run=current_step_run,
                    output_name=name,
                )
                output_artifacts[name] = artifact

                if fileio.exists(artifact.uri):
                    raise RuntimeError("Artifact already exists")

                fileio.makedirs(artifact.uri)

            executor = StepExecutor(step=self._step)

            try:
                executor.execute(
                    input_artifacts=input_artifacts,
                    output_artifacts=output_artifacts,
                    run_name=self._run_name,
                    pipeline_config=self._pipeline_config,
                )
            except:
                current_step_run.status = ExecutionStatus.FAILED
                Client().zen_store.update_run_step(current_step_run)
                logger.error(f"Failed to execute step `{self._step_name}`.")

                for artifact in output_artifacts.values():
                    try:
                        if fileio.isdir(artifact.uri):
                            fileio.rmtree(artifact.uri)
                    except:
                        pass
                raise

            output_artifact_ids = {}
            for name, artifact in output_artifacts.items():
                artifact_model = ArtifactModel(
                    name=name,
                    type=artifact.artifact_type.name,
                    uri=artifact.uri,
                    materializer=artifact.materializer,
                    data_type=artifact.datatype,
                )
                Client().zen_store.create_artifact(artifact_model)
                output_artifact_ids[name] = artifact_model.id

            current_step_run.output_artifacts = output_artifact_ids
            current_step_run.status = ExecutionStatus.COMPLETED
            current_step_run.end_time = datetime.now()
            Client().zen_store.update_run_step(current_step_run)
        duration = time.time() - start_time
        logger.info(
            f"Step `{self._step_name}` has finished in "
            f"{string_utils.get_human_readable_time(duration)}."
        )

        # TODO: do we need to update the run status here, or does that happen
        # on the SQL zen store automatically?
