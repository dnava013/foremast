#   Foremast - Pipeline Tooling
#
#   Copyright 2020 Redbox Automated Retail, LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""Retrieve GCP Environments and their configuration"""

from ..consts import GCP_ENVS
from ..exceptions import GoogleInfrastructureError
from google.oauth2 import service_account
from googleapiclient import discovery
import logging

LOG = logging.getLogger(__name__)


class GcpResource:
    def __init__(self, **entries):
        self.project = None
        self.__dict__.update(entries)

    def validate(self):
        if self.project is None:
            raise KeyError("A project must be specified when creating or referencing a GCP Resource")


class GcpEnvironment:

    def __init__(self, name, **entries):
        self.name = name
        self.organization = None
        self._all_projects_cache = []
        self._single_project_cache = dict()
        self.service_account_project = None
        self.service_account_path = None
        self.__dict__.update(entries)

    def get_credentials(self):
        """Gets a GCP service account credentials"""
        credentials = service_account.Credentials.from_service_account_file(
            filename=self.service_account_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform'])
        return credentials

    def get_all_projects(self):
        """Returns all projects in this environment.  If this method is called more
        than once a cached response will be returned to avoid duplicate calls to GCP APIs."""

        # Check cache for all projects in this env to avoid duplicate API calls to GCP
        if len(self._all_projects_cache) > 0:
            LOG.debug("Reusing GCP projects cache for environment {}".format(self.name))
            return self._all_projects_cache

        # No cached response found, check GCP APIs
        service = discovery.build('cloudresourcemanager', 'v1', credentials=self.get_credentials())
        project_filter = self._get_project_api_filter()
        request = service.projects().list(filter=project_filter)
        response = request.execute()
        projects = response.get('projects', [])

        if len(projects) == 0:
            raise GoogleInfrastructureError("No projects returned for filter {}. ".format(project_filter)
                                            + "A Foremast GCP Environment needs at least one project.")

        self._all_projects_cache = projects

        return projects

    def get_project(self, project_prefix):
        """Gets the project for the given project prefix in this environment.
        If duplicate calls to this method with the same arguments are made
        a cached response will be used to avoid duplicate calls to GCP APIs"""

        # Check cache for this project in this env to avoid duplicate API calls to GCP
        if project_prefix in self._single_project_cache:
            LOG.debug("Reusing GCP projects cache for environment {} and project {}".format(self.name, project_prefix))
            return self._single_project_cache[project_prefix]

        # No cached response found, check GCP APIs
        service = discovery.build('cloudresourcemanager', 'v1', credentials=self.get_credentials())
        project_filter = self._get_project_api_filter(name=project_prefix)
        request = service.projects().list(filter=project_filter)
        response = request.execute()
        projects = response.get('projects', [])

        # No projects found
        if len(projects) == 0:
            error_message = "No projects returned for filter {}".format(project_filter)
            raise GoogleInfrastructureError(error_message)

        # If more than one project is found, Foremast cannot determine which project should be used
        # raise and error with the projects so the user can adjust their labels or project_prefix
        if len(projects) > 1:
            error_message = "More than one project returned for filter {}. Projects returned:".format(project_filter)
            for project in projects:
                error_message += " " + project['name']
            raise GoogleInfrastructureError(error_message)

        # Only one project found
        self._single_project_cache[project_prefix] = projects[0]
        return projects[0]

    def _get_project_api_filter(self, name=None):
        """Gets the project filter based on the name and env for use in Google IAM APIs"""
        base_filter = "labels.cloud_env:{}".format(self.name)

        if name is not None:
            base_filter += " name:{}*".format(name)

        return base_filter

    @staticmethod
    def get_environments_from_config():
        gcp_envs = dict()
        for env_name in GCP_ENVS:
            env_config = GCP_ENVS[env_name]
            gcp_envs[env_name] = GcpEnvironment(name=env_name, **env_config)
        return gcp_envs
