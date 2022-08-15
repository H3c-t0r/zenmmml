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


from zenml.enums import StackComponentType
from zenml.integrations.deepchecks.data_validators import (
    DeepchecksDataValidator,
)

from zenml.integrations.deepchecks import (
    DEEPCHECKS_DATA_VALIDATOR_FLAVOR,
)


def test_deepchecks_data_validator_attributes():
    """Tests that the basic attributes of the Deepchecks data validator are set correctly."""
    validator = DeepchecksDataValidator(name="arias_validator")
    assert validator.TYPE == StackComponentType.DATA_VALIDATOR
    assert validator.FLAVOR == DEEPCHECKS_DATA_VALIDATOR_FLAVOR
    assert validator.name == "arias_validator"
    assert validator.NAME == "Deepchecks"
