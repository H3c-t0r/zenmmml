#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
"""Implementation of the MLflow experiment tracker for ZenML."""

import os
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Type, cast

import mlflow
from mlflow.entities import Experiment, Run
from mlflow.store.db.db_types import DATABASE_ENGINES
from pydantic import root_validator, validator

import zenml
from zenml.artifact_stores import LocalArtifactStore
from zenml.config.settings import Settings
from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
)
from zenml.integrations.mlflow import (
    MLFLOW_MODEL_EXPERIMENT_TRACKER_FLAVOR,
    mlflow_utils,
)
from zenml.logger import get_logger
from zenml.repository import Repository
from zenml.stack import StackValidator
from zenml.utils.secret_utils import SecretField

if TYPE_CHECKING:
    from zenml.config.pipeline_configurations import StepRunInfo

logger = get_logger(__name__)


MLFLOW_TRACKING_USERNAME = "MLFLOW_TRACKING_USERNAME"
MLFLOW_TRACKING_PASSWORD = "MLFLOW_TRACKING_PASSWORD"
MLFLOW_TRACKING_TOKEN = "MLFLOW_TRACKING_TOKEN"
MLFLOW_TRACKING_INSECURE_TLS = "MLFLOW_TRACKING_INSECURE_TLS"


class MLFlowExperimentTrackerSettings(Settings):
    """settings for the MLflow experiment tracker.

    Attributes:
        experiment_name: The MLflow experiment name.
        nested: If `True`, will create a nested sub-run for the step.
        tags: Tags for the Mlflow run.
    """

    experiment_name: Optional[str] = None
    nested: bool = False
    tags: Dict[str, Any] = {}


class MLFlowExperimentTracker(BaseExperimentTracker):
    """Stores Mlflow configuration options.

    ZenML should take care of configuring MLflow for you, but should you still
    need access to the configuration inside your step you can do it using a
    step context:
    ```python
    from zenml.steps import StepContext

    @enable_mlflow
    @step
    def my_step(context: StepContext, ...)
        context.stack.experiment_tracker  # get the tracking_uri etc. from here
    ```

    Attributes:
        tracking_uri: The uri of the mlflow tracking server. If no uri is set,
            your stack must contain a `LocalArtifactStore` and ZenML will
            point MLflow to a subdirectory of your artifact store instead.
        tracking_username: Username for authenticating with the MLflow
            tracking server. When a remote tracking uri is specified,
            either `tracking_token` or `tracking_username` and
            `tracking_password` must be specified.
        tracking_password: Password for authenticating with the MLflow
            tracking server. When a remote tracking uri is specified,
            either `tracking_token` or `tracking_username` and
            `tracking_password` must be specified.
        tracking_token: Token for authenticating with the MLflow
            tracking server. When a remote tracking uri is specified,
            either `tracking_token` or `tracking_username` and
            `tracking_password` must be specified.
        tracking_insecure_tls: Skips verification of TLS connection to the
            MLflow tracking server if set to `True`.
    """

    tracking_uri: Optional[str] = None
    tracking_username: Optional[str] = SecretField()
    tracking_password: Optional[str] = SecretField()
    tracking_token: Optional[str] = SecretField()
    tracking_insecure_tls: bool = False

    # Class Configuration
    FLAVOR: ClassVar[str] = MLFLOW_MODEL_EXPERIMENT_TRACKER_FLAVOR

    @validator("tracking_uri")
    def _ensure_valid_tracking_uri(
        cls, tracking_uri: Optional[str] = None
    ) -> Optional[str]:
        """Ensures that the tracking uri is a valid mlflow tracking uri.

        Args:
            tracking_uri: The tracking uri to validate.

        Returns:
            The tracking uri if it is valid.

        Raises:
            ValueError: If the tracking uri is not valid.
        """
        if tracking_uri:
            valid_schemes = DATABASE_ENGINES + ["http", "https", "file"]
            if not any(
                tracking_uri.startswith(scheme) for scheme in valid_schemes
            ):
                raise ValueError(
                    f"MLflow tracking uri does not start with one of the valid "
                    f"schemes {valid_schemes}. See "
                    f"https://www.mlflow.org/docs/latest/tracking.html#where-runs-are-recorded "
                    f"for more information."
                )
        return tracking_uri

    @root_validator(skip_on_failure=True)
    def _ensure_authentication_if_necessary(
        cls, values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ensures that credentials or a token for authentication exist.

        We make this check when running MLflow tracking with a remote backend.

        Args:
            values: The values to validate.

        Returns:
            The validated values.

        Raises:
            ValueError: If neither credentials nor a token are provided.
        """
        tracking_uri = values.get("tracking_uri")

        if tracking_uri and cls.is_remote_tracking_uri(tracking_uri):
            # we need either username + password or a token to authenticate to
            # the remote backend
            basic_auth = values.get("tracking_username") and values.get(
                "tracking_password"
            )
            token_auth = values.get("tracking_token")

            if not (basic_auth or token_auth):
                raise ValueError(
                    f"MLflow experiment tracking with a remote backend "
                    f"{tracking_uri} is only possible when specifying either "
                    f"username and password or an authentication token in your "
                    f"stack component. To update your component, run the "
                    f"following command: `zenml experiment-tracker update "
                    f"{values['name']} --tracking_username=MY_USERNAME "
                    f"--tracking_password=MY_PASSWORD "
                    f"--tracking_token=MY_TOKEN` and specify either your "
                    f"username and password or token."
                )

        return values

    @property
    def local_path(self) -> Optional[str]:
        """Path to the local directory where the MLflow artifacts are stored.

        Returns:
            None if configured with a remote tracking URI, otherwise the
            path to the local MLflow artifact store directory.
        """
        tracking_uri = self.get_tracking_uri()
        if self.is_remote_tracking_uri(tracking_uri):
            return None
        else:
            assert tracking_uri.startswith("file:")
            return tracking_uri[5:]

    @property
    def validator(self) -> Optional["StackValidator"]:
        """Checks the stack has a `LocalArtifactStore` if no tracking uri was specified.

        Returns:
            An optional `StackValidator`.
        """
        if self.tracking_uri:
            # user specified a tracking uri, do nothing
            return None
        else:
            # try to fall back to a tracking uri inside the zenml artifact
            # store. this only works in case of a local artifact store, so we
            # make sure to prevent stack with other artifact stores for now
            return StackValidator(
                custom_validation_function=lambda stack: (
                    isinstance(stack.artifact_store, LocalArtifactStore),
                    "MLflow experiment tracker without a specified tracking "
                    "uri only works with a local artifact store.",
                )
            )

    @property
    def settings_class(self) -> Optional[Type["Settings"]]:
        """settings class for the Mlflow experiment tracker.

        Returns:
            The settings class.
        """
        return MLFlowExperimentTrackerSettings

    @staticmethod
    def is_remote_tracking_uri(tracking_uri: str) -> bool:
        """Checks whether the given tracking uri is remote or not.

        Args:
            tracking_uri: The tracking uri to check.

        Returns:
            `True` if the tracking uri is remote, `False` otherwise.
        """
        return any(
            tracking_uri.startswith(prefix)
            for prefix in ["http://", "https://"]
        )

    @staticmethod
    def _local_mlflow_backend() -> str:
        """Gets the local MLflow backend inside the ZenML artifact repository directory.

        Returns:
            The MLflow tracking URI for the local MLflow backend.
        """
        repo = Repository(skip_repository_check=True)  # type: ignore[call-arg]
        artifact_store = repo.active_stack.artifact_store
        local_mlflow_backend_uri = os.path.join(artifact_store.path, "mlruns")
        if not os.path.exists(local_mlflow_backend_uri):
            os.makedirs(local_mlflow_backend_uri)
        return "file:" + local_mlflow_backend_uri

    def get_tracking_uri(self) -> str:
        """Returns the configured tracking URI or a local fallback.

        Returns:
            The tracking URI.
        """
        return self.tracking_uri or self._local_mlflow_backend()

    def prepare_step_run(self, step: "StepRunInfo") -> None:
        """Sets the MLflow tracking uri and credentials.

        Args:
            step: The step that will be executed.
        """
        self.configure_mlflow()
        config = cast(
            MLFlowExperimentTrackerSettings,
            self.get_settings(step) or MLFlowExperimentTrackerSettings(),
        )

        experiment_name = config.experiment_name or step.pipeline.name
        experiment = self._set_active_experiment(experiment_name)
        run_id = self.get_run_id(
            experiment_name=experiment_name, run_name=step.run_name
        )

        tags = config.tags.copy()
        tags.update(self._get_internal_tags())

        mlflow.start_run(
            run_id=run_id,
            run_name=step.run_name,
            experiment_id=experiment.experiment_id,
            tags=tags,
        )

        if config.nested:
            mlflow.start_run(run_name=step.config.name, nested=True, tags=tags)

    def cleanup_step_run(self, step: "StepRunInfo") -> None:
        """Stops active MLflow runs and resets the MLflow tracking uri.

        Args:
            step: The step that was executed.
        """
        mlflow_utils.stop_zenml_mlflow_runs()
        mlflow.set_tracking_uri("")

    def configure_mlflow(self) -> None:
        """Configures the MLflow tracking URI and any additional credentials."""
        mlflow.set_tracking_uri(self.get_tracking_uri())

        if self.tracking_username:
            os.environ[MLFLOW_TRACKING_USERNAME] = self.tracking_username
        if self.tracking_password:
            os.environ[MLFLOW_TRACKING_PASSWORD] = self.tracking_password
        if self.tracking_token:
            os.environ[MLFLOW_TRACKING_TOKEN] = self.tracking_token
        os.environ[MLFLOW_TRACKING_INSECURE_TLS] = (
            "true" if self.tracking_insecure_tls else "false"
        )

    def get_run_id(self, experiment_name: str, run_name: str) -> Optional[str]:
        """Gets the if of a run with the given name and experiment.

        Args:
            experiment_name: Name of the experiment in which to search for the
                run.
            run_name: Name of the run to search.

        Returns:
            The id of the run if it exists.
        """
        self.configure_mlflow()

        runs = mlflow.search_runs(
            experiment_names=[experiment_name],
            filter_string=f'tags.mlflow.runName = "{run_name}"',
            output_format="list",
        )

        if not runs:
            return None

        run: Run = runs[0]
        if mlflow_utils.is_zenml_run(run):
            return cast(str, run.info.run_id)
        else:
            return None

    @staticmethod
    def _set_active_experiment(experiment_name: str) -> Experiment:
        """Sets the active MLflow experiment.

        If no experiment with this name exists, it is created and then
        activated.

        Args:
            experiment_name: Name of the experiment to activate.

        Raises:
            RuntimeError: If the experiment creation or activation failed.

        Returns:
            The experiment.
        """
        mlflow.set_experiment(experiment_name=experiment_name)
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if not experiment:
            raise RuntimeError("Failed to set active mlflow experiment.")
        return experiment

    @staticmethod
    def _get_internal_tags() -> Dict[str, Any]:
        """Gets ZenML internal tags for MLflow runs.

        Returns:
            Internal tags.
        """
        return {mlflow_utils.ZENML_TAG_KEY: zenml.__version__}
