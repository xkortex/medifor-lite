#!/bin/python

import sys
import logging
import subprocess as subp
import uuid
import json

import click

from google.protobuf import json_format

from medifor.v1 import analyticservice
from medifor.v1.analytic_pb2 import ImageManipulation, ImageManipulationRequest
from medifor.v1 import pipeclient

log = logging.getLogger(__name__)


class Context:
    pass


def pushdown_json_extractor(s: str) -> str:
    """An extremely primitive 'parser' for extracting JSON-looking data from non-entirely-json
    strings. Do not trust this to handle more than the most trivial of cases

    :param s: string that should contain one valid json object, possibly surrounded by junk

    :returns: string of isolated JSON data

    Examples:
        >>> d1 = {"foo": "o'brien", "quotes": '"', "naughty":{"braces": "}", "escapes": r"\"}}
        >>> s1 =  json.dumps(d1,indent=2, sort_keys=True)
        >>> s2 = "junk" + s1 + "spam"
        >>> s3 = pushdown_json_extractor(s2)
        >>> assert s1 == s3
        >>> d2 = json.loads(s3)
        >>> assert d1 == d2

    """
    brace_count = 0
    quote_count = 0
    escape_count = 0
    brace_starts = []
    brace_ends = []

    for i, c in enumerate(s):
        if escape_count:
            if c == '\\':
                raise ValueError("Cannot handle nested escapes")
            escape_count = 0
            continue

        if c == '\\':
            escape_count += 1
            print('escape: {}'.format(escape_count))
            continue

        if quote_count == 0:
            if c == '"':
                quote_count += 1
                continue

            if c == '{':
                brace_starts.append(i)
                brace_count += 1

            elif c == '}':
                brace_ends.append(i)
                brace_count -= 1
        elif quote_count == 1:
            if c == '"':
                quote_count -= 1
                continue

        else:
            raise ValueError("Quote count unbalanced: {}".format(quote_count))

        if brace_count < 0:
            raise json.JSONDecodeError("Unexpected closing brace", s, i)

    if brace_count != 0:
        raise json.JSONDecodeError("Unbalanced brace count: {}".format(brace_count), s, i - 1)

    #     return brace_starts, brace_ends
    if not brace_starts:
        raise json.JSONDecodeError("Does not look like JSON", s, 0)
    start = brace_starts[0]
    end = brace_ends[-1]
    return s[start:end + 1]


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
        The JSON block be pretty-printed and should start and end with braces on their
        own lines
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

        extracted_out = pushdown_json_extractor(out)
        msgdict = json.loads(extracted_out)
        json_format.ParseDict(msgdict, resp)


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
