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
"""Kubernetes orchestrator flavor."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from zenml.config.base_settings import BaseSettings
from zenml.integrations.kubernetes import KUBERNETES_ORCHESTRATOR_FLAVOR
from zenml.orchestrators import BaseOrchestratorConfig, BaseOrchestratorFlavor

if TYPE_CHECKING:
    from zenml.integrations.kubernetes.orchestrators import (
        KubernetesOrchestrator,
    )


class KubernetesOrchestratorSettings(BaseSettings):
    """Settings for the Kubernetes orchestrator.

    Attributes:
        tolerations: Tolerations to apply to Kubernetes pods.
        affinity: Pod affinity(s) to apply to Kubernetes pods.
    """

    tolerations: List[Dict[str, str]] = []
    affinity: Dict[str, Dict[str, Any]] = {}


class KubernetesOrchestratorConfig(BaseOrchestratorConfig):
    """Configuration for the Kubernetes orchestrator.

    Attributes:
        kubernetes_context: Optional name of a Kubernetes context to run
            pipelines in. If not set, the current active context will be used.
            You can find the active context by running `kubectl config
            current-context`.
        kubernetes_namespace: Name of the Kubernetes namespace to be used.
            If not provided, `zenml` namespace will be used.
        synchronous: If `True`, running a pipeline using this orchestrator will
            block until all steps finished running on Kubernetes.
        skip_config_loading: If `True`, don't load the Kubernetes context and
            clients. This is only useful for unit testing.
    """

    kubernetes_context: Optional[str] = None
    kubernetes_namespace: str = "zenml"
    synchronous: bool = False
    skip_config_loading: bool = False

    @property
    def is_remote(self) -> bool:
        """Checks if this stack component is running remotely.

        This designation is used to determine if the stack component can be
        used with a local ZenML database or if it requires a remote ZenML
        server.

        Returns:
            True if this config is for a remote component, False otherwise.
        """
        return True


class KubernetesOrchestratorFlavor(BaseOrchestratorFlavor):
    """Kubernetes orchestrator flavor."""

    @property
    def name(self) -> str:
        """Name of the flavor.

        Returns:
            The name of the flavor.
        """
        return KUBERNETES_ORCHESTRATOR_FLAVOR

    @property
    def config_class(self) -> Type[KubernetesOrchestratorConfig]:
        """Returns `KubernetesOrchestratorConfig` config class.

        Returns:
                The config class.
        """
        return KubernetesOrchestratorConfig

    @property
    def implementation_class(self) -> Type["KubernetesOrchestrator"]:
        """Implementation class for this flavor.

        Returns:
            The implementation class.
        """
        from zenml.integrations.kubernetes.orchestrators import (
            KubernetesOrchestrator,
        )

        return KubernetesOrchestrator
