import os
import sys

from conda_gitlab_ci import cli

from dask import delayed
import pytest
from pytest_mock import mocker

from .utils import test_data_dir, testing_workdir

@delayed
def noop():
    pass


def test_default_args(mocker):
    args = [test_data_dir]
    mocker.patch.object(cli, 'get_dask_outputs')
    cli.get_dask_outputs.return_value = [noop(), ]
    cli.build_cli(args)
    cli.get_dask_outputs.assert_called_with(test_data_dir, filter_dirty=True,
                                            git_rev='HEAD', stop_rev=None,
                                            packages=[], steps=0, visualize='')


def test_visualize_generates_output_file(mocker, testing_workdir):
    args = [test_data_dir, '--visualize', 'output.png']
    mocker.patch.object(cli, 'get_dask_outputs')
    cli.get_dask_outputs.return_value = [noop(), ]
    cli.build_cli(args)
    assert os.path.isfile('output.png')


def test_argparse_input(mocker):
    mocker.patch.object(cli, 'get_dask_outputs')
    mocker.patch.object(cli, 'progress')
    mocker.patch('conda_gitlab_ci.cli.LocalCluster')
    mocker.patch('conda_gitlab_ci.cli.Client')
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises(SystemExit):
        cli.build_cli()
