"""Command-line interface for a local marketing workspace."""

import argparse
import contextlib
import os
import sys

from . import __version__, brain, checks, claims, gate, mcp, queue, scaffold, warehouse, workspace
from .errors import MktgError


def _common(parser):
    parser.add_argument("--workspace", "-w", help="client workspace directory")
    parser.add_argument("--now", help="UTC date or timestamp for a reproducible report")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="read command output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mktgkit", description="Review marketing work and measure the result."
    )
    parser.add_argument("--version", action="version", version=f"mktgkit {__version__}")
    _common(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create a new client workspace")
    init.add_argument("target")
    init.add_argument("--name")
    init.add_argument("--example", action="store_true", help="start with the fictional Wrenfield data")
    demo = commands.add_parser("demo", help="replay the fictional engagement offline")
    demo.set_defaults(handler=None)
    commands.add_parser("check", help="validate the whole workspace").set_defaults(handler=checks.handle)
    for module in (queue, claims, gate, brain, warehouse, mcp):
        module.register(commands)
    return parser


def _mutating(args):
    if args.command == "claims":
        return args.claim_command == "approve"
    if args.command == "gate":
        return args.gate_command in ("promote", "demote")
    if args.command == "queue":
        return args.queue_command not in ("list", "show", "render")
    return False


def main(argv=None, *, stdout=None, stderr=None, stdin=None, env=None):
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    inp = sys.stdin if stdin is None else stdin
    env = os.environ if env is None else env
    args = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            # Read workspace switches anywhere, including after a nested subcommand.
            common = argparse.ArgumentParser(add_help=False, allow_abbrev=False, prog="mktgkit")
            _common(common)
            opts, rest = common.parse_known_args(argv)
            args = build_parser().parse_args(rest)
        for key, value in vars(opts).items():
            setattr(args, key, value)
        args.review_env = env
        if args.command == "init":
            target = scaffold.init(args.target, name=args.name, example=args.example)
            print(f'Created {target.name}. Run mktgkit check --workspace "{args.target}".', file=out)
            return 0
        if args.command == "demo":
            from .demo import replay

            return replay(out)
        root = workspace.resolve_root(args.workspace, env)
        config = workspace.config(root)
        now = workspace.clock(config, args.now, env)
        if args.command == "mcp":
            # A long-lived read-only server must leave other CLI processes free to build a fresh warehouse.
            return args.handler(args, root, now, out, inp)
        with workspace.locked(root, mutate=_mutating(args)):
            return args.handler(args, root, now, out, inp)
    except SystemExit as exc:
        return exc.code
    except MktgError as exc:
        print(exc.format(), file=err)
        return 2 if args and getattr(args, "gate_command", "") == "hook" else exc.exit_code
    except (OSError, ValueError) as exc:
        print(f"mktgkit: {exc}", file=err)
        return 2 if args and getattr(args, "gate_command", "") == "hook" else 1
