import os

import networkx as nx
import pytest
from pytest_mock import mocker

import conda_gitlab_ci.compute_build_graph
from .utils import (testing_workdir, testing_git_repo, testing_graph, testing_conda_resolve,
                    testing_metadata)

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
graph_data_dir = os.path.join(test_data_dir, 'graph_data')


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
    g = conda_gitlab_ci.compute_build_graph.construct_graph(graph_data_dir, 'some_os', 'somearch',
                                                            folders=('b'))
    assert set(g.nodes()) == set(['a', 'b', 'c', 'd'])
    assert not any([g.node[dirname]['dirty'] for dirname in ('a', 'c', 'd')])
    assert g.node['b']['dirty']
    assert set(g.edges()) == set([('b', 'a'), ('c', 'b'), ('d', 'c')])


def test_construct_graph_git_rev(testing_git_repo):
    g = conda_gitlab_ci.compute_build_graph.construct_graph(testing_git_repo, 'some_os', 'somearch')
    assert set(g.nodes()) == set(['test_dir_3', 'test_dir_2', 'test_dir_1'])
    assert g.node['test_dir_3']['dirty']
    assert not any([g.node[dirname]['dirty'] for dirname in ('test_dir_1', 'test_dir_2')])
    assert set(g.edges()) == set([('test_dir_2', 'test_dir_1'),
                                  ('test_dir_3', 'test_dir_2')])
    g = conda_gitlab_ci.compute_build_graph.construct_graph(testing_git_repo, 'some_os', 'somearch',
                                                            git_rev="HEAD@{2}", stop_rev="HEAD")
    assert set(g.nodes()) == set(['test_dir_3', 'test_dir_2', 'test_dir_1'])
    assert all([g.node[dirname]['dirty'] for dirname in ('test_dir_2',
                                                         'test_dir_3')])
    assert set(g.edges()) == set([('test_dir_2', 'test_dir_1'),
                                  ('test_dir_3', 'test_dir_2')])


def test_platform_specific_graph():
    g = conda_gitlab_ci.compute_build_graph.construct_graph(graph_data_dir, 'win', 32,
                                                            folders=('a'), deps_type='run_test')
    assert set(g.edges()) == set([('a', 'c'), ('b', 'c'), ('c', 'd')])
    g = conda_gitlab_ci.compute_build_graph.construct_graph(graph_data_dir, 'win', 64,
                                                            folders=('a'), deps_type='run_test')
    assert set(g.edges()) == set([('a', 'd'), ('a', 'c'), ('b', 'c'), ('c', 'd')])


def test_run_test_graph():
    g = conda_gitlab_ci.compute_build_graph.construct_graph(graph_data_dir, 'some_os', 'somearch',
                                                            folders=('d'), deps_type='run_test')
    assert set(g.nodes()) == set(['a', 'b', 'c', 'd'])
    assert set(g.edges()) == set([('b', 'c'), ('c', 'd')])


def test_describe_meta(testing_metadata):
    d = conda_gitlab_ci.compute_build_graph.describe_meta(testing_metadata)
    assert 'build' in d
    assert d['build'] == '1'
    assert 'build_depends' in d
    assert d['build_depends'] == {'build_requirement': ""}
    assert 'run_test_depends' in d
    assert d['run_test_depends'] == {'run_requirement': "1.0", 'test_requirement': ""}
    assert 'version' in d
    assert d['version'] == '1.0'


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


def test_expand_dirty_step_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, 'upstream_dependencies_needing_build')
    conda_gitlab_ci.compute_build_graph.upstream_dependencies_needing_build.return_value = set(['b'])
    dirty = conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve, steps=1)
    assert dirty == set(['b', 'c'])
    dirty = conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve, steps=2)
    assert dirty == set(['b', 'c', 'd'])

def test_expand_raises_when_neither_installable_or_buildable(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')
    conda_gitlab_ci.compute_build_graph._installable.return_value = False
    conda_gitlab_ci.compute_build_graph._buildable.return_value = False
    with pytest.raises(ValueError):
        conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve)


def test_expand_dirty_build_non_installable_prereq(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_buildable')
    conda_gitlab_ci.compute_build_graph._installable.return_value = False
    conda_gitlab_ci.compute_build_graph._buildable.return_value = True
    dirty = conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve)
    assert dirty == set(['a', 'b'])
    dirty = conda_gitlab_ci.compute_build_graph.expand_dirty(testing_graph, testing_conda_resolve, steps=1)
    assert dirty == set(['a', 'b', 'c'])



def test_order_build_no_filter(testing_graph):
    g, order = conda_gitlab_ci.compute_build_graph.order_build(testing_graph,
                                                               filter_dirty=False)
    assert order == ['a', 'b', 'c', 'd']

    with pytest.raises(ValueError):
        testing_graph.add_edge('a', 'd')
        conda_gitlab_ci.compute_build_graph.order_build(testing_graph, filter_dirty=False)


def test_order_build(testing_graph):
    g, order = conda_gitlab_ci.compute_build_graph.order_build(testing_graph)
    assert order == ['b']
