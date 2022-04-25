#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
import tempfile

import numpy as np
import requests
import xgboost as xgb

from zenml.integrations.constants import XGBOOST
from zenml.logger import get_logger
from zenml.pipelines import pipeline
from zenml.steps import BaseStepConfig, Output, step

logger = get_logger(__name__)

TRAIN_SET_RAW = "https://raw.githubusercontent.com/dmlc/xgboost/master/demo/data/agaricus.txt.train"
TEST_SET_RAW = "https://raw.githubusercontent.com/dmlc/xgboost/master/demo/data/agaricus.txt.test"


class XGBoostConfig(BaseStepConfig):
    max_depth: int = 1
    eta: int = 1
    objective: str = "binary:logistic"
    num_round: int = 2


@step
def data_loader() -> Output(df_train=xgb.DMatrix, df_test=xgb.DMatrix):
    """Return the renewable energy dataset as pandas dataframes."""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".html", encoding="utf-8"
    ) as f:
        f.write(requests.get(TRAIN_SET_RAW).text)
        df_train = xgb.DMatrix(f.name)

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".html", encoding="utf-8"
    ) as f:
        f.write(requests.get(TEST_SET_RAW).text)
        df_test = xgb.DMatrix(f.name)

    return df_train, df_test


@step
def trainer(
    config: XGBoostConfig, df_train: xgb.DMatrix, df_test: xgb.DMatrix
) -> xgb.Booster:
    """Trains a XGBoost model on the data."""
    num_round = 2
    params = {
        "max_depth": config.max_depth,
        "eta": config.eta,
        "objective": config.objective,
    }
    return xgb.train(params, df_train, num_round)


@step
def predictor(model: xgb.Booster, df: xgb.DMatrix) -> np.ndarray:
    """Makes predictions on a trained XGBoost booster model."""
    return model.predict(df)


@pipeline(enable_cache=False, required_integrations=[XGBOOST])
def xgboost_pipeline(
    data_loader,
    trainer,
    predictor,
):
    """Links all the steps together in a pipeline"""
    df_train, df_test = data_loader()
    m = trainer(df_train, df_test)
    predictor(m, df_train)


if __name__ == "__main__":

    pipeline = xgboost_pipeline(
        data_loader=data_loader(), trainer=trainer(), predictor=predictor()
    )

    pipeline.run()

    print(
        "Pipeline has run and model is trained. Please run the "
        "`post_execution.ipynb` notebook to inspect the results."
    )
