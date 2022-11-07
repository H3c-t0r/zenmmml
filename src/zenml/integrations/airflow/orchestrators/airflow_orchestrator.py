# Copyright 2019 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

# Minor parts of the  `prepare_or_run_pipeline()` method of this file are
# inspired by the airflow dag runner implementation of tfx
"""Implementation of Airflow orchestrator integration."""

import datetime
import os
import shutil
import tempfile
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Type, cast

from zenml.config.global_config import GlobalConfiguration
from zenml.constants import ORCHESTRATOR_DOCKER_IMAGE_KEY
from zenml.entrypoints import StepEntrypointConfiguration
from zenml.enums import StackComponentType
from zenml.integrations.airflow.flavors.airflow_orchestrator_flavor import (
    AirflowOrchestratorConfig,
    AirflowOrchestratorSettings,
)
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.orchestrators import BaseOrchestrator
from zenml.orchestrators.utils import get_orchestrator_run_name
from zenml.stack import StackValidator
from zenml.utils import daemon, io_utils
from zenml.utils.pipeline_docker_image_builder import PipelineDockerImageBuilder

if TYPE_CHECKING:
    from zenml.config.base_settings import BaseSettings
    from zenml.config.pipeline_deployment import PipelineDeployment
    from zenml.integrations.airflow.orchestrators.dag_generator import (
        DagConfiguration,
    )
    from zenml.pipelines import Schedule
    from zenml.stack import Stack


AIRFLOW_ROOT_DIR = "airflow"
logger = get_logger(__name__)


class AirflowOrchestrator(BaseOrchestrator):
    """Orchestrator responsible for running pipelines using Airflow."""

    def __init__(self, **values: Any):
        """Sets environment variables to configure airflow.

        Args:
            **values: Values to set in the orchestrator.
        """
        super().__init__(**values)
        self.airflow_home = os.path.join(
            io_utils.get_global_config_directory(),
            AIRFLOW_ROOT_DIR,
            str(self.id),
        )
        self._set_env()

    @property
    def config(self) -> AirflowOrchestratorConfig:
        """Returns the orchestrator config.

        Returns:
            The configuration.
        """
        return cast(AirflowOrchestratorConfig, self._config)

    @property
    def settings_class(self) -> Optional[Type["BaseSettings"]]:
        """Settings class for the Kubeflow orchestrator.

        Returns:
            The settings class.
        """
        return AirflowOrchestratorSettings

    @property
    def dags_directory(self) -> str:
        """Returns path to the airflow dags directory.

        Returns:
            Path to the airflow dags directory.
        """
        return os.path.join(self.airflow_home, "dags")

    def _set_env(self) -> None:
        """Sets environment variables to configure airflow."""
        os.environ["AIRFLOW_HOME"] = self.airflow_home

        if self.config.local:
            os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = self.dags_directory
            os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "false"
            # check the DAG folder every 10 seconds for new files
            os.environ["AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL"] = "10"

    @property
    def validator(self) -> Optional["StackValidator"]:
        """Validates the stack.

        In the remote case, checks that the stack contains a container registry
        and only remote components.

        Returns:
            A `StackValidator` instance.
        """
        if self.config.local:
            # No container registry required if just running locally.
            return None
        else:

            def _validate_remote_components(stack: "Stack") -> Tuple[bool, str]:
                for component in stack.components.values():
                    if not component.config.is_local:
                        continue

                    return False, (
                        f"The Airflow orchestrator is configured to run "
                        f"pipelines remotely, but the '{component.name}' "
                        f"{component.type.value} is a local stack component "
                        f"and will not be available in the Airflow "
                        f"task.\nPlease ensure that you always use non-local "
                        f"stack components with a remote Airflow orchestrator, "
                        f"otherwise you may run into pipeline execution "
                        f"problems."
                    )

                return True, ""

            return StackValidator(
                required_components={StackComponentType.CONTAINER_REGISTRY},
                custom_validation_function=_validate_remote_components,
            )

    def prepare_pipeline_deployment(
        self,
        deployment: "PipelineDeployment",
        stack: "Stack",
    ) -> None:
        """Checks Airflow is running and copies DAG file to the DAGs directory.

        Args:
            deployment: The pipeline deployment configuration.
            stack: The stack on which the pipeline will be deployed.

        Raises:
            RuntimeError: If Airflow is not running or no DAG filepath runtime
                          option is provided.
        """
        if self.config.local:
            stack.check_local_paths()

        docker_image_builder = PipelineDockerImageBuilder()
        if stack.container_registry:
            repo_digest = docker_image_builder.build_and_push_docker_image(
                deployment=deployment, stack=stack
            )
            deployment.add_extra(ORCHESTRATOR_DOCKER_IMAGE_KEY, repo_digest)
        else:
            # If there is no container registry, we only build the image
            target_image_name = docker_image_builder.get_target_image_name(
                deployment=deployment
            )
            docker_image_builder.build_docker_image(
                target_image_name=target_image_name,
                deployment=deployment,
                stack=stack,
            )
            deployment.add_extra(
                ORCHESTRATOR_DOCKER_IMAGE_KEY, target_image_name
            )

    def prepare_or_run_pipeline(
        self,
        deployment: "PipelineDeployment",
        stack: "Stack",
    ) -> Any:
        """Creates and writes an Airflow DAG zip file.

        Args:
            deployment: The pipeline deployment to prepare or run.
            stack: The stack the pipeline will run on.
        """
        from zenml.integrations.airflow.orchestrators import dag_generator

        command = StepEntrypointConfiguration.get_entrypoint_command()

        tasks = []
        for step_name, step in deployment.steps.items():
            settings = cast(
                AirflowOrchestratorSettings,
                self.get_settings(step) or AirflowOrchestratorSettings(),
            )
            arguments = StepEntrypointConfiguration.get_entrypoint_arguments(
                step_name=step_name
            )
            task = dag_generator.TaskConfiguration(
                id=step_name,
                zenml_step_name=step.config.name,
                upstream_steps=step.spec.upstream_steps,
                command=command,
                arguments=arguments,
                operator_source=settings.operator,
                operator_kwargs=settings.operator_kwargs,
            )
            tasks.append(task)

        local_stores_path = (
            os.path.expanduser(GlobalConfiguration().local_stores_path)
            if self.config.local
            else None
        )
        docker_image = deployment.pipeline.extra[ORCHESTRATOR_DOCKER_IMAGE_KEY]
        pipeline_settings = cast(
            AirflowOrchestratorSettings,
            self.get_settings(deployment) or AirflowOrchestratorSettings(),
        )
        dag_id = pipeline_settings.dag_id or get_orchestrator_run_name(
            pipeline_name=deployment.pipeline.name
        )
        dag_config = dag_generator.DagConfiguration(
            id=dag_id,
            docker_image=docker_image,
            local_stores_path=local_stores_path,
            tasks=tasks,
            tags=pipeline_settings.dag_tags,
            dag_kwargs=pipeline_settings.dag_kwargs,
            **self._translate_schedule(deployment.schedule),
        )

        self._write_dag(dag_config)

    def _write_dag(self, dag_config: "DagConfiguration") -> None:
        """Writes an Airflow DAG to disk.

        Args:
            dag_config: Configuration of the DAG to write.
        """
        from zenml.integrations.airflow.orchestrators import dag_generator

        output_dir = self.config.dag_output_dir or self.dags_directory
        io_utils.create_dir_recursive_if_not_exists(output_dir)

        if self.config.local and output_dir != self.dags_directory:
            logger.warning(
                "You're using a local Airflow orchestrator but specified a "
                "custom DAG output directory `%s`. This DAG will not be found "
                "by the local Airflow server until you copy it in the DAGs "
                "directory `%s`.",
                output_dir,
                self.dags_directory,
            )

        dag_basename = os.path.join(output_dir, dag_config.id)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, dag_generator.CONFIG_FILENAME)
            dag_generator_path = os.path.join(tmp_dir, "dag.py")

            with open(config_path, "w") as f:
                f.write(dag_config.json())

            fileio.copy(dag_generator.__file__, dag_generator_path)
            dag_path = shutil.make_archive(
                dag_basename, format="zip", root_dir=tmp_dir
            )

        logger.info("Writing DAG definition to `%s`.", dag_path)

    def get_orchestrator_run_id(self) -> str:
        """Returns the active orchestrator run id.

        Raises:
            RuntimeError: If the environment variable specifying the run id
                is not set.

        Returns:
            The orchestrator run id.
        """
        from zenml.integrations.airflow.orchestrators.dag_generator import (
            ENV_ZENML_AIRFLOW_RUN_ID,
        )

        try:
            return os.environ[ENV_ZENML_AIRFLOW_RUN_ID]
        except KeyError:
            raise RuntimeError(
                "Unable to read run id from environment variable "
                f"{ENV_ZENML_AIRFLOW_RUN_ID}."
            )

    @staticmethod
    def _translate_schedule(
        schedule: Optional["Schedule"] = None,
    ) -> Dict[str, Any]:
        """Convert ZenML schedule into Airflow schedule.

        The Airflow schedule uses slightly different naming and needs some
        default entries for execution without a schedule.

        Args:
            schedule: Containing the interval, start and end date and
                a boolean flag that defines if past runs should be caught up
                on

        Returns:
            Airflow configuration dict.
        """
        if schedule:
            if schedule.cron_expression:
                start_time = schedule.start_time or (
                    datetime.datetime.now() - datetime.timedelta(7)
                )
                return {
                    "schedule_interval": schedule.cron_expression,
                    "start_date": start_time,
                    "end_date": schedule.end_time,
                    "catchup": schedule.catchup,
                }
            else:
                return {
                    "schedule_interval": schedule.interval_second,
                    "start_date": schedule.start_time,
                    "end_date": schedule.end_time,
                    "catchup": schedule.catchup,
                }

        return {
            "schedule_interval": "@once",
            # set the a start time in the past and disable catchup so airflow
            # runs the dag immediately
            "start_date": datetime.datetime.now() - datetime.timedelta(7),
            "catchup": False,
        }

    #####################
    #   Local Airflow   #
    #####################

    @property
    def pid_file(self) -> str:
        """Returns path to the daemon PID file.

        Returns:
            Path to the daemon PID file.
        """
        return os.path.join(self.airflow_home, "airflow_daemon.pid")

    @property
    def log_file(self) -> str:
        """Returns path to the airflow log file.

        Returns:
            str: Path to the airflow log file.
        """
        return os.path.join(self.airflow_home, "airflow_orchestrator.log")

    @property
    def password_file(self) -> str:
        """Returns path to the webserver password file.

        Returns:
            Path to the webserver password file.
        """
        return os.path.join(self.airflow_home, "standalone_admin_password.txt")

    @property
    def is_running(self) -> bool:
        """Returns whether the orchestrator is "running".

        In the non-local case, this is always True. Otherwise checks if the
        local Airflow server is running.

        Returns:
            If the orchestrator is running.

        Raises:
            RuntimeError: If port 8080 is occupied.
        """
        if not self.config.local:
            return True

        from airflow.cli.commands.standalone_command import StandaloneCommand
        from airflow.jobs.triggerer_job import TriggererJob

        daemon_running = daemon.check_if_daemon_is_running(self.pid_file)

        command = StandaloneCommand()
        webserver_port_open = command.port_open(8080)

        if not daemon_running:
            if webserver_port_open:
                raise RuntimeError(
                    "The airflow daemon does not seem to be running but "
                    "local port 8080 is occupied. Make sure the port is "
                    "available and try again."
                )

            # exit early so we don't check non-existing airflow databases
            return False

        # we can't use StandaloneCommand().is_ready() here as the
        # Airflow SequentialExecutor apparently does not send a heartbeat
        # while running a task which would result in this returning `False`
        # even if Airflow is running.
        airflow_running = webserver_port_open and command.job_running(
            TriggererJob
        )
        return airflow_running

    @property
    def is_provisioned(self) -> bool:
        """Returns whether the airflow daemon is currently running.

        Returns:
            True if the airflow daemon is running, False otherwise.
        """
        return self.is_running

    def provision(self) -> None:
        """Ensures that Airflow is running."""
        if not self.config.local:
            return

        if self.is_running:
            logger.info("Airflow is already running.")
            self._log_webserver_credentials()
            return

        if not fileio.exists(self.dags_directory):
            io_utils.create_dir_recursive_if_not_exists(self.dags_directory)

        from airflow.cli.commands.standalone_command import StandaloneCommand

        try:
            command = StandaloneCommand()
            daemon.run_as_daemon(
                command.run,
                pid_file=self.pid_file,
                log_file=self.log_file,
            )
            while not self.is_running:
                # Wait until the daemon started all the relevant airflow
                # processes
                time.sleep(0.1)
            self._log_webserver_credentials()
        except Exception as e:
            logger.error(e)
            logger.error(
                "An error occurred while starting the Airflow daemon. If you "
                "want to start it manually, use the commands described in the "
                "official Airflow quickstart guide for running Airflow locally."
            )
            self.deprovision()

    def deprovision(self) -> None:
        """Stops the airflow daemon if necessary and tears down resources."""
        if not self.config.local:
            return

        if self.is_running:
            daemon.stop_daemon(self.pid_file)

        fileio.rmtree(self.airflow_home)
        logger.info("Airflow spun down.")

    def _log_webserver_credentials(self) -> None:
        """Logs URL and credentials to log in to the airflow webserver.

        Raises:
            FileNotFoundError: If the password file does not exist.
        """
        if fileio.exists(self.password_file):
            with open(self.password_file) as file:
                password = file.read().strip()
        else:
            raise FileNotFoundError(
                f"Can't find password file '{self.password_file}'"
            )
        logger.info(
            "To inspect your DAGs, login to http://localhost:8080 "
            "with username: admin password: %s",
            password,
        )
