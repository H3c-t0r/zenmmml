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
"""Entrypoint of the Skypilot master/orchestrator VM."""

import argparse
import socket
from typing import Dict, cast

import sky

from zenml.client import Client
from zenml.entrypoints.step_entrypoint_configuration import (
    StepEntrypointConfiguration,
)
from zenml.integrations.skypilot.flavors.skypilot_orchestrator_base_vm_config import (
    SkypilotBaseOrchestratorSettings,
)
from zenml.integrations.skypilot.orchestrators.skypilot_base_vm_orchestrator import (
    ENV_ZENML_SKYPILOT_ORCHESTRATOR_RUN_ID,
    SkypilotBaseOrchestrator,
)
from zenml.logger import get_logger
from zenml.orchestrators.dag_runner import ThreadedDagRunner
from zenml.orchestrators.utils import get_config_environment_vars

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse entrypoint arguments.

    Returns:
        Parsed args.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--deployment_id", type=str, required=True)
    return parser.parse_args()


def main() -> None:
    """Entrypoint of the Skypilot master/orchestrator VM."""
    # Log to the container's stdout so it can be streamed by the client.
    logger.info("Skypilot orchestrator VM started.")

    # Parse / extract args.
    args = parse_args()

    orchestrator_run_id = socket.gethostname()

    deployment_config = Client().get_deployment(args.deployment_id)

    pipeline_dag = {
        step_name: step.spec.upstream_steps
        for step_name, step in deployment_config.step_configurations.items()
    }
    step_command = StepEntrypointConfiguration.get_entrypoint_command()
    entrypoint_str = " ".join(step_command)

    active_stack = Client().active_stack

    orchestrator = active_stack.orchestrator
    if not isinstance(orchestrator, SkypilotBaseOrchestrator):
        raise TypeError(
            "The active stack's orchestrator is not an instance of SkypilotBaseOrchestrator."
        )

    # Set up credentials
    orchestrator.setup_credentials()

    # Set the service connector AWS profile ENV variable
    orchestrator.prepare_environment_variable(set=True)

    # get active container registry
    container_registry = active_stack.container_registry
    if container_registry is None:
        raise ValueError("Container registry cannot be None.")

    if docker_creds := container_registry.credentials:
        docker_username, docker_password = docker_creds
        setup = (
            f"docker login --username $DOCKER_USERNAME --password "
            f"$DOCKER_PASSWORD {container_registry.config.uri}"
        )
        task_envs = {
            "DOCKER_USERNAME": docker_username,
            "DOCKER_PASSWORD": docker_password,
        }
    else:
        setup = None
        task_envs = None

    unique_resource_configs: Dict[str, str] = {}
    for step_name, step in deployment_config.step_configurations.items():
        settings = cast(
            SkypilotBaseOrchestratorSettings,
            orchestrator.get_settings(step),
        )
        # Handle both str and Dict[str, int] types for accelerators
        if isinstance(settings.accelerators, dict):
            accelerators_hashable = frozenset(settings.accelerators.items())
        elif isinstance(settings.accelerators, str):
            accelerators_hashable = frozenset({(settings.accelerators, 1)})
        else:
            accelerators_hashable = None
        resource_config = (
            settings.instance_type,
            settings.cpus,
            settings.memory,
            settings.disk_size,  # Assuming disk_size is part of the settings
            settings.disk_tier,  # Assuming disk_tier is part of the settings
            settings.use_spot,
            settings.spot_recovery,
            settings.region,
            settings.zone,
            accelerators_hashable,
        )
        cluster_name_parts = [
            orchestrator.sanitize_cluster_name(str(part))
            for part in resource_config
            if part is not None
        ]
        cluster_name = f"cluster-{orchestrator_run_id}" + "-".join(
            cluster_name_parts
        )
        unique_resource_configs[step_name] = cluster_name

    def run_step_on_skypilot_vm(step_name: str) -> None:
        """Run a pipeline step in a separate Skypilot VM.

        Args:
            step_name: Name of the step.
        """
        cluster_name = unique_resource_configs[step_name]

        image = SkypilotBaseOrchestrator.get_image(
            deployment=deployment_config, step_name=step_name
        )

        step_args = StepEntrypointConfiguration.get_entrypoint_arguments(
            step_name=step_name, deployment_id=deployment_config.id
        )
        arguments_str = " ".join(step_args)

        step_config = deployment_config.step_configurations[step_name].config
        settings = SkypilotBaseOrchestratorSettings.parse_obj(
            step_config.settings.get("orchestrator.skypilot", {})
        )

        env = get_config_environment_vars()
        env[ENV_ZENML_SKYPILOT_ORCHESTRATOR_RUN_ID] = orchestrator_run_id

        docker_environment_str = " ".join(
            f"-e {k}={v}" for k, v in env.items()
        )

        # Set up the task
        run_command = f"docker run --rm {docker_environment_str} {image} {entrypoint_str} {arguments_str}"
        logger.info(f"Running step `{step_name}` with command: {run_command}")
        task = sky.Task(
            run=run_command,
            setup=setup,
            envs=task_envs,
        )
        task = task.set_resources(
            sky.Resources(
                cloud=orchestrator.cloud,
                instance_type=settings.instance_type
                or orchestrator.DEFAULT_INSTANCE_TYPE,
                cpus=settings.cpus,
                memory=settings.memory,
                disk_size=settings.disk_size,
                disk_tier=settings.disk_tier,
                accelerators=settings.accelerators,
                accelerator_args=settings.accelerator_args,
                use_spot=settings.use_spot,
                spot_recovery=settings.spot_recovery,
                region=settings.region,
                zone=settings.zone,
                image_id=settings.image_id,
            )
        )

        sky.launch(
            task,
            cluster_name,
            retry_until_up=settings.retry_until_up,
            idle_minutes_to_autostop=settings.idle_minutes_to_autostop,
            down=settings.down,
            stream_logs=settings.stream_logs,
        )

        # Pop the resource configuration for this step
        unique_resource_configs.pop(step_name)

        if cluster_name in unique_resource_configs.values():
            # If there are more steps using this configuration, skip downing the cluster
            logger.info(
                f"Resource configuration for cluster '{cluster_name}' "
                "is used by subsequent steps. Skipping the downing of "
                "the cluster."
            )
        else:
            # If there are no more steps using this configuration, down the cluster
            logger.info(
                f"Resource configuration for cluster '{cluster_name}' "
                "is not used by subsequent steps. Downing the cluster."
            )
            sky.down(cluster_name)

        logger.info(f"Pod of step `{step_name}` completed.")

    ThreadedDagRunner(dag=pipeline_dag, run_fn=run_step_on_skypilot_vm).run()

    logger.info("Orchestration pod completed.")


if __name__ == "__main__":
    main()
