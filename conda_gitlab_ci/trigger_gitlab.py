import os
from itertools import izip, product
import urlparse

import requests
import yaml


def get_target_labels(platforms_dir):
    labels = []
    for f in os.listdir(platforms_dir):
        with open(f) as buff:
            platform = yaml.load(buff)
            labels.append(platform['worker_label'])
    return labels


def get_versions_product(versions_file):
    with open(versions_file) as f:
        dicts = yaml.load(f)
    # http://stackoverflow.com/a/5228294/1170370
    return (dict(izip(dicts, x)) for x in product(*dicts.itervalues()))


def submit_builds(build_recipe, dependent_recipes, repo_ref, repo_base_dir,
                  ci_submit_url=None, ci_submit_token=None):
    if not ci_submit_url:
        # These CI variables are set by gitlab.  We allow passing the URL more
        #    directly for the sake of testing.
        url = urlparse.urlsplit(os.getenv("CI_PROJECT_URL"))
        project_id = os.getenv("CI_PROJECT_ID")
        if not project_id:
            raise ValueError("Did not get value for CI_PROJECT_ID.  "
                             "You must provide ci_submit_url arg if not "
                             "running under a gitlab ci build.")
        location = "/api/v3/projects/{0}/trigger/builds".format(project_id)
        ci_submit_url = urlparse.urlsplit((url.scheme, url.hostname, location,
                                           "", ""))
    if not ci_submit_token:
        ci_submit_token = os.getenv('TRIGGER_TOKEN')
        if not ci_submit_token:
            raise ValueError("Did not get value for TRIGGER_TOKEN.  "
                             "You must provide ci_submit_url arg if not "
                             "running under a gitlab ci build.  Also, you must"
                             "set the TRIGGER_TOKEN secret environment "
                             "variable for your project.")

    platforms_dir = os.path.join(repo_base_dir, 'platforms.d')
    labels = get_target_labels(platforms_dir)
    for label in labels:
        for version_set in get_versions_product(os.path.join(repo_base_dir,
                                                             'versions.yml')):
            requests.post(ci_submit_url, data={
                'variables': version_set.update({
                    "TARGET_PLATFORM": label,
                    "BUILD_RECIPE": build_recipe,
                    "DEPENDENT_RECIPES": dependent_recipes,
                }),
                'token': ci_submit_token,
                'ref': repo_ref,
            })
