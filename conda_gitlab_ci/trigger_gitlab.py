from itertools import izip, product
import os
from time import sleep
import urlparse


import requests
import yaml
from conda_build import api
from dask import delayed


def load_platforms(platforms_dir):
    platforms = []
    for f in os.listdir(platforms_dir):
        if f.endswith('.yml'):
            with open(os.path.join(platforms_dir, f)) as buff:
                platforms.append(yaml.load(buff))
    return platforms


def _filter_environment_with_metadata(build_recipe, version_dicts):
    def del_key(version_dicts, key):
        if key == 'python':
            key = 'py'
        elif key == 'numpy':
            key = 'npy'
        elif key == 'r-base':
            key = 'r'
        del version_dicts['CONDA_' + key.upper()]
        return version_dicts

    metadata, _, _ = api.render(build_recipe)

    for name in ('numpy', 'python', 'perl', 'lua', 'r-base'):
        for req in metadata.get_value('requirements/run'):
            if hasattr(req, 'encode'):
                req = req.encode('utf-8')
            req_parts = req.split(' ')
            if req_parts[0] == name:
                # logic here: if a version is provided, then ignore the build matrix - except
                #   numpy.  If numpy has x.x, that is the only way that it is considered part
                #   of the build matrix.
                #
                # Break = keep the recipe (since we don't fall through to del_key for this name)
                if len(req_parts) > 1:
                    if name == 'numpy' and 'x.x' in req_parts:
                        break
                    # we have a version specified for something other than numpy.  This means
                    #    we are overriding our build matrix.  Do not consider this variable.
                    else:
                        continue
                # fall through for numpy when it does not have any associated x.x
                if name == 'numpy':
                    continue
                break
        else:
            version_dicts = del_key(version_dicts, name)
    return version_dicts


def _get_versions_product(build_recipe, versions_file):
    with open(versions_file) as f:
        dicts = yaml.load(f)
    dicts = _filter_environment_with_metadata(build_recipe, dicts)
    # http://stackoverflow.com/a/5228294/1170370
    return (dict(izip(dicts, x)) for x in product(*dicts.itervalues()))


def _get_url_from_env_vars(url_type, commit_sha=None):
    ci_urls = {"trigger": "/api/v3/projects/{id}/trigger/builds",
               "status": "/api/v3/projects/{id}/repository/commits/{sha}/statuses"}
    # These CI variables are set by gitlab during a build.
    base_url = os.getenv("CI_PROJECT_URL")
    if not base_url:
        raise ValueError("Did not get value for CI_PROJECT_URL.  Please set this"
                         "variable and try again.")
    url = urlparse.urlsplit(base_url)
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
    ci_url = urlparse.urlunsplit((url.scheme, url.hostname, location,
                                  "", ""))
    return ci_url


def expand_build_matrix(build_recipe, repo_base_dir, label):
    configurations = []
    if not os.path.isabs(build_recipe):
        build_recipe = os.path.join(repo_base_dir, build_recipe)
    version_sets = _get_versions_product(build_recipe,
                                            os.path.join(repo_base_dir,
                                                        'versions.yml'))
    for version_set in version_sets:
        version_set.update({
                "TARGET_PLATFORM": label,
                "BUILD_RECIPE": build_recipe,
        })
        configurations.append({'variables': version_set})
    return configurations


def submit_build(configuration, repo_ref, ci_submit_url=None, ci_submit_token=None, **kwargs):
    """returns job id for later checking on status"""
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
    import pdb; pdb.set_trace()
    assert response.code < 300, "Failed to submit job.  Error message was: %s" % response.text
    return response.json()['id']


def check_build_status(build_id, commit_sha=None, ci_status_url=None, **kwargs):
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
    ci_status_url = urlparse.urljoin(ci_status_url, '?private_token=' + private_token)
    response = requests.get(ci_status_url).json()
    status = [build['status'] for build in response if int(build['id']) == build_id][0]
    return status


@delayed(pure=True)
def build(configuration, dependencies, commit_sha=None, **kwargs):
    # configuration is the dictionary defined in expand_build_matrix, and includes the package to build
    build_id = submit_build(configuration, commit_sha, **kwargs)
    while True:
        status = check_build_status(build_id, commit_sha=commit_sha, **kwargs)
        if status in ('pending', 'running'):
            sleep(1)
            continue
        if status == 'success':
            break
        if status == 'failed':
            raise Exception("Build failed", (configuration, commit_sha))

    return commit_sha
