import os
import responses

from conda_gitlab_ci import trigger_gitlab
import pytest
from pytest_mock import mocker

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


@pytest.fixture
def set_ci_environ_vars(monkeypatch):
    monkeypatch.setenv('GITLAB_PRIVATE_TOKEN', 'private_token_value')
    monkeypatch.setenv('TRIGGER_TOKEN', 'trigger_token_value')
    monkeypatch.setenv('TRIGGER_TOKEN', 'trigger_token_value')
    monkeypatch.setenv('CI_BUILD_REF', '123abc')
    monkeypatch.setenv('CI_PROJECT_ID', '2')
    monkeypatch.setenv('CI_PROJECT_URL', "http://some.test.ci.com/somegroup/projectname")


@responses.activate
def test_check_build_status(set_ci_environ_vars, monkeypatch):
    responses.add(responses.GET,
                  'http://some.test.ci.com/api/v3/projects/2/repository/commits/123abc/statuses',
                  status=200,
                  json=[{"id": 1, "status": "success"}, {"id": 2, "status": "failed"}],
                  content_type='application/json')
    assert trigger_gitlab.check_build_status(1, repo_ref='123abc') == 'success'
    assert trigger_gitlab.check_build_status(2, repo_ref='123abc') == 'failed'
    monkeypatch.delenv('GITLAB_PRIVATE_TOKEN')
    with pytest.raises(ValueError):
        trigger_gitlab.check_build_status(2, repo_ref='123abc')


@responses.activate
def test_submit_build(set_ci_environ_vars, monkeypatch):
    responses.add(responses.POST,
                  'http://some.test.ci.com/api/v3/projects/2/trigger/builds',
                  status=201,
                  json={'id': 1, 'variables': {'BUILD_RECIPE': 'frank'}},
                  )
    config = {'variables': {'BUILD_RECIPE': 'frank'}}
    assert trigger_gitlab.submit_build(config, '123abc') == 1
    monkeypatch.delenv('TRIGGER_TOKEN')
    with pytest.raises(ValueError):
        trigger_gitlab.submit_build(config, '123abc')


def test_submit_build_with_no_recipe_is_noop():
    config = {"variables": {}}
    assert trigger_gitlab.submit_build(config, '123abc') is None


def test_url_from_env_vars(set_ci_environ_vars, monkeypatch):
    assert (trigger_gitlab._get_url_from_env_vars('trigger') ==
            "http://some.test.ci.com/api/v3/projects/2/trigger/builds")
    assert (trigger_gitlab._get_url_from_env_vars('status') ==
            "http://some.test.ci.com/api/v3/projects/2/repository/commits/123abc/statuses")


@pytest.mark.parametrize("var", ('CI_PROJECT_URL', 'CI_PROJECT_ID', 'CI_BUILD_REF'))
def test_url_from_env_vars_raises_missing_vars(set_ci_environ_vars, monkeypatch, var):
    with pytest.raises(ValueError):
        monkeypatch.delenv(var)
        trigger_gitlab._get_url_from_env_vars('trigger')
        monkeypatch.undo()
