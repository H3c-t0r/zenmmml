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
"""Implementation of Kubernetes metadata store."""

from typing import Any, ClassVar, Dict

from kubernetes import client as k8s_client
from pydantic import root_validator

from zenml.exceptions import StackComponentInterfaceError
from zenml.integrations.kubernetes import KUBERNETES_METADATA_STORE_FLAVOR
from zenml.integrations.kubernetes.orchestrators import kube_utils
from zenml.logger import get_logger
from zenml.metadata_stores.mysql_metadata_store import MySQLMetadataStore

logger = get_logger(__name__)


class KubernetesMetadataStore(MySQLMetadataStore):
    """Kubernetes metadata store (MySQL database deployed in the cluster).

    Attributes:
        deployment_name: Name of the kubernetes deployment and corresponding
            service/pod that will be created when calling `provision()`.
        kubernetes_context: Name of the kubernetes context in which to deploy
            and provision the MySQL database.
        kubernetes_namespace: Name of the kubernetes namespace.
            Defaults to "default".
        storage_capacity: Storage capacity of the metadata store.
            Defaults to `"10Gi"` (=10GB).
    """

    deployment_name: str
    kubernetes_context: str
    kubernetes_namespace: str = "zenml"
    storage_capacity: str = "10Gi"
    _k8s_core_api: k8s_client.CoreV1Api = None
    _k8s_apps_api: k8s_client.AppsV1Api = None

    FLAVOR: ClassVar[str] = KUBERNETES_METADATA_STORE_FLAVOR

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initiate the Pydantic object and initialize the k8s clients.

        Args:
            *args: The positional arguments to pass to the Pydantic object.
            **kwargs: The keyword arguments to pass to the Pydantic object.
        """
        super().__init__(*args, **kwargs)
        self._initialize_k8s_clients()

    def _initialize_k8s_clients(self) -> None:
        """Initialize the Kubernetes clients."""
        kube_utils.load_kube_config(context=self.kubernetes_context)
        self._k8s_core_api = k8s_client.CoreV1Api()
        self._k8s_apps_api = k8s_client.AppsV1Api()

    @root_validator(skip_on_failure=False)
    def check_deployment_name_set(
        cls, values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Pydantic root_validator.

        This ensures that the `deployment_name` is set and raises an error
        with a custom error message otherwise.

        Args:
            values: Values passed to the object constructor.

        Raises:
            StackComponentInterfaceError: if `deployment_name` attribute is not
                defined.

        Returns:
            Values passed to the Pydantic constructor.
        """
        if "deployment_name" not in values:
            raise StackComponentInterfaceError(
                "Required field `deployment_name` missing for "
                "`KubernetesMetadataStore`. "
                "Note: the `kubernetes` metadata store flavor is a special "
                "subtype of the `mysql` metadata store that deploys a fresh "
                "MySQL database within your k8s cluster when running "
                "`zenml stack up`. "
                "If you already have a MySQL database running in your cluster "
                "(or elsewhere), simply use the `mysql` metadata store flavor "
                "instead."
            )
        return values

    @property
    def deployment_exists(self) -> bool:
        """Check whether a MySQL deployment exists in the cluster.

        Returns:
            Whether a MySQL deployment exists in the cluster.
        """
        resp = self._k8s_apps_api.list_namespaced_deployment(
            namespace=self.kubernetes_namespace
        )
        for i in resp.items:
            if i.metadata.name == self.deployment_name:
                return True
        return False

    @property
    def is_provisioned(self) -> bool:
        """If the component provisioned resources to run.

        Checks whether the required MySQL deployment exists.

        Returns:
            True if the component provisioned resources to run.
        """
        return super().is_provisioned and self.deployment_exists

    @property
    def is_running(self) -> bool:
        """If the component is running.

        Returns:
            True if `is_provisioned` else False.
        """
        return self.is_provisioned

    def provision(self) -> None:
        """Provision the metadata store.

        Creates a deployment with a MySQL database running in it.
        """
        logger.info("Provisioning Kubernetes MySQL metadata store...")
        kube_utils.create_namespace(
            core_api=self._k8s_core_api, namespace=self.kubernetes_namespace
        )
        kube_utils.create_mysql_deployment(
            core_api=self._k8s_core_api,
            apps_api=self._k8s_apps_api,
            namespace=self.kubernetes_namespace,
            storage_capacity=self.storage_capacity,
            deployment_name=self.deployment_name,
        )

    def deprovision(self) -> None:
        """Deprovision the metadata store by deleting the MySQL deployment."""
        logger.info("Deleting Kubernetes MySQL metadata store...")
        kube_utils.delete_deployment(
            apps_api=self._k8s_apps_api,
            deployment_name=self.deployment_name,
            namespace=self.kubernetes_namespace,
        )
