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
"""RBAC utility functions."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type, TypeVar
from uuid import UUID

from fastapi import HTTPException

from zenml.models.base_models import BaseResponseModel, UserScopedResponseModel
from zenml.models.page_model import Page
from zenml.zen_server.auth import get_auth_context
from zenml.zen_server.rbac.models import Action, Resource, ResourceType
from zenml.zen_server.utils import rbac, server_config

M = TypeVar("M", bound=BaseResponseModel)


def verify_read_permissions_and_dehydrate(
    model: M,
) -> M:
    """Verify read permissions of the model and dehydrate it if necessary.

    Args:
        model: The model for which to verify permissions.

    Returns:
        The (potentially) dehydrated model.
    """
    if not server_config().rbac_enabled:
        return model

    verify_permissions_for_model(model=model, action=Action.READ)

    return dehydrate_response_model(model=model)


def dehydrate_page(page: Page[M]) -> Page[M]:
    """Dehydrate all items of a page.

    Args:
        page: The page to dehydrate.

    Returns:
        The page with (potentially) dehydrated items.
    """
    auth_context = get_auth_context()
    assert auth_context

    resource_list = [get_subresources_for_model(item) for item in page.items]
    resources = set.union(*resource_list) if resource_list else set()
    permissions = rbac().check_permissions(
        user=auth_context.user, resources=resources, action=Action.READ
    )

    new_items = [
        dehydrate_response_model(item, permissions=permissions)
        for item in page.items
    ]

    return page.copy(update={"items": new_items})


def dehydrate_response_model(
    model: M, permissions: Optional[Dict[Resource, bool]] = None
) -> M:
    """Dehydrate a model if necessary.

    Args:
        model: The model to dehydrate.
        permissions: Prefetched permissions that will be used to check whether
            sub-models will be included in the model or not. If a sub-model
            refers to a resource which is not included in this dictionary, the
            permissions will be checked with the RBAC component.

    Returns:
        The (potentially) dehydrated model.
    """
    dehydrated_fields = {}

    for field_name in model.__fields__.keys():
        value = getattr(model, field_name)
        dehydrated_fields[field_name] = _dehydrate_value(
            value, permissions=permissions
        )

    return type(model).parse_obj(dehydrated_fields)


def _dehydrate_value(
    value: Any, permissions: Optional[Dict[Resource, bool]] = None
) -> Any:
    """Helper function to recursive dehydrate any object.

    Args:
        value: The value to dehydrate.
        permissions: Prefetched permissions that will be used to check whether
            sub-models will be included in the model or not. If a sub-model
            refers to a resource which is not included in this dictionary, the
            permissions will be checked with the RBAC component.

    Returns:
        The recursively dehydrated value.
    """
    if isinstance(value, BaseResponseModel):
        resource = get_resource_for_model(value)
        has_permissions = resource and (permissions or {}).get(resource, False)

        if has_permissions or has_permissions_for_model(
            model=value, action=Action.READ
        ):
            return dehydrate_response_model(value, permissions=permissions)
        else:
            return get_permission_denied_model(value)
    elif isinstance(value, Dict):
        return {
            k: _dehydrate_value(v, permissions=permissions)
            for k, v in value.items()
        }
    elif isinstance(value, (List, Set, tuple)):
        type_ = type(value)
        return type_(
            _dehydrate_value(v, permissions=permissions) for v in value
        )
    else:
        return value


def has_permissions_for_model(model: "BaseResponseModel", action: str) -> bool:
    """If the active user has permissions to perform the action on the model.

    Args:
        model: The model the user wants to perform the action on.
        action: The action the user wants to perform.

    Returns:
        If the active user has permissions to perform the action on the model.
    """
    try:
        verify_permissions_for_model(model=model, action=action)
        return True
    except HTTPException:
        return False


def get_permission_denied_model(
    model: M, keep_id: bool = True, keep_name: bool = True
) -> M:
    """Get a model to return in case of missing read permissions.

    This function replaces all attributes except name and ID in the given model.

    Args:
        model: The original model.
        keep_id: If `True`, the model ID will not be replaced.
        keep_name: If `True`, the model name will not be replaced.

    Returns:
        The model with attribute values replaced by default values.
    """
    values = {}

    for field_name, field in model.__fields__.items():
        value = getattr(model, field_name)

        if keep_id and field_name == "id" and isinstance(value, UUID):
            pass
        elif keep_name and field_name == "name" and isinstance(value, str):
            pass
        elif field.allow_none:
            value = None
        elif isinstance(value, BaseResponseModel):
            value = get_permission_denied_model(
                value, keep_id=False, keep_name=False
            )
        elif isinstance(value, UUID):
            value = UUID(int=0)
        elif isinstance(value, datetime):
            value = datetime.utcnow()
        elif isinstance(value, Enum):
            # TODO: handle enums in a more sensible way
            value = list(type(value))[0]
        else:
            type_ = type(value)
            # For the remaining cases (dict, list, set, tuple, int, float, str),
            # simply return an empty value
            value = type_()

        values[field_name] = value

    values["missing_permissions"] = True

    return type(model).parse_obj(values)


def verify_permissions_for_model(
    model: "BaseResponseModel",
    action: str,
) -> None:
    """Verifies if a user has permissions to perform an action on a model.

    Args:
        model: The model the user wants to perform the action on.
        action: The action the user wants to perform.
    """
    if not server_config().rbac_enabled:
        return

    if is_owned_by_authenticated_user(model):
        # The model owner always has permissions
        return

    resource_type = get_resource_type_for_model(model)
    if not resource_type:
        # This model is not tied to any RBAC resource type and therefore doesn't
        # require any special permissions
        return

    verify_permissions(
        resource_type=resource_type, resource_id=model.id, action=action
    )


def verify_permissions(
    resource_type: str,
    action: str,
    resource_id: Optional[UUID] = None,
) -> None:
    """Verifies if a user has permissions to perform an action on a resource.

    Args:
        resource_type: The type of resource that the user wants to perform the
            action on.
        action: The action the user wants to perform.
        resource_id: ID of the resource the user wants to perform the action on.

    Raises:
        HTTPException: If the user is not allowed to perform the action.
        RuntimeError: If the permission verification failed unexpectedly.
    """
    if not server_config().rbac_enabled:
        return

    auth_context = get_auth_context()
    assert auth_context

    resource = Resource(type=resource_type, id=resource_id)
    permissions = rbac().check_permissions(
        user=auth_context.user, resources={resource}, action=action
    )

    if resource not in permissions:
        # This should never happen if the RBAC implementation is working
        # correctly
        raise RuntimeError(
            f"Failed to verify permissions to {action.upper()} resource "
            f"'{resource}'."
        )

    if not permissions[resource]:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions to {action.upper()} resource "
            f"'{resource}'.",
        )


def get_allowed_resource_ids(
    resource_type: str,
    action: str = Action.READ,
) -> Optional[List[UUID]]:
    """Get all resource IDs of a resource type that a user can access.

    Args:
        resource_type: The resource type.
        action: The action the user wants to perform on the resource.

    Returns:
        A list of resource IDs or `None` if the user has full access to the
        all instances of the resource.
    """
    if not server_config().rbac_enabled:
        return None

    auth_context = get_auth_context()
    assert auth_context

    (
        has_full_resource_access,
        allowed_ids,
    ) = rbac().list_allowed_resource_ids(
        user=auth_context.user,
        resource=Resource(type=resource_type),
        action=action,
    )

    if has_full_resource_access:
        return None

    return [UUID(id) for id in allowed_ids]


def get_resource_for_model(model: "BaseResponseModel") -> Optional[Resource]:
    """Get the resource associated with a model object.

    Args:
        model: The model for which to get the resource.

    Returns:
        The resource associated with the model, or `None` if the model
        is not associated with any resource type.
    """
    resource_type = get_resource_type_for_model(model)
    if not resource_type:
        # This model is not tied to any RBAC resource type
        return None

    return Resource(type=resource_type, id=model.id)


def get_resource_type_for_model(
    model: "BaseResponseModel",
) -> Optional[ResourceType]:
    """Get the resource type associated with a model object.

    Args:
        model: The model for which to get the resource type.

    Returns:
        The resource type associated with the model, or `None` if the model
        is not associated with any resource type.
    """
    from zenml.models import (
        ArtifactResponseModel,
        CodeRepositoryResponseModel,
        ComponentResponseModel,
        FlavorResponseModel,
        ModelResponseModel,
        PipelineResponseModel,
        SecretResponseModel,
        ServiceConnectorResponseModel,
        StackResponseModel,
    )

    mapping: Dict[Type[BaseResponseModel], ResourceType] = {
        FlavorResponseModel: ResourceType.FLAVOR,
        ServiceConnectorResponseModel: ResourceType.SERVICE_CONNECTOR,
        ComponentResponseModel: ResourceType.STACK_COMPONENT,
        StackResponseModel: ResourceType.STACK,
        PipelineResponseModel: ResourceType.PIPELINE,
        CodeRepositoryResponseModel: ResourceType.CODE_REPOSITORY,
        SecretResponseModel: ResourceType.SECRET,
        ModelResponseModel: ResourceType.MODEL,
        ArtifactResponseModel: ResourceType.ARTIFACT,
    }

    return mapping.get(type(model))


def is_owned_by_authenticated_user(model: "BaseResponseModel") -> bool:
    """Returns whether the currently authenticated user owns the model.

    Args:
        model: The model for which to check the ownership.

    Returns:
        Whether the currently authenticated user owns the model.
    """
    auth_context = get_auth_context()
    assert auth_context

    if (
        isinstance(model, UserScopedResponseModel)
        and model.user
        and model.user.id == auth_context.user.id
    ):
        # User is the owner of the model
        return True

    return False


def get_subresources_for_model(
    model: "BaseResponseModel",
) -> Set[Resource]:
    """Get all subresources of a model which need permission verification.

    Args:
        model: The model for which to get all the resources.

    Returns:
        All resources of a model which need permission verification.
    """
    resources = set()

    for field_name in model.__fields__.keys():
        value = getattr(model, field_name)
        resources.update(_get_subresources_for_value(value))

    return resources


def _get_subresources_for_value(value: Any) -> Set[Resource]:
    """Helper function to recursive retrieve resources of any object.

    Args:
        value: The value for which to get all the resources.

    Returns:
        All resources of the value which need permission verification.
    """
    if isinstance(value, BaseResponseModel):
        resources = set()
        if not is_owned_by_authenticated_user(value):
            if resource := get_resource_for_model(value):
                resources.add(resource)

        return resources.union(get_subresources_for_model(value))
    elif isinstance(value, Dict):
        resources_list = [
            _get_subresources_for_value(v) for v in value.values()
        ]
        return set.union(*resources_list) if resources_list else set()
    elif isinstance(value, (List, Set, tuple)):
        resources_list = [_get_subresources_for_value(v) for v in value]
        return set.union(*resources_list) if resources_list else set()
    else:
        return set()
