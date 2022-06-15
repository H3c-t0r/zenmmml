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


from zenml.integrations.constants import KSERVE, PYTORCH
from zenml.pipelines import pipeline


@pipeline(
    enable_cache=True,
    requirements=["torchvision"],
    required_integrations=[KSERVE, PYTORCH],
)
def kserve_pytorch_deployment_pipeline(
    data_loader_step,
    trainer,
    evaluator,
    deployment_trigger,
    custom_model_deployer,
):
    train_loader, test_loader = data_loader_step()
    model = trainer(train_loader)
    accuracy = evaluator(model=model, test_loader=test_loader)
    deployment_decision = deployment_trigger(accuracy=accuracy)
    custom_model_deployer(
        deployment_decision,
        model,
    )
