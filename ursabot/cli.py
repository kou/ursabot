# Copyright 2019 RStudio, Inc.
# All rights reserved.
#
# Use of this source code is governed by a BSD 2-Clause
# license that can be found in the LICENSE_BSD file.

import click
import logging
import toolz
from pathlib import Path

from dockermap.api import DockerClientWrapper

from .docker import images


logging.basicConfig()
logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose/--quiet', '-v', default=False, is_flag=True)
@click.pass_context
def ursabot(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    if verbose:
        logging.getLogger('ursabot').setLevel(logging.INFO)


@ursabot.group()
@click.option('--docker-host', '-dh', default=None,
              help='Docker host url in form: tcp://127.0.0.1:2375')
@click.option('--docker-username', '-du', default=None,
              help='Username to authenticate dockerhub with')
@click.option('--docker-password', '-dp', default=None,
              help='Password to authenticate dockerhub with')
@click.option('--arch', '-a', default=None,
              help='Filter images by architecture')
@click.option('--os', '-o', default=None,
              help='Filter images by operating system')
@click.option('--tag', '-t', default=None,
              help='Filter images by operating system')
@click.option('--variant', '-v', default=None,
              help='Filter images by variant')
@click.option('--name', '-n', default=None, help='Filter images by name')
@click.pass_context
def docker(ctx, docker_host, docker_username, docker_password, **kwargs):
    """Subcommand to build docker images for the docker builders"""
    if ctx.obj['verbose']:
        logging.getLogger('dockermap').setLevel(logging.INFO)

    client = DockerClientWrapper(docker_host)
    if docker_username is not None:
        client.login(username=docker_username, password=docker_password)

    filters = toolz.valfilter(lambda x: x is not None, kwargs)
    docker_images = images.filter(**filters)

    ctx.obj['client'] = client
    ctx.obj['images'] = docker_images


@docker.command('list')
@click.pass_context
def list_images(ctx):
    """List the docker images"""
    images = ctx.obj['images']
    for image in images:
        click.echo(image)


@docker.command()
@click.option('--push/--no-push', '-p', default=False,
              help='Push the built images')
@click.option('--nocache/--cache', default=False,
              help='Do not use cache when building the images')
@click.pass_context
def build(ctx, push, nocache):
    """Build docker images"""
    client = ctx.obj['client']
    images = ctx.obj['images']

    images.build(client=client, nocache=nocache)
    if push:
        images.push(client=client)


@docker.command()
@click.option('--directory', '-d', default='images',
              help='Path to the directory where the images should be written')
@click.pass_context
def write_dockerfiles(ctx, directory):
    """Write the corresponding Dockerfile for the images"""
    images = ctx.obj['images']
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    for image in images:
        image.save_dockerfile(directory)
