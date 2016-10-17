from __future__ import print_function, division
import os
import six

import requests


def _get_url_from_env_vars(url_type, commit_sha=None):
    ci_urls = {"trigger": "/api/v3/projects/{id}/trigger/builds",
               "status": "/api/v3/projects/{id}/repository/commits/{sha}/statuses"}
    # These CI variables are set by gitlab during a build.
    base_url = os.getenv("CI_PROJECT_URL")
    if not base_url:
        raise ValueError("Did not get value for CI_PROJECT_URL.  Please set this"
                         "variable and try again.")
    url = six.moves.urllib.parse.urlsplit(base_url)
    project_id = os.getenv("CI_PROJECT_ID")
    if not commit_sha:
        commit_sha = os.getenv("CI_BUILD_REF")
    if not project_id:
        raise ValueError("Did not get value for CI_PROJECT_ID.  "
                            "You must provide ci_submit_url arg if not "
                            "running under a gitlab ci build.")
    if not commit_sha:
        raise ValueError("Did not get value for CI_BUILD_REF.  "
                            "You must provide ci_submit_url arg if not "
                            "running under a gitlab ci build.")
    location = ci_urls[url_type].format(id=project_id, sha=commit_sha)
    ci_url = six.moves.urllib.parse.urlunsplit((url.scheme, url.hostname, location,
                                  "", ""))
    return ci_url


def submit_job(configuration, repo_ref, ci_submit_url=None, ci_submit_token=None, **kwargs):
    """returns job id for later checking on status"""
    if 'BUILD_RECIPE' not in configuration['variables']:
        return
    if not ci_submit_url:
        ci_submit_url = _get_url_from_env_vars('trigger')

    if not ci_submit_token:
        ci_submit_token = os.getenv('TRIGGER_TOKEN')
        if not ci_submit_token:
            raise ValueError("Did not get value for TRIGGER_TOKEN.  "
                             "You must provide ci_submit_url arg if not "
                             "running under a gitlab ci build.  Also, you must"
                             "set the TRIGGER_TOKEN secret environment "
                             "variable for your project.")
    configuration.update({
        'token': ci_submit_token,
        'ref': repo_ref,
    })

    response = requests.post(ci_submit_url, json=configuration)
    assert response.ok, "Failed to submit job.  Error message was: %s" % response.text
    return response.json()['id']


def check_job_status(build_id, commit_sha=None, ci_status_url=None, **kwargs):
    """
    Queries status of build.  Note that build_id and repo_ref are strongly tied.
       If a build_id does not exist for a given repo_ref, then you'll get an
       empty list back.

    returns one of:
      - success
      - pending
      - running
      - failed
    """
    if not commit_sha:
        commit_sha = os.getenv("CI_BUILD_REF")
    if not ci_status_url:
        ci_status_url = _get_url_from_env_vars('status', commit_sha)
    # need a token to use API.  This should be set using private variables.
    private_token = os.getenv("GITLAB_PRIVATE_TOKEN")
    if not private_token:
        raise ValueError("Did not get value for GITLAB_PRIVATE_TOKEN.  "
                        "You must set the GITLAB_PRIVATE_TOKEN secret environment "
                        "variable for your project.")
    ci_status_url = six.moves.urllib.parse.urljoin(ci_status_url, '?private_token=' + private_token)
    response = requests.get(ci_status_url).json()
    status = [build['status'] for build in response if int(build['id']) == build_id][0]
    return status
