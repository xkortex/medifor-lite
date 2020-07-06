#!/bin/python

import sys
import logging
import subprocess as subp
import uuid

import click

from google.protobuf import json_format

from medifor.v1 import analyticservice
from medifor.v1.analytic_pb2 import ImageManipulation, ImageManipulationRequest
from medifor.v1 import pipeclient

log = logging.getLogger(__name__)


class Context:
    pass


class MediforSubprocServer(object):
    """
    MediforCliServer provides a server which can run a subprocess as a
    "medifor analytic".

    Args:
        name: The name of the executable to run

    """

    def __init__(
        self, name,
    ):
        self.name = name

    def img_manip(self, req: ImageManipulation, resp: ImageManipulationRequest):
        """
        Run a subprocess command.
        We expect this command to emit on stdout ONLY a json-encoded message
        compatible with the ImageManipulation format.
        """
        log.info(req)
        options = dict(getattr(req, "options", {}))  # allows backwards compat with v1.0 (0.2.3), but without options
        cmd = [self.name, req.image.uri, "-o", req.out_dir]
        for key, value in options.items():
            cmd.extend(["--" + key, value])
        log.info(cmd)
        log.info("Running:\n {}".format(" ".join(cmd)))
        p = subp.run(cmd, stdout=subp.PIPE, stderr=subp.PIPE)
        out = p.stdout.decode()
        err = p.stdout.decode()

        if p.returncode != 0:
            # transmit the error across the rpc gap, since client will field it
            raise RuntimeError("Subprocess returned {}. Stderr:\n{}".format(p.returncode, err))
        elif err:
            log.warning("Subprocess stderr:\n{}".format(err))
        json_format.Parse(out, resp)


@click.group()
@click.option("--loglevel", default=20, help="Set the logging level (int)")
@click.pass_context
def main(ctx, loglevel):
    """Run a subprocess command as if it were a "medifor analytic".
    It expects that command to emit a json-encoded ImageManipulation message.
    """
    ctx.ensure_object(Context)
    logging.basicConfig(
        format="%(levelname)-7s[%(filename)s:%(lineno)d] %(message)s",
        datefmt="%d-%m-%Y:%H:%M:%S",
        level=loglevel,
        stream=sys.stderr,
    )
    log.debug("debug on")


@main.command()
@click.argument("name")
@click.option("--port", default="50051", show_default=True, help="Run API service on this port.")
@click.pass_context
def serve(ctx, name, port):
    """Run a subprocess command server as if it were a "medifor analytic".
    It uses the modified (v0.2.4a0) gRPC API but is backwards and forwards compatible with 0.2.3.
    It will ignore the `options` field if missing.
    `name` is the executable name.
    """
    log.info("Starting server for executable name: {}".format(name))
    port = int(port)
    subprocessor = MediforSubprocServer(name)
    svc = analyticservice.AnalyticService()
    svc.RegisterImageManipulation(subprocessor.img_manip)

    sys.exit(svc.Run(port, max_workers=1))


@main.command()
@click.argument("name")
@click.argument("img")
@click.option("--out", "-o", required=True, help="Output directory for analytic to use.")
@click.option("--option", "-D", multiple=True, help="Option maps to apply of the form `tag=value` or 'tag'.")
@click.pass_context
def run(ctx, name, img, out, option):
    """Run an executable directly"""
    log.info("Directly running executable name: {}".format(name))
    tmp_id = str(uuid.uuid4())
    options = pipeclient.parse_tags(option)
    subprocessor = MediforSubprocServer(name)
    req = ImageManipulationRequest(request_id=tmp_id, image={"uri": img}, out_dir=out, options=options)
    resp = ImageManipulation()
    subprocessor.img_manip(req, resp)
    sys.exit(0)


if __name__ == "__main__":
    main(obj=Context())
