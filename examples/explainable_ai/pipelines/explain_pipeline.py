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

from steps.explainer import explain
from steps.trainers import trainer
from steps.importers import importer_cifar10

from zenml import pipeline
from zenml.config import DockerSettings
from zenml.integrations.constants import PYTORCH

docker_settings = DockerSettings(
    required_integrations=[PYTORCH],
    requirements=["torchvision"],
)


@pipeline(settings={"docker": docker_settings})
def explain_pipeline(batch_size: int):
    """Link all the steps and artifacts together."""
    train, test, val, classes = importer_cifar10(batch_size=batch_size)
    model = trainer(
        dataloader_train=train,
        dataloader_test=test,
        dataloader_val=val,
    )
    explain(model=model, test_dataloader=test, classes=classes)
