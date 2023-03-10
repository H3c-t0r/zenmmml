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
import os
import re
from typing import List, Optional

from github import Github, GithubException
from github.Repository import Repository

from zenml.code_repositories import (
    BaseCodeRepository,
    LocalRepository,
)
from zenml.code_repositories.base_code_repository import (
    BaseCodeRepositoryConfig,
)
from zenml.code_repositories.git import LocalGitRepository
from zenml.logger import get_logger
from zenml.utils.secret_utils import SecretField

logger = get_logger(__name__)


class GitHubCodeRepositoryConfig(BaseCodeRepositoryConfig):
    """Config for GitHub code repositories."""

    url: Optional[str]
    owner: str
    repository: str
    host: Optional[str]
    token: str = SecretField()


class GitHubCodeRepository(BaseCodeRepository):
    """GitHub code repository."""

    @property
    def config(self) -> GitHubCodeRepositoryConfig:
        """Returns the `KubeflowOrchestratorConfig` config.

        Returns:
            The configuration.
        """
        return GitHubCodeRepositoryConfig(**self._config)

    @property
    def github_repo(self) -> Repository:
        """The GitHub repository."""
        return self._github_session.get_repo(
            f"{self.config.owner}/{self.config.repository}"
        )

    def login(
        self,
    ) -> None:
        """Logs in to GitHub."""
        try:
            self._github_session = Github(self.config.token)
            user = self._github_session.get_user().login
            logger.debug(f"Logged in as {user}")
        except Exception as e:
            raise RuntimeError(f"An error occurred while logging in: {str(e)}")

    def download_files(
        self, commit: str, directory: str, repo_sub_directory: Optional[str]
    ) -> None:
        """Downloads files from a commit to a local directory.

        Args:
            commit: The commit to download.
            directory: The directory to download to.
            repo_sub_directory: The sub directory to download from.
        """
        contents = self.github_repo.get_contents(
            repo_sub_directory or "", ref=commit
        )
        if not isinstance(contents, List):
            raise RuntimeError("Invalid repository subdirectory.")

        os.makedirs(directory, exist_ok=True)

        for content in contents:
            local_path = os.path.join(directory, content.name)
            if content.type == "dir":
                self.download_files(
                    commit=commit,
                    directory=local_path,
                    repo_sub_directory=content.path,
                )
            else:
                try:
                    with open(local_path, "wb") as f:
                        f.write(content.decoded_content)
                except (GithubException, IOError) as e:
                    logger.error("Error processing %s: %s", content.path, e)

    def get_local_repo(self, path: str) -> Optional[LocalRepository]:
        """Gets the local repository.

        Args:
            path: The path to the local repository.

        Returns:
            The local repository.
        """
        return LocalGitRepository.at(
            path=path,
            code_repository_id=self.id,
            remote_url_validation_callback=self.check_remote_url,
        )

    def check_remote_url(self, url: str) -> bool:
        """Checks whether the remote url matches the code repository.

        Args:
            url: The remote url.

        Returns:
            Whether the remote url is correct.
        """
        https_url = f"https://github.com/{self.config.owner}/{self.config.repository}.git"
        if url == https_url:
            return True

        ssh_regex = re.compile(
            f".*@github.com:{self.config.owner}/{self.config.repository}.git"
        )
        if ssh_regex.fullmatch(url):
            return True

        return False
