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

from zenml.enums import OrchestratorFlavor, StackComponentType
from zenml.integrations.airflow.orchestrators import AirflowOrchestrator


def test_airflow_orchestrator_attributes():
    """Tests that the basic attributes of the airflow orchestrator are set
    correctly."""
    orchestrator = AirflowOrchestrator(name="")

    assert orchestrator.supports_local_execution is True
    assert orchestrator.supports_remote_execution is False
    assert orchestrator.type == StackComponentType.ORCHESTRATOR
    assert orchestrator.flavor == OrchestratorFlavor.AIRFLOW

    assert orchestrator.runtime_options() == {"dag_filepath": None}
