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

import pytest

from zenml.utils.mlstacks_utils import get_stack_spec_file_path, stack_exists


def test_stack_exists_works(local_stack):
    """Tests that stack_exists util function works.

    Args:
        local_stack: ZenML local stack fixture.
    """
    stack_name = "aria_test_stack"
    assert not stack_exists(stack_name)
    assert stack_exists(local_stack.name)


def test_get_stack_spec_file_path_fails_when_no_stack():
    """Checks util function fails if no stack found."""
    with pytest.raises(KeyError):
        get_stack_spec_file_path("blupus_stack")


def test_get_stack_spec_file_path_works():
    """Checks util function works for default stack (always present)."""
    assert get_stack_spec_file_path("default") == ""


def test_get_stack_spec_file_path_only_works_with_full_name():
    """Checks util function only works for full name matches."""
    with pytest.raises(KeyError):
        get_stack_spec_file_path("defau")  # prefix of 'default'
