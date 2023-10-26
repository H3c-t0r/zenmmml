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
"""Endpoint definitions for stack components."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Security

from zenml.constants import API, COMPONENT_TYPES, STACK_COMPONENTS, VERSION_1
from zenml.enums import StackComponentType
from zenml.models import (
    ComponentFilterModel,
    ComponentResponseModel,
    ComponentUpdateModel,
)
from zenml.models.page_model import Page
from zenml.zen_server.auth import AuthContext, authorize
from zenml.zen_server.exceptions import error_response
from zenml.zen_server.rbac.endpoint_utils import (
    verify_permissions_and_delete_entity,
    verify_permissions_and_get_entity,
    verify_permissions_and_list_entities,
    verify_permissions_and_update_entity,
)
from zenml.zen_server.rbac.models import Action, ResourceType
from zenml.zen_server.rbac.utils import verify_permission_for_model
from zenml.zen_server.utils import (
    handle_exceptions,
    make_dependable,
    zen_store,
)

router = APIRouter(
    prefix=API + VERSION_1 + STACK_COMPONENTS,
    tags=["stack_components"],
    responses={401: error_response, 403: error_response},
)

types_router = APIRouter(
    prefix=API + VERSION_1 + COMPONENT_TYPES,
    tags=["stack_components"],
    responses={401: error_response, 403: error_response},
)


@router.get(
    "",
    response_model=Page[ComponentResponseModel],
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def list_stack_components(
    component_filter_model: ComponentFilterModel = Depends(
        make_dependable(ComponentFilterModel)
    ),
    _: AuthContext = Security(authorize),
) -> Page[ComponentResponseModel]:
    """Get a list of all stack components for a specific type.

    Args:
        component_filter_model: Filter model used for pagination, sorting,
                                filtering

    Returns:
        List of stack components for a specific type.
    """
    return verify_permissions_and_list_entities(
        filter_model=component_filter_model,
        resource_type=ResourceType.STACK_COMPONENT,
        list_method=zen_store().list_stack_components,
    )


@router.get(
    "/{component_id}",
    response_model=ComponentResponseModel,
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def get_stack_component(
    component_id: UUID,
    _: AuthContext = Security(authorize),
) -> ComponentResponseModel:
    """Returns the requested stack component.

    Args:
        component_id: ID of the stack component.

    Returns:
        The requested stack component.
    """
    return verify_permissions_and_get_entity(
        id=component_id, get_method=zen_store().get_stack_component
    )


@router.put(
    "/{component_id}",
    response_model=ComponentResponseModel,
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def update_stack_component(
    component_id: UUID,
    component_update: ComponentUpdateModel,
    _: AuthContext = Security(authorize),
) -> ComponentResponseModel:
    """Updates a stack component.

    Args:
        component_id: ID of the stack component.
        component_update: Stack component to use to update.

    Returns:
        Updated stack component.
    """
    if component_update.connector:
        service_connector = zen_store().get_service_connector(
            component_update.connector
        )
        verify_permission_for_model(service_connector, action=Action.READ)

    return verify_permissions_and_update_entity(
        id=component_id,
        update_model=component_update,
        get_method=zen_store().get_stack_component,
        update_method=zen_store().update_stack_component,
    )


@router.delete(
    "/{component_id}",
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def deregister_stack_component(
    component_id: UUID,
    _: AuthContext = Security(authorize),
) -> None:
    """Deletes a stack component.

    Args:
        component_id: ID of the stack component.
    """
    verify_permissions_and_delete_entity(
        id=component_id,
        get_method=zen_store().get_stack_component,
        delete_method=zen_store().delete_stack_component,
    )


@types_router.get(
    "",
    response_model=List[str],
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def get_stack_component_types(
    _: AuthContext = Security(authorize),
) -> List[str]:
    """Get a list of all stack component types.

    Returns:
        List of stack components.
    """
    return StackComponentType.values()
