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
"""Endpoint definitions for triggers."""

from uuid import UUID

from fastapi import APIRouter, Depends, Security

from zenml.constants import API, TRIGGERS, VERSION_1
from zenml.models import Page, TriggerFilter, TriggerResponse, TriggerUpdate
from zenml.zen_server.auth import AuthContext, authorize
from zenml.zen_server.exceptions import error_response
from zenml.zen_server.rbac.endpoint_utils import (
    verify_permissions_and_delete_entity,
    verify_permissions_and_get_entity,
    verify_permissions_and_list_entities,
    verify_permissions_and_update_entity,
)
from zenml.zen_server.rbac.models import ResourceType
from zenml.zen_server.utils import (
    handle_exceptions,
    make_dependable,
    zen_store,
)

router = APIRouter(
    prefix=API + VERSION_1 + TRIGGERS,
    tags=["triggers"],
    responses={401: error_response, 403: error_response},
)


@router.get(
    "",
    response_model=Page[TriggerResponse],
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def list_triggers(
    trigger_filter_model: TriggerFilter = Depends(make_dependable(TriggerFilter)),
    hydrate: bool = False,
    _: AuthContext = Security(authorize),
) -> Page[TriggerResponse]:
    """Returns all triggers.

    Args:
        trigger_filter_model: Filter model used for pagination, sorting,
            filtering.
        hydrate: Flag deciding whether to hydrate the output model(s)
            by including metadata fields in the response.

    Returns:
        All triggers.
    """
    return verify_permissions_and_list_entities(
        filter_model=trigger_filter_model,
        resource_type=ResourceType.TRIGGER,
        list_method=zen_store().list_triggers,
        hydrate=hydrate,
    )


@router.get(
    "/{trigger_id}",
    response_model=TriggerResponse,
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def get_trigger(
    trigger_id: UUID,
    hydrate: bool = True,
    _: AuthContext = Security(authorize),
) -> TriggerResponse:
    """Returns the requested trigger.

    Args:
        trigger_id: ID of the trigger.
        hydrate: Flag deciding whether to hydrate the output model(s)
            by including metadata fields in the response.

    Returns:
        The requested trigger.
    """
    return verify_permissions_and_get_entity(
        id=trigger_id, get_method=zen_store().get_trigger, hydrate=hydrate
    )


@router.put(
    "/{trigger_id}",
    response_model=TriggerResponse,
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def update_trigger(
    trigger_id: UUID,
    trigger_update: TriggerUpdate,
    _: AuthContext = Security(authorize),
) -> TriggerResponse:
    """Updates a trigger.

    Args:
        trigger_id: Name of the trigger.
        trigger_update: Trigger to use for the update.

    Returns:
        The updated trigger.
    """
    # TODO: Look into updating event/action
    return verify_permissions_and_update_entity(
        id=trigger_id,
        update_model=trigger_update,
        get_method=zen_store().get_trigger,
        update_method=zen_store().update_trigger,
    )


@router.delete(
    "/{trigger_id}",
    responses={401: error_response, 404: error_response, 422: error_response},
)
@handle_exceptions
def delete_trigger(
    trigger_id: UUID,
    _: AuthContext = Security(authorize),
) -> None:
    """Deletes a trigger.

    Args:
        trigger_id: Name of the trigger.
    """
    verify_permissions_and_delete_entity(
        id=trigger_id,
        get_method=zen_store().get_trigger,
        delete_method=zen_store().delete_trigger,
    )
