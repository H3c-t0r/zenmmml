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

import click
from pipelines import inference_pipeline, training_pipeline
from steps.convert_annotations_step import convert_annotations
from steps.deployment_triggers import deployment_trigger
from steps.get_labeled_data import get_labeled_data_step
from steps.get_or_create_dataset import get_or_create_the_dataset
from steps.load_image_data_step import load_image_data
from steps.model_deployers import model_deployer
from steps.prediction_steps import prediction_service_loader, predictor
from steps.pytorch_trainer import pytorch_model_trainer
from steps.sync_new_data_to_label_studio import azure_data_sync
from materializers.pillow_image_materializer import PillowImageMaterializer

@click.command()
@click.option(
    "--train",
    "pipeline",
    flag_value="train",
    default=True,
    help="Run the training pipeline.",
)
@click.option(
    "--inference",
    "pipeline",
    flag_value="inference",
    help="Run the inference pipeline.",
)
def main(pipeline):
    """Simple CLI interface for annotation example."""
    if pipeline == "train":
        training_pipeline(
            get_or_create_dataset=get_or_create_the_dataset,
            get_labeled_data=get_labeled_data_step,
            convert_annotations=convert_annotations(),
            model_trainer=pytorch_model_trainer(),
            deployment_trigger=deployment_trigger(),
            model_deployer=model_deployer,  # TODO: how to run label studio with local mlflow?
        ).run()
    elif pipeline == "inference":
        inference_pipeline(
            get_or_create_dataset=get_or_create_the_dataset,
            inference_data_loader=load_image_data().with_return_materializers(
                {"images": PillowImageMaterializer}
            ),  # TODO: configure image path
            prediction_service_loader=prediction_service_loader(),  # TODO
            predictor=predictor(),  # TODO
            data_syncer=azure_data_sync,
        ).run()


if __name__ == "__main__":
    main()
