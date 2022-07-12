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
"""Implementation of the Label Studio annotation integration."""

import os
import subprocess
import sys
import webbrowser
from typing import Any, ClassVar, Dict, List, Optional, Tuple, cast

from label_studio_sdk import Client, Project  # type: ignore[import]

from zenml.annotators.base_annotator import BaseAnnotator
from zenml.exceptions import ProvisioningError
from zenml.integrations.label_studio import LABEL_STUDIO_ANNOTATOR_FLAVOR
from zenml.integrations.label_studio.steps.label_studio_standard_steps import (
    LabelStudioDatasetRegistrationConfig,
    LabelStudioDatasetSyncConfig,
)
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.utils import io_utils, networking_utils

logger = get_logger(__name__)

DEFAULT_LABEL_STUDIO_PORT = 8093


class LabelStudioAnnotator(BaseAnnotator):
    """Class to interact with the Label Studio annotation interface.

    Attributes:
        port: The port to use for the annotation interface.
        api_key: The API key to use for authentication.
        project_name: The name of the project to interact with.
    """

    port: int = DEFAULT_LABEL_STUDIO_PORT
    api_key: str
    project_name: Optional[str]

    FLAVOR: ClassVar[str] = LABEL_STUDIO_ANNOTATOR_FLAVOR

    def get_url(self) -> str:
        """Gets the top-level URL of the annotation interface.

        Returns:
            The URL of the annotation interface.
        """
        return f"http://localhost:{self.port}"

    def get_annotation_url(self, dataset_name: str) -> str:
        """Gets the URL of the annotation interface for the given dataset.

        Args:
            name: The name of the dataset.

        Returns:
            The URL of the annotation interface.
        """
        project_id = self.get_id_from_name(dataset_name)
        return f"{self.get_url()}/projects/{project_id}/"

    def get_id_from_name(self, dataset_name: str) -> Optional[int]:
        """Gets the ID of the given dataset.

        Args:
            name: The name of the dataset.

        Returns:
            The ID of the dataset.
        """
        ls = self._get_client()
        projects = ls.get_projects()
        try:
            project = [
                project
                for project in projects
                if project.get_params()["title"] == dataset_name
            ][0]
        except IndexError:
            return None
        return cast(int, project.get_params()["id"])

    def get_datasets(self) -> List[Any]:
        """Gets the datasets currently available for annotation.

        Returns:
            A list of datasets.
        """
        ls = self._get_client()
        return cast(List[Any], ls.get_projects())

    def get_dataset_names(self) -> List[str]:
        """Gets the names of the datasets.

        Returns:
            A list of dataset names.
        """
        return [
            dataset.get_params()["title"] for dataset in self.get_datasets()
        ]

    def get_dataset_stats(self, dataset_name: str) -> Tuple[int, int]:
        """Gets the statistics of the given dataset.

        Args:
            dataset_name: The name of the dataset.

        Returns:
            A dictionary containing the statistics of the dataset.
        """
        projects = self.get_datasets()

        try:
            project = list(
                filter(
                    lambda x: dataset_name in x.get_params()["title"], projects
                )
            )[0]
        except IndexError as e:
            raise e(
                f"Dataset {name} not found. Please use `zenml annotator dataset list` to list all available datasets."
            ) from e

        labeled_task_count = len(project.get_labeled_tasks())
        unlabeled_task_count = len(project.get_unlabeled_tasks())
        return (labeled_task_count, unlabeled_task_count)

    @property
    def root_directory(self) -> str:
        """Returns path to the root directory.

        Returns:
            Path to the root directory.
        """
        return os.path.join(
            io_utils.get_global_config_directory(),
            "annotators",
            str(self.uuid),
        )

    @property
    def _pid_file_path(self) -> str:
        """Returns path to the daemon PID file.

        Returns:
            Path to the daemon PID file.
        """
        return os.path.join(self.root_directory, "label_studio_daemon.pid")

    @property
    def _log_file(self) -> str:
        """Path of the daemon log file.

        Returns:
            Path to the daemon log file.
        """
        return os.path.join(self.root_directory, "label_studio_daemon.log")

    @property
    def is_provisioned(self) -> bool:
        """If the component provisioned resources to run locally.

        Returns:
            True if the component provisioned resources to run locally.
        """
        return fileio.exists(self.root_directory)

    @property
    def is_running(self) -> bool:
        """If the component is running locally.

        Returns:
            True if the component is running locally, False otherwise.
        """
        if sys.platform != "win32":
            from zenml.utils.daemon import check_if_daemon_is_running

            if not check_if_daemon_is_running(self._pid_file_path):
                return False
        else:
            # Daemon functionality is not supported on Windows, so the PID
            # file won't exist. This if clause exists just for mypy to not
            # complain about missing functions
            pass

        return True

    def provision(self) -> None:
        """Spins up the annotation server backend."""
        fileio.makedirs(self.root_directory)

    def deprovision(self) -> None:
        """Spins down the annotation server backend."""
        if fileio.exists(self._log_file):
            fileio.remove(self._log_file)

    def resume(self) -> None:
        """Resumes the annotation interface."""
        if self.is_running:
            logger.info("Local kubeflow pipelines deployment already running.")
            return

        self.start_annotator_daemon()

    def suspend(self) -> None:
        """Suspends the annotation interface."""
        if not self.is_running:
            logger.info("Local annotation server is not running.")
            return

        self.stop_annotator_daemon()

    def start_annotator_daemon(self) -> None:
        """Starts the annotation server backend.

        Raises:
            ProvisioningError: If the annotation server backend is already
                running or the port is already occupied.
        """
        command = [
            "label-studio",
            "start",
            "--no-browser",
            "--port",
            f"{self.port}",
        ]

        if sys.platform == "win32":
            logger.warning(
                "Daemon functionality not supported on Windows. "
                "In order to access the Label Studio server locally, "
                "please run '%s' in a separate command line shell.",
                self.port,
                " ".join(command),
            )
        elif not networking_utils.port_available(self.port):
            raise ProvisioningError(
                f"Unable to port-forward Label Studio to local "
                f"port {self.port} because the port is occupied. In order to "
                f"access Label Studio locally, please "
                f"change the configuration to use an available "
                f"port or stop the other process currently using the port."
            )
        else:
            from zenml.utils import daemon

            def _daemon_function() -> None:
                """Forwards the port of the Kubeflow Pipelines Metadata pod ."""
                subprocess.check_call(command)

            daemon.run_as_daemon(
                _daemon_function,
                pid_file=self._pid_file_path,
                log_file=self._log_file,
            )
            logger.info(
                "Started Label Studio daemon (check the daemon"
                "logs at `%s` in case you're not able to access the annotation "
                f"interface). Please visit `{self.get_url()}/` to use the Label Studio interface.",
                self._log_file,
            )

    def stop_annotator_daemon(self) -> None:
        """Stops the annotation server backend."""
        if fileio.exists(self._pid_file_path):
            if sys.platform == "win32":
                # Daemon functionality is not supported on Windows, so the PID
                # file won't exist. This if clause exists just for mypy to not
                # complain about missing functions
                pass
            else:
                from zenml.utils import daemon

                daemon.stop_daemon(self._pid_file_path)
                fileio.remove(self._pid_file_path)

    def launch(self, url: Optional[str]) -> None:
        """Launches the annotation interface.

        Args:
            url: The URL of the annotation interface.
        """
        if not url:
            url = self.get_url()
        if self._connection_available():
            webbrowser.open(url, new=1, autoraise=True)
        else:
            logger.warning(
                "Could not launch annotation interface"
                "because the connection could not be established."
            )

    def _get_client(self) -> Client:
        """Gets Label Studio client.

        Returns:
            Label Studio client.
        """
        return Client(url=self.get_url(), api_key=self.api_key)

    def _connection_available(self) -> bool:
        """Checks if the connection to the annotation server is available.

        Returns:
            True if the connection is available, False otherwise.
        """
        ls = self._get_client()
        try:
            result = ls.check_connection()
            return result.get("status") == "UP"  # type: ignore[no-any-return]
        except Exception:
            logger.error(
                "Connection error: No connection was able to be established to the Label Studio backend."
            )
            return False

    def add_dataset(self, **kwargs: Any) -> Any:
        """Registers a dataset for annotation.

        Args:
            **kwargs: Additional keyword arguments to pass to the Label Studio client.

        Returns:
            A Label Studio Project object.
        """
        ls = self._get_client()
        dataset_name = kwargs.get("dataset_name")
        label_config = kwargs.get("label_config")
        if not dataset_name:
            raise ValueError("`dataset_name` keyword argument is required.")
        elif not label_config:
            raise ValueError("`label_config` keyword argument is required.")

        dataset_id = self.get_id_from_name(dataset_name)
        if not dataset_id:
            raise ValueError(
                f"Dataset name '{dataset_name}' has no corresponding `dataset_id` in Label Studio."
            )
        return ls.start_project(
            title=dataset_name,
            label_config=label_config,
        )

    def delete_dataset(self, **kwargs: Any) -> None:
        """Deletes a dataset from the annotation interface.

        Args:
            **kwargs: Additional keyword arguments to pass to the Label Studio
            client.

        Raises:
            NotImplementedError: If the deletion of a dataset is not supported.
        """
        raise NotImplementedError("Awaiting Label Studio release.")
        # TODO: Awaiting a new Label Studio version to be released with this method
        # ls = self._get_client()
        # dataset_name = kwargs.get("dataset_name")
        # if not dataset_name:
        #     raise ValueError("`dataset_name` keyword argument is required.")

        # dataset_id = self.get_id_from_name(dataset_name)
        # if not dataset_id:
        #     raise ValueError(
        #         f"Dataset name '{dataset_name}' has no corresponding `dataset_id` in Label Studio."
        #     )
        # ls.delete_project(dataset_id)

    def get_dataset(self, **kwargs: Any) -> Any:
        """Gets the dataset with the given name.

        Args:
            **kwargs: Additional keyword arguments to pass to the Label Studio client.

        Returns:
            The LabelStudio Dataset object (a 'Project') for the given name.
        """
        # TODO: check for and raise error if client unavailable
        ls = self._get_client()
        dataset_name = kwargs.get("dataset_name")
        if not dataset_name:
            raise ValueError("`dataset_name` keyword argument is required.")

        dataset_id = self.get_id_from_name(dataset_name)
        if not dataset_id:
            raise ValueError(
                f"Dataset name '{dataset_name}' has no corresponding `dataset_id` in Label Studio."
            )
        return ls.get_project(dataset_id)

    def _dataset_name_to_project(self, dataset_name: str) -> Optional[Project]:
        """Finds the project id for a specific dataset name.

        Args:
            dataset_name: Name of the dataset.

        Returns:
            The LabelStudio Dataset object (a 'Project') for the given name.
        """
        ls = self._get_client()
        projects = ls.get_projects()
        current_project = [
            project
            for project in projects
            if project.get_params()["title"] == dataset_name
        ]
        return current_project[0]

    def get_converted_dataset(
        self, dataset_name: str, output_format: str
    ) -> Dict[Any, Any]:
        """Extract annotated tasks in a specific converted format.

        Args:
            dataset_id: Id of the dataset.
            output_format: Output format.

        Returns:
            A dictionary containing the converted dataset.
        """
        # project = self._dataset_name_to_project(dataset_name)
        self._get_client()
        project = self.get_dataset(dataset_name=dataset_name)
        return project.export_tasks(export_type=output_format)  # type: ignore[no-any-return]

    def get_labeled_data(self, **kwargs: Any) -> Any:
        """Gets the labeled data for the given dataset.

        Args:
            dataset_name: Name of the dataset.
            *args: Additional arguments to pass to the Label Studio client.
            **kwargs: Additional keyword arguments to pass to the Label Studio client.

        Returns:
            A dictionary containing the labeled data.
        """
        ls = self._get_client()
        dataset_name = kwargs.get("dataset_name")
        if not dataset_name:
            raise ValueError("`dataset_name` keyword argument is required.")

        dataset_id = self.get_id_from_name(dataset_name)
        if not dataset_id:
            raise ValueError(
                f"Dataset name '{dataset_name}' has no corresponding `dataset_id` in Label Studio."
            )
        return ls.get_project(dataset_id).get_labeled_tasks()

    def get_unlabeled_data(self, **kwargs: str) -> Any:
        """Gets the unlabeled data for the given dataset.

        Args:
            **kwargs: Additional keyword arguments to pass to the Label Studio client.

        Returns:
            A dictionary containing the unlabeled data.
        """
        ls = self._get_client()
        dataset_name = kwargs.get("dataset_name")
        if not dataset_name:
            raise ValueError("`dataset_name` keyword argument is required.")

        dataset_id = self.get_id_from_name(dataset_name)
        if not dataset_id:
            raise ValueError(
                f"Dataset name '{dataset_name}' has no corresponding `dataset_id` in Label Studio."
            )
        return ls.get_project(dataset_id).get_unlabeled_tasks()

    def register_dataset_for_annotation(
        self,
        config: LabelStudioDatasetRegistrationConfig,
    ) -> Any:
        """Registers a dataset for annotation.

        Args:
            config: Configuration for the dataset.

        Returns:
            A Label Studio Project object.
        """
        ls = self._get_client()

        if self.get_id_from_name(config.dataset_name):
            dataset = ls.get_project(self.get_id_from_name(config.dataset_name))
        else:
            dataset = self.add_dataset(
                dataset_name=config.dataset_name,
                label_config=config.label_config,
            )

        return dataset

    def _get_azure_import_storage_sources(
        self, dataset_id: int
    ) -> List[Dict[str, Any]]:
        """Gets a list of all Azure import storage sources.

        Args:
            dataset_id: Id of the dataset.

        Returns:
            A list of Azure import storage sources.

        Raises:
            ConnectionError: If the connection to the Label Studio backend is unavailable.
        """
        # TODO: check if client actually is connected etc
        ls = self._get_client()
        query_url = f"/api/storages/azure?project={dataset_id}"
        response = ls.make_request(method="GET", url=query_url)
        if response.status_code == 200:
            return cast(List[Dict[str, Any]], response.json())
        else:
            raise ConnectionError(
                f"Unable to get list of import storage sources. Client raised HTTP error {response.status_code}."
            )

    def _get_gcs_import_storage_sources(
        self, dataset_id: int
    ) -> List[Dict[str, Any]]:
        """Gets a list of all Google Cloud Storage import storage sources.

        Args:
            dataset_id: Id of the dataset.

        Returns:
            A list of Google Cloud Storage import storage sources.

        Raises:
            ConnectionError: If the connection to the Label Studio backend is unavailable.
        """
        # TODO: check if client actually is connected etc
        ls = self._get_client()
        query_url = f"/api/storages/gcs?project={dataset_id}"
        response = ls.make_request(method="GET", url=query_url)
        if response.status_code == 200:
            return cast(List[Dict[str, Any]], response.json())
        else:
            raise ConnectionError(
                f"Unable to get list of import storage sources. Client raised HTTP error {response.status_code}."
            )

    def _get_s3_import_storage_sources(
        self, dataset_id: int
    ) -> List[Dict[str, Any]]:
        """Gets a list of all AWS S3 import storage sources.

        Args:
            dataset_id: Id of the dataset.

        Returns:
            A list of AWS S3 import storage sources.

        Raises:
            ConnectionError: If the connection to the Label Studio backend is unavailable.
        """
        # TODO: check if client actually is connected etc
        ls = self._get_client()
        query_url = f"/api/storages/s3?project={dataset_id}"
        response = ls.make_request(method="GET", url=query_url)
        if response.status_code == 200:
            return cast(List[Dict[str, Any]], response.json())
        else:
            raise ConnectionError(
                f"Unable to get list of import storage sources. Client raised HTTP error {response.status_code}."
            )

    def _storage_source_already_exists(
        self, uri: str, config: LabelStudioDatasetSyncConfig, dataset: Project
    ) -> bool:
        """Returns whether a storage source already exists.

        Args:
            uri: URI of the storage source.
            config: Configuration for the dataset.
            dataset: Label Studio dataset.

        Returns:
            True if the storage source already exists, False otherwise.

        Raises:
            NotImplementedError: If the storage source type is not supported.
        """
        # TODO: check we are already connected
        dataset_id = int(dataset.get_params()["id"])
        if config.storage_type == "azure":
            storage_sources = self._get_azure_import_storage_sources(dataset_id)
        elif config.storage_type == "gcs":
            storage_sources = self._get_gcs_import_storage_sources(dataset_id)
        elif config.storage_type == "s3":
            storage_sources = self._get_s3_import_storage_sources(dataset_id)
        else:
            raise NotImplementedError(
                f"Storage type '{config.storage_type}' not implemented."
            )
        return any(
            (
                source.get("presign") == config.presign
                and source.get("bucket") == uri
                and source.get("regex_filter") == config.regex_filter
                and source.get("use_blob_urls") == config.use_blob_urls
                and source.get("title") == dataset.get_params()["title"]
                and source.get("description") == config.description
                and source.get("presign_ttl") == config.presign_ttl
                and source.get("project") == dataset_id
            )
            for source in storage_sources
        )

    def get_parsed_label_config(self, dataset_id: int) -> Dict[str, Any]:
        """Returns the parsed Label Studio label config for a dataset.

        Args:
            dataset_id: Id of the dataset.

        Returns:
            A dictionary containing the parsed label config.

        Raises:
            ValueError: If no dataset is found for the given id.
        """
        # TODO: check if client actually is connected etc
        ls = self._get_client()
        dataset = ls.get_project(dataset_id)
        if dataset:
            return cast(Dict[str, Any], dataset.parsed_label_config)
        else:
            raise ValueError("No dataset found for the given id.")

    def connect_and_sync_external_storage(
        self,
        uri: str,
        config: LabelStudioDatasetSyncConfig,
        dataset: Project,
    ) -> Optional[Dict[str, Any]]:
        """Syncs the external storage for the given project.

        Args:
            uri: URI of the storage source.
            config: Configuration for the dataset.
            dataset: Label Studio dataset.

        Returns:
            A dictionary containing the sync result.

        Raises:
            ValueError: If the storage type is not supported.
        """
        if self._storage_source_already_exists(uri, config, dataset):
            return None
        if config.storage_type == "azure":
            if not config.azure_account_name or not config.azure_account_key:
                logger.warn(
                    "Authentication credentials for Azure aren't fully "
                    "provided. Please update the storage synchronization "
                    "settings in the Label Studio web UI as per your needs."
                )
            storage = dataset.connect_azure_import_storage(
                container=uri,
                prefix=config.prefix,
                regex_filter=config.regex_filter,
                use_blob_urls=config.use_blob_urls,
                presign=config.presign,
                presign_ttl=config.presign_ttl,
                title=dataset.get_params()["title"],
                description=config.description,
                account_name=config.azure_account_name,
                account_key=config.azure_account_key,
            )
        elif config.storage_type == "gcs":
            if not config.google_application_credentials:
                logger.warn(
                    "Authentication credentials for Google Cloud Storage "
                    "aren't fully provided. Please update the storage "
                    "synchronization settings in the Label Studio web UI as "
                    "per your needs."
                )
            storage = dataset.connect_google_import_storage(
                bucket=uri,
                prefix=config.prefix,
                regex_filter=config.regex_filter,
                use_blob_urls=config.use_blob_urls,
                presign=config.presign,
                presign_ttl=config.presign_ttl,
                title=dataset.get_params()["title"],
                description=config.description,
                google_application_credentials=config.google_application_credentials,
            )
        elif config.storage_type == "s3":
            if not config.aws_access_key_id or not config.aws_secret_access_key:
                logger.warn(
                    "Authentication credentials for S3 aren't fully provided."
                    "Please update the storage synchronization settings in the "
                    " Label Studio web UI as per your needs."
                )
            storage = dataset.connect_s3_import_storage(
                bucket=uri,
                prefix=config.prefix,
                regex_filter=config.regex_filter,
                use_blob_urls=config.use_blob_urls,
                presign=config.presign,
                presign_ttl=config.presign_ttl,
                title=dataset.get_params()["title"],
                description=config.description,
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                aws_session_token=config.aws_session_token,
                region_name=config.region_name,
                s3_endpoint=config.s3_endpoint,
            )
        else:
            raise ValueError(
                f"Invalid storage type. '{config.storage_type}' is not supported by ZenML's Label Studio integration. Please choose between 'azure', 'gcs' and 'aws'."
            )

        ls = self._get_client()
        return cast(
            Dict[str, Any],
            ls.sync_storage(
                storage_id=storage["id"], storage_type=storage["type"]
            ),
        )
