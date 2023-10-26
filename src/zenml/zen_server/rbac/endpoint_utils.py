"""High-level helper functions to write endpoints with RBAC."""
from typing import Callable, TypeVar
from uuid import UUID

from pydantic import BaseModel

from zenml.exceptions import IllegalOperationError
from zenml.models.base_models import (
    BaseRequestModel,
    BaseResponseModel,
    UserScopedRequestModel,
)
from zenml.models.filter_models import BaseFilterModel
from zenml.models.page_model import Page
from zenml.zen_server.auth import get_auth_context
from zenml.zen_server.rbac.models import Action, ResourceType
from zenml.zen_server.rbac.utils import (
    dehydrate_page,
    dehydrate_response_model,
    get_allowed_resource_ids,
    verify_permission,
    verify_permission_for_model,
)

AnyRequestModel = TypeVar("AnyRequestModel", bound=BaseRequestModel)
AnyResponseModel = TypeVar("AnyResponseModel", bound=BaseResponseModel)
AnyFilterModel = TypeVar("AnyFilterModel", bound=BaseFilterModel)
AnyUpdateModel = TypeVar("AnyUpdateModel", bound=BaseModel)


def verify_permissions_and_create_entity(
    request_model: AnyRequestModel,
    resource_type: ResourceType,
    create_method: Callable[[AnyRequestModel], AnyResponseModel],
) -> AnyResponseModel:
    """Verify permissions and create the entity if authorized.

    Args:
        request_model: The entity request model.
        resource_type: The resource type of the entity to create.
        create_method: The method to create the entity.

    Raises:
        IllegalOperationError: If the request model has a different owner then
            the currently authenticated user.

    Returns:
        A model of the created entity.
    """
    if isinstance(request_model, UserScopedRequestModel):
        auth_context = get_auth_context()
        assert auth_context

        if request_model.user != auth_context.user.id:
            raise IllegalOperationError(
                f"Not allowed to create resource '{resource_type}' for a "
                "different user."
            )

    verify_permission(resource_type=resource_type, action=Action.CREATE)
    return create_method(request_model)


def verify_permissions_and_get_entity(
    id: UUID, get_method: Callable[[UUID], AnyResponseModel]
) -> AnyResponseModel:
    """Verify permissions and fetch an entity.

    Args:
        id: The ID of the entity to fetch.
        get_method: The method to fetch the entity.

    Returns:
        A model of the fetched entity.
    """
    model = get_method(id)
    verify_permission_for_model(model, action=Action.READ)
    return dehydrate_response_model(model)


def verify_permissions_and_list_entities(
    filter_model: AnyFilterModel,
    resource_type: ResourceType,
    list_method: Callable[[AnyFilterModel], Page[AnyResponseModel]],
) -> Page[AnyResponseModel]:
    """Verify permissions and list entities.

    Args:
        filter_model: The entity filter model.
        resource_type: The resource type of the entities to list.
        list_method: The method to list the entities.

    Returns:
        A page of entity models.
    """
    allowed_ids = get_allowed_resource_ids(resource_type=resource_type)
    filter_model.set_allowed_ids(allowed_ids)
    page = list_method(filter_model)
    return dehydrate_page(page)


def verify_permissions_and_update_entity(
    id: UUID,
    update_model: AnyUpdateModel,
    get_method: Callable[[UUID], AnyResponseModel],
    update_method: Callable[[UUID, AnyUpdateModel], AnyResponseModel],
) -> AnyResponseModel:
    """Verify permissions and update an entity.

    Args:
        id: The ID of the entity to update.
        update_model: The entity update model.
        get_method: The method to fetch the entity.
        update_method: The method to update the entity.

    Returns:
        A model of the updated entity.
    """
    model = get_method(id)
    verify_permission_for_model(model, action=Action.UPDATE)
    updated_model = update_method(id, update_model)
    return dehydrate_response_model(updated_model)


def verify_permissions_and_delete_entity(
    id: UUID,
    get_method: Callable[[UUID], AnyResponseModel],
    delete_method: Callable[[UUID], None],
) -> None:
    """Verify permissions and delete an entity.

    Args:
        id: The ID of the entity to delete.
        get_method: The method to fetch the entity.
        delete_method: The method to delete the entity.
    """
    model = get_method(id)
    verify_permission_for_model(model, action=Action.DELETE)
    delete_method(id)
