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
import os
import time
import uuid
from contextlib import ExitStack as does_not_raise
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from tests.integration.functional.utils import sample_name
from tests.integration.functional.zen_stores.utils import (
    CodeRepositoryContext,
    ComponentContext,
    CrudTestConfig,
    LoginContext,
    ModelVersionContext,
    PipelineRunContext,
    SecretContext,
    ServiceAccountContext,
    ServiceConnectorContext,
    ServiceConnectorTypeContext,
    StackContext,
    UserContext,
    list_of_entities,
)
from tests.unit.pipelines.test_build_utils import (
    StubLocalRepositoryContext,
)
from zenml.artifacts.utils import (
    _load_artifact_store,
    _load_file_from_artifact_store,
)
from zenml.client import Client
from zenml.config.pipeline_configurations import PipelineConfiguration
from zenml.config.source import Source, SourceType
from zenml.config.step_configurations import Step, StepConfiguration, StepSpec
from zenml.constants import (
    ACTIVATE,
    DEACTIVATE,
    DEFAULT_STACK_AND_COMPONENT_NAME,
    DEFAULT_USERNAME,
    DEFAULT_WORKSPACE_NAME,
    USERS,
)
from zenml.enums import (
    ArtifactType,
    ColorVariants,
    ExecutionStatus,
    MetadataResourceTypes,
    ModelStages,
    StackComponentType,
    StoreType,
    TaggableResourceTypes,
)
from zenml.exceptions import (
    AuthorizationException,
    DoesNotExistException,
    EntityExistsError,
    IllegalOperationError,
    StackExistsError,
)
from zenml.logging.step_logging import prepare_logs_uri
from zenml.metadata.metadata_types import MetadataTypeEnum
from zenml.models import (
    APIKeyFilter,
    APIKeyRequest,
    APIKeyRotateRequest,
    APIKeyUpdate,
    ArtifactVersionFilter,
    ArtifactVersionRequest,
    ArtifactVersionResponse,
    ComponentFilter,
    ComponentUpdate,
    ModelVersionArtifactFilter,
    ModelVersionArtifactRequest,
    ModelVersionFilter,
    ModelVersionPipelineRunFilter,
    ModelVersionPipelineRunRequest,
    ModelVersionRequest,
    ModelVersionUpdate,
    PipelineRunFilter,
    PipelineRunResponse,
    ServiceAccountFilter,
    ServiceAccountRequest,
    ServiceAccountUpdate,
    ServiceConnectorFilter,
    ServiceConnectorUpdate,
    StackFilter,
    StackRequest,
    StackUpdate,
    StepRunFilter,
    StepRunUpdate,
    UserRequest,
    UserResponse,
    UserUpdate,
    WorkspaceFilter,
    WorkspaceUpdate,
)
from zenml.models.tag_models import (
    TagFilterModel,
    TagRequestModel,
    TagResourceRequestModel,
    TagUpdateModel,
)
from zenml.models.v2.core.artifact import ArtifactRequest
from zenml.models.v2.core.component import ComponentRequest
from zenml.models.v2.core.pipeline_deployment import PipelineDeploymentRequest
from zenml.models.v2.core.pipeline_run import PipelineRunRequest
from zenml.models.v2.core.run_metadata import RunMetadataRequest
from zenml.models.v2.core.step_run import StepRunRequest
from zenml.utils import code_repository_utils, source_utils
from zenml.utils.enum_utils import StrEnum
from zenml.zen_stores.sql_zen_store import SqlZenStore

DEFAULT_NAME = "default"

# .--------------.
# | GENERIC CRUD |
# '--------------'


@pytest.mark.parametrize(
    "crud_test_config",
    list_of_entities,
    ids=[e.entity_name for e in list_of_entities],
)
def test_basic_crud_for_entity(crud_test_config: CrudTestConfig):
    """Tests the basic crud operations for a given entity."""
    # Test the creation
    created_entity = crud_test_config.create()

    # Test that the create method returns a hydrated model, if applicable
    if hasattr(created_entity, "metadata"):
        assert created_entity.metadata is not None

    # Test the list method
    entities_list = crud_test_config.list_method(
        crud_test_config.filter_model(id=created_entity.id)
    )
    assert entities_list.total == 1
    entity = entities_list.items[0]
    assert entity == created_entity

    # Test that the list method returns a non-hydrated model, if applicable
    if hasattr(entity, "metadata"):
        assert entity.metadata is None

        # Try to hydrate the entity
        entity.get_metadata()
        assert entity.metadata is not None

        # Test that the list method has a `hydrate` argument
        entities_list = crud_test_config.list_method(
            crud_test_config.filter_model(id=created_entity.id),
            hydrate=True,
        )
        assert entities_list.total == 1
        entity = entities_list.items[0]
        assert entity.metadata is not None

    # Test filtering by name if applicable
    if "name" in created_entity.__fields__:
        entities_list = crud_test_config.list_method(
            crud_test_config.filter_model(name=created_entity.name)
        )
        assert entities_list.total == 1
        entity = entities_list.items[0]
        assert entity == created_entity

    # Test the get method
    entity = crud_test_config.get_method(created_entity.id)
    assert entity == created_entity

    # Test that the get method returns a hydrated model, if applicable
    if hasattr(entity, "metadata"):
        assert entity.metadata is not None

        # Test that the get method has a `hydrate` argument
        unhydrated_entity = crud_test_config.get_method(
            created_entity.id, hydrate=False
        )
        assert unhydrated_entity.metadata is None

        # Try to hydrate the entity
        unhydrated_entity.get_metadata()
        assert unhydrated_entity.metadata is not None

    # Test the update method if applicable
    if crud_test_config.update_model:
        updated_entity = crud_test_config.update()
        # Ids should remain the same
        assert updated_entity.id == created_entity.id
        # Something in the Model should have changed
        assert updated_entity.json() != created_entity.json()

        # Test that the update method returns a hydrated model, if applicable
        if hasattr(updated_entity, "metadata"):
            assert updated_entity.metadata is not None

    # Test the delete method
    crud_test_config.delete()
    with pytest.raises(KeyError):
        crud_test_config.get_method(created_entity.id)
    entities_list = crud_test_config.list_method(
        crud_test_config.filter_model(id=created_entity.id)
    )
    assert entities_list.total == 0

    # Cleanup
    crud_test_config.cleanup()


@pytest.mark.parametrize(
    "crud_test_config",
    list_of_entities,
    ids=[e.entity_name for e in list_of_entities],
)
def test_create_entity_twice_fails(crud_test_config: CrudTestConfig):
    """Tests getting a non-existent entity by id."""
    entity_name = crud_test_config.entity_name
    if entity_name in {"build", "deployment"}:
        pytest.skip(f"Duplicates of {entity_name} are allowed.")

    # First creation is successful
    crud_test_config.create()

    # Second one fails
    with pytest.raises(EntityExistsError):
        crud_test_config.create()

    # Cleanup
    crud_test_config.cleanup()


@pytest.mark.parametrize(
    "crud_test_config",
    list_of_entities,
    ids=[e.entity_name for e in list_of_entities],
)
def test_get_nonexistent_entity_fails(crud_test_config: CrudTestConfig):
    """Tests getting a non-existent entity by id."""
    with pytest.raises(KeyError):
        crud_test_config.get_method(uuid.uuid4())


@pytest.mark.parametrize(
    "crud_test_config",
    list_of_entities,
    ids=[e.entity_name for e in list_of_entities],
)
def test_updating_nonexisting_entity_raises_error(
    crud_test_config: CrudTestConfig,
):
    """Tests updating a nonexistent entity raises an error."""
    if crud_test_config.update_model:
        # Update the created entity
        update_model = crud_test_config.update_model
        with pytest.raises(KeyError):
            crud_test_config.update_method(uuid.uuid4(), update_model)
    else:
        pytest.skip(
            "For entities that do not support updates, this test is not run."
        )


@pytest.mark.parametrize(
    "crud_test_config",
    list_of_entities,
    ids=[e.entity_name for e in list_of_entities],
)
def test_deleting_nonexistent_entity_raises_error(
    crud_test_config: CrudTestConfig,
):
    """Tests deleting a nonexistent workspace raises an error."""
    with pytest.raises(KeyError):
        crud_test_config.delete_method(uuid.uuid4())


# .----------.
# | WORKSPACES |
# '----------'


def test_only_one_default_workspace_present():
    """Tests that one and only one default workspace is present."""
    client = Client()
    assert (
        len(client.zen_store.list_workspaces(WorkspaceFilter(name="default")))
        == 1
    )


def test_updating_default_workspace_fails():
    """Tests updating the default workspace."""
    client = Client()

    default_workspace = client.zen_store.get_workspace(DEFAULT_WORKSPACE_NAME)
    assert default_workspace.name == DEFAULT_WORKSPACE_NAME
    workspace_update = WorkspaceUpdate(
        name="aria_workspace",
        description="Aria has taken possession of this workspace.",
    )
    with pytest.raises(IllegalOperationError):
        client.zen_store.update_workspace(
            workspace_id=default_workspace.id,
            workspace_update=workspace_update,
        )


def test_deleting_default_workspace_fails():
    """Tests deleting the default workspace."""
    client = Client()
    with pytest.raises(IllegalOperationError):
        client.zen_store.delete_workspace(DEFAULT_NAME)


#  .------.
# | USERS |
# '-------'


def test_active_user():
    """Tests the active user can be queried with .get_user()."""
    zen_store = Client().zen_store
    active_user = zen_store.get_user()
    assert active_user is not None
    # The SQL zen_store only supports the default user as active user
    if zen_store.type == StoreType.SQL:
        assert active_user.name == DEFAULT_USERNAME
    else:
        # TODO: Implement this
        assert True


def test_creating_user_with_existing_name_fails():
    """Tests creating a user with an existing username fails."""
    zen_store = Client().zen_store

    with UserContext() as existing_user:
        with pytest.raises(EntityExistsError):
            zen_store.create_user(
                UserRequest(name=existing_user.name, password="password")
            )

    with ServiceAccountContext() as existing_service_account:
        with does_not_raise():
            user = zen_store.create_user(
                UserRequest(
                    name=existing_service_account.name, password="password"
                )
            )
            # clean up
            zen_store.delete_user(user.id)


def test_get_user():
    """Tests getting a user account."""
    zen_store = Client().zen_store
    with UserContext() as user_account:
        user = zen_store.get_user(user_account.name)
        assert user.id == user_account.id
        assert user.name == user_account.name
        assert user.active is True
        assert user.email == user_account.email
        assert user.is_service_account is False
        assert user.full_name == user_account.full_name
        assert user.email_opted_in == user_account.email_opted_in

        # Get a user account as a service account by ID is not possible
        with pytest.raises(KeyError):
            zen_store.get_service_account(user_account.id)

        # Get a user account as a service account by name is not possible
        with pytest.raises(KeyError):
            zen_store.get_service_account(user_account.name)

        with ServiceAccountContext(name=user_account.name) as service_account:
            # Get the service account as a user account by ID is allowed
            # for backwards compatibility
            user = zen_store.get_user(service_account.id)
            assert user.id == service_account.id
            assert user.name == service_account.name
            assert user.is_service_account is True

            # Getting the user by name returns the user, not the service account
            user = zen_store.get_user(user_account.name)
            assert user.id == user_account.id
            assert user.name == user_account.name
            assert user.is_service_account is False


def test_delete_user_with_resources_fails():
    """Tests deleting a user with resources fails."""
    zen_store = Client().zen_store

    login = zen_store.type == StoreType.REST

    with UserContext(delete=False, login=login) as user:
        component_context = ComponentContext(
            c_type=StackComponentType.ORCHESTRATOR,
            flavor="local",
            config={},
            user_id=user.id,
            delete=False,
        )
        with component_context as orchestrator:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user(user.id)

    component_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_user(user.id)

    with UserContext(delete=False, login=login) as user:
        orchestrator_context = ComponentContext(
            c_type=StackComponentType.ORCHESTRATOR,
            flavor="local",
            config={},
            user_id=user.id,
            delete=False,
        )
        artifact_store_context = ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE,
            flavor="local",
            config={},
            user_id=user.id,
            delete=False,
        )

        with orchestrator_context as orchestrator:
            # We only use the context as a shortcut to create the resource
            pass
        with artifact_store_context as artifact_store:
            # We only use the context as a shortcut to create the resource
            pass

        components = {
            StackComponentType.ORCHESTRATOR: [orchestrator.id],
            StackComponentType.ARTIFACT_STORE: [artifact_store.id],
        }
        stack_context = StackContext(
            components=components, user_id=user.id, delete=False
        )
        with stack_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user(user.id)

    stack_context.cleanup()
    artifact_store_context.cleanup()
    orchestrator_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_user(user.id)

    with UserContext(delete=False, login=login) as user:
        with SecretContext(user_id=user.id, delete=False):
            pass

    # Secrets are deleted when the user is deleted
    with does_not_raise():
        zen_store.delete_user(user.id)

    with UserContext(delete=False, login=login) as user:
        code_repo_context = CodeRepositoryContext(
            user_id=user.id, delete=False
        )
        with code_repo_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user(user.id)

    code_repo_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_user(user.id)

    with UserContext(delete=False, login=login) as user:
        service_connector_context = ServiceConnectorContext(
            connector_type="cat'o'matic",
            auth_method="paw-print",
            resource_types=["cat"],
            resource_id="aria",
            configuration={
                "language": "meow",
                "foods": "tuna",
            },
            user_id=user.id,
            delete=False,
        )
        with service_connector_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user(user.id)

    service_connector_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_user(user.id)

    with UserContext(delete=False, login=login) as user:
        model_version_context = ModelVersionContext(
            create_version=True, user_id=user.id, delete=False
        )
        with model_version_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user(user.id)

    model_version_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_user(user.id)


def test_updating_user_with_existing_name_fails():
    """Tests updating a user with an existing account name fails."""
    zen_store = Client().zen_store

    with UserContext() as user:
        with UserContext() as existing_user:
            with pytest.raises(EntityExistsError):
                zen_store.update_user(
                    user_id=user.id,
                    user_update=UserUpdate(name=existing_user.name),
                )

        with ServiceAccountContext() as existing_service_account:
            with does_not_raise():
                zen_store.update_user(
                    user_id=user.id,
                    user_update=UserUpdate(name=existing_service_account.name),
                )


def test_updating_default_user_fails():
    """Tests that updating the default user is prohibited."""
    client = Client()
    default_user = client.zen_store.get_user(DEFAULT_USERNAME)
    assert default_user
    user_update = UserUpdate(name="axl")
    with pytest.raises(IllegalOperationError):
        client.zen_store.update_user(
            user_id=default_user.id, user_update=user_update
        )


def test_deleting_default_user_fails():
    """Tests that deleting the default user is prohibited."""
    zen_store = Client().zen_store
    with pytest.raises(IllegalOperationError):
        zen_store.delete_user("default")


def test_create_user_no_password():
    """Tests that creating a user without a password needs to be activated."""
    client = Client()
    store = client.zen_store

    if store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support user activation")

    with UserContext(inactive=True) as user:
        assert not user.active
        assert user.activation_token is not None

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password=""):
                pass

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="password"):
                pass

        with pytest.raises(AuthorizationException):
            response_body = store.put(
                f"{USERS}/{str(user.id)}{ACTIVATE}",
                body=UserUpdate(password="password"),
            )

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="password"):
                pass

        response_body = store.put(
            f"{USERS}/{str(user.id)}{ACTIVATE}",
            body=UserUpdate(
                password="password", activation_token=user.activation_token
            ),
        )
        activated_user = UserResponse.parse_obj(response_body)
        assert activated_user.active
        assert activated_user.name == user.name
        assert activated_user.id == user.id

        with LoginContext(user_name=user.name, password="password"):
            new_store = Client().zen_store
            assert new_store.get_user().id == user.id


def test_reactivate_user():
    """Tests that reactivating a user with a new password works."""
    client = Client()
    store = client.zen_store

    if store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support user activation")

    with UserContext(password="password") as user:
        assert user.active
        assert user.activation_token is None

        with LoginContext(user_name=user.name, password="password"):
            new_store = Client().zen_store
            assert new_store.get_user().id == user.id

        response_body = store.put(
            f"{USERS}/{str(user.id)}{DEACTIVATE}",
        )
        deactivated_user = UserResponse.parse_obj(response_body)
        assert not deactivated_user.active
        assert deactivated_user.activation_token is not None

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="password"):
                pass

        with pytest.raises(AuthorizationException):
            response_body = store.put(
                f"{USERS}/{str(user.id)}{ACTIVATE}",
                body=UserUpdate(password="newpassword"),
            )

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="password"):
                pass

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="newpassword"):
                pass

        response_body = store.put(
            f"{USERS}/{str(user.id)}{ACTIVATE}",
            body=UserUpdate(
                password="newpassword",
                activation_token=deactivated_user.activation_token,
            ),
        )
        activated_user = UserResponse.parse_obj(response_body)
        assert activated_user.active
        assert activated_user.name == user.name
        assert activated_user.id == user.id

        with pytest.raises(AuthorizationException):
            with LoginContext(user_name=user.name, password="password"):
                pass

        with LoginContext(user_name=user.name, password="newpassword"):
            new_store = Client().zen_store
            assert new_store.get_user().id == user.id


#  .-----------------.
# | SERVICE ACCOUNTS |
# '------------------'


def test_create_service_account():
    """Tests creating a service account."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        account = zen_store.get_service_account(service_account.name)
        assert account.id == service_account.id
        assert account.name == service_account.name
        assert account.active is True

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.name == service_account.name
        assert account.active is True


def test_delete_service_account():
    """Tests deleting a service account."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        # delete by name
        zen_store.delete_service_account(service_account.name)

        with pytest.raises(KeyError):
            zen_store.get_service_account(service_account.name)

        with pytest.raises(KeyError):
            zen_store.get_service_account(service_account.id)

    with ServiceAccountContext() as service_account:
        # delete by ID
        zen_store.delete_service_account(service_account.id)

        with pytest.raises(KeyError):
            zen_store.get_service_account(service_account.name)

        with pytest.raises(KeyError):
            zen_store.get_service_account(service_account.id)


def test_delete_service_account_with_resources_fails():
    """Tests deleting a service account with resources fails."""
    zen_store = Client().zen_store

    login = zen_store.type == StoreType.REST

    with ServiceAccountContext(delete=False, login=login) as service_account:
        component_context = ComponentContext(
            c_type=StackComponentType.ORCHESTRATOR,
            flavor="local",
            config={},
            user_id=service_account.id,
            delete=False,
        )
        with component_context as orchestrator:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_service_account(service_account.id)

    component_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)

    with ServiceAccountContext(delete=False, login=login) as service_account:
        orchestrator_context = ComponentContext(
            c_type=StackComponentType.ORCHESTRATOR,
            flavor="local",
            config={},
            user_id=service_account.id,
            delete=False,
        )
        artifact_store_context = ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE,
            flavor="local",
            config={},
            user_id=service_account.id,
            delete=False,
        )

        with orchestrator_context as orchestrator:
            # We only use the context as a shortcut to create the resource
            pass
        with artifact_store_context as artifact_store:
            # We only use the context as a shortcut to create the resource
            pass

        components = {
            StackComponentType.ORCHESTRATOR: [orchestrator.id],
            StackComponentType.ARTIFACT_STORE: [artifact_store.id],
        }
        stack_context = StackContext(
            components=components, user_id=service_account.id, delete=False
        )
        with stack_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_service_account(service_account.id)

    stack_context.cleanup()
    artifact_store_context.cleanup()
    orchestrator_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)

    with ServiceAccountContext(delete=False, login=login) as service_account:
        with SecretContext(user_id=service_account.id, delete=False):
            pass

    # Secrets are deleted when the service_account is deleted
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)

    with ServiceAccountContext(delete=False, login=login) as service_account:
        code_repo_context = CodeRepositoryContext(
            user_id=service_account.id, delete=False
        )
        with code_repo_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_service_account(service_account.id)

    code_repo_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)

    with ServiceAccountContext(delete=False, login=login) as service_account:
        service_connector_context = ServiceConnectorContext(
            connector_type="cat'o'matic",
            auth_method="paw-print",
            resource_types=["cat"],
            resource_id="aria",
            configuration={
                "language": "meow",
                "foods": "tuna",
            },
            user_id=service_account.id,
            delete=False,
        )
        with service_connector_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_service_account(service_account.id)

    service_connector_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)

    with ServiceAccountContext(delete=False, login=login) as service_account:
        model_version_context = ModelVersionContext(
            create_version=True, user_id=service_account.id, delete=False
        )
        with model_version_context:
            # We only use the context as a shortcut to create the resource
            pass

    # Can't delete because owned resources exist
    with pytest.raises(IllegalOperationError):
        zen_store.delete_service_account(service_account.id)

    model_version_context.cleanup()

    # Can delete because owned resources have been removed
    with does_not_raise():
        zen_store.delete_service_account(service_account.id)


def test_create_service_account_used_name_fails():
    """Tests creating a service account name with a name that is already used."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as existing_service_account:
        with pytest.raises(EntityExistsError):
            zen_store.create_service_account(
                ServiceAccountRequest(
                    name=existing_service_account.name,
                    active=True,
                )
            )

    with UserContext() as existing_user:
        # Can create a service account with the same name as a user account
        with does_not_raise():
            account = zen_store.create_service_account(
                ServiceAccountRequest(
                    name=existing_user.name,
                    active=True,
                )
            )
            # clean up
            zen_store.delete_service_account(account.id)


def test_get_service_account():
    """Tests getting a service account."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        account = zen_store.get_service_account(service_account.name)
        assert account.id == service_account.id
        assert account.name == service_account.name
        assert account.active is True
        assert account.description == service_account.description

        # Get a service account as a user account by ID is allowed
        # for backwards compatibility
        user = zen_store.get_user(service_account.id)
        assert user.id == service_account.id
        assert user.name == service_account.name
        assert user.active is True
        assert user.activation_token is None
        assert user.email is None
        assert user.is_service_account is True
        assert user.full_name == ""
        assert user.email_opted_in is False
        assert user.hub_token is None

        # Get a service account as a user account by name
        with pytest.raises(KeyError):
            user = zen_store.get_user(service_account.name)

        with UserContext(user_name=service_account.name) as existing_user:
            # Get the service account as a user account by ID is allowed
            # for backwards compatibility
            user = zen_store.get_user(service_account.id)
            assert user.id == service_account.id
            assert user.name == service_account.name
            assert user.is_service_account is True

            # Getting the user by name returns the user, not the service account
            user = zen_store.get_user(service_account.name)
            assert user.id == existing_user.id
            assert user.name == service_account.name
            assert user.is_service_account is False


def test_list_service_accounts():
    """Tests listing service accounts."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account_one:
        accounts = zen_store.list_service_accounts(
            # TODO: we use a large size to get all accounts in one page, but
            #  the correct way to do this is to fetch all pages
            ServiceAccountFilter(size=1000)
        ).items
        assert service_account_one.id in [account.id for account in accounts]

        accounts = zen_store.list_service_accounts(
            ServiceAccountFilter(
                name=service_account_one.name,
            )
        ).items
        assert service_account_one.id in [account.id for account in accounts]

        accounts = zen_store.list_service_accounts(
            ServiceAccountFilter(
                id=service_account_one.id,
            )
        ).items
        assert service_account_one.id in [account.id for account in accounts]

        with ServiceAccountContext() as service_account_two:
            accounts = zen_store.list_service_accounts(
                # TODO: we use a large size to get all accounts in one page, but
                #  the correct way to do this is to fetch all pages
                ServiceAccountFilter(size=1000)
            ).items
            assert service_account_one.id in [
                account.id for account in accounts
            ]
            assert service_account_two.id in [
                account.id for account in accounts
            ]

            accounts = zen_store.list_service_accounts(
                ServiceAccountFilter(
                    name=service_account_one.name,
                )
            ).items
            assert len(accounts) == 1
            assert service_account_one.id in [
                account.id for account in accounts
            ]

            accounts = zen_store.list_service_accounts(
                ServiceAccountFilter(
                    name=service_account_two.name,
                )
            ).items
            assert len(accounts) == 1
            assert service_account_two.id in [
                account.id for account in accounts
            ]

            accounts = zen_store.list_service_accounts(
                ServiceAccountFilter(
                    active=True,
                    size=1000,
                )
            ).items
            assert service_account_one.id in [
                account.id for account in accounts
            ]
            assert service_account_two.id in [
                account.id for account in accounts
            ]

            with UserContext() as user:
                accounts = zen_store.list_service_accounts(
                    # TODO: we use a large size to get all accounts in one page,
                    # but the correct way to do this is to fetch all pages
                    ServiceAccountFilter(size=1000)
                ).items
                assert user.id not in [account.id for account in accounts]


def test_update_service_account_name():
    """Tests updating a service account name."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        account_name = service_account.name
        new_account_name = sample_name("aria")

        # Update by name
        updated_account = zen_store.update_service_account(
            service_account_name_or_id=account_name,
            service_account_update=ServiceAccountUpdate(
                name=new_account_name,
            ),
        )
        assert updated_account.id == service_account.id
        assert updated_account.name == new_account_name
        assert updated_account.active is True
        assert updated_account.description == service_account.description

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.name == new_account_name
        assert account.active is True
        assert updated_account.description == service_account.description

        account = zen_store.get_service_account(new_account_name)
        assert account.id == service_account.id
        assert account.name == new_account_name
        assert account.active is True
        assert updated_account.description == service_account.description

        with pytest.raises(KeyError):
            zen_store.get_service_account(account_name)

        account_name = new_account_name
        new_account_name = sample_name("aria")

        # Update by ID
        updated_account = zen_store.update_service_account(
            service_account_name_or_id=service_account.id,
            service_account_update=ServiceAccountUpdate(
                name=new_account_name,
            ),
        )
        assert updated_account.id == service_account.id
        assert updated_account.name == new_account_name
        assert updated_account.active is True
        assert updated_account.description == service_account.description

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.name == new_account_name
        assert account.active is True
        assert updated_account.description == service_account.description

        account = zen_store.get_service_account(new_account_name)
        assert account.id == service_account.id

        with pytest.raises(KeyError):
            zen_store.get_service_account(account_name)


def test_update_service_account_used_name_fails():
    """Tests updating a service account name to a name that is already used."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        with ServiceAccountContext() as existing_service_account:
            # Update by name
            with pytest.raises(EntityExistsError):
                zen_store.update_service_account(
                    service_account_name_or_id=service_account.name,
                    service_account_update=ServiceAccountUpdate(
                        name=existing_service_account.name,
                    ),
                )

            account = zen_store.get_service_account(service_account.id)
            assert account.name == service_account.name

            # Update by ID
            with pytest.raises(EntityExistsError):
                zen_store.update_service_account(
                    service_account_name_or_id=service_account.id,
                    service_account_update=ServiceAccountUpdate(
                        name=existing_service_account.name,
                    ),
                )

            account = zen_store.get_service_account(service_account.id)
            assert account.name == service_account.name

        with UserContext() as existing_user:
            # Update works if the name is the same as a user account
            with does_not_raise():
                zen_store.update_service_account(
                    service_account_name_or_id=service_account.id,
                    service_account_update=ServiceAccountUpdate(
                        name=existing_user.name,
                    ),
                )


def test_deactivate_service_account():
    """Tests deactivating a service account."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        account_name = service_account.name

        account = zen_store.get_service_account(service_account.id)
        assert account.active is True

        # Update by name
        updated_account = zen_store.update_service_account(
            service_account_name_or_id=account_name,
            service_account_update=ServiceAccountUpdate(
                active=False,
            ),
        )
        assert updated_account.id == service_account.id
        assert updated_account.active is False

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.active is False

        # Update by ID
        updated_account = zen_store.update_service_account(
            service_account_name_or_id=service_account.id,
            service_account_update=ServiceAccountUpdate(
                active=True,
            ),
        )
        assert updated_account.id == service_account.id
        assert updated_account.active is True

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.active is True


def test_update_service_account_description():
    """Tests updating a service account description."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        new_description = "Axl has taken possession of this account."

        updated_account = zen_store.update_service_account(
            service_account_name_or_id=service_account.id,
            service_account_update=ServiceAccountUpdate(
                description=new_description,
            ),
        )
        assert updated_account.id == service_account.id
        assert updated_account.name == service_account.name
        assert updated_account.active is True
        assert updated_account.description == new_description

        account = zen_store.get_service_account(service_account.id)
        assert account.id == service_account.id
        assert account.name == service_account.name
        assert account.active is True
        assert updated_account.description == new_description


# .----------.
# | API KEYS |
# '----------'


def test_create_api_key():
    """Tests creating a service account."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        new_api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        assert new_api_key.name == api_key_request.name
        assert new_api_key.description == api_key_request.description
        assert new_api_key.service_account.id == service_account.id
        assert new_api_key.key is not None
        assert new_api_key.active is True
        assert new_api_key.last_login is None
        assert new_api_key.last_rotated is None

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.id,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name
        assert api_key.description == api_key_request.description
        assert api_key.service_account.id == service_account.id
        assert api_key.key is None

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.name,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name


def test_delete_api_key():
    """Tests deleting an API key."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        new_api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.id,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.name,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name

        # delete by name
        zen_store.delete_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.name,
        )

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=new_api_key.id,
            )

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key_request.name,
            )

        with pytest.raises(KeyError):
            zen_store.delete_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=new_api_key.name,
            )

        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        new_api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.id,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.name,
        )
        assert api_key.id == new_api_key.id
        assert api_key.name == api_key_request.name

        # delete by ID
        zen_store.delete_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_api_key.id,
        )

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=new_api_key.id,
            )

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key_request.name,
            )

        with pytest.raises(KeyError):
            zen_store.delete_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=new_api_key.id,
            )


def test_create_api_key_used_name_fails():
    """Tests creating an API key with a name that is already used."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        with pytest.raises(EntityExistsError):
            zen_store.create_api_key(
                service_account_id=service_account.id,
                api_key=api_key_request,
            )


def test_list_api_keys():
    """Tests listing API keys."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        api_key_one = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(),
        ).items
        assert len(keys) == 1
        assert api_key_one.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                name=api_key_one.name,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_one.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                id=api_key_one.id,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_one.id in [key.id for key in keys]

        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key_two = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(),
        ).items
        assert len(keys) == 2
        assert api_key_one.id in [key.id for key in keys]
        assert api_key_two.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                name=api_key_one.name,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_one.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                name=api_key_two.name,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_two.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                id=api_key_one.id,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_one.id in [key.id for key in keys]

        keys = zen_store.list_api_keys(
            service_account_id=service_account.id,
            filter_model=APIKeyFilter(
                id=api_key_two.id,
            ),
        ).items
        assert len(keys) == 1
        assert api_key_two.id in [key.id for key in keys]


def test_update_key_name():
    """Tests updating an API key name."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        # Update by name
        new_key_name = "aria"
        updated_key = zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key_request.name,
            api_key_update=APIKeyUpdate(
                name=new_key_name,
            ),
        )
        assert updated_key.id == api_key.id
        assert updated_key.name == new_key_name
        assert updated_key.active is True
        assert updated_key.description == api_key.description

        key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_key_name,
        )
        assert key.id == api_key.id
        assert key.name == new_key_name

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.name,
            )

        # Update by ID
        new_new_key_name = "blupus"
        updated_key = zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            api_key_update=APIKeyUpdate(
                name=new_new_key_name,
            ),
        )
        assert updated_key.id == api_key.id
        assert updated_key.name == new_new_key_name
        assert updated_key.active is True
        assert updated_key.description == api_key.description

        key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=new_new_key_name,
        )
        assert key.id == api_key.id
        assert key.name == new_new_key_name

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.name,
            )

        with pytest.raises(KeyError):
            zen_store.get_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=new_key_name,
            )


def test_update_api_key_used_name_fails():
    """Tests updating an API key name to a name that is already used."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        other_api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=other_api_key_request,
        )

        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        # Update by name
        with pytest.raises(EntityExistsError):
            zen_store.update_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key_request.name,
                api_key_update=APIKeyUpdate(
                    name=other_api_key_request.name,
                ),
            )

        # Update by ID
        with pytest.raises(EntityExistsError):
            zen_store.update_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.id,
                api_key_update=APIKeyUpdate(
                    name=other_api_key_request.name,
                ),
            )


def test_deactivate_api_key():
    """Tests deactivating an API key."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
        )
        assert key.id == api_key.id
        assert key.name == api_key_request.name
        assert key.active is True

        # Update by name
        updated_key = zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key_request.name,
            api_key_update=APIKeyUpdate(
                active=False,
            ),
        )
        assert updated_key.id == api_key.id
        assert updated_key.name == api_key.name
        assert updated_key.active is False
        assert updated_key.description == api_key.description

        # Update by ID
        updated_key = zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            api_key_update=APIKeyUpdate(
                active=True,
            ),
        )
        assert updated_key.id == api_key.id
        assert updated_key.name == api_key.name
        assert updated_key.active is True
        assert updated_key.description == api_key.description


def test_update_api_key_description():
    """Tests updating an API key description."""
    zen_store = Client().zen_store

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        new_description = "Axl has taken possession of this API key."

        updated_key = zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            api_key_update=APIKeyUpdate(
                description=new_description,
            ),
        )
        assert updated_key.id == api_key.id
        assert updated_key.name == api_key.name
        assert updated_key.active is True
        assert updated_key.description == new_description

        key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
        )
        assert key.id == api_key.id
        assert key.name == api_key.name
        assert key.active is True
        assert key.description == new_description


def test_rotate_api_key():
    """Tests rotating a service account."""
    zen_store = Client().zen_store
    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="axl",
            description="Axl's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        assert api_key.name == api_key_request.name
        assert api_key.key is not None
        assert api_key.active is True
        assert api_key.last_login is None
        assert api_key.last_rotated is None

        rotated_api_key = zen_store.rotate_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            rotate_request=APIKeyRotateRequest(),
        )

        assert rotated_api_key.name == api_key_request.name
        assert rotated_api_key.key is not None
        assert rotated_api_key.key != api_key.key
        assert rotated_api_key.active is True
        assert rotated_api_key.last_login is None
        assert rotated_api_key.last_rotated is not None


def test_login_api_key():
    """Tests logging in with an API key."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        api_key = zen_store.get_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
        )
        assert api_key.last_login is not None
        assert api_key.last_rotated is None


def test_login_inactive_api_key():
    """Tests logging in with an inactive API key."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            api_key_update=APIKeyUpdate(
                active=False,
            ),
        )

        with pytest.raises(AuthorizationException):
            with LoginContext(api_key=api_key.key):
                pass

        zen_store.update_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            api_key_update=APIKeyUpdate(
                active=True,
            ),
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        # Test deactivation while logged in
        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

            new_zen_store.update_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.id,
                api_key_update=APIKeyUpdate(
                    active=False,
                ),
            )

            with pytest.raises(AuthorizationException):
                new_zen_store.get_user()

            # NOTE: use the old store to update the key, since the new store
            # is no longer authorized
            zen_store.update_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.id,
                api_key_update=APIKeyUpdate(
                    active=True,
                ),
            )

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id


def test_login_inactive_service_account():
    """Tests logging in with an inactive service account."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        zen_store.update_service_account(
            service_account_name_or_id=service_account.id,
            service_account_update=ServiceAccountUpdate(
                active=False,
            ),
        )

        with pytest.raises(AuthorizationException):
            with LoginContext(api_key=api_key.key):
                pass

        zen_store.update_service_account(
            service_account_name_or_id=service_account.id,
            service_account_update=ServiceAccountUpdate(
                active=True,
            ),
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        # Test deactivation while logged in
        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

            new_zen_store.update_service_account(
                service_account_name_or_id=service_account.id,
                service_account_update=ServiceAccountUpdate(
                    active=False,
                ),
            )

            with pytest.raises(AuthorizationException):
                new_zen_store.get_user()

            # NOTE: use the old store to update the key, since the new store
            # is no longer authorized
            zen_store.update_service_account(
                service_account_name_or_id=service_account.id,
                service_account_update=ServiceAccountUpdate(
                    active=True,
                ),
            )

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id


def test_login_deleted_api_key():
    """Tests logging in with a deleted key."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        zen_store.delete_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
        )

        with pytest.raises(AuthorizationException):
            with LoginContext(api_key=api_key.key):
                pass

        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        # Test deletion while logged in
        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

            new_zen_store.delete_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.id,
            )

            with pytest.raises(AuthorizationException):
                new_zen_store.get_user()

            # NOTE: use the old store to re-add the key, since the new store
            # is no longer authorized
            zen_store.create_api_key(
                service_account_id=service_account.id,
                api_key=api_key_request,
            )

            with pytest.raises(AuthorizationException):
                new_zen_store.get_user()


def test_login_rotate_api_key():
    """Tests logging in with a rotated API key."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        rotated_api_key = zen_store.rotate_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            rotate_request=APIKeyRotateRequest(),
        )

        with pytest.raises(AuthorizationException):
            with LoginContext(api_key=api_key.key):
                pass

        with LoginContext(api_key=rotated_api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        # Test rotation while logged in
        with LoginContext(api_key=rotated_api_key.key):
            new_zen_store = Client().zen_store

            new_zen_store.rotate_api_key(
                service_account_id=service_account.id,
                api_key_name_or_id=api_key.id,
                rotate_request=APIKeyRotateRequest(),
            )

            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id


def test_login_rotate_api_key_retain_period():
    """Tests logging in with a rotated API key with a retain period."""
    zen_store = Client().zen_store
    if zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support API keys login")

    with ServiceAccountContext() as service_account:
        api_key_request = APIKeyRequest(
            name="aria",
            description="Aria's API key",
        )
        api_key = zen_store.create_api_key(
            service_account_id=service_account.id,
            api_key=api_key_request,
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        rotated_api_key = zen_store.rotate_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            rotate_request=APIKeyRotateRequest(retain_period_minutes=1),
        )

        with LoginContext(api_key=api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        with LoginContext(api_key=rotated_api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        re_rotated_api_key = zen_store.rotate_api_key(
            service_account_id=service_account.id,
            api_key_name_or_id=api_key.id,
            rotate_request=APIKeyRotateRequest(retain_period_minutes=1),
        )

        with LoginContext(api_key=re_rotated_api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        with LoginContext(api_key=rotated_api_key.key):
            new_zen_store = Client().zen_store
            active_user = new_zen_store.get_user()
            assert active_user.id == service_account.id

        with pytest.raises(AuthorizationException):
            with LoginContext(api_key=api_key.key):
                pass


# .------------------.
# | Stack components |
# '------------------'


def test_update_default_stack_component_fails():
    """Tests that updating default stack components fails."""
    client = Client()
    store = client.zen_store
    default_artifact_store = store.list_stack_components(
        ComponentFilter(
            workspace_id=client.active_workspace.id,
            type=StackComponentType.ARTIFACT_STORE,
            name=DEFAULT_STACK_AND_COMPONENT_NAME,
        )
    )[0]

    default_orchestrator = store.list_stack_components(
        ComponentFilter(
            workspace_id=client.active_workspace.id,
            type=StackComponentType.ORCHESTRATOR,
            name=DEFAULT_STACK_AND_COMPONENT_NAME,
        )
    )[0]

    component_update = ComponentUpdate(name="aria")
    with pytest.raises(IllegalOperationError):
        store.update_stack_component(
            component_id=default_orchestrator.id,
            component_update=component_update,
        )

    default_orchestrator.name = "axl"
    with pytest.raises(IllegalOperationError):
        store.update_stack_component(
            component_id=default_artifact_store.id,
            component_update=component_update,
        )


def test_delete_default_stack_component_fails():
    """Tests that deleting default stack components is prohibited."""
    client = Client()
    store = client.zen_store
    default_artifact_store = store.list_stack_components(
        ComponentFilter(
            workspace_id=client.active_workspace.id,
            type=StackComponentType.ARTIFACT_STORE,
            name=DEFAULT_STACK_AND_COMPONENT_NAME,
        )
    )[0]

    default_orchestrator = store.list_stack_components(
        ComponentFilter(
            workspace_id=client.active_workspace.id,
            type=StackComponentType.ORCHESTRATOR,
            name=DEFAULT_STACK_AND_COMPONENT_NAME,
        )
    )[0]

    with pytest.raises(IllegalOperationError):
        store.delete_stack_component(default_artifact_store.id)

    with pytest.raises(IllegalOperationError):
        store.delete_stack_component(default_orchestrator.id)


def test_count_stack_components():
    """Tests that the count stack_component command returns the correct amount."""
    client = Client()
    store = client.zen_store
    if not isinstance(store, SqlZenStore):
        pytest.skip("Test only applies to SQL store")
    active_workspace = client.active_workspace
    filter_model = ComponentFilter(scope_workspace=active_workspace.id)
    count_before = store.list_stack_components(filter_model).total

    assert store.count_stack_components(filter_model) == count_before

    with ComponentContext(
        StackComponentType.ARTIFACT_STORE, config={}, flavor="s3"
    ):
        assert store.count_stack_components(filter_model) == count_before + 1


# .-------------------------.
# | Stack component flavors |
# '-------------------------'

# .--------.
# | STACKS |
# '--------'


def test_updating_default_stack_fails():
    """Tests that updating the default stack is prohibited."""
    client = Client()

    default_stack = client.get_stack(DEFAULT_STACK_AND_COMPONENT_NAME)
    assert default_stack.name == DEFAULT_STACK_AND_COMPONENT_NAME
    stack_update = StackUpdate(name="axls_stack")
    with pytest.raises(IllegalOperationError):
        client.zen_store.update_stack(
            stack_id=default_stack.id, stack_update=stack_update
        )


def test_deleting_default_stack_fails():
    """Tests that deleting the default stack is prohibited."""
    client = Client()

    default_stack = client.get_stack(DEFAULT_STACK_AND_COMPONENT_NAME)
    with pytest.raises(IllegalOperationError):
        client.zen_store.delete_stack(default_stack.id)


def test_get_stack_fails_with_nonexistent_stack_id():
    """Tests getting stack fails with nonexistent stack id."""
    client = Client()
    store = client.zen_store

    with pytest.raises(KeyError):
        store.get_stack(uuid.uuid4())


def test_filter_stack_succeeds():
    """Tests getting stack."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(components=components) as stack:
                returned_stacks = store.list_stacks(
                    StackFilter(name=stack.name)
                )
                assert returned_stacks


def test_crud_on_stack_succeeds():
    """Tests getting stack."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            stack_name = sample_name("arias_stack")
            new_stack = StackRequest(
                name=stack_name,
                components=components,
                workspace=client.active_workspace.id,
                user=client.active_user.id,
            )
            created_stack = store.create_stack(stack=new_stack)

            stacks = store.list_stacks(StackFilter(name=stack_name))
            assert len(stacks) == 1

            with does_not_raise():
                stack = store.get_stack(created_stack.id)
                assert stack is not None

            # Update
            stack_update = StackUpdate(name="axls_stack")
            store.update_stack(stack_id=stack.id, stack_update=stack_update)

            stacks = store.list_stacks(StackFilter(name="axls_stack"))
            assert len(stacks) == 1
            stacks = store.list_stacks(StackFilter(name=stack_name))
            assert len(stacks) == 0

            # Cleanup
            store.delete_stack(created_stack.id)
            with pytest.raises(KeyError):
                store.get_stack(created_stack.id)


def test_register_stack_fails_when_stack_exists():
    """Tests registering stack fails when stack exists."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(components=components) as stack:
                new_stack = StackRequest(
                    name=stack.name,
                    components=components,
                    workspace=client.active_workspace.id,
                    user=client.active_user.id,
                )
                with pytest.raises(StackExistsError):
                    # TODO: [server] inject user and workspace into stack as well
                    store.create_stack(
                        stack=new_stack,
                    )


def test_updating_nonexistent_stack_fails():
    """Tests updating nonexistent stack fails."""
    client = Client()
    store = client.zen_store

    stack_update = StackUpdate(name="axls_stack")
    nonexistent_id = uuid.uuid4()
    with pytest.raises(KeyError):
        store.update_stack(stack_id=nonexistent_id, stack_update=stack_update)
    with pytest.raises(KeyError):
        store.get_stack(nonexistent_id)


def test_deleting_nonexistent_stack_fails():
    """Tests deleting nonexistent stack fails."""
    client = Client()
    store = client.zen_store
    non_existent_stack_id = uuid.uuid4()
    with pytest.raises(KeyError):
        store.delete_stack(non_existent_stack_id)


def test_deleting_a_stack_succeeds():
    """Tests deleting stack."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(components=components) as stack:
                store.delete_stack(stack.id)
                with pytest.raises(KeyError):
                    store.get_stack(stack.id)


def test_deleting_a_stack_recursively_succeeds():
    """Tests deleting stack recursively."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(components=components) as stack:
                client.delete_stack(stack.id, recursive=True)
                with pytest.raises(KeyError):
                    store.get_stack(stack.id)
                with pytest.raises(KeyError):
                    store.get_stack_component(orchestrator.id)
                with pytest.raises(KeyError):
                    store.get_stack_component(artifact_store.id)


def test_deleting_a_stack_recursively_with_some_stack_components_present_in_another_stack_succeeds():
    """Tests deleting stack recursively."""
    client = Client()
    store = client.zen_store

    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR, flavor="local", config={}
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE, flavor="local", config={}
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(components=components) as stack:
                with ComponentContext(
                    c_type=StackComponentType.SECRETS_MANAGER,
                    flavor="local",
                    config={},
                ) as secret:
                    components = {
                        StackComponentType.ORCHESTRATOR: [orchestrator.id],
                        StackComponentType.ARTIFACT_STORE: [artifact_store.id],
                        StackComponentType.SECRETS_MANAGER: [secret.id],
                    }
                    with StackContext(components=components) as stack:
                        client.delete_stack(stack.id, recursive=True)
                        with pytest.raises(KeyError):
                            store.get_stack(stack.id)
                        with pytest.raises(KeyError):
                            store.get_stack_component(secret.id)


def test_stacks_are_accessible_by_other_users():
    """Tests accessing stack on rest zen stores."""
    client = Client()
    store = client.zen_store
    if store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support stack scoping")

    default_user_id = client.active_user.id
    with ComponentContext(
        c_type=StackComponentType.ORCHESTRATOR,
        flavor="local",
        config={},
        user_id=default_user_id,
    ) as orchestrator:
        with ComponentContext(
            c_type=StackComponentType.ARTIFACT_STORE,
            flavor="local",
            config={},
            user_id=default_user_id,
        ) as artifact_store:
            components = {
                StackComponentType.ORCHESTRATOR: [orchestrator.id],
                StackComponentType.ARTIFACT_STORE: [artifact_store.id],
            }
            with StackContext(
                components=components, user_id=default_user_id
            ) as stack:
                with UserContext(login=True):
                    #  Client() needs to be instantiated here with the new
                    #  logged-in user
                    filtered_stacks = Client().zen_store.list_stacks(
                        StackFilter(name=stack.name)
                    )
                    assert len(filtered_stacks) == 1


# .-----------.
# | Pipelines |
# '-----------'

# .----------------.
# | Pipeline runs  |
# '----------------'


def test_list_runs_is_ordered():
    """Tests listing runs returns ordered runs."""
    client = Client()
    store = client.zen_store

    num_pipelines_before = store.list_runs(PipelineRunFilter()).total

    num_runs = 5
    with PipelineRunContext(num_runs):
        pipelines = store.list_runs(PipelineRunFilter()).items
        assert (
            store.list_runs(PipelineRunFilter()).total
            == num_pipelines_before + num_runs
        )
        assert all(
            pipelines[i].created <= pipelines[i + 1].created
            for i in range(len(pipelines) - 1)
        )


def test_count_runs():
    """Tests that the count runs command returns the correct amount."""
    client = Client()
    store = client.zen_store
    if not isinstance(store, SqlZenStore):
        pytest.skip("Test only applies to SQL store")
    active_workspace = client.active_workspace
    filter_model = PipelineRunFilter(scope_workspace=active_workspace.id)
    num_runs = store.list_runs(filter_model).total

    # At baseline this should be the same
    assert store.count_runs(filter_model) == num_runs

    with PipelineRunContext(5):
        assert (
            store.count_runs(filter_model)
            == store.list_runs(
                PipelineRunFilter(scope_workspace=active_workspace.id)
            ).total
        )
        assert store.count_runs(filter_model) == num_runs + 5


def test_filter_runs_by_code_repo(mocker):
    """Tests filtering runs by code repository id."""
    mocker.patch.object(
        source_utils, "get_source_root", return_value=os.getcwd()
    )
    store = Client().zen_store

    with CodeRepositoryContext() as repo:
        clean_local_context = StubLocalRepositoryContext(
            code_repository_id=repo.id, root=os.getcwd(), commit="commit"
        )
        mocker.patch.object(
            code_repository_utils,
            "find_active_code_repository",
            return_value=clean_local_context,
        )

        with PipelineRunContext(1):
            filter_model = PipelineRunFilter(code_repository_id=uuid.uuid4())
            assert store.list_runs(filter_model).total == 0

            filter_model = PipelineRunFilter(code_repository_id=repo.id)
            assert store.list_runs(filter_model).total == 1


def test_deleting_run_deletes_steps():
    """Tests deleting run deletes its steps."""
    client = Client()
    store = client.zen_store
    with PipelineRunContext(num_runs=1) as runs:
        run_id = runs[0].id
        filter_model = StepRunFilter(pipeline_run_id=run_id)
        assert store.list_run_steps(filter_model).total == 2
        store.delete_run(run_id)
        assert store.list_run_steps(filter_model).total == 0


# .--------------------.
# | Pipeline run steps |
# '--------------------'


def test_get_run_step_outputs_succeeds():
    """Tests getting run step outputs."""
    client = Client()
    store = client.zen_store

    with PipelineRunContext(1):
        steps = store.list_run_steps(StepRunFilter(name="step_2"))

        for step in steps.items:
            run_step_outputs = store.get_run_step(step.id).outputs
            assert len(run_step_outputs) == 1


def test_get_run_step_inputs_succeeds():
    """Tests getting run step inputs."""
    client = Client()
    store = client.zen_store

    with PipelineRunContext(1):
        steps = store.list_run_steps(StepRunFilter(name="step_2"))
        for step in steps.items:
            run_step_inputs = store.get_run_step(step.id).inputs
            assert len(run_step_inputs) == 1


# .-----------.
# | Artifacts |
# '-----------'


def test_list_unused_artifacts():
    """Tests listing with `unused=True` only returns unused artifacts."""
    client = Client()
    store = client.zen_store

    num_artifact_versions_before = store.list_artifact_versions(
        ArtifactVersionFilter()
    ).total
    num_unused_artifact_versions_before = store.list_artifact_versions(
        ArtifactVersionFilter(only_unused=True)
    ).total
    num_runs = 1
    with PipelineRunContext(num_runs):
        artifact_versions = store.list_artifact_versions(
            ArtifactVersionFilter()
        )
        assert (
            artifact_versions.total
            == num_artifact_versions_before + num_runs * 2
        )

        artifact_versions = store.list_artifact_versions(
            ArtifactVersionFilter(only_unused=True)
        )
        assert artifact_versions.total == num_unused_artifact_versions_before


def test_artifacts_are_not_deleted_with_run(clean_client: "Client"):
    """Tests listing with `unused=True` only returns unused artifacts."""
    store = clean_client.zen_store

    num_artifact_versions_before = store.list_artifact_versions(
        ArtifactVersionFilter()
    ).total
    num_runs = 1
    with PipelineRunContext(num_runs):
        artifacts = store.list_artifact_versions(ArtifactVersionFilter())
        assert artifacts.total == num_artifact_versions_before + num_runs * 2

        # Cleanup
        pipelines = store.list_runs(PipelineRunFilter()).items
        for p in pipelines:
            store.delete_run(p.id)

        artifacts = store.list_artifact_versions(ArtifactVersionFilter())
        assert artifacts.total == num_artifact_versions_before + num_runs * 2


# .---------.
# | Logs    |
# '---------'


def test_logs_are_recorded_properly(clean_client):
    """Tests if logs are stored in the artifact store."""
    client = Client()
    store = client.zen_store

    with PipelineRunContext(2):
        steps = store.list_run_steps(StepRunFilter())
        step1_logs = steps[0].logs
        step2_logs = steps[1].logs
        artifact_store = _load_artifact_store(
            step1_logs.artifact_store_id, store
        )
        step1_logs_content = _load_file_from_artifact_store(
            step1_logs.uri, artifact_store=artifact_store, mode="r"
        )
        step2_logs_content = _load_file_from_artifact_store(
            step2_logs.uri, artifact_store=artifact_store, mode="r"
        )

        # Step 1 has the word log! Defined in PipelineRunContext
        assert "log" in step1_logs_content

        # Step 2 does not have logs!
        assert "Step step_2 has started." in step2_logs_content


def test_logs_are_recorded_properly_when_disabled(clean_client):
    """Tests no logs are stored in the artifact store when disabled"""
    client = Client()
    store = client.zen_store

    with PipelineRunContext(2, enable_step_logs=False):
        steps = store.list_run_steps(StepRunFilter())
        step1_logs = steps[0].logs
        step2_logs = steps[1].logs
        assert not step1_logs
        assert not step2_logs

        artifact_store_id = steps[0].output.artifact_store_id
        assert artifact_store_id

        artifact_store = _load_artifact_store(artifact_store_id, store)

        logs_uri_1 = prepare_logs_uri(
            artifact_store=artifact_store,
            step_name=steps[0].name,
        )

        logs_uri_2 = prepare_logs_uri(
            artifact_store=artifact_store,
            step_name=steps[1].name,
        )

        prepare_logs_uri(
            artifact_store=artifact_store,
            step_name=steps[1].name,
        )

        with pytest.raises(DoesNotExistException):
            _load_file_from_artifact_store(
                logs_uri_1, artifact_store=artifact_store, mode="r"
            )

        with pytest.raises(DoesNotExistException):
            _load_file_from_artifact_store(
                logs_uri_2, artifact_store=artifact_store, mode="r"
            )


# .--------------------.
# | Service Connectors |
# '--------------------'


def test_connector_with_no_secrets():
    """Tests that a connector with no secrets has no attached secret."""
    client = Client()
    store = client.zen_store

    config = {
        "language": "meow",
        "foods": "tuna",
    }
    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
        resource_id="aria",
        configuration=config,
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "paw-print"
        assert connector.resource_types == ["cat"]
        assert connector.resource_id == "aria"
        assert connector.configuration == config
        assert len(connector.secrets) == 0
        assert connector.secret_id is None

        registered_connector = store.get_service_connector(connector.id)

        assert registered_connector.id == connector.id
        assert registered_connector.name == connector.name
        assert registered_connector.type == connector.type
        assert registered_connector.auth_method == connector.auth_method
        assert registered_connector.resource_types == connector.resource_types
        assert registered_connector.configuration == config
        assert len(registered_connector.secrets) == 0
        assert registered_connector.secret_id is None


def test_connector_with_secrets():
    """Tests that a connector with secrets has an attached secret."""
    client = Client()
    store = client.zen_store

    config = {
        "language": "meow",
        "foods": "tuna",
    }
    secrets = {
        "hiding-place": SecretStr("thatsformetoknowandyouneverfindout"),
        "dreams": SecretStr("notyourbusiness"),
    }
    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
        resource_id="blupus",
        configuration=config,
        secrets=secrets,
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "paw-print"
        assert connector.resource_types == ["cat"]
        assert connector.resource_id == "blupus"
        assert connector.configuration == config
        assert len(connector.secrets) == 0
        assert connector.secret_id is not None

        secret = store.get_secret(connector.secret_id)
        assert secret.id == connector.secret_id
        assert secret.name.startswith(f"connector-{connector.name}")
        assert secret.values == secrets

        registered_connector = store.get_service_connector(connector.id)

        assert registered_connector.id == connector.id
        assert registered_connector.name == connector.name
        assert registered_connector.type == connector.type
        assert registered_connector.auth_method == connector.auth_method
        assert registered_connector.resource_types == connector.resource_types
        assert registered_connector.configuration == config
        assert len(registered_connector.secrets) == 0
        assert registered_connector.secret_id == connector.secret_id


def test_connector_with_no_config_no_secrets():
    """Tests that a connector with no config and no secrets is possible."""
    client = Client()
    store = client.zen_store

    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="whiskers",
        resource_types=["spacecat"],
        resource_id="axl",
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "whiskers"
        assert connector.resource_types == ["spacecat"]
        assert connector.resource_id == "axl"
        assert len(connector.configuration) == 0
        assert len(connector.secrets) == 0
        assert connector.secret_id is None

        registered_connector = store.get_service_connector(connector.id)

        assert registered_connector.id == connector.id
        assert registered_connector.name == connector.name
        assert registered_connector.type == connector.type
        assert registered_connector.auth_method == connector.auth_method
        assert registered_connector.resource_types == connector.resource_types
        assert len(connector.configuration) == 0
        assert len(registered_connector.secrets) == 0
        assert registered_connector.secret_id is None


def test_connector_with_labels():
    """Tests that a connector with labels is possible."""
    client = Client()
    store = client.zen_store

    config = {
        "language": "meow",
        "foods": "tuna",
    }
    secrets = {
        "hiding-place": SecretStr("thatsformetoknowandyouneverfindout"),
        "dreams": SecretStr("notyourbusiness"),
    }
    labels = {
        "whereabouts": "unknown",
        "age": "eternal",
    }
    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="tail-print",
        resource_types=["cat"],
        resource_id="aria",
        configuration=config,
        secrets=secrets,
        labels=labels,
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "tail-print"
        assert connector.resource_types == ["cat"]
        assert connector.resource_id == "aria"
        assert connector.configuration == config
        assert len(connector.secrets) == 0
        assert connector.secret_id is not None
        assert connector.labels == labels

        secret = store.get_secret(connector.secret_id)
        assert secret.id == connector.secret_id
        assert secret.name.startswith(f"connector-{connector.name}")
        assert secret.values == secrets

        registered_connector = store.get_service_connector(connector.id)

        assert registered_connector.id == connector.id
        assert registered_connector.name == connector.name
        assert registered_connector.type == connector.type
        assert registered_connector.auth_method == connector.auth_method
        assert registered_connector.resource_types == connector.resource_types
        assert registered_connector.configuration == config
        assert len(registered_connector.secrets) == 0
        assert registered_connector.secret_id == connector.secret_id
        assert registered_connector.labels == labels


def test_connector_secret_share_lifespan():
    """Tests that a connector's secret shares its lifespan."""
    client = Client()
    store = client.zen_store

    config = {
        "language": "meow",
        "foods": "tuna",
    }
    secrets = {
        "hiding-place": SecretStr("thatsformetoknowandyouneverfindout"),
        "dreams": SecretStr("notyourbusiness"),
    }
    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
        resource_id="blupus",
        configuration=config,
        secrets=secrets,
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "paw-print"
        assert connector.resource_types == ["cat"]
        assert connector.resource_id == "blupus"
        assert connector.configuration == config
        assert len(connector.secrets) == 0
        assert connector.secret_id is not None

        secret = store.get_secret(connector.secret_id)
        assert secret.id == connector.secret_id
        assert secret.name.startswith(f"connector-{connector.name}")
        assert secret.values == secrets

        store.delete_service_connector(connector.id)

        with pytest.raises(KeyError):
            store.get_service_connector(connector.id)

        with pytest.raises(KeyError):
            store.get_secret(connector.secret_id)


def test_connector_name_reuse_for_same_user_fails():
    """Tests that a connector's name cannot be re-used for the same user."""

    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
    ) as connector_one:
        with pytest.raises(EntityExistsError):
            with ServiceConnectorContext(
                name=connector_one.name,
                connector_type="cat'o'matic",
                auth_method="paw-print",
                resource_types=["cat"],
            ):
                pass


def test_connector_name_reuse_for_different_user_fails():
    """Tests that a connector's name cannot be re-used by another user."""
    if Client().zen_store.type == StoreType.SQL:
        pytest.skip("SQL Zen Stores do not support user switching.")

    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
    ) as connector_one:
        with UserContext(login=True):
            #  Client() needs to be instantiated here with the new
            #  logged-in user
            other_client = Client()

            with pytest.raises(EntityExistsError):
                with ServiceConnectorContext(
                    name=connector_one.name,
                    connector_type="cat'o'matic",
                    auth_method="paw-print",
                    resource_types=["cat"],
                    client=other_client,
                ):
                    pass


def test_connector_list():
    """Tests connector listing and filtering."""
    client = Client()
    store = client.zen_store

    config1 = {
        "language": "meow",
        "foods": "tuna",
    }
    secrets1 = {
        "hiding-place": SecretStr("thatsformetoknowandyouneverfindout"),
        "dreams": SecretStr("notyourbusiness"),
    }
    labels1 = {
        "whereabouts": "unknown",
        "age": "eternal",
    }
    config2 = {
        "language": "beast",
        "foods": "everything",
    }
    secrets2 = {
        "hiding-place": SecretStr("someplaceyouwillneverfindme"),
        "dreams": SecretStr("milkandmiceandeverythingnice"),
    }
    labels2 = {
        "whereabouts": "everywhere",
        "weight": "ethereal",
    }
    config3 = {
        "language": "mousespeech",
        "foods": "cheese",
    }
    secrets3 = {
        "hiding-place": SecretStr("underthebed"),
        "dreams": SecretStr("cheesecheesecheese"),
    }
    labels3 = {
        "whereabouts": "unknown",
        "nick": "rodent",
    }

    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
        resource_id="aria",
        configuration=config1,
        secrets=secrets1,
        labels=labels1,
    ) as aria_connector:
        with ServiceConnectorContext(
            connector_type="tail'o'matic",
            auth_method="tail-print",
            resource_types=["cat", "mouse"],
            configuration=config2,
            secrets=secrets2,
            labels=labels2,
        ) as multi_connector:
            with ServiceConnectorContext(
                connector_type="tail'o'matic",
                auth_method="tail-print",
                resource_types=["mouse"],
                resource_id="bartholomew",
                configuration=config3,
                secrets=secrets3,
                labels=labels3,
            ) as rodent_connector:
                # List all connectors
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter()
                ).items
                assert len(connectors) >= 3
                assert aria_connector in connectors
                assert multi_connector in connectors
                assert rodent_connector in connectors

                # Filter by name
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(name=aria_connector.name)
                ).items
                assert len(connectors) == 1
                assert aria_connector.id == connectors[0].id

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(name=multi_connector.name)
                ).items
                assert len(connectors) == 1
                assert multi_connector.id == connectors[0].id

                # Filter by connector type
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(connector_type="cat'o'matic")
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id not in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(connector_type="tail'o'matic")
                ).items
                assert len(connectors) >= 2
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                # Filter by auth method
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(auth_method="paw-print")
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id not in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(auth_method="tail-print")
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                # Filter by resource type
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(resource_type="cat")
                ).items
                assert len(connectors) >= 2
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id not in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(resource_type="mouse")
                ).items
                assert len(connectors) >= 2
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                # Filter by resource id
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(
                        resource_type="cat",
                        resource_id="aria",
                    )
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id not in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(
                        resource_type="mouse",
                        resource_id="bartholomew",
                    )
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                # Filter by labels
                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(labels={"whereabouts": "unknown"})
                ).items
                assert len(connectors) >= 2
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(labels={"whereabouts": None})
                ).items
                assert len(connectors) >= 3
                assert aria_connector.id in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(
                        labels={"nick": "rodent", "whereabouts": "unknown"}
                    )
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id not in [c.id for c in connectors]
                assert rodent_connector.id in [c.id for c in connectors]

                connectors = store.list_service_connectors(
                    ServiceConnectorFilter(
                        labels={"weight": None, "whereabouts": None}
                    )
                ).items
                assert len(connectors) >= 1
                assert aria_connector.id not in [c.id for c in connectors]
                assert multi_connector.id in [c.id for c in connectors]
                assert rodent_connector.id not in [c.id for c in connectors]


def _update_connector_and_test(
    new_name: Optional[str] = None,
    new_connector_type: Optional[str] = None,
    new_auth_method: Optional[str] = None,
    new_resource_types: Optional[List[str]] = None,
    new_resource_id_or_not: Optional[Tuple[Optional[str]]] = None,
    new_config: Optional[Dict[str, str]] = None,
    new_secrets: Optional[Dict[str, Optional[SecretStr]]] = None,
    new_expires_at: Optional[datetime] = None,
    new_expiration_seconds_or_not: Optional[Tuple[Optional[int]]] = None,
    new_labels: Optional[Dict[str, str]] = None,
):
    """Helper function to update a connector and test that the update was successful."""
    client = Client()
    store = client.zen_store

    config = {
        "language": "meow",
        "foods": "tuna",
    }
    secrets = {
        "hiding-place": SecretStr("thatsformetoknowandyouneverfindout"),
        "dreams": SecretStr("notyourbusiness"),
    }
    labels = {
        "whereabouts": "unknown",
        "age": "eternal",
    }
    now = datetime.utcnow()
    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
        resource_id="blupus",
        configuration=config,
        secrets=secrets,
        expires_at=now,
        expiration_seconds=60,
        labels=labels,
    ) as connector:
        assert connector.id is not None
        assert connector.type == "cat'o'matic"
        assert connector.auth_method == "paw-print"
        assert connector.resource_types == ["cat"]
        assert connector.resource_id == "blupus"
        assert connector.configuration == config
        assert len(connector.secrets) == 0
        assert connector.secret_id is not None
        assert connector.labels == labels

        secret = store.get_secret(connector.secret_id)
        assert secret.id == connector.secret_id
        assert secret.name.startswith(f"connector-{connector.name}")
        assert secret.values == secrets

        # Update the connector
        # NOTE: we need to pass the `resource_id` and `expiration_seconds`
        # fields in the update model, otherwise the update will remove them
        # from the connector.
        new_resource_id = (
            new_resource_id_or_not[0]
            if new_resource_id_or_not
            else connector.resource_id
        )
        new_expiration_seconds = (
            new_expiration_seconds_or_not[0]
            if new_expiration_seconds_or_not
            else connector.expiration_seconds
        )
        store.update_service_connector(
            connector.id,
            update=ServiceConnectorUpdate(
                name=new_name,
                connector_type=new_connector_type,
                auth_method=new_auth_method,
                resource_types=new_resource_types,
                resource_id=new_resource_id,
                configuration=new_config,
                secrets=new_secrets,
                expires_at=new_expires_at,
                expiration_seconds=new_expiration_seconds,
                labels=new_labels,
            ),
        )

        # Check that the connector has been updated
        registered_connector = store.get_service_connector(connector.id)

        assert registered_connector.id == connector.id
        assert registered_connector.name == new_name or connector.name
        assert (
            registered_connector.type == new_connector_type or connector.type
        )
        assert (
            registered_connector.auth_method == new_auth_method
            or connector.auth_method
        )
        assert (
            registered_connector.resource_types == new_resource_types
            or connector.resource_types
        )
        assert registered_connector.resource_id == new_resource_id
        assert len(registered_connector.secrets) == 0

        # the `configuration` and `secrets` fields represent a full
        # valid configuration update, not just a partial update. If either is
        # set (i.e. not None) in the update, their values
        # will replace the existing configuration and secrets values.

        if new_config is not None:
            assert registered_connector.configuration == new_config or {}
        else:
            assert (
                registered_connector.configuration == connector.configuration
            )

        if new_secrets is not None:
            if not new_secrets:
                # Existing secret is deleted if no new secrets are provided
                assert registered_connector.secret_id is None
            else:
                # New secret is created if secrets are updated
                assert registered_connector.secret_id != connector.secret_id
        else:
            assert registered_connector.secret_id == connector.secret_id

        assert registered_connector.labels == new_labels or connector.labels

        if new_secrets is not None:
            if not new_secrets:
                # Existing secret is deleted if secrets are removed
                with pytest.raises(KeyError):
                    store.get_secret(connector.secret_id)
            else:
                # Previous secret is deleted if secrets are updated
                with pytest.raises(KeyError):
                    store.get_secret(connector.secret_id)

                # Check that a new secret has been created
                new_secret = store.get_secret(registered_connector.secret_id)
                assert new_secret.id == registered_connector.secret_id
                # Secret name should have changed
                assert new_secret.name.startswith(
                    f"connector-{new_name or connector.name}"
                )
                assert new_secret.values == new_secrets
        else:
            new_secret = store.get_secret(connector.secret_id)
            assert new_secret.id == connector.secret_id
            # Secret name should not have changed
            assert new_secret.name == secret.name
            assert new_secret.values == secrets


def test_connector_update_name():
    """Tests that a connector's name can be updated."""
    _update_connector_and_test(
        new_name="axl-incognito",
    )


def test_connector_update_type():
    """Tests that a connector's type can be updated."""
    _update_connector_and_test(
        new_connector_type="dog'o'matic",
    )


def test_connector_update_resource_types():
    """Tests that a connector's resource types can be updated."""
    _update_connector_and_test(new_resource_types=["cat", "dog"])


def test_connector_update_resource_id():
    """Tests that a connector's resource ID can be updated or removed."""
    _update_connector_and_test(new_resource_id_or_not=("axl",))
    _update_connector_and_test(new_resource_id_or_not=(None,))


def test_connector_update_auth_method():
    """Tests that a connector's auth method can be updated."""
    _update_connector_and_test(
        new_auth_method="collar",
    )


def test_connector_update_config():
    """Tests that a connector's configuration and secrets can be updated."""

    new_config = {
        "language": "purr",
        "chase": "own-tail",
    }
    new_secrets = {
        "hiding-place": SecretStr("anotherplaceyouwillneverfindme"),
        "food": SecretStr("firebreathingdragon"),
    }

    _update_connector_and_test(
        new_config=new_config,
    )
    _update_connector_and_test(
        new_secrets=new_secrets,
    )
    _update_connector_and_test(
        new_config=new_config,
        new_secrets=new_secrets,
    )
    _update_connector_and_test(
        new_config={},
    )
    _update_connector_and_test(
        new_secrets={},
    )


def test_connector_update_expiration():
    """Tests that a connector's expiration period can be updated or removed."""
    _update_connector_and_test(new_expiration_seconds_or_not=(90,))
    _update_connector_and_test(new_expiration_seconds_or_not=(None,))


def test_connector_update_expires_at():
    """Tests that a connector's expiration date can be updated."""
    _update_connector_and_test(new_expires_at=datetime.now())


def test_connector_update_labels():
    """Tests that a connector's labels can be updated."""
    labels = {
        "whereabouts": "everywhere",
        "form": "fluid",
    }
    _update_connector_and_test(new_labels=labels)
    _update_connector_and_test(new_labels={})


def test_connector_name_update_fails_if_exists():
    """Tests that a connector's name cannot be updated to an existing name."""

    client = Client()
    store = client.zen_store

    with ServiceConnectorContext(
        connector_type="cat'o'matic",
        auth_method="paw-print",
        resource_types=["cat"],
    ) as connector_one:
        with ServiceConnectorContext(
            connector_type="cat'o'matic",
            auth_method="paw-print",
            resource_types=["cat"],
        ) as connector_two:
            with pytest.raises(EntityExistsError):
                store.update_service_connector(
                    connector_one.id,
                    update=ServiceConnectorUpdate(name=connector_two.name),
                )


# .-------------------------.
# | Service Connector Types |
# '-------------------------'


def test_connector_type_register():
    """Tests that a connector type can be registered locally."""

    client = Client()
    store = client.zen_store

    connector_type = sample_name("cat'o'matic")
    resource_type_one = sample_name("scratch")
    resource_type_two = sample_name("purr")

    with pytest.raises(KeyError):
        store.get_service_connector_type(connector_type)
    assert (
        store.list_service_connector_types(connector_type=connector_type) == []
    )
    assert (
        store.list_service_connector_types(resource_type=resource_type_one)
        == []
    )
    assert (
        store.list_service_connector_types(resource_type=resource_type_two)
        == []
    )

    with ServiceConnectorTypeContext(
        connector_type=connector_type,
        resource_type_one=resource_type_one,
        resource_type_two=resource_type_two,
    ) as connector_type_spec:
        assert (
            store.get_service_connector_type(connector_type)
            == connector_type_spec
        )
        assert store.list_service_connector_types(
            resource_type=resource_type_one
        ) == [connector_type_spec]
        assert store.list_service_connector_types(
            resource_type=resource_type_two
        ) == [connector_type_spec]


def test_connector_validation():
    """Tests that a connector type is used to validate a connector."""

    client = Client()
    store = client.zen_store

    if store.type != StoreType.SQL:
        pytest.skip("Only applicable to SQL store")

    connector_type = sample_name("cat'o'matic")
    resource_type_one = sample_name("scratch")
    resource_type_two = sample_name("purr")

    with ServiceConnectorTypeContext(
        connector_type=connector_type,
        resource_type_one=resource_type_one,
        resource_type_two=resource_type_two,
    ):
        # All attributes
        config = {
            "color": "pink",
            "name": "aria",
        }
        secrets = {
            "hiding_spot": SecretStr("thatsformetoknowandyouneverfindout"),
            "secret_word": SecretStr("meowmeowmeow"),
        }
        with ServiceConnectorContext(
            connector_type=connector_type,
            auth_method="voice-print",
            resource_types=[resource_type_one, resource_type_two],
            configuration=config,
            secrets=secrets,
        ) as connector:
            assert connector.configuration == config
            assert connector.secrets == {}
            assert connector.secret_id is not None
            secret = store.get_secret(connector.secret_id)
            assert secret.values == secrets

        # Only required attributes
        config = {
            "name": "aria",
        }
        secrets = {
            "secret_word": SecretStr("meowmeowmeow"),
        }
        with ServiceConnectorContext(
            connector_type=connector_type,
            auth_method="voice-print",
            resource_types=[resource_type_one, resource_type_two],
            configuration=config,
            secrets=secrets,
        ) as connector:
            assert connector.configuration == config
            assert connector.secrets == {}
            assert connector.secret_id is not None
            secret = store.get_secret(connector.secret_id)
            assert secret.values == secrets

        # Missing required configuration attribute
        config = {}
        secrets = {
            "secret_word": SecretStr("meowmeowmeow"),
        }
        with pytest.raises(ValueError):
            with ServiceConnectorContext(
                connector_type=connector_type,
                auth_method="voice-print",
                resource_types=[resource_type_one, resource_type_two],
                configuration=config,
                secrets=secrets,
            ):
                pass

        # Missing required secret attribute
        config = {
            "name": "aria",
        }
        secrets = {}
        with pytest.raises(ValueError):
            with ServiceConnectorContext(
                connector_type=connector_type,
                auth_method="voice-print",
                resource_types=[resource_type_one, resource_type_two],
                configuration=config,
                secrets=secrets,
            ):
                pass

        # All attributes mashed together
        config = {
            "color": "pink",
            "name": "aria",
        }
        secrets = {
            "hiding_spot": SecretStr("thatsformetoknowandyouneverfindout"),
            "secret_word": SecretStr("meowmeowmeow"),
        }
        full_config = config.copy()
        full_config.update(
            {k: v.get_secret_value() for k, v in secrets.items()}
        )
        with ServiceConnectorContext(
            connector_type=connector_type,
            auth_method="voice-print",
            resource_types=[resource_type_one, resource_type_two],
            configuration=full_config,
        ) as connector:
            assert connector.configuration == config
            assert connector.secrets == {}
            assert connector.secret_id is not None
            secret = store.get_secret(connector.secret_id)
            assert secret.values == secrets

        # Different auth method
        with pytest.raises(ValueError):
            with ServiceConnectorContext(
                connector_type=connector_type,
                auth_method="claw-marks",
                resource_types=[resource_type_one, resource_type_two],
                configuration=config,
                secrets=secrets,
            ):
                pass

        # Wrong auth method
        with pytest.raises(ValueError):
            with ServiceConnectorContext(
                connector_type=connector_type,
                auth_method="paw-print",
                resource_types=[resource_type_one, resource_type_two],
                configuration=config,
                secrets=secrets,
            ):
                pass

        # Single type
        with ServiceConnectorContext(
            connector_type=connector_type,
            auth_method="voice-print",
            resource_types=[resource_type_one],
            configuration=config,
            secrets=secrets,
        ):
            pass

        # Wrong resource type
        with pytest.raises(ValueError):
            with ServiceConnectorContext(
                connector_type=connector_type,
                auth_method="voice-print",
                resource_types=["purr"],
                configuration=config,
                secrets=secrets,
            ):
                pass

        # Single instance
        with ServiceConnectorContext(
            connector_type=connector_type,
            auth_method="voice-print",
            resource_types=[resource_type_one],
            resource_id="aria",
            configuration=config,
            secrets=secrets,
        ):
            pass


#################
# Models
#################


class TestModel:
    def test_latest_version_properly_fetched(self):
        """Test that latest version can be properly fetched."""
        with ModelVersionContext() as created_model:
            zs = Client().zen_store
            assert zs.get_model(created_model.id).latest_version is None
            for name in ["great one", "yet another one"]:
                mv = zs.create_model_version(
                    ModelVersionRequest(
                        user=created_model.user.id,
                        workspace=created_model.workspace.id,
                        model=created_model.id,
                        name=name,
                    )
                )
                assert zs.get_model(created_model.id).latest_version == mv.name
                time.sleep(1)  # thanks to MySQL again!


class TestModelVersion:
    def test_create_pass(self):
        """Test that vanilla creation pass."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )

    def test_create_duplicated(self):
        """Test that duplicated creation fails."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            with pytest.raises(EntityExistsError):
                zs.create_model_version(
                    ModelVersionRequest(
                        user=model.user.id,
                        workspace=model.workspace.id,
                        model=model.id,
                        name="great one",
                    )
                )

    def test_create_no_model(self):
        """Test that model relation in DB works."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.create_model_version(
                    ModelVersionRequest(
                        user=model.user.id,
                        workspace=model.workspace.id,
                        model=uuid4(),
                        name="great one",
                    )
                )

    def test_get_not_found(self):
        """Test that get fails if not found."""
        with ModelVersionContext():
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.get_model_version(
                    model_version_id=uuid4(),
                )

    def test_get_found(self):
        """Test that get works, if model version exists."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            mv2 = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(
                    name="great one"
                ),
            ).items[0]
            assert mv1.id == mv2.id

    def test_list_empty(self):
        """Test list without any versions."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mvs = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(),
            )
            assert len(mvs) == 0

    def test_list_not_empty(self):
        """Test list with some versions."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            mv2 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="and yet another one",
                )
            )
            mvs = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(),
            )
            assert len(mvs) == 2
            assert mv1 in mvs
            assert mv2 in mvs

    def test_delete_not_found(self):
        """Test that delete fails if not found."""
        with ModelVersionContext():
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.delete_model_version(
                    model_version_id=uuid4(),
                )

    def test_delete_found(self):
        """Test that delete works, if model version exists."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            zs.delete_model_version(
                model_version_id=mv.id,
            )
            mvl = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(
                    name="great one"
                ),
            ).items
            assert len(mvl) == 0

    def test_update_not_found(self):
        """Test that update fails if not found."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.update_model_version(
                    model_version_id=uuid4(),
                    model_version_update_model=ModelVersionUpdate(
                        model=model.id,
                        stage="staging",
                        force=False,
                    ),
                )

    def test_update_not_forced(self):
        """Test that update fails if not forced on existing stage version."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            mv2 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="yet another one",
                )
            )
            zs.update_model_version(
                model_version_id=mv1.id,
                model_version_update_model=ModelVersionUpdate(
                    model=model.id,
                    stage="staging",
                    force=False,
                ),
            )
            mv2 = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(stage="staging"),
            ).items[0]
            assert mv1.id == mv2.id
            mv3 = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(
                    stage=ModelStages.STAGING
                ),
            ).items[0]
            assert mv1.id == mv3.id

    def test_in_stage_not_found(self):
        """Test that get in stage fails if not found."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )

            mvl = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(
                    stage=ModelStages.STAGING
                ),
            ).items

            assert len(mvl) == 0

    def test_latest_found(self):
        """Test that get latest works, if model version exists."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            time.sleep(1)  # thanks to MySQL way of storing datetimes
            latest = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="yet another one",
                )
            )
            found_latest = Client().get_model_version(
                model_name_or_id=model.id
            )
            assert latest.id == found_latest.id

    def test_update_forced(self):
        """Test that update works, if model version in stage exists and force=True."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            mv2 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="yet another one",
                )
            )
            zs.update_model_version(
                model_version_id=mv1.id,
                model_version_update_model=ModelVersionUpdate(
                    model=model.id,
                    stage="staging",
                    force=False,
                ),
            )
            assert (
                zs.get_model_version(
                    model_version_id=mv1.id,
                ).stage
                == "staging"
            )
            zs.update_model_version(
                model_version_id=mv2.id,
                model_version_update_model=ModelVersionUpdate(
                    model=model.id,
                    stage="staging",
                    force=True,
                    name="I changed that...",
                ),
            )

            assert (
                zs.get_model_version(
                    model_version_id=mv1.id,
                ).stage
                == "archived"
            )
            assert (
                zs.get_model_version(
                    model_version_id=mv2.id,
                ).stage
                == "staging"
            )
            assert (
                zs.get_model_version(
                    model_version_id=mv2.id,
                ).name
                == "I changed that..."
            )

    def test_update_public_interface(self):
        """Test that update works via public interface."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                )
            )

            assert mv1.stage is None
            mv1.set_stage("staging")
            assert (
                zs.get_model_version(
                    model_version_id=mv1.id,
                ).stage
                == "staging"
            )

            assert (
                zs.get_model_version(
                    model_version_id=mv1.id,
                ).name
                == "1"
            )

    def test_update_public_interface_bad_stage(self):
        """Test that update fails via public interface on bad stage value."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            mv1 = zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )

            with pytest.raises(ValueError):
                mv1.set_stage("my_super_stage")

    def test_model_bad_stage(self):
        """Test that update fails on bad stage value."""
        with pytest.raises(ValueError):
            ModelVersionUpdate(model=uuid4(), stage="my_super_stage")

    def test_model_ok_stage(self):
        """Test that update works on valid stage value."""
        mvum = ModelVersionUpdate(model=uuid4(), stage="staging")
        assert mvum.stage == "staging"

    def test_increments_version_number(self):
        """Test that increment version number works on sequential insertions."""
        with ModelVersionContext() as model:
            zs = Client().zen_store
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great one",
                )
            )
            time.sleep(1)  # thanks MySQL again!
            zs.create_model_version(
                ModelVersionRequest(
                    user=model.user.id,
                    workspace=model.workspace.id,
                    model=model.id,
                    name="great second",
                )
            )

            model_versions = zs.list_model_versions(
                model_name_or_id=model.id,
                model_version_filter_model=ModelVersionFilter(),
            )
            assert len(model_versions) == 2
            assert model_versions[0].name == "great one"
            assert model_versions[1].name == "great second"
            assert model_versions[0].number == 1
            assert model_versions[1].number == 2

    def test_get_found_by_number(self):
        """Test that get works by integer version number."""
        with ModelVersionContext(create_version=True) as model_version:
            zs = Client().zen_store
            found = zs.list_model_versions(
                model_name_or_id=model_version.model.id,
                model_version_filter_model=ModelVersionFilter(number=1),
            ).items[0]
            assert found.id == model_version.id
            assert found.number == 1
            assert found.name == model_version.name

    def test_get_not_found_by_number(self):
        """Test that get fails by integer version number, if not found and by string version number, cause treated as name."""
        with ModelVersionContext(create_version=True) as model_version:
            zs = Client().zen_store

            found = zs.list_model_versions(
                model_name_or_id=model_version.model.id,
                model_version_filter_model=ModelVersionFilter(number=2),
            ).items

            assert len(found) == 0


class TestModelVersionArtifactLinks:
    def test_link_create_pass(self):
        with ModelVersionContext(True, create_artifacts=1) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )

    def test_link_create_versioned(self):
        with ModelVersionContext(True, create_artifacts=2) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            al1 = zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )
            assert al1.artifact_version.id == artifacts[0].id
            al2 = zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[1].id,
                )
            )
            assert al2.artifact_version.id == artifacts[1].id

    def test_link_create_duplicated_by_id(self):
        """Assert that creating a link with the same artifact returns the same link."""
        with ModelVersionContext(True, create_artifacts=1) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            link1 = zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )

            link2 = zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )

            assert link1.id == link2.id

    def test_link_create_single_version_of_same_output_name_from_different_steps(
        self,
    ):
        with ModelVersionContext(True, create_artifacts=2) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )
            zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[1].id,
                )
            )

            links = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(links) == 2

    def test_link_delete_found(self):
        with ModelVersionContext(True, create_artifacts=1) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            link = zs.create_model_version_artifact_link(
                ModelVersionArtifactRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    artifact_version=artifacts[0].id,
                )
            )
            zs.delete_model_version_artifact_link(
                model_version_id=model_version.id,
                model_version_artifact_link_name_or_id=link.id,
            )
            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0

    def test_link_delete_not_found(self):
        with ModelVersionContext(True) as model_version:
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.delete_model_version_artifact_link(
                    model_version_id=model_version.id,
                    model_version_artifact_link_name_or_id="link",
                )

    def test_link_list_empty(self):
        with ModelVersionContext(True) as model_version:
            zs = Client().zen_store
            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0

    def test_link_list_populated(self):
        with ModelVersionContext(True, create_artifacts=4) as (
            model_version,
            artifacts,
        ):
            zs = Client().zen_store
            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0
            for mo, dep, artifact in [
                (False, False, artifacts[0]),
                (True, False, artifacts[1]),
                (False, True, artifacts[2]),
                (False, False, artifacts[3]),
            ]:
                zs.create_model_version_artifact_link(
                    ModelVersionArtifactRequest(
                        user=model_version.user.id,
                        workspace=model_version.workspace.id,
                        model=model_version.model.id,
                        model_version=model_version.id,
                        artifact_version=artifact.id,
                        is_model_artifact=mo,
                        is_deployment_artifact=dep,
                    )
                )
            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == len(artifacts)

            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id, only_data_artifacts=True
                ),
            )
            assert len(mvls) == 2

            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id,
                    only_model_artifacts=True,
                ),
            )
            assert len(mvls) == 1

            mvls = zs.list_model_version_artifact_links(
                model_version_artifact_link_filter_model=ModelVersionArtifactFilter(
                    model_version_id=model_version.id,
                    only_deployment_artifacts=True,
                ),
            )
            assert len(mvls) == 1

            mv = zs.get_model_version(
                model_version_id=model_version.id,
            )

            assert len(mv.model_artifact_ids) == 1
            assert len(mv.data_artifact_ids) == 2
            assert len(mv.deployment_artifact_ids) == 1

            assert isinstance(
                mv.get_model_artifact(artifacts[1].name),
                ArtifactVersionResponse,
            )
            assert isinstance(
                mv.get_data_artifact(artifacts[0].name),
                ArtifactVersionResponse,
            )
            assert isinstance(
                mv.get_deployment_artifact(artifacts[2].name),
                ArtifactVersionResponse,
            )
            assert (
                mv.model_artifacts[artifacts[1].name]["1"].id
                == artifacts[1].id
            )
            assert (
                mv.get_model_artifact(artifacts[1].name, "1")
                == mv.model_artifacts[artifacts[1].name]["1"]
            )
            assert (
                mv.get_deployment_artifact(artifacts[2].name, "1")
                == mv.endpoint_artifacts[artifacts[2].name]["1"]
            )


class TestModelVersionPipelineRunLinks:
    def test_link_create_pass(self):
        with ModelVersionContext(True, create_prs=1) as (
            model_version,
            prs,
        ):
            zs = Client().zen_store
            zs.create_model_version_pipeline_run_link(
                ModelVersionPipelineRunRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    pipeline_run=prs[0].id,
                )
            )

    def test_link_create_duplicated(self):
        """Assert that creating a link with the same run returns the same link."""
        with ModelVersionContext(True, create_prs=1) as (
            model_version,
            prs,
        ):
            zs = Client().zen_store
            link_1 = zs.create_model_version_pipeline_run_link(
                ModelVersionPipelineRunRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    pipeline_run=prs[0].id,
                )
            )
            link_2 = zs.create_model_version_pipeline_run_link(
                ModelVersionPipelineRunRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    pipeline_run=prs[0].id,
                )
            )
            assert link_1.id == link_2.id

    def test_link_delete_found(self):
        with ModelVersionContext(True, create_prs=1) as (
            model_version,
            prs,
        ):
            zs = Client().zen_store
            link = zs.create_model_version_pipeline_run_link(
                ModelVersionPipelineRunRequest(
                    user=model_version.user.id,
                    workspace=model_version.workspace.id,
                    model=model_version.model.id,
                    model_version=model_version.id,
                    name="link",
                    pipeline_run=prs[0].id,
                )
            )
            zs.delete_model_version_pipeline_run_link(
                model_version.id,
                link.id,
            )
            mvls = zs.list_model_version_pipeline_run_links(
                model_version_pipeline_run_link_filter_model=ModelVersionPipelineRunFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0

    def test_link_delete_not_found(self):
        with ModelVersionContext(True) as model_version:
            zs = Client().zen_store
            with pytest.raises(KeyError):
                zs.delete_model_version_pipeline_run_link(
                    model_version.id, "link"
                )

    def test_link_list_empty(self):
        with ModelVersionContext(True) as model_version:
            zs = Client().zen_store
            mvls = zs.list_model_version_pipeline_run_links(
                model_version_pipeline_run_link_filter_model=ModelVersionPipelineRunFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0

    def test_link_list_populated(self):
        with ModelVersionContext(True, create_prs=2) as (
            model_version,
            prs,
        ):
            zs = Client().zen_store
            mvls = zs.list_model_version_pipeline_run_links(
                model_version_pipeline_run_link_filter_model=ModelVersionPipelineRunFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 0
            for pr in prs:
                zs.create_model_version_pipeline_run_link(
                    ModelVersionPipelineRunRequest(
                        user=model_version.user.id,
                        workspace=model_version.workspace.id,
                        model=model_version.model.id,
                        model_version=model_version.id,
                        pipeline_run=pr.id,
                    )
                )
            mvls = zs.list_model_version_pipeline_run_links(
                model_version_pipeline_run_link_filter_model=ModelVersionPipelineRunFilter(
                    model_version_id=model_version.id
                ),
            )
            assert len(mvls) == 2

            mv = zs.get_model_version(
                model_version_id=model_version.id,
            )

            assert len(mv.pipeline_run_ids) == 2

            assert isinstance(
                mv.pipeline_runs[prs[0].name],
                PipelineRunResponse,
            )
            assert isinstance(
                mv.pipeline_runs[prs[1].name],
                PipelineRunResponse,
            )

            assert mv.pipeline_runs[prs[0].name].id == prs[0].id
            assert mv.pipeline_runs[prs[1].name].id == prs[1].id

            assert (
                mv.get_pipeline_run(prs[0].name)
                == mv.pipeline_runs[prs[0].name]
            )
            assert (
                mv.get_pipeline_run(prs[1].name)
                == mv.pipeline_runs[prs[1].name]
            )


class TestTag:
    def test_create_pass(self, clean_client: "Client"):
        """Tests that tag creation passes."""
        tag = clean_client.create_tag(TagRequestModel(name="foo"))
        assert tag.name == "foo"
        assert tag.color is not None
        tag = clean_client.create_tag(
            TagRequestModel(name="bar", color="yellow")
        )
        assert tag.name == "bar"
        assert tag.color == ColorVariants.YELLOW.name.lower()
        with pytest.raises(ValueError):
            clean_client.create_tag(TagRequestModel(color="yellow"))

    def test_create_bad_input(self, clean_client: "Client"):
        """Tests that tag creation fails without a name."""
        with pytest.raises(ValueError):
            clean_client.create_tag(TagRequestModel(color="yellow"))

    def test_create_duplicate(self, clean_client: "Client"):
        """Tests that tag creation fails on duplicate."""
        clean_client.create_tag(TagRequestModel(name="foo"))
        with pytest.raises(EntityExistsError):
            clean_client.create_tag(
                TagRequestModel(name="foo", color="yellow")
            )

    def test_get_tag_found(self, clean_client: "Client"):
        """Tests that tag get pass if found."""
        clean_client.create_tag(TagRequestModel(name="foo"))
        tag = clean_client.get_tag("foo")
        assert tag.name == "foo"
        assert tag.color is not None

    def test_get_tag_not_found(self, clean_client: "Client"):
        """Tests that tag get fails if not found."""
        with pytest.raises(KeyError):
            clean_client.get_tag("foo")

    def test_list_tags(self, clean_client: "Client"):
        """Tests various list scenarios."""
        tags = clean_client.list_tags(TagFilterModel())
        assert len(tags) == 0
        clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        clean_client.create_tag(TagRequestModel(name="bar", color="green"))

        tags = clean_client.list_tags(TagFilterModel())
        assert len(tags) == 2
        assert {t.name for t in tags} == {"foo", "bar"}
        assert {t.color for t in tags} == {"red", "green"}

        tags = clean_client.list_tags(TagFilterModel(name="foo"))
        assert len(tags) == 1
        assert tags[0].name == "foo"
        assert tags[0].color == "red"

        tags = clean_client.list_tags(TagFilterModel(color="green"))
        assert len(tags) == 1
        assert tags[0].name == "bar"
        assert tags[0].color == "green"

    def test_update_tag(self, clean_client: "Client"):
        """Tests various update scenarios."""
        clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        tag = clean_client.create_tag(
            TagRequestModel(name="bar", color="green")
        )

        clean_client.update_tag("foo", TagUpdateModel(name="foo2"))
        assert clean_client.get_tag("foo2").color == "red"
        with pytest.raises(KeyError):
            clean_client.get_tag("foo")

        clean_client.update_tag(tag.id, TagUpdateModel(color="yellow"))
        assert clean_client.get_tag(tag.id).color == "yellow"
        assert clean_client.get_tag("bar").color == "yellow"


class TestTagResource:
    def test_create_tag_resource_pass(self, clean_client: "Client"):
        """Tests creating tag<>resource mapping pass."""
        if clean_client.zen_store.type != StoreType.SQL:
            pytest.skip("Only SQL Zen Stores support tagging resources")
        tag = clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        mapping = clean_client.zen_store.create_tag_resource(
            TagResourceRequestModel(
                tag_id=tag.id,
                resource_id=uuid4(),
                resource_type=TaggableResourceTypes.MODEL,
            )
        )
        assert isinstance(mapping.tag_id, UUID)
        assert isinstance(mapping.resource_id, UUID)

    def test_create_tag_resource_fails_on_duplicate(
        self, clean_client: "Client"
    ):
        """Tests creating tag<>resource mapping fails on duplicate."""
        if clean_client.zen_store.type != StoreType.SQL:
            pytest.skip("Only SQL Zen Stores support tagging resources")
        tag = clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        mapping = clean_client.zen_store.create_tag_resource(
            TagResourceRequestModel(
                tag_id=tag.id,
                resource_id=uuid4(),
                resource_type=TaggableResourceTypes.MODEL,
            )
        )

        with pytest.raises(EntityExistsError):
            clean_client.zen_store.create_tag_resource(
                TagResourceRequestModel(
                    tag_id=mapping.tag_id,
                    resource_id=mapping.resource_id,
                    resource_type=TaggableResourceTypes.MODEL,
                )
            )

    def test_delete_tag_resource_pass(self, clean_client: "Client"):
        """Tests deleting tag<>resource mapping pass."""
        if clean_client.zen_store.type != StoreType.SQL:
            pytest.skip("Only SQL Zen Stores support tagging resources")
        tag = clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        resource_id = uuid4()
        clean_client.zen_store.create_tag_resource(
            TagResourceRequestModel(
                tag_id=tag.id,
                resource_id=resource_id,
                resource_type=TaggableResourceTypes.MODEL,
            )
        )
        clean_client.zen_store.delete_tag_resource(
            tag_id=tag.id,
            resource_id=resource_id,
            resource_type=TaggableResourceTypes.MODEL,
        )
        with pytest.raises(KeyError):
            clean_client.zen_store.delete_tag_resource(
                tag_id=tag.id,
                resource_id=resource_id,
                resource_type=TaggableResourceTypes.MODEL,
            )

    def test_delete_tag_resource_mismatch(self, clean_client: "Client"):
        """Tests deleting tag<>resource mapping pass."""
        if clean_client.zen_store.type != StoreType.SQL:
            pytest.skip("Only SQL Zen Stores support tagging resources")

        class MockTaggableResourceTypes(StrEnum):
            APPLE = "apple"

        tag = clean_client.create_tag(TagRequestModel(name="foo", color="red"))
        resource_id = uuid4()
        clean_client.zen_store.create_tag_resource(
            TagResourceRequestModel(
                tag_id=tag.id,
                resource_id=resource_id,
                resource_type=TaggableResourceTypes.MODEL,
            )
        )
        with pytest.raises(KeyError):
            clean_client.zen_store.delete_tag_resource(
                tag_id=tag.id,
                resource_id=resource_id,
                resource_type=MockTaggableResourceTypes.APPLE,
            )

    @pytest.mark.parametrize(
        "use_model,use_tag",
        [[True, False], [False, True]],
        ids=["delete_model", "delete_tag"],
    )
    def test_cascade_deletion(
        self, use_model, use_tag, clean_client: "Client"
    ):
        """Test that link is deleted on tag deletion."""
        if clean_client.zen_store.type != StoreType.SQL:
            pytest.skip("Only SQL Zen Stores support tagging resources")
        with ModelVersionContext() as model:
            tag = clean_client.create_tag(
                TagRequestModel(name="foo", color="red")
            )
            fake_model_id = uuid4() if not use_model else model.id
            clean_client.zen_store.create_tag_resource(
                TagResourceRequestModel(
                    tag_id=tag.id,
                    resource_id=fake_model_id,
                    resource_type=TaggableResourceTypes.MODEL,
                )
            )

            # duplicate
            with pytest.raises(EntityExistsError):
                clean_client.zen_store.create_tag_resource(
                    TagResourceRequestModel(
                        tag_id=tag.id,
                        resource_id=fake_model_id,
                        resource_type=TaggableResourceTypes.MODEL,
                    )
                )
            if use_tag:
                clean_client.delete_tag(tag.id)
                tag = clean_client.create_tag(
                    TagRequestModel(name="foo", color="red")
                )
            else:
                clean_client.delete_model(model.id)
            # should pass
            clean_client.zen_store.create_tag_resource(
                TagResourceRequestModel(
                    tag_id=tag.id,
                    resource_id=fake_model_id,
                    resource_type=TaggableResourceTypes.MODEL,
                )
            )


class TestRunMetadata:
    @pytest.mark.parametrize(
        argnames="type_",
        argvalues=MetadataResourceTypes,
        ids=MetadataResourceTypes.values(),
    )
    def test_metadata_full_cycle_with_cascade_deletion(
        self,
        type_: MetadataResourceTypes,
    ):
        client = Client()

        sc = client.zen_store.create_stack_component(
            ComponentRequest(
                user=client.active_user.id,
                workspace=client.active_workspace.id,
                name=sample_name("foo"),
                type=StackComponentType.ORCHESTRATOR,
                flavor="local",
                configuration={},
            )
        )

        if type_ == MetadataResourceTypes.ARTIFACT_VERSION:
            artifact = client.zen_store.create_artifact(
                ArtifactRequest(
                    name=sample_name("foo"),
                    has_custom_name=True,
                )
            )
            resource = client.zen_store.create_artifact_version(
                ArtifactVersionRequest(
                    artifact_id=artifact.id,
                    user=client.active_user.id,
                    workspace=client.active_workspace.id,
                    version="1",
                    type=ArtifactType.DATA,
                    uri=sample_name("foo"),
                    materializer=Source(
                        module="acme.foo", type=SourceType.INTERNAL
                    ),
                    data_type=Source(
                        module="acme.foo", type=SourceType.INTERNAL
                    ),
                )
            )
        elif type_ == MetadataResourceTypes.MODEL_VERSION:
            from zenml import ModelVersion

            model_name = sample_name("foo")
            resource = ModelVersion(
                name=model_name
            )._get_or_create_model_version()

        elif (
            type_ == MetadataResourceTypes.PIPELINE_RUN
            or type_ == MetadataResourceTypes.STEP_RUN
        ):
            step_name = sample_name("foo")
            deployment = client.zen_store.create_deployment(
                PipelineDeploymentRequest(
                    user=client.active_user.id,
                    workspace=client.active_workspace.id,
                    run_name_template=sample_name("foo"),
                    pipeline_configuration=PipelineConfiguration(
                        name=sample_name("foo")
                    ),
                    stack=client.active_stack.id,
                    client_version="0.1.0",
                    server_version="0.1.0",
                    step_configurations={
                        step_name: Step(
                            spec=StepSpec(
                                source=Source(
                                    module="acme.foo",
                                    type=SourceType.INTERNAL,
                                ),
                                upstream_steps=[],
                            ),
                            config=StepConfiguration(name=step_name),
                        )
                    },
                )
            )
            pr = client.zen_store.create_run(
                PipelineRunRequest(
                    user=client.active_user.id,
                    workspace=client.active_workspace.id,
                    id=uuid4(),
                    name=sample_name("foo"),
                    deployment=deployment.id,
                    status=ExecutionStatus.RUNNING,
                )
            )
            sr = client.zen_store.create_run_step(
                StepRunRequest(
                    user=client.active_user.id,
                    workspace=client.active_workspace.id,
                    name=step_name,
                    status=ExecutionStatus.RUNNING,
                    pipeline_run_id=pr.id,
                    deployment=deployment.id,
                )
            )
            resource = (
                pr if type_ == MetadataResourceTypes.PIPELINE_RUN else sr
            )

        rm = client.zen_store.create_run_metadata(
            RunMetadataRequest(
                user=client.active_user.id,
                workspace=client.active_workspace.id,
                resource_id=resource.id,
                resource_type=type_,
                values={"foo": "bar"},
                types={"foo": MetadataTypeEnum.STRING},
                stack_component_id=sc.id
                if type_ == MetadataResourceTypes.PIPELINE_RUN
                or type_ == MetadataResourceTypes.STEP_RUN
                else None,
            )
        )
        rm = client.zen_store.get_run_metadata(rm[0].id, True)
        assert rm.key == "foo"
        assert rm.value == "bar"
        assert rm.resource_id == resource.id
        assert rm.resource_type == type_
        assert rm.type == MetadataTypeEnum.STRING

        if type_ == MetadataResourceTypes.ARTIFACT_VERSION:
            client.zen_store.delete_artifact_version(resource.id)
            client.zen_store.delete_artifact(artifact.id)
        elif type_ == MetadataResourceTypes.MODEL_VERSION:
            client.zen_store.delete_model(resource.model.id)
        elif (
            type_ == MetadataResourceTypes.PIPELINE_RUN
            or type_ == MetadataResourceTypes.STEP_RUN
        ):
            client.zen_store.delete_run(pr.id)
            client.zen_store.delete_deployment(deployment.id)

        with pytest.raises(KeyError):
            client.zen_store.get_run_metadata(rm.id)

        client.zen_store.delete_stack_component(sc.id)


@pytest.mark.parametrize(
    "step_status, expected_run_status",
    [
        (ExecutionStatus.RUNNING, ExecutionStatus.RUNNING),
        (ExecutionStatus.COMPLETED, ExecutionStatus.COMPLETED),
        (ExecutionStatus.CACHED, ExecutionStatus.COMPLETED),
        (ExecutionStatus.FAILED, ExecutionStatus.FAILED),
    ],
)
def test_updating_the_pipeline_run_status(step_status, expected_run_status):
    """Tests updating the status of a pipeline run."""
    run_context = PipelineRunContext(1)
    with run_context:
        Client().zen_store.update_run_step(
            step_run_id=run_context.steps[-1].id,
            step_run_update=StepRunUpdate(status=step_status),
        )
        run_status = Client().get_pipeline_run(run_context.runs[-1].id).status
        assert run_status == expected_run_status
