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

from abc import ABC, abstractmethod
from typing import ClassVar, List, Optional, Union

from feast.feature_service import FeatureService  # type: ignore[import]
from pandas import DataFrame

from zenml.enums import StackComponentType
from zenml.stack import StackComponent


class BaseFeatureStore(StackComponent, ABC):
    """Base class for all ZenML feature stores."""

    TYPE: ClassVar[StackComponentType] = StackComponentType.FEATURE_STORE
    FLAVOR: ClassVar[str]

    @abstractmethod
    def get_historical_features(
        self,
        entity_df: Union[DataFrame, str],
        features: Union[List[str], FeatureService],
        full_feature_names: bool = False,
    ) -> Optional[DataFrame]:
        """Returns the historical features for training or batch scoring."""
        return NotImplementedError

    @abstractmethod
    def get_online_features(self) -> Optional[DataFrame]:
        """Returns the latest online feature data."""
        return NotImplementedError
