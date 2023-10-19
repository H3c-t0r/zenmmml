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
"""ZenML Store interface."""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union
from uuid import UUID

from zenml.enums import ModelStages
from zenml.models import (
    ModelFilterModel,
    ModelRequestModel,
    ModelResponseModel,
    ModelUpdateModel,
    ModelVersionArtifactFilterModel,
    ModelVersionArtifactRequestModel,
    ModelVersionArtifactResponseModel,
    ModelVersionFilterModel,
    ModelVersionPipelineRunFilterModel,
    ModelVersionPipelineRunRequestModel,
    ModelVersionPipelineRunResponseModel,
    ModelVersionRequestModel,
    ModelVersionResponseModel,
    ModelVersionUpdateModel,
    OAuthDeviceFilterModel,
    OAuthDeviceResponseModel,
    OAuthDeviceUpdateModel,
    ServerModel,
)
from zenml.new_models.base import Page
from zenml.new_models.core import (
    ArtifactFilter,
    ArtifactRequest,
    ArtifactResponse,
    CodeRepositoryFilter,
    CodeRepositoryRequest,
    CodeRepositoryResponse,
    CodeRepositoryUpdate,
    ComponentFilter,
    ComponentRequest,
    ComponentResponse,
    ComponentUpdate,
    FlavorFilter,
    FlavorRequest,
    FlavorResponse,
    FlavorUpdate,
    PipelineBuildFilter,
    PipelineBuildRequest,
    PipelineBuildResponse,
    PipelineDeploymentFilter,
    PipelineDeploymentRequest,
    PipelineDeploymentResponse,
    PipelineFilter,
    PipelineRequest,
    PipelineResponse,
    PipelineRunFilter,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineRunUpdate,
    PipelineUpdate,
    RunMetadataFilter,
    RunMetadataRequest,
    RunMetadataResponse,
    ScheduleFilter,
    ScheduleRequest,
    ScheduleResponse,
    ScheduleUpdate,
    ServiceConnectorFilter,
    ServiceConnectorRequest,
    ServiceConnectorResponse,
    ServiceConnectorUpdate,
    StackFilter,
    StackRequest,
    StackResponse,
    StackUpdate,
    StepRunFilter,
    StepRunRequest,
    StepRunResponse,
    StepRunUpdate,
    UserFilter,
    UserRequest,
    UserResponse,
    UserUpdate,
    WorkspaceFilter,
    WorkspaceRequest,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from zenml.new_models.service_connector_type import (
    ServiceConnectorResourcesModel,
    ServiceConnectorTypeModel,
)


class ZenStoreInterface(ABC):
    """ZenML store interface.

    All ZenML stores must implement the methods in this interface.

    The methods in this interface are organized in the following way:

     * they are grouped into categories based on the type of resource
       that they operate on (e.g. stacks, stack components, etc.)

     * each category has a set of CRUD methods (create, read, update, delete)
       that operate on the resources in that category. The order of the methods
       in each category should be:

       * create methods - store a new resource. These methods
         should fill in generated fields (e.g. UUIDs, creation timestamps) in
         the resource and return the updated resource.
       * get methods - retrieve a single existing resource identified by a
         unique key or identifier from the store. These methods should always
         return a resource and raise an exception if the resource does not
         exist.
       * list methods - retrieve a list of resources from the store. These
         methods should accept a set of filter parameters that can be used to
         filter the list of resources retrieved from the store.
       * update methods - update an existing resource in the store. These
         methods should expect the updated resource to be correctly identified
         by its unique key or identifier and raise an exception if the resource
         does not exist.
       * delete methods - delete an existing resource from the store. These
         methods should expect the resource to be correctly identified by its
         unique key or identifier. If the resource does not exist,
         an exception should be raised.

    Best practices for implementing and keeping this interface clean and easy to
    maintain and extend:

      * keep methods organized by resource type and ordered by CRUD operation
      * for resources with multiple keys, don't implement multiple get or list
      methods here if the same functionality can be achieved by a single get or
      list method. Instead, implement them in the BaseZenStore class and have
      them call the generic get or list method in this interface.
      * keep the logic required to convert between ZenML domain Model classes
      and internal store representations outside the ZenML domain Model classes
      * methods for resources that have two or more unique keys (e.g. a Workspace
      is uniquely identified by its name as well as its UUID) should reflect
      that in the method variants and/or method arguments:
        * methods that take in a resource identifier as argument should accept
        all variants of the identifier (e.g. `workspace_name_or_uuid` for methods
        that get/list/update/delete Workspaces)
        * if a compound key is involved, separate get methods should be
        implemented (e.g. `get_pipeline` to get a pipeline by ID and
        `get_pipeline_in_workspace` to get a pipeline by its name and the ID of
        the workspace it belongs to)
      * methods for resources that are scoped as children of other resources
      (e.g. a Stack is always owned by a Workspace) should reflect the
      key(s) of the parent resource in the provided methods and method
      arguments:
        * create methods should take the parent resource UUID(s) as an argument
        (e.g. `create_stack` takes in the workspace ID)
        * get methods should be provided to retrieve a resource by the compound
        key that includes the parent resource key(s)
        * list methods should feature optional filter arguments that reflect
        the parent resource key(s)
    """

    # ---------------------------------
    # Initialization and configuration
    # ---------------------------------

    @abstractmethod
    def _initialize(self) -> None:
        """Initialize the store.

        This method is called immediately after the store is created. It should
        be used to set up the backend (database, connection etc.).
        """

    @abstractmethod
    def get_store_info(self) -> ServerModel:
        """Get information about the store.

        Returns:
            Information about the store.
        """

    @abstractmethod
    def get_deployment_id(self) -> UUID:
        """Get the ID of the deployment.

        Returns:
            The ID of the deployment.
        """

    # -------------------- Stacks --------------------

    @abstractmethod
    def create_stack(self, stack: StackRequest) -> StackResponse:
        """Create a new stack.

        Args:
            stack: The stack to create.

        Returns:
            The created stack.

        Raises:
            StackExistsError: If a stack with the same name is already owned
                by this user in this workspace.
        """

    @abstractmethod
    def get_stack(self, stack_id: UUID) -> StackResponse:
        """Get a stack by its unique ID.

        Args:
            stack_id: The ID of the stack to get.

        Returns:
            The stack with the given ID.

        Raises:
            KeyError: if the stack doesn't exist.
        """

    @abstractmethod
    def list_stacks(
        self, stack_filter_model: StackFilter
    ) -> Page[StackResponse]:
        """List all stacks matching the given filter criteria.

        Args:
            stack_filter_model: All filter parameters including pagination
                params

        Returns:
            A list of all stacks matching the filter criteria.
        """

    @abstractmethod
    def update_stack(
        self, stack_id: UUID, stack_update: StackUpdate
    ) -> StackResponse:
        """Update a stack.

        Args:
            stack_id: The ID of the stack update.
            stack_update: The update request on the stack.

        Returns:
            The updated stack.

        Raises:
            KeyError: if the stack doesn't exist.
        """

    @abstractmethod
    def delete_stack(self, stack_id: UUID) -> None:
        """Delete a stack.

        Args:
            stack_id: The ID of the stack to delete.

        Raises:
            KeyError: if the stack doesn't exist.
        """

    # -------------------- Components --------------------

    @abstractmethod
    def create_stack_component(
        self, component: ComponentRequest
    ) -> ComponentResponse:
        """Create a stack component.

        Args:
            component: The stack component to create.

        Returns:
            The created stack component.

        Raises:
            StackComponentExistsError: If a stack component with the same name
                and type is already owned by this user in this workspace.
        """

    @abstractmethod
    def list_stack_components(
        self, component_filter_model: ComponentFilter
    ) -> Page[ComponentResponse]:
        """List all stack components matching the given filter criteria.

        Args:
            component_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all stack components matching the filter criteria.
        """

    @abstractmethod
    def get_stack_component(self, component_id: UUID) -> ComponentResponse:
        """Get a stack component by ID.

        Args:
            component_id: The ID of the stack component to get.

        Returns:
            The stack component.

        Raises:
            KeyError: if the stack component doesn't exist.
        """

    @abstractmethod
    def update_stack_component(
        self,
        component_id: UUID,
        component_update: ComponentUpdate,
    ) -> ComponentResponse:
        """Update an existing stack component.

        Args:
            component_id: The ID of the stack component to update.
            component_update: The update to be applied to the stack component.

        Returns:
            The updated stack component.

        Raises:
            KeyError: if the stack component doesn't exist.
        """

    @abstractmethod
    def delete_stack_component(self, component_id: UUID) -> None:
        """Delete a stack component.

        Args:
            component_id: The ID of the stack component to delete.

        Raises:
            KeyError: if the stack component doesn't exist.
            ValueError: if the stack component is part of one or more stacks.
        """

    # -------------------- Flavors --------------------

    @abstractmethod
    def create_flavor(
        self,
        flavor: FlavorRequest,
    ) -> FlavorResponse:
        """Creates a new stack component flavor.

        Args:
            flavor: The stack component flavor to create.

        Returns:
            The newly created flavor.

        Raises:
            EntityExistsError: If a flavor with the same name and type
                is already owned by this user in this workspace.
        """

    @abstractmethod
    def update_flavor(
        self, flavor_id: UUID, flavor_update: FlavorUpdate
    ) -> FlavorResponse:
        """Updates an existing user.

        Args:
            flavor_id: The id of the flavor to update.
            flavor_update: The update to be applied to the flavor.

        Returns:
            The updated flavor.
        """

    @abstractmethod
    def get_flavor(self, flavor_id: UUID) -> FlavorResponse:
        """Get a stack component flavor by ID.

        Args:
            flavor_id: The ID of the flavor to get.

        Returns:
            The stack component flavor.

        Raises:
            KeyError: if the stack component flavor doesn't exist.
        """

    @abstractmethod
    def list_flavors(
        self, flavor_filter_model: FlavorFilter
    ) -> Page[FlavorResponse]:
        """List all stack component flavors matching the given filter criteria.

        Args:
            flavor_filter_model: All filter parameters including pagination
                params.

        Returns:
            List of all the stack component flavors matching the given criteria.
        """

    @abstractmethod
    def delete_flavor(self, flavor_id: UUID) -> None:
        """Delete a stack component flavor.

        Args:
            flavor_id: The ID of the stack component flavor to delete.

        Raises:
            KeyError: if the stack component flavor doesn't exist.
        """

    # -------------------- Users --------------------

    @abstractmethod
    def create_user(self, user: UserRequest) -> UserResponse:
        """Creates a new user.

        Args:
            user: User to be created.

        Returns:
            The newly created user.

        Raises:
            EntityExistsError: If a user with the given name already exists.
        """

    @abstractmethod
    def get_user(
        self,
        user_name_or_id: Optional[Union[str, UUID]] = None,
        include_private: bool = False,
    ) -> UserResponse:
        """Gets a specific user, when no id is specified the active user is returned.

        Args:
            user_name_or_id: The name or ID of the user to get.
            include_private: Whether to include private user information

        Returns:
            The requested user, if it was found.

        Raises:
            KeyError: If no user with the given name or ID exists.
        """

    @abstractmethod
    def list_users(self, user_filter_model: UserFilter) -> Page[UserResponse]:
        """List all users.

        Args:
            user_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all users.
        """

    @abstractmethod
    def update_user(
        self, user_id: UUID, user_update: UserUpdate
    ) -> UserResponse:
        """Updates an existing user.

        Args:
            user_id: The id of the user to update.
            user_update: The update to be applied to the user.

        Returns:
            The updated user.

        Raises:
            KeyError: If no user with the given name exists.
        """

    @abstractmethod
    def delete_user(self, user_name_or_id: Union[str, UUID]) -> None:
        """Deletes a user.

        Args:
            user_name_or_id: The name or ID of the user to delete.

        Raises:
            KeyError: If no user with the given ID exists.
        """

    # -------------------- Workspaces --------------------

    @abstractmethod
    def create_workspace(
        self, workspace: WorkspaceRequest
    ) -> WorkspaceResponse:
        """Creates a new workspace.

        Args:
            workspace: The workspace to create.

        Returns:
            The newly created workspace.

        Raises:
            EntityExistsError: If a workspace with the given name already exists.
        """

    @abstractmethod
    def get_workspace(
        self, workspace_name_or_id: Union[UUID, str]
    ) -> WorkspaceResponse:
        """Get an existing workspace by name or ID.

        Args:
            workspace_name_or_id: Name or ID of the workspace to get.

        Returns:
            The requested workspace.

        Raises:
            KeyError: If there is no such workspace.
        """

    @abstractmethod
    def list_workspaces(
        self, workspace_filter_model: WorkspaceFilter
    ) -> Page[WorkspaceResponse]:
        """List all workspace matching the given filter criteria.

        Args:
            workspace_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all workspace matching the filter criteria.
        """

    @abstractmethod
    def update_workspace(
        self, workspace_id: UUID, workspace_update: WorkspaceUpdate
    ) -> WorkspaceResponse:
        """Update an existing workspace.

        Args:
            workspace_id: The ID of the workspace to be updated.
            workspace_update: The update to be applied to the workspace.

        Returns:
            The updated workspace.

        Raises:
            KeyError: if the workspace does not exist.
        """

    @abstractmethod
    def delete_workspace(self, workspace_name_or_id: Union[str, UUID]) -> None:
        """Deletes a workspace.

        Args:
            workspace_name_or_id: Name or ID of the workspace to delete.

        Raises:
            KeyError: If no workspace with the given name exists.
        """

    # -------------------- Pipelines --------------------

    @abstractmethod
    def create_pipeline(
        self,
        pipeline: PipelineRequest,
    ) -> PipelineResponse:
        """Creates a new pipeline in a workspace.

        Args:
            pipeline: The pipeline to create.

        Returns:
            The newly created pipeline.

        Raises:
            KeyError: if the workspace does not exist.
            EntityExistsError: If an identical pipeline already exists.
        """

    @abstractmethod
    def get_pipeline(self, pipeline_id: UUID) -> PipelineResponse:
        """Get a pipeline with a given ID.

        Args:
            pipeline_id: ID of the pipeline.

        Returns:
            The pipeline.

        Raises:
            KeyError: if the pipeline does not exist.
        """

    @abstractmethod
    def list_pipelines(
        self, pipeline_filter_model: PipelineFilter
    ) -> Page[PipelineResponse]:
        """List all pipelines matching the given filter criteria.

        Args:
            pipeline_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all pipelines matching the filter criteria.
        """

    @abstractmethod
    def update_pipeline(
        self,
        pipeline_id: UUID,
        pipeline_update: PipelineUpdate,
    ) -> PipelineResponse:
        """Updates a pipeline.

        Args:
            pipeline_id: The ID of the pipeline to be updated.
            pipeline_update: The update to be applied.

        Returns:
            The updated pipeline.

        Raises:
            KeyError: if the pipeline doesn't exist.
        """

    @abstractmethod
    def delete_pipeline(self, pipeline_id: UUID) -> None:
        """Deletes a pipeline.

        Args:
            pipeline_id: The ID of the pipeline to delete.

        Raises:
            KeyError: if the pipeline doesn't exist.
        """

    # -------------------- Pipeline builds --------------------

    @abstractmethod
    def create_build(
        self,
        build: PipelineBuildRequest,
    ) -> PipelineBuildResponse:
        """Creates a new build in a workspace.

        Args:
            build: The build to create.

        Returns:
            The newly created build.

        Raises:
            KeyError: If the workspace does not exist.
            EntityExistsError: If an identical build already exists.
        """

    @abstractmethod
    def get_build(self, build_id: UUID) -> PipelineBuildResponse:
        """Get a build with a given ID.

        Args:
            build_id: ID of the build.

        Returns:
            The build.

        Raises:
            KeyError: If the build does not exist.
        """

    @abstractmethod
    def list_builds(
        self, build_filter_model: PipelineBuildFilter
    ) -> Page[PipelineBuildResponse]:
        """List all builds matching the given filter criteria.

        Args:
            build_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all builds matching the filter criteria.
        """

    @abstractmethod
    def delete_build(self, build_id: UUID) -> None:
        """Deletes a build.

        Args:
            build_id: The ID of the build to delete.

        Raises:
            KeyError: if the build doesn't exist.
        """

    # -------------------- Pipeline deployments --------------------

    @abstractmethod
    def create_deployment(
        self,
        deployment: PipelineDeploymentRequest,
    ) -> PipelineDeploymentResponse:
        """Creates a new deployment in a workspace.

        Args:
            deployment: The deployment to create.

        Returns:
            The newly created deployment.

        Raises:
            KeyError: If the workspace does not exist.
            EntityExistsError: If an identical deployment already exists.
        """

    @abstractmethod
    def get_deployment(
        self, deployment_id: UUID
    ) -> PipelineDeploymentResponse:
        """Get a deployment with a given ID.

        Args:
            deployment_id: ID of the deployment.

        Returns:
            The deployment.

        Raises:
            KeyError: If the deployment does not exist.
        """

    @abstractmethod
    def list_deployments(
        self, deployment_filter_model: PipelineDeploymentFilter
    ) -> Page[PipelineDeploymentResponse]:
        """List all deployments matching the given filter criteria.

        Args:
            deployment_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all deployments matching the filter criteria.
        """

    @abstractmethod
    def delete_deployment(self, deployment_id: UUID) -> None:
        """Deletes a deployment.

        Args:
            deployment_id: The ID of the deployment to delete.

        Raises:
            KeyError: If the deployment doesn't exist.
        """

    # -------------------- Schedules --------------------

    @abstractmethod
    def create_schedule(self, schedule: ScheduleRequest) -> ScheduleResponse:
        """Creates a new schedule.

        Args:
            schedule: The schedule to create.

        Returns:
            The newly created schedule.
        """

    @abstractmethod
    def get_schedule(self, schedule_id: UUID) -> ScheduleResponse:
        """Get a schedule with a given ID.

        Args:
            schedule_id: ID of the schedule.

        Returns:
            The schedule.

        Raises:
            KeyError: if the schedule does not exist.
        """

    @abstractmethod
    def list_schedules(
        self, schedule_filter_model: ScheduleFilter
    ) -> Page[ScheduleResponse]:
        """List all schedules in the workspace.

        Args:
            schedule_filter_model: All filter parameters including pagination
                params

        Returns:
            A list of schedules.
        """

    @abstractmethod
    def update_schedule(
        self,
        schedule_id: UUID,
        schedule_update: ScheduleUpdate,
    ) -> ScheduleResponse:
        """Updates a schedule.

        Args:
            schedule_id: The ID of the schedule to be updated.
            schedule_update: The update to be applied.

        Returns:
            The updated schedule.

        Raises:
            KeyError: if the schedule doesn't exist.
        """

    @abstractmethod
    def delete_schedule(self, schedule_id: UUID) -> None:
        """Deletes a schedule.

        Args:
            schedule_id: The ID of the schedule to delete.

        Raises:
            KeyError: if the schedule doesn't exist.
        """

    # -------------------- Pipeline runs --------------------

    @abstractmethod
    def create_run(
        self, pipeline_run: PipelineRunRequest
    ) -> PipelineRunResponse:
        """Creates a pipeline run.

        Args:
            pipeline_run: The pipeline run to create.

        Returns:
            The created pipeline run.

        Raises:
            EntityExistsError: If an identical pipeline run already exists.
            KeyError: If the pipeline does not exist.
        """

    @abstractmethod
    def get_run(self, run_name_or_id: Union[str, UUID]) -> PipelineRunResponse:
        """Gets a pipeline run.

        Args:
            run_name_or_id: The name or ID of the pipeline run to get.

        Returns:
            The pipeline run.

        Raises:
            KeyError: if the pipeline run doesn't exist.
        """

    @abstractmethod
    def get_or_create_run(
        self, pipeline_run: PipelineRunRequest
    ) -> Tuple[PipelineRunResponse, bool]:
        """Gets or creates a pipeline run.

        If a run with the same ID or name already exists, it is returned.
        Otherwise, a new run is created.

        Args:
            pipeline_run: The pipeline run to get or create.

        Returns:
            The pipeline run, and a boolean indicating whether the run was
            created or not.
        """

    @abstractmethod
    def list_runs(
        self, runs_filter_model: PipelineRunFilter
    ) -> Page[PipelineRunResponse]:
        """List all pipeline runs matching the given filter criteria.

        Args:
            runs_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all pipeline runs matching the filter criteria.
        """

    @abstractmethod
    def update_run(
        self, run_id: UUID, run_update: PipelineRunUpdate
    ) -> PipelineRunResponse:
        """Updates a pipeline run.

        Args:
            run_id: The ID of the pipeline run to update.
            run_update: The update to be applied to the pipeline run.

        Returns:
            The updated pipeline run.

        Raises:
            KeyError: if the pipeline run doesn't exist.
        """

    @abstractmethod
    def delete_run(self, run_id: UUID) -> None:
        """Deletes a pipeline run.

        Args:
            run_id: The ID of the pipeline run to delete.

        Raises:
            KeyError: if the pipeline run doesn't exist.
        """

    # -------------------- Step runs --------------------

    @abstractmethod
    def create_run_step(self, step_run: StepRunRequest) -> StepRunResponse:
        """Creates a step run.

        Args:
            step_run: The step run to create.

        Returns:
            The created step run.

        Raises:
            EntityExistsError: if the step run already exists.
            KeyError: if the pipeline run doesn't exist.
        """

    @abstractmethod
    def get_run_step(self, step_run_id: UUID) -> StepRunResponse:
        """Get a step run by ID.

        Args:
            step_run_id: The ID of the step run to get.

        Returns:
            The step run.

        Raises:
            KeyError: if the step run doesn't exist.
        """

    @abstractmethod
    def list_run_steps(
        self, step_run_filter_model: StepRunFilter
    ) -> Page[StepRunResponse]:
        """List all step runs matching the given filter criteria.

        Args:
            step_run_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all step runs matching the filter criteria.
        """

    @abstractmethod
    def update_run_step(
        self,
        step_run_id: UUID,
        step_run_update: StepRunUpdate,
    ) -> StepRunResponse:
        """Updates a step run.

        Args:
            step_run_id: The ID of the step to update.
            step_run_update: The update to be applied to the step.

        Returns:
            The updated step run.

        Raises:
            KeyError: if the step run doesn't exist.
        """

    # -------------------- Artifacts --------------------

    @abstractmethod
    def create_artifact(self, artifact: ArtifactRequest) -> ArtifactResponse:
        """Creates an artifact.

        Args:
            artifact: The artifact to create.

        Returns:
            The created artifact.
        """

    @abstractmethod
    def get_artifact(self, artifact_id: UUID) -> ArtifactResponse:
        """Gets an artifact.

        Args:
            artifact_id: The ID of the artifact to get.

        Returns:
            The artifact.

        Raises:
            KeyError: if the artifact doesn't exist.
        """

    @abstractmethod
    def list_artifacts(
        self, artifact_filter_model: ArtifactFilter
    ) -> Page[ArtifactResponse]:
        """List all artifacts matching the given filter criteria.

        Args:
            artifact_filter_model: All filter parameters including pagination
                params.

        Returns:
            A list of all artifacts matching the filter criteria.
        """

    @abstractmethod
    def delete_artifact(self, artifact_id: UUID) -> None:
        """Deletes an artifact.

        Args:
            artifact_id: The ID of the artifact to delete.

        Raises:
            KeyError: if the artifact doesn't exist.
        """

    # -------------------- Run metadata --------------------

    @abstractmethod
    def create_run_metadata(
        self, run_metadata: RunMetadataRequest
    ) -> List[RunMetadataResponse]:
        """Creates run metadata.

        Args:
            run_metadata: The run metadata to create.

        Returns:
            The created run metadata.
        """

    @abstractmethod
    def list_run_metadata(
        self,
        run_metadata_filter_model: RunMetadataFilter,
    ) -> Page[RunMetadataResponse]:
        """List run metadata.

        Args:
            run_metadata_filter_model: All filter parameters including
                pagination params.

        Returns:
            The run metadata.
        """

    # -------------------- Code repositories --------------------

    @abstractmethod
    def create_code_repository(
        self, code_repository: CodeRepositoryRequest
    ) -> CodeRepositoryResponse:
        """Creates a new code repository.

        Args:
            code_repository: Code repository to be created.

        Returns:
            The newly created code repository.

        Raises:
            EntityExistsError: If a code repository with the given name already
                exists.
        """

    @abstractmethod
    def get_code_repository(
        self, code_repository_id: UUID
    ) -> CodeRepositoryResponse:
        """Gets a specific code repository.

        Args:
            code_repository_id: The ID of the code repository to get.

        Returns:
            The requested code repository, if it was found.

        Raises:
            KeyError: If no code repository with the given ID exists.
        """

    @abstractmethod
    def list_code_repositories(
        self, filter_model: CodeRepositoryFilter
    ) -> Page[CodeRepositoryResponse]:
        """List all code repositories.

        Args:
            filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all code repositories.
        """

    @abstractmethod
    def update_code_repository(
        self, code_repository_id: UUID, update: CodeRepositoryUpdate
    ) -> CodeRepositoryResponse:
        """Updates an existing code repository.

        Args:
            code_repository_id: The ID of the code repository to update.
            update: The update to be applied to the code repository.

        Returns:
            The updated code repository.

        Raises:
            KeyError: If no code repository with the given name exists.
        """

    @abstractmethod
    def delete_code_repository(self, code_repository_id: UUID) -> None:
        """Deletes a code repository.

        Args:
            code_repository_id: The ID of the code repository to delete.

        Raises:
            KeyError: If no code repository with the given ID exists.
        """

    # -------------------- Service Connectors --------------------

    @abstractmethod
    def create_service_connector(
        self,
        service_connector: ServiceConnectorRequest,
    ) -> ServiceConnectorResponse:
        """Creates a new service connector.

        Args:
            service_connector: Service connector to be created.

        Returns:
            The newly created service connector.

        Raises:
            EntityExistsError: If a service connector with the given name
                is already owned by this user in this workspace.
        """

    @abstractmethod
    def get_service_connector(
        self, service_connector_id: UUID
    ) -> ServiceConnectorResponse:
        """Gets a specific service connector.

        Args:
            service_connector_id: The ID of the service connector to get.

        Returns:
            The requested service connector, if it was found.

        Raises:
            KeyError: If no service connector with the given ID exists.
        """

    @abstractmethod
    def list_service_connectors(
        self, filter_model: ServiceConnectorFilter
    ) -> Page[ServiceConnectorResponse]:
        """List all service connectors.

        Args:
            filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all service connectors.
        """

    @abstractmethod
    def update_service_connector(
        self, service_connector_id: UUID, update: ServiceConnectorUpdate
    ) -> ServiceConnectorResponse:
        """Updates an existing service connector.

        The update model contains the fields to be updated. If a field value is
        set to None in the model, the field is not updated, but there are
        special rules concerning some fields:

        * the `configuration` and `secrets` fields together represent a full
        valid configuration update, not just a partial update. If either is
        set (i.e. not None) in the update, their values are merged together and
        will replace the existing configuration and secrets values.
        * the `resource_id` field value is also a full replacement value: if set
        to `None`, the resource ID is removed from the service connector.
        * the `expiration_seconds` field value is also a full replacement value:
        if set to `None`, the expiration is removed from the service connector.
        * the `secret_id` field value in the update is ignored, given that
        secrets are managed internally by the ZenML store.
        * the `labels` field is also a full labels update: if set (i.e. not
        `None`), all existing labels are removed and replaced by the new labels
        in the update.

        Args:
            service_connector_id: The ID of the service connector to update.
            update: The update to be applied to the service connector.

        Returns:
            The updated service connector.

        Raises:
            KeyError: If no service connector with the given name exists.
        """

    @abstractmethod
    def delete_service_connector(self, service_connector_id: UUID) -> None:
        """Deletes a service connector.

        Args:
            service_connector_id: The ID of the service connector to delete.

        Raises:
            KeyError: If no service connector with the given ID exists.
        """

    @abstractmethod
    def verify_service_connector_config(
        self,
        service_connector: ServiceConnectorRequest,
        list_resources: bool = True,
    ) -> ServiceConnectorResourcesModel:
        """Verifies if a service connector configuration has access to resources.

        Args:
            service_connector: The service connector configuration to verify.
            list_resources: If True, the list of all resources accessible
                through the service connector is returned.

        Returns:
            The list of resources that the service connector configuration has
            access to.

        Raises:
            NotImplementError: If the service connector cannot be verified
                on the store e.g. due to missing package dependencies.
        """

    @abstractmethod
    def verify_service_connector(
        self,
        service_connector_id: UUID,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        list_resources: bool = True,
    ) -> ServiceConnectorResourcesModel:
        """Verifies if a service connector instance has access to one or more resources.

        Args:
            service_connector_id: The ID of the service connector to verify.
            resource_type: The type of resource to verify access to.
            resource_id: The ID of the resource to verify access to.
            list_resources: If True, the list of all resources accessible
                through the service connector and matching the supplied resource
                type and ID are returned.

        Returns:
            The list of resources that the service connector has access to,
            scoped to the supplied resource type and ID, if provided.

        Raises:
            KeyError: If no service connector with the given name exists.
            NotImplementError: If the service connector cannot be verified
                e.g. due to missing package dependencies.
        """

    @abstractmethod
    def get_service_connector_client(
        self,
        service_connector_id: UUID,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> ServiceConnectorResponse:
        """Get a service connector client for a service connector and given resource.

        Args:
            service_connector_id: The ID of the base service connector to use.
            resource_type: The type of resource to get a client for.
            resource_id: The ID of the resource to get a client for.

        Returns:
            A service connector client that can be used to access the given
            resource.

        Raises:
            KeyError: If no service connector with the given name exists.
            NotImplementError: If the service connector cannot be instantiated
                on the store e.g. due to missing package dependencies.
        """

    @abstractmethod
    def list_service_connector_resources(
        self,
        user_name_or_id: Union[str, UUID],
        workspace_name_or_id: Union[str, UUID],
        connector_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> List[ServiceConnectorResourcesModel]:
        """List resources that can be accessed by service connectors.

        Args:
            user_name_or_id: The name or ID of the user to scope to.
            workspace_name_or_id: The name or ID of the workspace to scope to.
            connector_type: The type of service connector to scope to.
            resource_type: The type of resource to scope to.
            resource_id: The ID of the resource to scope to.

        Returns:
            The matching list of resources that available service
            connectors have access to.
        """

    @abstractmethod
    def list_service_connector_types(
        self,
        connector_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        auth_method: Optional[str] = None,
    ) -> List[ServiceConnectorTypeModel]:
        """Get a list of service connector types.

        Args:
            connector_type: Filter by connector type.
            resource_type: Filter by resource type.
            auth_method: Filter by authentication method.

        Returns:
            List of service connector types.
        """

    @abstractmethod
    def get_service_connector_type(
        self,
        connector_type: str,
    ) -> ServiceConnectorTypeModel:
        """Returns the requested service connector type.

        Args:
            connector_type: the service connector type identifier.

        Returns:
            The requested service connector type.

        Raises:
            KeyError: If no service connector type with the given ID exists.
        """

    # -------------------- Model --------------------

    @abstractmethod
    def create_model(self, model: ModelRequestModel) -> ModelResponseModel:
        """Creates a new model.

        Args:
            model: the Model to be created.

        Returns:
            The newly created model.

        Raises:
            EntityExistsError: If a model with the given name already exists.
        """

    @abstractmethod
    def delete_model(self, model_name_or_id: Union[str, UUID]) -> None:
        """Deletes a model.

        Args:
            model_name_or_id: name or id of the model to be deleted.

        Raises:
            KeyError: specified ID or name not found.
        """

    @abstractmethod
    def update_model(
        self,
        model_id: UUID,
        model_update: ModelUpdateModel,
    ) -> ModelResponseModel:
        """Updates an existing model.

        Args:
            model_id: UUID of the model to be updated.
            model_update: the Model to be updated.

        Returns:
            The updated model.
        """

    @abstractmethod
    def get_model(
        self, model_name_or_id: Union[str, UUID]
    ) -> ModelResponseModel:
        """Get an existing model.

        Args:
            model_name_or_id: name or id of the model to be retrieved.

        Returns:
            The model of interest.

        Raises:
            KeyError: specified ID or name not found.
        """

    @abstractmethod
    def list_models(
        self,
        model_filter_model: ModelFilterModel,
    ) -> Page[ModelResponseModel]:
        """Get all models by filter.

        Args:
            model_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all models.
        """

    # -------------------- Model versions --------------------

    @abstractmethod
    def create_model_version(
        self, model_version: ModelVersionRequestModel
    ) -> ModelVersionResponseModel:
        """Creates a new model version.

        Args:
            model_version: the Model Version to be created.

        Returns:
            The newly created model version.

        Raises:
            ValueError: If `number` is not None during model version creation.
            EntityExistsError: If a model version with the given name already exists.
        """

    @abstractmethod
    def delete_model_version(
        self,
        model_name_or_id: Union[str, UUID],
        model_version_name_or_id: Union[str, UUID],
    ) -> None:
        """Deletes a model version.

        Args:
            model_name_or_id: name or id of the model containing the model version.
            model_version_name_or_id: name or id of the model version to be deleted.

        Raises:
            KeyError: specified ID or name not found.
        """

    @abstractmethod
    def get_model_version(
        self,
        model_name_or_id: Union[str, UUID],
        model_version_name_or_number_or_id: Optional[
            Union[str, int, UUID, ModelStages]
        ] = None,
    ) -> ModelVersionResponseModel:
        """Get an existing model version.

        Args:
            model_name_or_id: name or id of the model containing the model version.
            model_version_name_or_number_or_id: name, id, stage or number of the model version to be retrieved.
                If skipped latest version will be retrieved.

        Returns:
            The model version of interest.

        Raises:
            KeyError: specified ID or name not found.
        """

    @abstractmethod
    def list_model_versions(
        self,
        model_version_filter_model: ModelVersionFilterModel,
    ) -> Page[ModelVersionResponseModel]:
        """Get all model versions by filter.

        Args:
            model_version_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all model versions.
        """

    @abstractmethod
    def update_model_version(
        self,
        model_version_id: UUID,
        model_version_update_model: ModelVersionUpdateModel,
    ) -> ModelVersionResponseModel:
        """Get all model versions by filter.

        Args:
            model_version_id: The ID of model version to be updated.
            model_version_update_model: The model version to be updated.

        Returns:
            An updated model version.

        Raises:
            KeyError: If the model version not found
            RuntimeError: If there is a model version with target stage, but `force` flag is off
        """

    ###########################
    # Model Versions Artifacts
    ###########################

    @abstractmethod
    def create_model_version_artifact_link(
        self, model_version_artifact_link: ModelVersionArtifactRequestModel
    ) -> ModelVersionArtifactResponseModel:
        """Creates a new model version link.

        Args:
            model_version_artifact_link: the Model Version to Artifact Link to be created.

        Returns:
            The newly created model version to artifact link.

        Raises:
            EntityExistsError: If a link with the given name already exists.
        """

    @abstractmethod
    def list_model_version_artifact_links(
        self,
        model_version_artifact_link_filter_model: ModelVersionArtifactFilterModel,
    ) -> Page[ModelVersionArtifactResponseModel]:
        """Get all model version to artifact links by filter.

        Args:
            model_version_artifact_link_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all model version to artifact links.
        """

    @abstractmethod
    def delete_model_version_artifact_link(
        self,
        model_name_or_id: Union[str, UUID],
        model_version_name_or_id: Union[str, UUID],
        model_version_artifact_link_name_or_id: Union[str, UUID],
    ) -> None:
        """Deletes a model version to artifact link.

        Args:
            model_name_or_id: name or ID of the model containing the model version.
            model_version_name_or_id: name or ID of the model version containing the link.
            model_version_artifact_link_name_or_id: name or ID of the model version to artifact link to be deleted.

        Raises:
            KeyError: specified ID or name not found.
        """

    ###############################
    # Model Versions Pipeline Runs
    ###############################

    @abstractmethod
    def create_model_version_pipeline_run_link(
        self,
        model_version_pipeline_run_link: ModelVersionPipelineRunRequestModel,
    ) -> ModelVersionPipelineRunResponseModel:
        """Creates a new model version to pipeline run link.

        Args:
            model_version_pipeline_run_link: the Model Version to Pipeline Run Link to be created.

        Returns:
            - If Model Version to Pipeline Run Link already exists - returns the existing link.
            - Otherwise, returns the newly created model version to pipeline run link.
        """

    @abstractmethod
    def list_model_version_pipeline_run_links(
        self,
        model_version_pipeline_run_link_filter_model: ModelVersionPipelineRunFilterModel,
    ) -> Page[ModelVersionPipelineRunResponseModel]:
        """Get all model version to pipeline run links by filter.

        Args:
            model_version_pipeline_run_link_filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all model version to pipeline run links.
        """

    @abstractmethod
    def delete_model_version_pipeline_run_link(
        self,
        model_name_or_id: Union[str, UUID],
        model_version_name_or_id: Union[str, UUID],
        model_version_pipeline_run_link_name_or_id: Union[str, UUID],
    ) -> None:
        """Deletes a model version to pipeline run link.

        Args:
            model_name_or_id: name or ID of the model containing the model version.
            model_version_name_or_id: name or ID of the model version containing the link.
            model_version_pipeline_run_link_name_or_id: name or ID of the model version to pipeline run link to be deleted.

        Raises:
            KeyError: specified ID not found.
        """

    # ------------------
    # Authorized Devices
    # ------------------

    @abstractmethod
    def get_authorized_device(
        self, device_id: UUID
    ) -> OAuthDeviceResponseModel:
        """Gets a specific OAuth 2.0 authorized device.

        Args:
            device_id: The ID of the device to get.

        Returns:
            The requested device, if it was found.

        Raises:
            KeyError: If no device with the given ID exists.
        """

    @abstractmethod
    def list_authorized_devices(
        self, filter_model: OAuthDeviceFilterModel
    ) -> Page[OAuthDeviceResponseModel]:
        """List all OAuth 2.0 authorized devices for a user.

        Args:
            filter_model: All filter parameters including pagination
                params.

        Returns:
            A page of all matching OAuth 2.0 authorized devices.
        """

    @abstractmethod
    def update_authorized_device(
        self, device_id: UUID, update: OAuthDeviceUpdateModel
    ) -> OAuthDeviceResponseModel:
        """Updates an existing OAuth 2.0 authorized device for internal use.

        Args:
            device_id: The ID of the device to update.
            update: The update to be applied to the device.

        Returns:
            The updated OAuth 2.0 authorized device.

        Raises:
            KeyError: If no device with the given ID exists.
        """

    @abstractmethod
    def delete_authorized_device(self, device_id: UUID) -> None:
        """Deletes an OAuth 2.0 authorized device.

        Args:
            device_id: The ID of the device to delete.

        Raises:
            KeyError: If no device with the given ID exists.
        """
