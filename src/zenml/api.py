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
"""Public Python API of ZenML.

Everything defined/imported here should be highly import-optimized so we don't
slow down the CLI.
"""


from typing import Optional

from zenml.logger import get_logger

logger = get_logger(__name__)


def show(ngrok: Optional[str] = None) -> None:
    """Show the ZenML dashboard.

    Args:
        ngrok: An ngrok auth token to use for exposing the ZenML dashboard on a
            public domain. Primarily used for accessing the dashboard in Colab.
    """
    from zenml.utils.dashboard_utils import show_dashboard
    from zenml.utils.networking_utils import get_or_create_ngrok_tunnel
    from zenml.zen_server.utils import get_active_server_details

    url, port = get_active_server_details()

    if ngrok and port:
        url = get_or_create_ngrok_tunnel(ngrok_token=ngrok, port=port)
        logger.info(f"Exposing ZenML dashboard at {url}.")

    show_dashboard(url)
