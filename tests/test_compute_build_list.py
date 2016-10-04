import os

from conda_gitlab_ci import compute_build_list as cbl
from conda_build.api import metadata_from_dict, render

from .utils import testing_workdir, testing_git_repo

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


def test_get_build_deps():
    pass


def test_describe_meta():
    meta = metadata_from_dict({'package': {
                                  'name': 'testpkg',
                                  'version': 1.0,
                                  },
                               'build': {
                                   'number': 0
                               },
                               'requirements': {
                                   'build': ['steve'],
                                   'run': ['bob  1.0'],
                               },
                               'test': {
                                   'requires': ['frank']
                               }
                               })
    descriptor = cbl.describe_meta(meta)
    assert 'build' in descriptor
    assert descriptor['build'] == 0
    assert 'depends' in descriptor
    assert 'steve' in descriptor['depends']
    assert descriptor['depends']['steve'] == ''
    assert 'bob' in descriptor['depends']
    assert descriptor['depends']['bob'] == '1.0'
    assert 'frank' in descriptor['depends']
    assert descriptor['depends']['frank'] == ''
    assert 'version' in descriptor
    assert descriptor['version'] == 1.0


def test_git_changed_files_single_rev(testing_git_repo):
    folders = cbl.git_changed_recipes('HEAD')
    assert folders == ['test_dir_2']
    folders = cbl.git_changed_recipes('HEAD@{1}')
    assert folders == ['test_dir_1']


def test_git_changed_files_specify_two_revisions(testing_git_repo):
    folders = cbl.git_changed_recipes('HEAD@{2}', 'HEAD')
    assert folders == ['test_dir_1', 'test_dir_2']


def test_dirty():
    pass


def test_build_order():
    pass


def test_construct_graph():
    pass


def test_platform_specific_dependencies():
    # linux-64
    meta, _, _ = render(os.path.join(test_data_dir, 'platform_dependencies'),
                        platform='linux', bits=64)
    assert cbl.get_deps(meta) == {'linux_dep': ''}

    # osx-64
    meta, _, _ = render(os.path.join(test_data_dir, 'platform_dependencies'),
                        platform='osx', bits=64)
    assert cbl.get_deps(meta) == {'osx_dep': '1.0'}

    # win-64 (no dependencies expected)
    meta, _, _ = render(os.path.join(test_data_dir, 'platform_dependencies'),
                        platform='win', bits=64)
    assert cbl.get_deps(meta) == {}

    # win-32
    meta, _, _ = render(os.path.join(test_data_dir, 'platform_dependencies'),
                        platform='win', bits=32)
    assert cbl.get_deps(meta) == {'win_dep': ''}
