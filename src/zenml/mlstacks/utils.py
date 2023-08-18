#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.

#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:

#       https://www.apache.org/licenses/LICENSE-2.0

#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Functionality to handle interaction with the mlstacks package."""

import json
import uuid
from functools import wraps
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import click
import pkg_resources

from zenml.cli.utils import (
    error,
    print_model_url,
    verify_mlstacks_prerequisites_installation,
)
from zenml.client import Client
from zenml.constants import (
    MLSTACKS_SUPPORTED_STACK_COMPONENTS,
    STACK_RECIPE_PACKAGE_NAME,
)
from zenml.enums import StackComponentType
from zenml.utils.dashboard_utils import get_component_url, get_stack_url
from zenml.utils.yaml_utils import read_yaml

if TYPE_CHECKING:
    from mlstacks.models import Component, Stack


def verify_installation(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for verifying mlstacks installation before running a function.

    Args:
        func: The function to be decorated.

    Returns:
        The decorated function, which will run verify_mlstacks_installation()
        before executing the original function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        verify_mlstacks_prerequisites_installation()
        return func(*args, **kwargs)

    return wrapper


def stack_exists(stack_name: str) -> bool:
    """Checks whether a stack with that name exists or not.

    Args:
        stack_name: The name of the stack to check for.

    Returns:
        A boolean indicating whether the stack exists or not.
    """
    try:
        Client().get_stack(
            name_id_or_prefix=stack_name, allow_name_prefix_match=False
        )
    except KeyError:
        return False
    return True


@verify_installation
def stack_spec_exists(stack_name: str) -> bool:
    """Checks whether a stack spec with that name exists or not.

    Args:
        stack_name: The name of the stack spec to check for.

    Returns:
        A boolean indicating whether the stack spec exists or not.
    """
    from mlstacks.constants import MLSTACKS_PACKAGE_NAME

    spec_dir = (
        f"{click.get_app_dir(MLSTACKS_PACKAGE_NAME)}/stack_specs/{stack_name}"
    )
    return Path(spec_dir).exists()


def get_mlstacks_version() -> Optional[str]:
    """Gets the version of mlstacks locally installed.

    Raises:
        pkg_resources.DistributionNotFound: If mlstacks is not installed.
    """
    try:
        return pkg_resources.get_distribution(
            STACK_RECIPE_PACKAGE_NAME
        ).version
    except pkg_resources.DistributionNotFound:
        return None


def _get_component_flavor(
    key: str, value: Union[bool, str], provider: str
) -> str:
    """Constructs the component flavor from Click CLI params.

    Args:
        key: The component key.
        value: The component value.
        provider: The provider name.

    Returns:
        The component flavor.
    """
    if key in {"artifact_store", "container_registry"} and bool(value):
        if provider == "aws":
            flavor = "s3"
        elif provider == "azure":
            flavor = "azure"
        elif provider == "gcp":
            flavor = "gcp"
    elif (
        key
        in {
            "experiment_tracker",
            "orchestrator",
            "model_deployer",
            "model_registry",
            "mlops_platform",
            "step_operator",
        }
        and value
        and type(value) == str
    ):
        flavor = value
    return flavor


@verify_installation
def _add_extra_config_to_components(
    components: List["Component"], extra_config: Dict[str, str]
) -> List["Component"]:
    """Adds extra config to mlstacks `Component` objects.

    Args:
        components: A list of mlstacks `Component` objects.
        extra_config: A dictionary of extra config.

    Returns:
        A list of mlstacks `Component` objects.
    """
    from mlstacks.models.component import ComponentMetadata

    # Define configuration map
    config_map = {
        ("container_registry",): ["repo_name"],
        ("artifact_store",): ["bucket_name"],
        ("experiment_tracker", "mlflow"): [
            "mlflow-artifact-S3-access-key",
            "mlflow-artifact-S3-secret-key",
            "mlflow-username",
            "mlflow-password",
            "mlflow_bucket",
        ],
        ("mlops_platform", "zenml"): [
            "zenml-version",
            "zenml-username",
            "zenml-password",
            "zenml-database-url",
        ],
        ("artifact_store", "minio", "k3d"): [
            "zenml-minio-store-access-key",
            "zenml-minio-store-secret-key",
        ],
        ("experiment_tracker", "mlflow", "k3d"): [
            "mlflow_minio_bucket",
            "mlflow-username",
            "mlflow-password",
        ],
        ("model_deployer", "seldon", "k3d"): ["seldon-secret-name"],
        ("model_deployer", "kserve", "k3d"): ["kserve-secret-name"],
    }

    def _add_config(
        component_metadata: ComponentMetadata, keys: List[str]
    ) -> None:
        """Adds key-value pair to the component_metadata config if it exists in extra_config.

        Args:
            component_metadata: The metadata of the component.
            keys: The keys of the configurations.
        """
        for key in keys:
            value = extra_config.get(key)
            if value is not None:
                component_metadata.config[key] = value

    # Define a list of component attributes that need checking
    component_attributes = ["component_type", "component_flavor", "provider"]

    for component in components:
        component_metadata = ComponentMetadata()
        component_metadata.config = {}

        # Create a dictionary that maps attribute names to their values
        component_values = {
            attr: getattr(component, attr, None)
            for attr in component_attributes
        }

        for config_keys, extra_keys in config_map.items():
            # If all attributes in config_keys match their values in the component
            if all(
                component_values.get(key) == value
                for key, value in zip(component_attributes, config_keys)
            ):
                _add_config(component_metadata, extra_keys)

        # always add project_id to gcp components
        if component.provider == "gcp":
            project_id = extra_config.get("project_id")
            if project_id:
                component_metadata.config["project_id"] = extra_config.get(
                    "project_id"
                )
            else:
                raise KeyError(
                    "No `project_id` is included. Please try again with "
                    "`--extra-config project_id=<project_id>`"
                )

        component.metadata = component_metadata

    return components


@verify_installation
def _construct_components(
    params: Dict[str, Any], zenml_component_deploy: bool = False
) -> List["Component"]:
    """Constructs mlstacks `Component` objects from raw Click CLI params.

    Args:
        params: Raw Click CLI params.
        zenml_component_deploy: A boolean indicating whether the stack
            contains a single component and is being deployed through `zenml
            component deploy`

    Returns:
        A list of mlstacks `Component` objects.
    """
    from mlstacks.models import Component

    provider = params["provider"]
    extra_config = (
        dict(config.split("=") for config in params["extra_config"])
        if params["extra_config"]
        else {}
    )
    if zenml_component_deploy:
        components = [
            Component(
                name=params[key],
                component_type=key,
                component_flavor=_get_component_flavor(key, value, provider),
                provider=params["provider"],
            )
            for key, value in params.items()
            if (value) and (key in MLSTACKS_SUPPORTED_STACK_COMPONENTS)
        ]
    else:
        components = [
            Component(
                name=f"{provider}-{key}",
                component_type=key,
                component_flavor=_get_component_flavor(key, value, provider),
                provider=params["provider"],
            )
            for key, value in params.items()
            if (value) and (key in MLSTACKS_SUPPORTED_STACK_COMPONENTS)
        ]

    components = _add_extra_config_to_components(components, extra_config)
    return components


def _get_stack_tags(tags: Dict[str, str]) -> Dict[str, str]:
    """Gets and parses tags from Click params.

    Args:
        tags: Raw Click CLI params.

    Returns:
        A dictionary of tags.
    """
    return dict(tag.split("=") for tag in tags) if tags else {}


@verify_installation
def _construct_stack(params: Dict[str, Any]) -> "Stack":
    """Constructs mlstacks `Stack` object from raw Click CLI params.

    Args:
        params: Raw Click CLI params.

    Returns:
        A mlstacks `Stack` object.
    """
    from mlstacks.models import Stack

    tags = _get_stack_tags(params["tags"])

    return Stack(
        spec_version=1,
        spec_type="stack",
        name=params["stack_name"],
        provider=params["provider"],
        default_region=params["region"],
        default_tags=tags,
        components=[],
    )


@verify_installation
def convert_click_params_to_mlstacks_primitives(
    params: Dict[str, Any],
    zenml_component_deploy: bool = False,
) -> Tuple["Stack", List["Component"]]:
    """Converts raw Click CLI params to mlstacks primitives.

    Args:
        params: Raw Click CLI params.
        zenml_component_deploy: A boolean indicating whether the stack
            contains a single component and is being deployed through `zenml
            component deploy`

    Returns:
        A tuple of Stack and List[Component] objects.
    """
    from mlstacks.constants import MLSTACKS_PACKAGE_NAME
    from mlstacks.models import Component, Stack

    stack: Stack = _construct_stack(params)
    components: List[Component] = _construct_components(
        params, zenml_component_deploy
    )

    # writes the file names to the stack spec
    # using format '<provider>-<component_name>.yaml'
    for component in components:
        stack.components.append(
            f"{click.get_app_dir(MLSTACKS_PACKAGE_NAME)}/stack_specs/{stack.name}/{component.name}.yaml"
        )

    return stack, components


@verify_installation
def convert_mlstacks_primitives_to_dicts(
    stack: "Stack", components: List["Component"]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Converts mlstacks Stack and Components to dicts.

    Args:
        stack: A mlstacks Stack object.
        components: A list of mlstacks Component objects.

    Returns:
        A tuple of Stack and List[Component] dicts.
    """
    verify_mlstacks_prerequisites_installation()

    # convert to json first to strip out Enums objects
    stack_dict = json.loads(stack.json())
    components_dicts = [
        json.loads(component.json()) for component in components
    ]

    return stack_dict, components_dicts


def generate_unique_filename(base_filename: str) -> str:
    """Generates a unique filename by appending a UUID to the base filename.

    Args:
        base_filename: The base filename.

    Returns:
        The unique filename.
    """
    unique_suffix = (
        uuid.uuid4().hex
    )  # Generate a random UUID and convert it to a string.
    return f"{base_filename}_{unique_suffix}"


@verify_installation
def import_new_mlstacks_stack(
    stack_name: str, provider: str, stack_spec_dir: str
) -> None:
    """Import a new stack deployed for a particular cloud provider.

    Args:
        stack_name: The name of the stack to import.
        provider: The cloud provider for which the stack is deployed.
        stack_spec_dir: The path to the directory containing the stack spec.
    """
    from mlstacks.constants import MLSTACKS_PACKAGE_NAME
    from mlstacks.utils import terraform_utils

    tf_dir = f"{click.get_app_dir(MLSTACKS_PACKAGE_NAME)}/terraform/{provider}-modular"
    stack_spec_file = f"{stack_spec_dir}/stack-{stack_name}.yaml"
    # strip out the `./` from the stack_file_path
    stack_filename = terraform_utils.get_stack_outputs(
        stack_spec_file, output_key="stack-yaml-path"
    ).get("stack-yaml-path")[2:]
    import_stack_path = f"{tf_dir}/{stack_filename}"
    data = read_yaml(import_stack_path)
    # import stack components
    component_ids = {}
    for component_type_str, component_config in data["components"].items():
        component_type = StackComponentType(component_type_str)
        component_spec_path = f"{stack_spec_dir}/{component_config['flavor']}-{component_type_str}.yaml"

        from zenml.cli.stack import _import_stack_component

        component_id = _import_stack_component(
            component_type=component_type,
            component_dict=component_config,
            component_spec_path=component_spec_path,
        )
        component_ids[component_type] = component_id

    imported_stack = Client().create_stack(
        name=stack_name,
        components=component_ids,
        is_shared=False,
        stack_spec_file=stack_spec_file,
    )

    print_model_url(get_stack_url(imported_stack))


@verify_installation
def import_new_mlstacks_component(
    stack_name: str, component_name: str, provider: str, stack_spec_dir: str
) -> None:
    """Import a new component deployed for a particular cloud provider.

    Args:
        stack_name: The name of the stack to import.
        component_name: The name of the component to import.
        provider: The cloud provider for which the stack is deployed.
        stack_spec_dir: The path to the directory containing the stack spec.
    """
    from mlstacks.constants import MLSTACKS_PACKAGE_NAME
    from mlstacks.utils import terraform_utils

    tf_dir = f"{click.get_app_dir(MLSTACKS_PACKAGE_NAME)}/terraform/{provider}-modular"
    stack_spec_file = f"{stack_spec_dir}/stack-{stack_name}.yaml"
    # strip out the `./` from the stack_file_path
    stack_filename = terraform_utils.get_stack_outputs(
        stack_spec_file, output_key="stack-yaml-path"
    ).get("stack-yaml-path")[2:]
    import_stack_path = f"{tf_dir}/{stack_filename}"
    data = read_yaml(import_stack_path)
    # import stack components
    component_ids = {}
    for component_type_str, component_config in data["components"].items():
        component_type = StackComponentType(component_type_str)
        component_spec_path = f"{stack_spec_dir}/{component_name}.yaml"
        # TODO: find a nicer way to do this (most likely fix the TF
        # recipe stack yaml output)
        component_config["name"] = component_name

        from zenml.cli.stack import _import_stack_component

        component_id = _import_stack_component(
            component_type=component_type,
            component_dict=component_config,
            component_spec_path=component_spec_path,
        )
        component_ids[component_type] = component_id
        component = Client().get_stack_component(component_type, component_id)

    print_model_url(get_component_url(component))


def verify_spec_and_tf_files_exist(
    spec_file_path: str, tf_file_path: str
) -> None:
    """Checks whether both the spec and tf files exist.

    Args:
        spec_file_path: The path to the spec file.
        tf_file_path: The path to the tf file.
    """
    if not Path(spec_file_path).exists():
        error(f"Could not find the Stack spec file at {spec_file_path}.")
    elif not Path(tf_file_path).exists():
        error(
            f"Could not find the Terraform files for the stack "
            f"at {tf_file_path}."
        )
