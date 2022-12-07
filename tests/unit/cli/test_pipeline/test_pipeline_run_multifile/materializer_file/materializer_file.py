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
import os
from typing import Type

from custom_obj_file.custom_obj_file import SomeObj

from zenml.artifacts import DataArtifact
from zenml.io import fileio
from zenml.materializers.base_materializer import BaseMaterializer


class SomeMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (SomeObj,)
    ASSOCIATED_ARTIFACT_TYPES = (DataArtifact,)

    def load(self, data_type: Type[SomeObj]) -> SomeObj:
        super().load(data_type)
        with fileio.open(os.path.join(self.artifact.uri, "data.txt"), "r") as f:
            name = f.read()
        return SomeObj(name=name)

    def save(self, my_obj: SomeObj) -> None:
        super().save(my_obj)
        with fileio.open(os.path.join(self.artifact.uri, "data.txt"), "w") as f:
            f.write(my_obj.name)
