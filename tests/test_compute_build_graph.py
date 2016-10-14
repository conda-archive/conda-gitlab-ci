import os

import networkx as nx
from pytest_mock import mocker

import conda_gitlab_ci.compute_build_graph
from .utils import testing_workdir, testing_git_repo, testing_graph, testing_conda_resolve


def test_dirty(testing_graph):
    assert (conda_gitlab_ci.compute_build_graph.dirty(testing_graph) ==
            {'b': {'dirty': True, 'meta': 'something', 'version': "1.0", 'build': "0"}})


def test_get_build_deps():
    pass


def test_get_run_test_deps():
    pass


def test_construct_graph():
    pass


def test_describe_meta():
    pass


def test_git_changed_recipes_head(testing_git_repo):
    pass


def test_git_changed_recipes_rev_range(testing_git_repo):
    pass


def test_upstream_dependencies_needing_build():
    pass


def test_buildable():
    pass


def test_installable(testing_conda_resolve):
    assert conda_gitlab_ci.compute_build_graph._installable('a', "920", testing_conda_resolve)
    assert not conda_gitlab_ci.compute_build_graph._installable('a', "921", testing_conda_resolve)
    assert not conda_gitlab_ci.compute_build_graph._installable('e', "920", testing_conda_resolve)


def test_expand_dirty_no_up_or_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')

    conda_gitlab_ci.compute_build_graph._installable.return_value = True
    conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve)
