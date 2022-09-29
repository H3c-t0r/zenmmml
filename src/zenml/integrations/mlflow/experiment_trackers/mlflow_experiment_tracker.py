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
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, cast

import mlflow
from mlflow.entities import Experiment, Run
from mlflow.store.db.db_types import DATABASE_ENGINES

import zenml
from zenml.artifact_stores import LocalArtifactStore
from zenml.config.base_settings import BaseSettings
from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
)
from zenml.integrations.mlflow import mlflow_utils
from zenml.integrations.mlflow.flavors.mlflow_experiment_tracker_flavor import (
    MLFlowExperimentTrackerConfig,
    MLFlowExperimentTrackerSettings,
    is_databricks_tracking_uri,
    is_remote_mlflow_tracking_uri,
)
from zenml.logger import get_logger
from zenml.client import Client
from zenml.stack import StackValidator

if TYPE_CHECKING:
    from zenml.config.step_run_info import StepRunInfo

logger = get_logger(__name__)


MLFLOW_TRACKING_USERNAME = "MLFLOW_TRACKING_USERNAME"
MLFLOW_TRACKING_PASSWORD = "MLFLOW_TRACKING_PASSWORD"
MLFLOW_TRACKING_TOKEN = "MLFLOW_TRACKING_TOKEN"
MLFLOW_TRACKING_INSECURE_TLS = "MLFLOW_TRACKING_INSECURE_TLS"

DATABRICKS_HOST = "DATABRICKS_HOST"
DATABRICKS_USERNAME = "DATABRICKS_USERNAME"
DATABRICKS_PASSWORD = "DATABRICKS_PASSWORD"
DATABRICKS_TOKEN = "DATABRICKS_TOKEN"


class MLFlowExperimentTracker(BaseExperimentTracker):
    """Track experiments using MLflow."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the experiment tracker and validate the tracking uri.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self._ensure_valid_tracking_uri()

    def _ensure_valid_tracking_uri(self) -> None:
        """Ensures that the tracking uri is a valid mlflow tracking uri.

        Raises:
            ValueError: If the tracking uri is not valid.
        """
        tracking_uri = self.config.tracking_uri
        if tracking_uri:
            valid_schemes = DATABASE_ENGINES + ["http", "https", "file"]
            if not any(
                tracking_uri.startswith(scheme) for scheme in valid_schemes
            ) and not is_databricks_tracking_uri(tracking_uri):
                raise ValueError(
                    f"MLflow tracking uri does not start with one of the valid "
                    f"schemes {valid_schemes} or its value is not set to "
                    f"'databricks'. See "
                    f"https://www.mlflow.org/docs/latest/tracking.html#where-runs-are-recorded "
                    f"for more information."
                )

    @property
    def config(self) -> MLFlowExperimentTrackerConfig:
        """Returns the `MLFlowExperimentTrackerConfig` config.

        Returns:
            The configuration.
        """
        return cast(MLFlowExperimentTrackerConfig, self._config)

    @property
    def local_path(self) -> Optional[str]:
        """Path to the local directory where the MLflow artifacts are stored.

        Returns:
            None if configured with a remote tracking URI, otherwise the
            path to the local MLflow artifact store directory.
        """
        tracking_uri = self.get_tracking_uri()
        if is_remote_mlflow_tracking_uri(tracking_uri):
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
        if self.config.tracking_uri:
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
    def settings_class(self) -> Optional[Type["BaseSettings"]]:
        """Settings class for the Mlflow experiment tracker.

        Returns:
            The settings class.
        """
        return MLFlowExperimentTrackerSettings

    @staticmethod
    def _local_mlflow_backend() -> str:
        """Gets the local MLflow backend inside the ZenML artifact repository directory.

        Returns:
            The MLflow tracking URI for the local MLflow backend.
        """
        client = Client(skip_repository_check=True)  # type: ignore[call-arg]
        artifact_store = client.active_stack.artifact_store
        local_mlflow_backend_uri = os.path.join(artifact_store.path, "mlruns")
        if not os.path.exists(local_mlflow_backend_uri):
            os.makedirs(local_mlflow_backend_uri)
        return "file:" + local_mlflow_backend_uri

    def get_tracking_uri(self) -> str:
        """Returns the configured tracking URI or a local fallback.

        Returns:
            The tracking URI.
        """
        return self.config.tracking_uri or self._local_mlflow_backend()

    def prepare_step_run(self, info: "StepRunInfo") -> None:
        """Sets the MLflow tracking uri and credentials.

        Args:
            info: Info about the step that will be executed.
        """
        self.configure_mlflow()
        settings = cast(
            MLFlowExperimentTrackerSettings,
            self.get_settings(info) or MLFlowExperimentTrackerSettings(),
        )

        experiment_name = settings.experiment_name or info.pipeline.name
        experiment = self._set_active_experiment(experiment_name)
        run_id = self.get_run_id(
            experiment_name=experiment_name, run_name=info.run_name
        )

        tags = settings.tags.copy()
        tags.update(self._get_internal_tags())

        mlflow.start_run(
            run_id=run_id,
            run_name=info.run_name,
            experiment_id=experiment.experiment_id,
            tags=tags,
        )

        if settings.nested:
            mlflow.start_run(run_name=info.config.name, nested=True, tags=tags)

    def cleanup_step_run(self, info: "StepRunInfo") -> None:
        """Stops active MLflow runs and resets the MLflow tracking uri.

        Args:
            info: Info about the step that was executed.
        """
        mlflow_utils.stop_zenml_mlflow_runs()
        mlflow.set_tracking_uri("")

    def configure_mlflow(self) -> None:
        """Configures the MLflow tracking URI and any additional credentials."""
        tracking_uri = self.get_tracking_uri()
        mlflow.set_tracking_uri(tracking_uri)

        if is_databricks_tracking_uri(tracking_uri):
            if self.config.databricks_host:
                os.environ[DATABRICKS_HOST] = self.config.databricks_host
            if self.config.tracking_username:
                os.environ[DATABRICKS_USERNAME] = self.config.tracking_username
            if self.config.tracking_password:
                os.environ[DATABRICKS_PASSWORD] = self.config.tracking_password
            if self.config.tracking_token:
                os.environ[DATABRICKS_TOKEN] = self.config.tracking_token
        else:
            if self.config.tracking_username:
                os.environ[
                    MLFLOW_TRACKING_USERNAME
                ] = self.config.tracking_username
            if self.config.tracking_password:
                os.environ[
                    MLFLOW_TRACKING_PASSWORD
                ] = self.config.tracking_password
            if self.config.tracking_token:
                os.environ[MLFLOW_TRACKING_TOKEN] = self.config.tracking_token

        os.environ[MLFLOW_TRACKING_INSECURE_TLS] = (
            "true" if self.config.tracking_insecure_tls else "false"
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
        experiment_name = self._adjust_experiment_name(experiment_name)

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

    def _set_active_experiment(self, experiment_name: str) -> Experiment:
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
        experiment_name = self._adjust_experiment_name(experiment_name)

        mlflow.set_experiment(experiment_name=experiment_name)
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if not experiment:
            raise RuntimeError("Failed to set active mlflow experiment.")
        return experiment

    def _adjust_experiment_name(self, experiment_name: str) -> str:
        """Prepends a slash to the experiment name if using Databricks.

        Databricks requires the experiment name to be an absolute path within
        the Databricks workspace.

        Args:
            experiment_name: The experiment name.

        Returns:
            The potentially adjusted experiment name.
        """
        tracking_uri = self.get_tracking_uri()

        if (
            tracking_uri
            and is_databricks_tracking_uri(tracking_uri)
            and not experiment_name.startswith("/")
        ):
            return f"/{experiment_name}"
        else:
            return experiment_name

    @staticmethod
    def _get_internal_tags() -> Dict[str, Any]:
        """Gets ZenML internal tags for MLflow runs.

        Returns:
            Internal tags.
        """
        return {mlflow_utils.ZENML_TAG_KEY: zenml.__version__}
