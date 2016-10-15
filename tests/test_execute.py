import time

from conda_gitlab_ci import execute
import conda_gitlab_ci

from distributed import LocalCluster, Client, progress
import pytest
from pytest_mock import mocker

from .utils import testing_graph, test_data_dir, testing_conda_resolve
from . import utils


def dask_evaluate(outputs):
    utils.port_increment += 2
    scheduler_port = 8786 + utils.port_increment
    diagnostics_port = 8787 + utils.port_increment

    cluster = LocalCluster(n_workers=1, threads_per_worker=10, nanny=False,
                           scheduler_port=scheduler_port, diagnostics_port=diagnostics_port)
    client = Client(cluster)
    futures = client.persist(outputs)
    return client.gather(futures)


def test_build(mocker):
    mocker.patch.object(execute, 'submit_build')
    mocker.patch.object(execute, 'check_build_status')
    mocker.patch.object(execute, 'delayed')
    execute.check_build_status.return_value = 'success'
    ret = execute._build('something', None, commit_sha='abc')
    assert ret == 'abc'

    with pytest.raises(Exception):
        execute.check_build_status.return_value = 'failed'
        ret = execute._build('something', None, commit_sha='abc')


def test_build_passthrough():
    ret = execute._build({'something': 123}, None, passthrough=True)
    assert ret == {'something': 123}


def test_build_wait_and_timeout(mocker):
    mocker.patch.object(execute, 'submit_build')
    mocker.patch.object(execute, 'check_build_status')
    execute.check_build_status.return_value = 'running'
    now = time.time()
    with pytest.raises(Exception):
        execute._build('something', None, commit_sha='abc', sleep_interval=0.5, run_timeout=2)
    assert time.time() - now >= 2.0


def test_platform_package_key():
    assert execute._platform_package_key('frank', {'worker_label': 'steve'}) == 'frank_steve'


def test_get_dask_outputs(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(execute, 'construct_graph')
    mocker.patch.object(execute, 'Resolve')
    mocker.patch.object(execute, 'get_index')
    mocker.patch.object(execute, 'expand_dirty')
    mocker.patch.object(execute, '_build')
    mocker.patch.object(execute.subprocess, 'check_call')
    mocker.patch.object(execute.subprocess, 'check_output')
    mocker.patch.object(conda_gitlab_ci.compute_build_graph, '_installable')
    execute.subprocess.check_output.return_value = 'abc'
    execute.construct_graph.return_value = testing_graph
    execute.Resolve.return_value = testing_conda_resolve
    execute._build.return_value = 'abc'
    execute.delayed = lambda x, pure: x
    conda_gitlab_ci.compute_build_graph._installable.return_value = True
    execute.get_dask_outputs(test_data_dir)
