#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.

import os
from asyncio.log import logger
from typing import Optional, cast

import numpy as np  # type: ignore [import]
import pandas as pd
import requests  # type: ignore [import]
import tensorflow as tf  # type: ignore [import]
from pydantic import ValidationError  # type: ignore [import]
from rich import print
from sklearn.base import ClassifierMixin
from sklearn.linear_model import LogisticRegression

from zenml.artifacts import ModelArtifact
from zenml.environment import Environment
from zenml.integrations.constants import SELDON, SKLEARN, TENSORFLOW
from zenml.integrations.seldon.services import (
    SeldonDeploymentConfig,
    SeldonDeploymentService,
)
from zenml.io import utils as io_utils
from zenml.pipelines import pipeline
from zenml.services import load_last_service_from_step
from zenml.steps import BaseStepConfig, Output, StepContext, step
from zenml.steps.step_environment import STEP_ENVIRONMENT_NAME, StepEnvironment


@step
def importer_mnist() -> Output(
    x_train=np.ndarray, y_train=np.ndarray, x_test=np.ndarray, y_test=np.ndarray
):
    """Download the MNIST data store it as an artifact"""
    (x_train, y_train), (
        x_test,
        y_test,
    ) = tf.keras.datasets.mnist.load_data()
    return x_train, y_train, x_test, y_test


@step
def normalizer(
    x_train: np.ndarray, x_test: np.ndarray
) -> Output(x_train_normed=np.ndarray, x_test_normed=np.ndarray):
    """Normalize the values for all the images so they are between 0 and 1"""
    x_train_normed = x_train / 255.0
    x_test_normed = x_test / 255.0
    return x_train_normed, x_test_normed


class TensorflowTrainerConfig(BaseStepConfig):
    """Trainer params"""

    epochs: int = 1
    lr: float = 0.001


@step
def tf_trainer(
    config: TensorflowTrainerConfig,
    x_train: np.ndarray,
    y_train: np.ndarray,
) -> tf.keras.Model:
    """Train a neural net from scratch to recognize MNIST digits return our
    model or the learner"""
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Flatten(input_shape=(28, 28)),
            tf.keras.layers.Dense(10),
        ]
    )

    model.compile(
        optimizer=tf.keras.optimizers.Adam(config.lr),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
        metrics=["accuracy"],
    )

    model.fit(
        x_train,
        y_train,
        epochs=config.epochs,
    )

    # write model
    return model


@step
def tf_evaluator(
    x_test: np.ndarray,
    y_test: np.ndarray,
    model: tf.keras.Model,
) -> float:
    """Calculate the loss for the model for each epoch in a graph"""

    _, test_acc = model.evaluate(x_test, y_test, verbose=2)
    return test_acc


class SklearnTrainerConfig(BaseStepConfig):
    """Trainer params"""

    solver: str = "saga"
    penalty: str = "l1"
    C: float = 1.0
    tol: float = 0.1


@step
def sklearn_trainer(
    config: SklearnTrainerConfig,
    x_train: np.ndarray,
    y_train: np.ndarray,
) -> ClassifierMixin:
    """Train SVC from sklearn."""
    clf = LogisticRegression(
        penalty=config.penalty, solver=config.solver, tol=config.tol, C=config.C
    )
    clf.fit(x_train.reshape((x_train.shape[0], -1)), y_train)
    return clf


@step
def sklearn_evaluator(
    x_test: np.ndarray,
    y_test: np.ndarray,
    model: ClassifierMixin,
) -> float:
    """Calculate accuracy score with classifier."""

    test_acc = model.score(x_test.reshape((x_test.shape[0], -1)), y_test)
    return test_acc


class DeploymentTriggerConfig(BaseStepConfig):
    """Parameters that are used to trigger the deployment"""

    min_accuracy: float


@step
def deployment_trigger(
    accuracy: float,
    config: DeploymentTriggerConfig,
) -> bool:
    """Implements a simple model deployment trigger that looks at the
    input model accuracy and decides if it is good enough to deploy"""

    return accuracy > config.min_accuracy


class SeldonDeployerConfig(BaseStepConfig):
    """Seldon model deployer step configuration

    Attributes:
        model_name: the name of the Seldon model logged in the Seldon artifact
            store for the current pipeline.
        replicas: number of server replicas to use for the prediction service
        implementation: the Seldon Core implementation to use for the prediction
            service
    """

    model_name: str = "model"
    replicas: int = 1
    implementation: str
    secret_name: Optional[str]
    kubernetes_context: Optional[str]
    namespace: Optional[str]
    base_url: str
    timeout: int
    step_name: Optional[str]


@step(enable_cache=True)
def seldon_model_deployer(
    deploy_decision: bool,
    config: SeldonDeployerConfig,
    model: ModelArtifact,
    context: StepContext,
) -> SeldonDeploymentService:
    """Seldon Core model deployer pipeline step

    Args:
        deploy_decision: whether to deploy the model or not
        config: configuration for the deployer step
        model: the model artifact to deploy
        context: pipeline step context

    Returns:
        Seldon Core deployment service
    """
    # Find a service created by a previous run of this step
    step_env = cast(StepEnvironment, Environment()[STEP_ENVIRONMENT_NAME])
    step_name = config.step_name or step_env.step_name

    logger.info(
        f"Loading last service deployed by step {step_name} and "
        f"pipeline {step_env.pipeline_name}..."
    )

    try:
        service = cast(
            SeldonDeploymentService,
            # TODO [HIGH]: catch errors that are raised because a previous step used
            #   an integration that is no longer available
            load_last_service_from_step(
                pipeline_name=step_env.pipeline_name,
                step_name=step_name,
                step_context=context,
            ),
        )
    except KeyError as e:
        # pipeline or step name not found (e.g. never ran before)
        logger.error(f"No service found: {str(e)}.")
        service = None
    except ValidationError as e:
        # invalid service configuration (e.g. missing required fields because
        # the previous pipeline was run with an older service version and
        # the schemas are not compatible)
        logger.error(f"Invalide service found: {str(e)}.")
        service = None
    if service and not isinstance(service, SeldonDeploymentService):
        logger.error(
            f"Last service deployed by step {step_name} and "
            f"pipeline {step_env.pipeline_name} has invalid type. Expected "
            f"SeldonDeploymentService, found {type(service)}."
        )
        service = None

    def prepare_service_config(model_uri: str) -> SeldonDeploymentConfig:
        """Prepare the model files for model serving and create and return a
        Seldon service configuration for the model.

        This function ensures that the model files are in the correct format
        and file structure required by the Seldon Core server implementation
        used for model serving.

        Args:
            model_uri: the URI of the model artifact being served

        Returns:
            The URL to the model ready for serving.
        """
        served_model_uri = os.path.join(
            context.get_output_artifact_uri(), "seldon"
        )
        io_utils.makedirs(served_model_uri)

        # TODO [MEDIUM]: validate the model artifact type against the
        #   supported built-in Seldon server implementations
        if config.implementation == "TENSORFLOW_SERVER":
            # the TensorFlow server expects model artifacts to be
            # stored in numbered subdirectories, each representing a model version
            io_utils.copy_dir(model_uri, os.path.join(served_model_uri, "1"))
        elif config.implementation == "SKLEARN_SERVER":
            # the sklearn server expects model artifacts to be
            # stored in a file called model.joblib
            model_uri = os.path.join(model.uri, "model")
            if not io_utils.exists(model.uri):
                raise RuntimeError(
                    f"Expected sklearn model artifact was not found at {model_uri}"
                )
            io_utils.copy(
                model_uri, os.path.join(served_model_uri, "model.joblib")
            )
        else:
            # TODO [MEDIUM]: implement model preprocessing for other built-in
            #   Seldon server implementations
            pass

        return SeldonDeploymentConfig(
            model_uri=served_model_uri,
            model_name=config.model_name,
            # TODO [MEDIUM]: auto-detect built-in Seldon server implementation
            #   from the model artifact type
            implementation=config.implementation,
            secret_name=config.secret_name,
            pipeline_name=step_env.pipeline_name,
            pipeline_run_id=step_env.pipeline_run_id,
            pipeline_step_name=step_name,
            replicas=config.replicas,
            kubernetes_context=config.kubernetes_context,
            namespace=config.namespace,
            base_url=config.base_url,
        )

    if not deploy_decision:
        print(
            "Skipping model deployment because the model quality does not meet "
            "the criteria"
        )
        if not service:
            service_config = prepare_service_config(model.uri)
            service = SeldonDeploymentService(config=service_config)
        return service

    service_config = prepare_service_config(model.uri)
    if service and not service.is_stopped:
        print("Updating an existing Seldon deployment service")
        service.update(service_config)
    else:
        print("Creating a new Seldon deployment service")
        service = SeldonDeploymentService(config=service_config)

    service.start(timeout=config.timeout)
    print(
        f"Seldon deployment service started and reachable at:\n"
        f"    {service.prediction_url}\n"
    )

    return service


class SeldonDeploymentLoaderStepConfig(BaseStepConfig):
    """Seldon deployment loader configuration

    Attributes:
        pipeline_name: name of the pipeline that deployed the Seldon prediction
            server
        step_name: the name of the step that deployed the Seldon prediction
            server
        running: when this flag is set, the step only returns a running service
    """

    pipeline_name: str
    step_name: str
    running: bool = True


@step(enable_cache=False)
def prediction_service_loader(
    config: SeldonDeploymentLoaderStepConfig, context: StepContext
) -> SeldonDeploymentService:
    """Get the prediction service started by the deployment pipeline"""

    service = load_last_service_from_step(
        pipeline_name=config.pipeline_name,
        step_name=config.step_name,
        step_context=context,
        running=config.running,
    )
    if not service:
        raise RuntimeError(
            f"No Seldon prediction service deployed by the "
            f"{config.step_name} step in the {config.pipeline_name} pipeline "
            f"is currently running."
        )
    if not service.is_running:
        raise RuntimeError(
            f"The Seldon prediction service last deployed by the "
            f"{config.step_name} step in the {config.pipeline_name} pipeline "
            f"is not currently running."
        )

    return service


def get_data_from_api():
    url = (
        "https://storage.googleapis.com/zenml-public-bucket/mnist"
        "/mnist_handwritten_test.json"
    )

    df = pd.DataFrame(requests.get(url).json())
    data = df["image"].map(lambda x: np.array(x)).values
    data = np.array([x.reshape(28, 28) for x in data])
    return data


@step(enable_cache=False)
def dynamic_importer() -> Output(data=np.ndarray):
    """Downloads the latest data from a mock API."""
    data = get_data_from_api()
    return data


@step
def tf_predict_preprocessor(input: np.ndarray) -> Output(data=np.ndarray):
    """Prepares the data for inference."""
    input = input / 255.0
    return input


@step
def sklearn_predict_preprocessor(input: np.ndarray) -> Output(data=np.ndarray):
    """Prepares the data for inference."""
    input = input / 255.0
    return input.reshape((input.shape[0], -1))


@step
def predictor(
    service: SeldonDeploymentService,
    data: np.ndarray,
) -> Output(predictions=np.ndarray):
    """Run a inference request against a prediction service"""

    service.start(timeout=120)  # should be a NOP if already started
    prediction = service.predict(data)
    prediction = prediction.argmax(axis=-1)
    print("Prediction: ", prediction)
    return prediction


@pipeline(
    enable_cache=True, required_integrations=[SELDON, TENSORFLOW, SKLEARN]
)
def continuous_deployment_pipeline(
    importer,
    normalizer,
    trainer,
    evaluator,
    deployment_trigger,
    model_deployer,
):
    # Link all the steps artifacts together
    x_train, y_train, x_test, y_test = importer()
    x_trained_normed, x_test_normed = normalizer(x_train=x_train, x_test=x_test)
    model = trainer(x_train=x_trained_normed, y_train=y_train)
    accuracy = evaluator(x_test=x_test_normed, y_test=y_test, model=model)
    deployment_decision = deployment_trigger(accuracy=accuracy)
    model_deployer(deployment_decision, model)


@pipeline(
    enable_cache=True, required_integrations=[SELDON, TENSORFLOW, SKLEARN]
)
def inference_pipeline(
    dynamic_importer,
    predict_preprocessor,
    prediction_service_loader,
    predictor,
):
    # Link all the steps artifacts together
    batch_data = dynamic_importer()
    inference_data = predict_preprocessor(batch_data)
    model_deployment_service = prediction_service_loader()
    predictor(model_deployment_service, inference_data)
