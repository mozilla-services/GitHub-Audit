#!/usr/bin/env python
"""
    Report on branches that don't match protection guidelines from local json
    data.
"""
_epilog = """
Currently checks for the following checkboxes to be enabled on the default
branch:
    Protect this branch
    Restrict who can commit to this branch
    Require signed commits
    Include Administrators
"""
import argparse  # noqa: E402
import collections  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
# import tinydb  # noqa: E402

DEBUG = False
logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        for all repos
            check restrictions
            ouput default branch protection
"""

Repo = collections.namedtuple('Repo', "name protected restricted enforcement"
                              " signed team_used".split())


def report_repos(repo_dict):
    def get_nested(eventual_obj, *keys, default=None):
        for key in keys:
            try:
                eventual_obj = eventual_obj[key]
            except (KeyError, TypeError):
                eventual_obj = default
        return eventual_obj

    report = []
    for name, info in ((k, v) for k, v in repo_dict.items() if '/' in k):
        protected = get_nested(info, "default_protected", default=False)
        # protections apply to admins
        enforcement = get_nested(info, "protections", "enforce_admins",
                                 "enabled", default=False)
        # limit commits to default
        num_teams = len(get_nested(info, "protections", "restrictions",
                                   "teams", default=[]))
        num_users = len(get_nested(info, "protections", "restrictions",
                                   "users", default=[]))
        limited_commits = bool(num_teams + num_users > 0)
        # commits signed
        signing_required = get_nested(info, "signatures", "enabled",
                                      default=False)
        # prefer team restrictions
        team_preferred = num_teams > 0 and num_users == 0
        repo = Repo(name, protected, limited_commits, enforcement,
                    signing_required, team_preferred)
        report.append(repo)
    writer = csv.writer(sys.stdout)
    writer.writerow(Repo._fields)
    writer.writerows(report)
    # print(report)


def main(driver=None):
    args = parse_args()
    repos = json.loads(args.infile.read())
    if 'branch_results' in repos:
        # tinydb file, hack for now
        br = repos['branch_results']
        repos = {v["repo"]: v["branch"] for v in br.values()}
        # print(repos)
    report_repos(repos)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument('--debug', help='Enter pdb on problem',
                        action='store_true')
    parser.add_argument("infile", help="input json file",
                        type=argparse.FileType(), nargs="?", default=sys.stdin)
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s')
    try:
        rc = main()
    except (KeyboardInterrupt, BrokenPipeError):
        rc = 2
    raise SystemExit(rc)
