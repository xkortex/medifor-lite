#!/usr/bin/env python3

import sys
import json
import click

sys.stderr.write("Dumps an ImageManipulation message json to stdout. This status is stderr and should not be parsed \n")


@click.command()
@click.argument("img")
@click.option("--out", "-o", required=True, help="Output directory for analytic to use.")
@click.option("--foo", "-f", required=False, help="dummy option")
@click.option("--bar", "-b", required=False, help="dummy option")
@click.option("--tle", "-t", required=False, help="dummy option")
def run(img, out, foo, bar, tle, option=None):
    """Run an executable directly"""
    sys.stderr.write("input img: {}\n".format(img))
    sys.stderr.write("options: {}\n".format({"foo": foo, "bar": bar, "tle": tle}))
    d = {
        "score": 0.5,
        "localization": {
            "mask": {"uri": out + "/cli/mask.png", "type": "image/png"},
            "maskOptout": {"uri": out + "/cli/omask.png", "type": "image/png"},
        },
    }

    print(json.dumps(d))
    sys.exit(0)


if __name__ == "__main__":
    run()
