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
"""External artifact definition."""
import os
from typing import Any, Dict, Optional, Type, Union
from uuid import UUID, uuid4

from pydantic import root_validator

from zenml.artifacts.external_artifact_config import (
    ExternalArtifactConfiguration,
)
from zenml.config.source import Source
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.materializers.base_materializer import BaseMaterializer

MaterializerClassOrSource = Union[str, Source, Type[BaseMaterializer]]


logger = get_logger(__name__)


class ExternalArtifact(ExternalArtifactConfiguration):
    """External artifacts can be used to provide values as input to ZenML steps.

    ZenML steps accept either artifacts (=outputs of other steps), parameters
    (raw, JSON serializable values) or external artifacts. External artifacts
    can be used to provide any value as input to a step without needing to
    write an additional step that returns this value.

    The external artifact needs to have either a value associated with it
    that will be uploaded to the artifact store, or reference an artifact
    that is already registered in ZenML.

    There are several ways to reference an existing artifact:
    - By providing an artifact ID.
    - By providing an artifact name and version.
    - By providing an artifact name and a pipeline run name.
    - By providing an artifact name and a pipeline name, in which case ZenML
        will attempt to find the artifact in the latest run of the pipeline.
    - By only providing an artifact name, in which case the latest version
        of the artifact will be used.

    Args:
        value: The artifact value.
        id: The ID of an artifact that should be referenced by this external
            artifact.
        name: Name of an artifact to search. If none of
            `version`, `pipeline_run_name`, or `pipeline_name` are set, the
            latest version of the artifact will be used.
        version: Version of the artifact to search. Only used when `name` is
            provided.
        pipeline_run_name: Name of a pipeline run to search artifacts in. Only
            used when `name` is provided.
        pipeline_name: Name of a pipeline in which to search for the artifact.
            Only used when `name` is provided.
        materializer: The materializer to use for saving the artifact value
            to the artifact store. Only used when `value` is provided.
        store_artifact_metadata: Whether metadata for the artifact should
            be stored. Only used when `value` is provided.
        store_artifact_visualizations: Whether visualizations for the
            artifact should be stored. Only used when `value` is provided.

    Example:
    ```
    from zenml import step, pipeline
    from zenml.artifacts.external_artifact import ExternalArtifact
    import numpy as np

    @step
    def my_step(value: np.ndarray) -> None:
      print(value)

    my_array = np.array([1, 2, 3])

    @pipeline
    def my_pipeline():
      my_step(value=ExternalArtifact(my_array))
    ```
    """

    value: Optional[Any] = None
    materializer: Optional[MaterializerClassOrSource] = None
    store_artifact_metadata: bool = True
    store_artifact_visualizations: bool = True

    @root_validator
    def _validate_all(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        options = [
            values.get(field, None) is not None
            for field in ["value", "id", "name"]
        ]
        if sum(options) > 1:
            raise ValueError(
                "Only one of `value`, `id`, or `name` can be provided when "
                "creating an external artifact."
            )
        elif sum(options) == 0:
            raise ValueError(
                "Either `value`, `id`, or `name` must be provided when "
                "creating an external artifact."
            )
        return values

    def upload_by_value(self) -> UUID:
        """Uploads the artifact by value.

        Returns:
            The uploaded artifact ID.

        Raises:
            RuntimeError: If artifact URI already exists.
        """
        from zenml.client import Client
        from zenml.utils.artifact_utils import upload_artifact

        client = Client()

        artifact_store_id = client.active_stack.artifact_store.id

        logger.info("Uploading external artifact...")
        artifact_name = f"external_{uuid4()}"
        materializer_class = self._get_materializer_class(value=self.value)

        uri = os.path.join(
            client.active_stack.artifact_store.path,
            "external_artifacts",
            artifact_name,
        )
        if fileio.exists(uri):
            raise RuntimeError(f"Artifact URI '{uri}' already exists.")
        fileio.makedirs(uri)

        materializer = materializer_class(uri)

        artifact_id: UUID = upload_artifact(
            name=artifact_name,
            data=self.value,
            materializer=materializer,
            artifact_store_id=artifact_store_id,
            extract_metadata=self.store_artifact_metadata,
            include_visualizations=self.store_artifact_visualizations,
        )

        # To avoid duplicate uploads, switch to referencing the uploaded
        # artifact by ID
        self.id = artifact_id
        self.value = None

        logger.info("Finished uploading external artifact %s.", artifact_id)
        return self.id

    @property
    def config(self) -> ExternalArtifactConfiguration:
        """Returns the lightweight config without hard for JSON properties.

        Returns:
            The config object to be evaluated in runtime by step interface.
        """
        return ExternalArtifactConfiguration(
            id=self.id,
            name=self.name,
            version=self.version,
            pipeline_run_name=self.pipeline_run_name,
            pipeline_name=self.pipeline_name,
        )

    def _get_materializer_class(self, value: Any) -> Type[BaseMaterializer]:
        """Gets a materializer class for a value.

        If a custom materializer is defined for this artifact it will be
        returned. Otherwise it will get the materializer class from the
        registry, falling back to the Cloudpickle materializer if no concrete
        materializer is registered for the type of value.

        Args:
            value: The value for which to get the materializer class.

        Returns:
            The materializer class.
        """
        from zenml.materializers.materializer_registry import (
            materializer_registry,
        )
        from zenml.utils import source_utils

        if isinstance(self.materializer, type):
            return self.materializer
        elif self.materializer:
            return source_utils.load_and_validate_class(
                self.materializer, expected_class=BaseMaterializer
            )
        else:
            return materializer_registry[type(value)]
