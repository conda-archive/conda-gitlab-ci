import os

from pytest_mock import mocker

import conda_gitlab_ci.compute_build_graph
from .utils import (testing_workdir, testing_git_repo, testing_graph, testing_conda_resolve,
                    testing_metadata)

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


def test_dirty(testing_graph):
    assert (conda_gitlab_ci.compute_build_graph.dirty(testing_graph) ==
            {'b': {'dirty': True, 'meta': 'something', 'version': "1.0", 'build': "0"}})


def test_get_build_deps(testing_metadata):
    assert (conda_gitlab_ci.compute_build_graph.get_build_deps(testing_metadata) ==
            {'build_requirement': ""})


def test_get_run_test_deps(testing_metadata):
    assert (conda_gitlab_ci.compute_build_graph.get_run_test_deps(testing_metadata) ==
            {'run_requirement': "1.0", 'test_requirement': ""})


def test_construct_graph():
    pass


def test_describe_meta():
    pass


def test_git_changed_recipes_head(testing_git_repo):
    assert (conda_gitlab_ci.compute_build_graph.git_changed_recipes('HEAD') ==
            ['test_dir_3'])


def test_git_changed_recipes_earlier_rev(testing_git_repo):
    assert (conda_gitlab_ci.compute_build_graph.git_changed_recipes('HEAD@{1}') ==
            ['test_dir_2'])


def test_git_changed_recipes_rev_range(testing_git_repo):
    assert (conda_gitlab_ci.compute_build_graph.git_changed_recipes('HEAD@{3}', 'HEAD@{1}') ==
            ['test_dir_1', 'test_dir_2'])


def test_upstream_dependencies_needing_build(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    conda_gitlab_ci.compute_build_graph._installable.return_value = False
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')
    conda_gitlab_ci.compute_build_graph._buildable.return_value = True
    dirty_nodes = conda_gitlab_ci.compute_build_graph.upstream_dependencies_needing_build(
        testing_graph, testing_conda_resolve)
    assert dirty_nodes == set(('a', 'b'))


def test_buildable(monkeypatch):
    monkeypatch.chdir(test_data_dir)
    assert conda_gitlab_ci.compute_build_graph._buildable('somepackage', "")
    assert conda_gitlab_ci.compute_build_graph._buildable('somepackage', "1.2.8")
    assert not conda_gitlab_ci.compute_build_graph._buildable('somepackage', "5.2.9")
    assert not conda_gitlab_ci.compute_build_graph._buildable('not_a_package', "5.2.9")


def test_installable(testing_conda_resolve):
    assert conda_gitlab_ci.compute_build_graph._installable('a', "920", testing_conda_resolve)
    assert not conda_gitlab_ci.compute_build_graph._installable('a', "921", testing_conda_resolve)
    assert not conda_gitlab_ci.compute_build_graph._installable('e', "920", testing_conda_resolve)


def test_expand_dirty_no_up_or_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')

    # all packages are installable in the default index
    conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve)
    assert len(conda_gitlab_ci.compute_build_graph.dirty(testing_graph)) == 1


def test_expand_dirty_build_non_installable_prereq(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')
    conda_gitlab_ci.compute_build_graph._installable.return_value = False
