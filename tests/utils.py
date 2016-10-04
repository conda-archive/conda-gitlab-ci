import os
import subprocess

import pytest


@pytest.fixture(scope='function')
def testing_workdir(tmpdir, request):
    """ Create a workdir in a safe temporary folder; cd into dir above before test, cd out after

    :param tmpdir: py.test fixture, will be injected
    :param request: py.test fixture-related, will be injected (see pytest docs)
    """

    saved_path = os.getcwd()

    tmpdir.chdir()
    # temporary folder for profiling output, if any
    tmpdir.mkdir('prof')

    def return_to_saved_path():
        if os.path.isdir(os.path.join(saved_path, 'prof')):
            profdir = tmpdir.join('prof')
            files = profdir.listdir('*.prof') if profdir.isdir() else []

            for f in files:
                f.rename(os.path.join(saved_path, 'prof', f.basename))
        os.chdir(saved_path)

    request.addfinalizer(return_to_saved_path)

    return str(tmpdir)


@pytest.fixture(scope='function')
def testing_git_repo(testing_workdir, request):
    subprocess.check_call(['git', 'init'])
    with open('sample_file', 'w') as f:
        f.write('weee')
    subprocess.check_call(['git', 'add', 'sample_file'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 1'])
    os.makedirs('test_dir_1')
    os.makedirs('not_a_recipe')
    with open(os.path.join('test_dir_1', 'meta.yaml'), 'w') as f:
        # not valid meta.yaml.  Doesn't matter for test.
        f.write('weee')
    with open(os.path.join('not_a_recipe', 'testfile'), 'w') as f:
        f.write('weee')
    subprocess.check_call(['git', 'add', 'test_dir_1'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 2'])
    os.makedirs('test_dir_2')
    with open(os.path.join('test_dir_2', 'meta.yaml'), 'w') as f:
        f.write('weee')
    subprocess.check_call(['git', 'add', 'test_dir_2'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 3'])
    return request
