# Copyright 2019 RStudio, Inc.
# All rights reserved.
#
# Use of this source code is governed by a BSD 2-Clause
# license that can be found in the LICENSE_BSD file.

from textwrap import dedent

import pytest
from dockermap.api import DockerClientWrapper

from ursabot.docker import DockerImage, ImageCollection
from ursabot.docker import RUN, CMD, WORKDIR, apk, apt, pip, conda


@pytest.fixture
def image():
    steps = [
        RUN(apt('python', 'python-pip')),
        RUN(pip('six', 'toolz')),
        CMD(['python']),
        WORKDIR('/buildbot')
    ]
    return DockerImage('worker-image', base='ubuntu', os='ubuntu',
                       arch='amd64', steps=steps)


@pytest.fixture
def collection():
    a = DockerImage('a', base='ubuntu', os='ubuntu', arch='amd64', steps=[])
    b = DockerImage('b', base='centos', os='centos', arch='arm64v8', steps=[])
    c = DockerImage('c', base=a, steps=[])
    d = DockerImage('d', base=c, steps=[])
    e = DockerImage('e', base=c, steps=[])
    f = DockerImage('f', base=b, steps=[])
    g = DockerImage('g', base=b, steps=[])
    h = DockerImage('h', base=g, steps=[])
    i = DockerImage('i', base=f, steps=[])
    j = DockerImage('j', base=e, steps=[])
    k = DockerImage('k', base=e, steps=[])
    return ImageCollection(
        # not in order to test toposort
        [k, b, e, j, i, a, c, d, f, g, h]
    )


def test_basics():
    mother = DockerImage('mother', base='ubuntu', os='ubuntu', arch='amd64')
    assert mother.fqn == 'amd64-ubuntu-mother:latest'
    assert mother.name == 'mother'
    assert mother.base == 'ubuntu'
    assert mother.os == 'ubuntu'
    assert mother.arch == 'amd64'
    assert mother.steps == tuple()
    assert mother.variant is None

    stepmother = DockerImage('mother', base='centos', os='centos',
                             variant='step', arch='amd64')
    assert stepmother.fqn == 'amd64-centos-step-mother:latest'
    assert stepmother.name == 'mother'
    assert stepmother.base == 'centos'
    assert stepmother.os == 'centos'
    assert stepmother.arch == 'amd64'
    assert stepmother.steps == tuple()
    assert stepmother.variant == 'step'

    with pytest.raises(ValueError):
        DockerImage('child', base=mother, arch='aarm64v8')
    with pytest.raises(ValueError):
        DockerImage('child', base=mother, os='debian')

    child = DockerImage('child', base=mother)
    assert child.fqn == 'amd64-ubuntu-child:latest'
    assert child.name == 'child'
    assert child.base == mother
    assert child.os == 'ubuntu'
    assert child.arch == 'amd64'
    assert child.steps == tuple()

    variant = DockerImage('variant', base=mother, variant='conda')
    assert variant.fqn == 'amd64-ubuntu-conda-variant:latest'
    assert variant.name == 'variant'
    assert variant.base == mother
    assert variant.os == 'ubuntu'
    assert variant.arch == 'amd64'
    assert variant.steps == tuple()

    grandchild = DockerImage('grandchild', base=child, tag='awesome')
    assert grandchild.fqn == 'amd64-ubuntu-grandchild:awesome'
    assert grandchild.name == 'grandchild'
    assert grandchild.base == child
    assert grandchild.os == 'ubuntu'
    assert grandchild.arch == 'amd64'
    assert grandchild.steps == tuple()


def test_apk():
    cmd = "apk add --no-cache -q \\\n"
    tab = ' ' * 8
    assert apk('bash') == f"{cmd}{tab}bash\n"
    assert apk('bash', 'cmake') == f"{cmd}{tab}bash \\\n{tab}cmake\n"


def test_shortcuts_smoke():
    for fn in [apk, apt]:
        assert 'ninja' in fn('ninja')
        assert 'cmake' in fn('ninja', 'cmake', 'make')

    for fn in [pip, conda]:
        assert 'six' in fn('six')
        assert 'numpy' in fn('six', 'numpy', 'pandas')
        assert 'requirements.txt' in fn('six', files=['requirements.txt'])


def test_dockerfile_dsl(image):
    assert image.repo == 'amd64-ubuntu-worker-image'
    assert image.base == 'ubuntu'
    assert image.workdir == '/buildbot'

    dockerfile = str(image.dockerfile)
    expected = dedent("""
        FROM ubuntu

        RUN export DEBIAN_FRONTEND=noninteractive && \\
            apt-get update -y -q && \\
            apt-get install -y -q \\
                python \\
                python-pip && \\
            rm -rf /var/lib/apt/lists/*

        RUN pip install \\
                six \\
                toolz

        CMD ["python"]
        WORKDIR /buildbot
    """)
    assert dockerfile.strip() == expected.strip()


def test_docker_image_hashing(collection):
    unique_images = set(collection)
    assert len(unique_images) == len(collection)


def test_docker_image_save(tmp_path, image):
    target = tmp_path / f'{image.repo}.{image.tag}.dockerfile'
    image.save_dockerfile(tmp_path)
    assert target.read_text().startswith('FROM ubuntu')


@pytest.mark.docker
@pytest.mark.integration
def test_docker_image_build(image):
    with DockerClientWrapper() as client:
        image.build(client=client)
        assert len(client.images(image.fqn))


def test_image_collection(collection):
    assert isinstance(collection, ImageCollection)
    assert len(collection) == 11

    imgs = [img.name for img in collection.filter(arch='amd64')]
    assert sorted(imgs) == ['a', 'c', 'd', 'e', 'j', 'k']

    imgs = [img.name for img in collection.filter(os='centos')]
    assert sorted(imgs) == ['b', 'f', 'g', 'h', 'i']


@pytest.mark.docker
@pytest.mark.integration
def test_image_collection_build(collection):
    collection.build()


def test_readme_example():
    images = ImageCollection()

    miniconda = DockerImage('conda', base='continuumio/miniconda3',
                            arch='amd64', os='debian-9')
    pandas = DockerImage('pandas', base=miniconda, steps=[
        RUN(conda('pandas'))
    ])
    pyarrow = DockerImage('pyarrow', base=miniconda, steps=[
        RUN(conda('pyarrow'))
    ])
    images.extend([miniconda, pandas, pyarrow])

    images.extend([
        DockerImage(
            name=img.name,
            base=img,
            tag='jupyter',
            steps=[
                RUN(conda('jupyter')),
                CMD(['jupyter', 'notebook', '--ip', '0.0.0.0', '--no-browser',
                     '--allow-root'])
            ]
        ) for img in images
    ])

    assert len(images) == 6
    assert len(images.filter(name='pyarrow', tag='jupyter')) == 1
