import os

from conda_gitlab_ci import build_matrix as bm

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


def test_expand_build_matrix():
    # python version specified; ignores matrix for python
    configurations = bm.expand_build_matrix('python_version_specified',
                                            repo_base_dir=test_data_dir,
                                            label='dummy')
    assert len(configurations) == 1

    # python version not specified; uses matrix for python
    # (python 2 + python 3) = 6
    configurations = bm.expand_build_matrix('python_test',
                                            repo_base_dir=test_data_dir,
                                            label='dummy')
    assert len(configurations) == 2

    # (python 2 + python 3) = 6
    configurations = bm.expand_build_matrix('python_numpy_no_xx',
                                            repo_base_dir=test_data_dir,
                                            label='dummy')
    assert len(configurations) == 2

    # (python 2 + python 3) * (numpy 1.10 + 1.11) = 12
    configurations = bm.expand_build_matrix('python_numpy_xx',
                                            repo_base_dir=test_data_dir,
                                            label='dummy')
    assert len(configurations) == 4


def test_load_platforms():
    platforms = bm.load_platforms(os.path.join(test_data_dir, 'platforms.d'))
    assert len(platforms) == 3
    assert 'worker_label' in platforms[0]
    assert 'platform' in platforms[0]
    assert 'arch' in platforms[0]
