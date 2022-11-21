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
from zenml.integrations.label_studio.label_config_generators import (
    generate_image_classification_label_config,
)
from zenml.integrations.label_studio.steps import (
    LabelStudioDatasetRegistrationParameters,
    get_or_create_dataset,
)

LABELS = ["aria", "not_aria"]

label_config, _ = generate_image_classification_label_config(LABELS)

label_studio_registration_params = LabelStudioDatasetRegistrationParameters(
    label_config=label_config,
    dataset_name="aria_detector",
)

get_or_create_the_dataset = get_or_create_dataset(
    label_studio_registration_params
)
