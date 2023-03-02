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


from pipelines import inference_pipeline, training_pipeline
from steps import (
    drift_detector,
    evaluator,
    inference_data_loader,
    predictor,
    svc_trainer_mlflow,
    training_data_loader,
)

from zenml.integrations.evidently.visualizers import EvidentlyVisualizer
from zenml.integrations.mlflow.steps.mlflow_deployer import (
    MLFlowDeployerParameters,
    mlflow_model_registry_deployer_step,
)
from zenml.integrations.mlflow.steps.mlflow_registry import (
    MLFlowRegistryParameters,
    mlflow_register_model_step,
)
from zenml.model_registries.base_model_registry import (
    ModelRegistryModelMetadata,
)


def main():

    # initialize and run the training pipeline
    training_pipeline_instance = training_pipeline(
        training_data_loader=training_data_loader(),
        trainer=svc_trainer_mlflow(),
        evaluator=evaluator(),
        model_register=mlflow_register_model_step(
            params=MLFlowRegistryParameters(
                name="tensorflow-mnist-model",
                metadata=ModelRegistryModelMetadata(gamma=0.01, arch="svc"),
                description="The first run of the Quickstart pipeline.",
            )
        ),
    )
    training_pipeline_instance.run()

    # initialize and run the inference pipeline
    inference_pipeline_instance = inference_pipeline(
        inference_data_loader=inference_data_loader(),
        mlflow_model_deployer=mlflow_model_registry_deployer_step(
            params=MLFlowDeployerParameters(
                registry_model_name="tensorflow-mnist-model",
                registry_model_version="1",
                # or you can use the model stage if you have set it in the MLflow registry
                # registered_model_stage="None" # "Staging", "Production", "Archived"
            )
        ),
        predictor=predictor(),
        training_data_loader=training_data_loader(),
        drift_detector=drift_detector,
    )
    inference_pipeline_instance.run()

    # visualize the data drift
    inf_run = inference_pipeline_instance.get_runs()[-1]
    drift_detection_step = inf_run.get_step(step="drift_detector")
    EvidentlyVisualizer().visualize(drift_detection_step)


if __name__ == "__main__":
    main()
