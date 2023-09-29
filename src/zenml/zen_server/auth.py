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
"""Authentication module for ZenML server."""

from contextvars import ContextVar
from datetime import datetime
from typing import (
    Callable,
    List,
    Optional,
    Set,
    Union,
)
from urllib.parse import urlencode
from uuid import UUID

import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    SecurityScopes,
)
from pydantic import BaseModel
from starlette.requests import Request

from zenml.constants import (
    API,
    EXTERNAL_AUTHENTICATOR_TIMEOUT,
    LOGIN,
    VERSION_1,
)
from zenml.enums import AuthScheme, OAuthDeviceStatus, PermissionType
from zenml.exceptions import AuthorizationException, OAuthError
from zenml.logger import get_logger
from zenml.models import (
    ExternalUserModel,
    OAuthDeviceInternalResponseModel,
    OAuthDeviceInternalUpdateModel,
    UserAuthModel,
    UserRequestModel,
    UserResponseModel,
    UserRoleAssignmentRequestModel,
    UserUpdateModel,
)
from zenml.zen_server.jwt import JWTToken
from zenml.zen_server.utils import server_config, zen_store
from zenml.zen_stores.base_zen_store import DEFAULT_USERNAME

logger = get_logger(__name__)

# create a context variable to store the authentication context
_auth_context: ContextVar[Optional["AuthContext"]] = ContextVar(
    "auth_context", default=None
)


def get_auth_context() -> Optional["AuthContext"]:
    """Returns the current authentication context.

    Returns:
        The authentication context.
    """
    auth_context = _auth_context.get()
    return auth_context


def set_auth_context(auth_context: "AuthContext") -> "AuthContext":
    """Sets the current authentication context.

    Args:
        auth_context: The authentication context.

    Returns:
        The authentication context.
    """
    _auth_context.set(auth_context)
    return auth_context


class AuthContext(BaseModel):
    """The authentication context."""

    user: UserResponseModel
    access_token: Optional[JWTToken] = None
    device: Optional[OAuthDeviceInternalResponseModel] = None

    @property
    def permissions(self) -> Set[PermissionType]:
        """Returns the permissions of the user.

        Returns:
            The permissions of the user.
        """
        if self.user.roles:
            # Merge permissions from all roles
            permissions: List[PermissionType] = []
            for role in self.user.roles:
                permissions.extend(role.permissions)

            # Remove duplicates
            return set(permissions)

        return set()


def authenticate_credentials(
    user_name_or_id: Optional[Union[str, UUID]] = None,
    password: Optional[str] = None,
    access_token: Optional[str] = None,
    activation_token: Optional[str] = None,
) -> AuthContext:
    """Verify if user authentication credentials are valid.

    This function can be used to validate all supplied user credentials to
    cover a range of possibilities:

     * username only - only when the no-auth scheme is used
     * username+password - for basic HTTP authentication or the OAuth2 password
       grant
     * access token (with embedded user id) - after successful authentication
       using one of the supported grants
     * username+activation token - for user activation

    Args:
        user_name_or_id: The username or user ID.
        password: The password.
        access_token: The access token.
        activation_token: The activation token.

    Returns:
        The authenticated account details.

    Raises:
        AuthorizationException: If the credentials are invalid.
    """
    user: Optional[UserAuthModel] = None
    auth_context: Optional[AuthContext] = None
    if user_name_or_id:
        try:
            user = zen_store().get_auth_user(user_name_or_id)
            user_model = zen_store().get_user(
                user_name_or_id=user_name_or_id, include_private=True
            )
            auth_context = AuthContext(user=user_model)
        except KeyError:
            # even when the user does not exist, we still want to execute the
            # password/token verification to protect against response discrepancy
            # attacks (https://cwe.mitre.org/data/definitions/204.html)
            logger.exception(
                f"Authentication error: error retrieving user "
                f"{user_name_or_id}"
            )
            pass

    if password is not None:
        if not UserAuthModel.verify_password(password, user):
            error = "Authentication error: invalid username or password"
            logger.error(error)
            raise AuthorizationException(error)
    elif access_token is not None:
        try:
            decoded_token = JWTToken.decode_token(
                token=access_token,
            )
        except AuthorizationException:
            error = "Authentication error: error decoding access token"
            logger.exception(error)
            raise AuthorizationException(error)

        try:
            user_model = zen_store().get_user(
                user_name_or_id=decoded_token.user_id, include_private=True
            )
        except KeyError:
            error = (
                f"Authentication error: error retrieving token user "
                f"{decoded_token.user_id}"
            )
            logger.error(error)
            raise AuthorizationException(error)

        if not user_model.active:
            error = (
                f"Authentication error: user {decoded_token.user_id} is not "
                f"active"
            )
            logger.error(error)
            raise AuthorizationException(error)

        device_model: Optional[OAuthDeviceInternalResponseModel] = None
        if decoded_token.device_id:
            # Access tokens that have been issued for a device are only valid
            # for that device, so we need to check if the device ID matches any
            # of the valid devices in the database.
            try:
                device_model = zen_store().get_internal_authorized_device(
                    device_id=decoded_token.device_id
                )
            except KeyError:
                error = (
                    f"Authentication error: error retrieving token device "
                    f"{decoded_token.device_id}"
                )
                logger.error(error)
                raise AuthorizationException(error)

            if (
                device_model.user is None
                or device_model.user.id != user_model.id
            ):
                error = (
                    f"Authentication error: device {decoded_token.device_id} "
                    f"does not belong to user {user_model.id}"
                )
                logger.error(error)
                raise AuthorizationException(error)

            if device_model.status != OAuthDeviceStatus.ACTIVE:
                error = (
                    f"Authentication error: device {decoded_token.device_id} "
                    f"is not active"
                )
                logger.error(error)
                raise AuthorizationException(error)

            if (
                device_model.expires
                and datetime.utcnow() >= device_model.expires
            ):
                error = (
                    f"Authentication error: device {decoded_token.device_id} "
                    "has expired"
                )
                logger.error(error)
                raise AuthorizationException(error)

            zen_store().update_internal_authorized_device(
                device_id=device_model.id,
                update=OAuthDeviceInternalUpdateModel(
                    update_last_login=True,
                ),
            )

        auth_context = AuthContext(
            user=user_model, access_token=decoded_token, device=device_model
        )
    elif activation_token is not None:
        if not UserAuthModel.verify_activation_token(activation_token, user):
            error = (
                f"Authentication error: invalid activation token for user "
                f"{user_name_or_id}"
            )
            logger.error(error)
            raise AuthorizationException(error)

    if not auth_context:
        error = "Authentication error: invalid credentials"
        logger.error(error)
        raise AuthorizationException(error)

    return auth_context


def authenticate_device(client_id: UUID, device_code: str) -> AuthContext:
    """Verify if device authorization credentials are valid.

    Args:
        client_id: The OAuth2 client ID.
        device_code: The device code.

    Returns:
        The authenticated account details.

    Raises:
        OAuthError: If the device authorization credentials are invalid.
    """
    # This is the part of the OAuth2 device code grant flow where a client
    # device is continuously polling the server to check if the user has
    # authorized a device. The following needs to happen to successfully
    # authenticate the device and return a valid access token:
    #
    # 1. the device code and client ID must match a device in the DB
    # 2. the device must be in the VERIFIED state, meaning that the user
    # has successfully authorized the device via the user code but the
    # device client hasn't yet fetched the associated API access token yet.
    # 3. the device must not be expired

    config = server_config()
    store = zen_store()

    try:
        device_model = store.get_internal_authorized_device(
            client_id=client_id
        )
    except KeyError:
        error = (
            f"Authentication error: error retrieving device with client ID "
            f"{client_id}"
        )
        logger.error(error)
        raise OAuthError(
            error="invalid_client",
            error_description=error,
        )

    if device_model.status != OAuthDeviceStatus.VERIFIED:
        error = (
            f"Authentication error: device with client ID {client_id} is "
            f"{device_model.status.value}."
        )
        logger.error(error)
        if device_model.status == OAuthDeviceStatus.PENDING:
            oauth_error = "authorization_pending"
        elif device_model.status == OAuthDeviceStatus.LOCKED:
            oauth_error = "access_denied"
        else:
            oauth_error = "expired_token"
        raise OAuthError(
            error=oauth_error,
            error_description=error,
        )

    if device_model.expires and datetime.utcnow() >= device_model.expires:
        error = (
            f"Authentication error: device for client ID {client_id} has "
            "expired"
        )
        logger.error(error)
        raise OAuthError(
            error="expired_token",
            error_description=error,
        )

    # Check the device code
    if not device_model.verify_device_code(device_code):
        # If the device code is invalid, increment the failed auth attempts
        # counter and lock the device if the maximum number of failed auth
        # attempts has been reached.
        failed_auth_attempts = device_model.failed_auth_attempts + 1
        update = OAuthDeviceInternalUpdateModel(
            failed_auth_attempts=failed_auth_attempts
        )
        if failed_auth_attempts >= config.max_failed_device_auth_attempts:
            update.locked = True

        store.update_internal_authorized_device(
            device_id=device_model.id,
            update=update,
        )

        if failed_auth_attempts >= config.max_failed_device_auth_attempts:
            error = (
                f"Authentication error: device for client ID {client_id} "
                "has been locked due to too many failed authentication "
                "attempts."
            )
        else:
            error = (
                f"Authentication error: device for client ID {client_id} "
                "has an invalid device code."
            )

        logger.error(error)
        raise OAuthError(
            error="access_denied",
            error_description=error,
        )

    # The device is valid, so we can return the user associated with it.
    # This is the one and only time we return an AuthContext authorized by
    # a device code in order to be exchanged for an access token. Subsequent
    # requests to the API will be authenticated using the access token.
    #
    # Update the device state to ACTIVE and set an expiration date for it
    # past which it can no longer be used for authentication. The expiration
    # date also determines the expiration date of the access token issued
    # for this device.
    expires_in: int = 0
    if config.jwt_token_expire_minutes:
        if device_model.trusted_device:
            expires_in = config.trusted_device_expiration_minutes or 0
        else:
            expires_in = config.device_expiration_minutes or 0

    update = OAuthDeviceInternalUpdateModel(
        status=OAuthDeviceStatus.ACTIVE,
        expires_in=expires_in,
    )
    device_model = zen_store().update_internal_authorized_device(
        device_id=device_model.id,
        update=update,
    )

    # This can never happen because the VERIFIED state is only set if
    # a user verified and has been associated with the device.
    assert device_model.user is not None

    return AuthContext(user=device_model.user, device=device_model)


def authenticate_external_user(external_access_token: str) -> AuthContext:
    """Implement external authentication.

    Args:
        external_access_token: The access token used to authenticate the user
            to the external authenticator.

    Returns:
        The authentication context reflecting the authenticated user.

    Raises:
        AuthorizationException: If the external user could not be authorized.
    """
    config = server_config()
    store = zen_store()

    assert config.external_user_info_url is not None

    # Use the external access token to extract the user information and
    # permissions

    # Get the user information from the external authenticator
    user_info_url = config.external_user_info_url
    headers = {"Authorization": "Bearer " + external_access_token}
    query_params = dict(server_id=str(zen_store().get_deployment_id()))

    try:
        auth_response = requests.get(
            user_info_url,
            headers=headers,
            params=urlencode(query_params),
            timeout=EXTERNAL_AUTHENTICATOR_TIMEOUT,
        )
    except Exception as e:
        logger.exception(
            f"Error fetching user information from external authenticator: "
            f"{e}"
        )
        raise AuthorizationException(
            "Error fetching user information from external authenticator."
        )

    external_user: Optional[ExternalUserModel] = None

    if 200 <= auth_response.status_code < 300:
        try:
            payload = auth_response.json()
        except requests.exceptions.JSONDecodeError:
            logger.exception(
                "Error decoding JSON response from external authenticator."
            )
            raise AuthorizationException(
                "Unknown external authenticator error"
            )

        if isinstance(payload, dict):
            try:
                external_user = ExternalUserModel.parse_obj(payload)
            except Exception as e:
                logger.exception(
                    f"Error parsing user information from external "
                    f"authenticator: {e}"
                )
                pass

    elif auth_response.status_code == 401:
        raise AuthorizationException("Not authorized to access this server.")
    else:
        logger.error(
            f"Error fetching user information from external authenticator. "
            f"Status code: {auth_response.status_code}, "
            f"Response: {auth_response.text}"
        )
        raise AuthorizationException(
            "Error fetching user information from external authenticator. "
        )

    if not external_user:
        raise AuthorizationException("Unknown external authenticator error")

    # With an external user object, we can now authenticate the user against
    # the ZenML server

    # Check if the external user already exists in the ZenML server database
    # If not, create a new user. If yes, update the existing user.
    try:
        user = store.get_external_user(user_id=external_user.id)

        # Update the user information
        user = store.update_user(
            user_id=user.id,
            user_update=UserUpdateModel(
                name=external_user.name or external_user.email,
                full_name=external_user.name or "",
                email_opted_in=True,
                active=True,
                email=external_user.email,
            ),
        )
    except KeyError:
        logger.info(
            f"External user with ID {external_user.id} not found in ZenML "
            f"server database. Creating a new user."
        )
        user = store.create_user(
            UserRequestModel(
                name=external_user.name or external_user.email,
                full_name=external_user.name or "",
                external_user_id=external_user.id,
                email_opted_in=True,
                active=True,
                email=external_user.email,
            )
        )

        # Create a new user role assignment for the new user
        store.create_user_role_assignment(
            UserRoleAssignmentRequestModel(
                role=store._admin_role.id,
                user=user.id,
                workspace=None,
            )
        )

    return AuthContext(user=user)


def http_authentication(
    security_scopes: SecurityScopes,
    credentials: HTTPBasicCredentials = Depends(HTTPBasic()),
) -> AuthContext:
    """Authenticates any request to the ZenML Server with basic HTTP authentication.

    Args:
        security_scopes: Security scope will be ignored for http_auth
        credentials: HTTP basic auth credentials passed to the request.

    Returns:
        The authentication context reflecting the authenticated user.

    Raises:
        HTTPException: If the credentials are invalid.
    """
    try:
        return authenticate_credentials(
            user_name_or_id=credentials.username, password=credentials.password
        )
    except AuthorizationException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Basic"},
        )


class CookieOAuth2TokenBearer(OAuth2PasswordBearer):
    """OAuth2 token bearer authentication scheme that uses a cookie."""

    async def __call__(self, request: Request) -> Optional[str]:
        """Extract the bearer token from the request.

        Args:
            request: The request.

        Returns:
            The bearer token extracted from the request cookie or header.
        """
        # First, try to get the token from the cookie
        authorization = request.cookies.get(server_config().auth_cookie_name)
        if authorization:
            logger.info("Got token from cookie")
            return authorization

        # If the token is not present in the cookie, try to get it from the
        # Authorization header
        return await super().__call__(request)


def oauth2_authentication(
    security_scopes: SecurityScopes,
    token: str = Depends(
        CookieOAuth2TokenBearer(
            tokenUrl=server_config().root_url_path + API + VERSION_1 + LOGIN,
            scopes={
                "read": "Read permissions on all entities",
                "write": "Write permissions on all entities",
                "me": "Editing permissions to own user",
            },
        )
    ),
) -> AuthContext:
    """Authenticates any request to the ZenML server with OAuth2 JWT tokens.

    Args:
        security_scopes: Security scope for this token
        token: The JWT bearer token to be authenticated.

    Returns:
        The authentication context reflecting the authenticated user.

    Raises:
        HTTPException: If the JWT token could not be authorized.
    """
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    try:
        auth_context = authenticate_credentials(access_token=token)
    except AuthorizationException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": authenticate_value},
        )

    for scope in security_scopes.scopes:
        if (
            auth_context.access_token
            and scope not in auth_context.access_token.permissions
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )

    return auth_context


def no_authentication(security_scopes: SecurityScopes) -> AuthContext:
    """Doesn't authenticate requests to the ZenML server.

    Args:
        security_scopes: Security scope will be ignored for http_auth

    Returns:
        The authentication context reflecting the default user.
    """
    return authenticate_credentials(user_name_or_id=DEFAULT_USERNAME)


def authentication_provider() -> Callable[..., AuthContext]:
    """Returns the authentication provider.

    Returns:
        The authentication provider.

    Raises:
        ValueError: If the authentication scheme is not supported.
    """
    auth_scheme = server_config().auth_scheme
    if auth_scheme == AuthScheme.NO_AUTH:
        return no_authentication
    elif auth_scheme == AuthScheme.HTTP_BASIC:
        return http_authentication
    elif auth_scheme == AuthScheme.OAUTH2_PASSWORD_BEARER:
        return oauth2_authentication
    elif auth_scheme == AuthScheme.EXTERNAL:
        return oauth2_authentication
    else:
        raise ValueError(f"Unknown authentication scheme: {auth_scheme}")


authorize = authentication_provider()
