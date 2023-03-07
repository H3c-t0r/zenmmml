#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.
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

import random

from zenml.hooks import alerter_failure_hook, alerter_success_hook
from zenml.pipelines import pipeline
from zenml.steps import BaseParameters, Output, StepContext, step


def pipeline_success_hook(context: StepContext) -> None:
    print(f"Step {context.step_name} succeeded!")


class HookParams(BaseParameters):
    """Parameters to define which hook to trigger"""

    fail: bool = True


@step(on_failure=alerter_failure_hook, on_success=alerter_success_hook)
def get_first_num(params: HookParams) -> int:
    """Returns an integer."""
    if params.fail:
        raise ValueError("This is an exception")

    return 10


@step(enable_cache=False)
def get_random_int() -> Output(random_num=int):
    """Get a random integer between 0 and 10"""
    return random.randint(0, 10)


@step
def subtract_numbers(first_num: int, random_num: int) -> Output(result=int):
    """Subtract random_num from first_num."""
    return first_num - random_num


@pipeline(enable_cache=False, on_success=pipeline_success_hook)
def hook_pipeline(get_first_num, get_random_int, subtract_numbers):
    # Link all the steps artifacts together
    first_num = get_first_num()
    random_num = get_random_int()
    subtract_numbers(first_num, random_num)


if __name__ == "__main__":
    # Initialize a new pipeline run

    p1 = hook_pipeline(
        get_first_num=get_first_num(params=HookParams(fail=False)),
        get_random_int=get_random_int(),
        subtract_numbers=subtract_numbers(),
    )
    p1.run()

    p2 = hook_pipeline(
        get_first_num=get_first_num(params=HookParams(fail=True)),
        get_random_int=get_random_int(),
        subtract_numbers=subtract_numbers(),
    )
    p2.run()
