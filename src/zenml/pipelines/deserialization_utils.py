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
"""Pipeline deserialization utilities."""
import inspect
from typing import TYPE_CHECKING, Callable, Dict, Set, Type

from packaging import version

from zenml.logger import get_logger
from zenml.new.pipelines.pipeline import Pipeline
from zenml.steps.base_step import BaseStep
from zenml.steps.entrypoint_function_utils import StepArtifact
from zenml.utils import source_utils

if TYPE_CHECKING:
    from zenml.config.pipeline_spec import PipelineSpec
    from zenml.models import PipelineResponseModel

logger = get_logger(__name__)


def load_pipeline(model: "PipelineResponseModel") -> "Pipeline":
    """Load a pipeline from a model.

    Args:
        model: The pipeline model to load.

    Raises:
        ValueError: If the pipeline can't be loaded due to an old model spec
            (version <0.2).

    Returns:
        The loaded pipeline.
    """
    model_version = version.parse(model.spec.version)
    if model_version < version.parse("0.2"):
        raise ValueError(
            "Loading a pipeline is only possible for pipeline specs with "
            "version 0.2 or higher."
        )
    elif model_version == version.parse("0.2"):
        pipeline_instance = load_pipeline_v_0_2(model=model)
    else:
        pipeline_instance = load_pipeline_v_0_3(model=model)

    version_hash = pipeline_instance._compute_unique_identifier(
        pipeline_spec=model.spec
    )
    if version_hash != model.version_hash:
        logger.warning(
            "Trying to load pipeline version `%s`, but the local step code "
            "changed since this pipeline version was registered. Using "
            "this pipeline instance will result in a different pipeline "
            "version being registered or reused.",
            model.version,
        )
    return pipeline_instance


def load_pipeline_v_0_3(model: "PipelineResponseModel") -> "Pipeline":
    """Load a pipeline from a model with spec version 0.3.

    Args:
        model: The pipeline model to load.

    Raises:
        RuntimeError: If an upstream step or output is missing.

    Returns:
        The loaded pipeline.
    """
    outputs = {}

    with Pipeline(name=model.name) as p:
        for step_spec in model.spec.steps:
            for upstream_step in step_spec.upstream_steps:
                if upstream_step not in outputs:
                    raise RuntimeError(
                        f"Unable to find upstream step `{upstream_step}`. "
                        "This is probably because the step was renamed in code."
                    )

            step_inputs = {}
            for input_name, input_spec in step_spec.inputs.items():
                if input_spec.output_name not in outputs[input_spec.step_name]:
                    raise RuntimeError(
                        f"Missing output `{input_spec.output_name}` for step "
                        f"`{input_spec.step_name}`. This is probably because "
                        "the output of the step was renamed."
                    )
                step_inputs[input_name] = outputs[input_spec.step_name][
                    input_spec.output_name
                ]

            step_class: Type[BaseStep] = source_utils.load_and_validate_class(
                step_spec.source, expected_class=BaseStep
            )
            step_outputs = step_class(
                **step_inputs,
                id=step_spec.pipeline_parameter_name,
                after=step_spec.upstream_steps,
            )
            output_keys = list(step_class.OUTPUT_SIGNATURE.keys())

            if isinstance(step_outputs, StepArtifact):
                step_outputs = (step_outputs,)

            outputs[step_spec.pipeline_parameter_name] = {
                key: step_outputs[i] for i, key in enumerate(output_keys)
            }

    p.__doc__ = model.docstring
    return p


def load_pipeline_v_0_2(model: "PipelineResponseModel") -> "Pipeline":
    """Load a pipeline from a model with spec version 0.2.

    Args:
        model: The pipeline model to load.

    Returns:
        The loaded pipeline.
    """
    from zenml.pipelines.base_pipeline import BasePipeline

    steps = _load_and_verify_steps(pipeline_spec=model.spec)
    connect_method = _generate_connect_method(model=model)

    pipeline_class = type(
        model.name,
        (BasePipeline,),
        {
            "connect": staticmethod(connect_method),
            "__doc__": model.docstring,
        },
    )

    return pipeline_class(**steps)


def _load_and_verify_steps(
    pipeline_spec: "PipelineSpec",
) -> Dict[str, BaseStep]:
    """Loads steps and verifies their names and inputs/outputs names.

    Args:
        pipeline_spec: The pipeline spec from which to load the steps.

    Raises:
        RuntimeError: If the step names or input/output names of the
            loaded steps don't match with the names defined in the spec.

    Returns:
        The loaded steps.
    """
    steps = {}
    available_outputs: Dict[str, Set[str]] = {}

    for step_spec in pipeline_spec.steps:
        for upstream_step in step_spec.upstream_steps:
            if upstream_step not in available_outputs:
                raise RuntimeError(
                    f"Unable to find upstream step `{upstream_step}`. "
                    "This is probably because the step was renamed in code."
                )

        for input_spec in step_spec.inputs.values():
            if (
                input_spec.output_name
                not in available_outputs[input_spec.step_name]
            ):
                raise RuntimeError(
                    f"Missing output `{input_spec.output_name}` for step "
                    f"`{input_spec.step_name}`. This is probably because "
                    "the output of the step was renamed."
                )

        step = BaseStep.load_from_source(step_spec.source)
        input_names = set(step.INPUT_SIGNATURE)
        spec_input_names = set(step_spec.inputs)

        if input_names != spec_input_names:
            raise RuntimeError(
                f"Input names of step {step_spec.source} and the spec "
                f"from the database don't match. Step inputs: "
                f"`{input_names}`, spec inputs: `{spec_input_names}`."
            )

        steps[step_spec.pipeline_parameter_name] = step
        available_outputs[step.name] = set(
            step.entrypoint_definition.outputs.keys()
        )

    return steps


def _generate_connect_method(
    model: "PipelineResponseModel",
) -> Callable[..., None]:
    """Dynamically generates a connect method for a pipeline model.

    Args:
        model: The model for which to generate the method.

    Returns:
        The generated connect method.
    """

    def connect(**steps: BaseStep) -> None:
        # Bind **steps to the connect signature assigned to this method
        # below. This ensures that the method inputs get verified and only
        # the arguments defined in the signature are allowed
        inspect.signature(connect).bind(**steps)

        step_outputs: Dict[str, Dict[str, StepArtifact]] = {}
        for step_spec in model.spec.steps:
            step = steps[step_spec.pipeline_parameter_name]

            step_inputs = {}
            for input_name, input_ in step_spec.inputs.items():
                try:
                    upstream_step = step_outputs[input_.step_name]
                    step_input = upstream_step[input_.output_name]
                    step_inputs[input_name] = step_input
                except KeyError:
                    raise RuntimeError(
                        f"Unable to find upstream step "
                        f"`{input_.step_name}` in pipeline `{model.name}`. "
                        "This is probably due to configuring a new step "
                        "name after loading a pipeline using "
                        "`Pipeline.from_model`."
                    )

            step_output = step(**step_inputs)
            output_keys = list(step.entrypoint_definition.outputs.keys())

            if isinstance(step_output, StepArtifact):
                step_output = (step_output,)

            step_outputs[step.name] = {
                key: step_output[i] for i, key in enumerate(output_keys)
            }

    # Create the connect method signature based on the expected steps
    parameters = [
        inspect.Parameter(
            name=step_spec.pipeline_parameter_name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        for step_spec in model.spec.steps
    ]
    signature = inspect.Signature(parameters=parameters)
    connect.__signature__ = signature  # type: ignore[attr-defined]

    return connect
