import os
import responses

from conda_gitlab_ci import trigger_gitlab
import pytest

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


@pytest.fixture
def set_ci_environ_vars():
    os.environ['GITLAB_PRIVATE_TOKEN'] = 'private_token_value'
    os.environ['TRIGGER_TOKEN'] = 'trigger_token_value'
    os.environ['CI_BUILD_REF'] = "123abc"
    os.environ['CI_PROJECT_ID'] = "2"
    os.environ['CI_PROJECT_URL'] = "http://some.test.ci.com/somegroup/projectname"


@responses.activate
def test_check_build_status(set_ci_environ_vars):
    responses.add(responses.GET,
                  'http://some.test.ci.com/api/v3/projects/2/repository/commits/123abc/statuses',
                  status=200,
                  json=[{"id": 1, "status": "success"}, {"id": 2, "status": "failed"}],
                  content_type='application/json')
    assert trigger_gitlab.check_build_status(1, repo_ref='123abc') == 'success'
    assert trigger_gitlab.check_build_status(2, repo_ref='123abc') == 'failed'


@responses.activate
def test_submit_build(set_ci_environ_vars):
    responses.add(responses.POST,
                  'http://some.test.ci.com/api/v3/projects/2/trigger/builds',
                  status=201,
                  json={'id': 1, 'variables': {'BUILD_RECIPE': 'frank'}},
                  )
    vars = {"variables": {"BUILD_RECIPE": "frank"}}
    assert trigger_gitlab.submit_build(vars, '123abc') == 1
