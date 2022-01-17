#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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
from uuid import uuid4

import pytest

from zenml.config.global_config import GlobalConfig
from zenml.io import fileio


def test_global_config_file_creation():
    """Tests whether a config file gets created when instantiating a global
    config object."""
    if fileio.file_exists(GlobalConfig.config_file()):
        fileio.remove(GlobalConfig.config_file())

    GlobalConfig()

    assert fileio.file_exists(GlobalConfig.config_file())


def test_global_config_user_id_is_immutable():
    """Tests that the global config user id attribute is immutable."""
    with pytest.raises(TypeError):
        GlobalConfig().user_id = uuid4()
