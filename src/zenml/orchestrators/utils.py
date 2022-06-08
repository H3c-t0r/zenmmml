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

from typing import TYPE_CHECKING, List

import tfx.orchestration.pipeline as tfx_pipeline
from tfx.proto.orchestration.pipeline_pb2 import PipelineNode

from zenml.logger import get_logger
from zenml.steps import BaseStep

if TYPE_CHECKING:
    from zenml.pipelines.base_pipeline import BasePipeline
    from zenml.stack import Stack

logger = get_logger(__name__)


def create_tfx_pipeline(
    zenml_pipeline: "BasePipeline", stack: "Stack"
) -> tfx_pipeline.Pipeline:
    """Creates a tfx pipeline from a ZenML pipeline."""
    # Connect the inputs/outputs of all steps in the pipeline
    zenml_pipeline.connect(**zenml_pipeline.steps)

    tfx_components = [step.component for step in zenml_pipeline.steps.values()]

    artifact_store = stack.artifact_store

    # We do not pass the metadata connection config here as it might not be
    # accessible. Instead it is queried from the active stack right before a
    # step is executed (see `BaseOrchestrator.run_step(...)`)
    return tfx_pipeline.Pipeline(
        pipeline_name=zenml_pipeline.name,
        components=tfx_components,  # type: ignore[arg-type]
        pipeline_root=artifact_store.path,
        enable_cache=zenml_pipeline.enable_cache,
    )


def get_step_for_node(node: PipelineNode, steps: List[BaseStep]) -> BaseStep:
    """Finds the matching step for a tfx pipeline node."""
    step_name = node.node_info.id
    try:
        return next(step for step in steps if step.name == step_name)
    except StopIteration:
        raise RuntimeError(f"Unable to find step with name '{step_name}'.")
