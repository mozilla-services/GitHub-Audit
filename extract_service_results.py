#!/usr/bin/env python
"""
    join the service name with the score for the repositories it uses
    and output as csv
"""
_epilog = """ """
import argparse  # noqa: E402
import collections  # noqa: E402
import csv  # noqa: E402
import fileinput  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import urllib.parse  # noqa: E402

# import tinydb  # noqa: E402

DEBUG = False
logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        for all repos
            check restrictions
            ouput default branch protection
"""

Repo = collections.namedtuple(
    "Repo", "name protected restricted enforcement signed team_used".split()
)


def report_repos(repo_dict):
    def get_nested(eventual_obj, *keys, default=None):
        for key in keys:
            try:
                eventual_obj = eventual_obj[key]
            except (KeyError, TypeError):
                eventual_obj = default
        return eventual_obj

    report = []
    for name, info in ((k, v) for k, v in repo_dict.items() if "/" in k):
        protected = get_nested(info, "default_protected", default=False)
        # protections apply to admins
        enforcement = get_nested(
            info, "protections", "enforce_admins", "enabled", default=False
        )
        # limit commits to default
        num_teams = len(
            get_nested(info, "protections", "restrictions", "teams", default=[])
        )
        num_users = len(
            get_nested(info, "protections", "restrictions", "users", default=[])
        )
        limited_commits = bool(num_teams + num_users > 0)
        # commits signed
        signing_required = get_nested(info, "signatures", "enabled", default=False)
        # prefer team restrictions
        team_preferred = num_teams > 0 and num_users == 0
        repo = Repo(
            name,
            protected,
            limited_commits,
            enforcement,
            signing_required,
            team_preferred,
        )
        report.append(repo)
    writer = csv.writer(sys.stdout)
    writer.writerow(Repo._fields)
    writer.writerows(report)
    # print(report)


def load_status(files):
    all_status = {}
    for line in fileinput.input(files, mode="r"):
        repo_full_name, *status = line.strip().split(",")
        all_status[repo_full_name] = status
    return all_status


def full_name_from_url(url):
    parts = urllib.parse.urlparse(url)
    # parts.path has leading '/', so first element is empty
    path = parts.path.split("/")
    owner, repo = path[1:3]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return "{}/{}".format(owner, repo)


def main(driver=None):
    args = parse_args()
    status_reports = load_status(args.csv_files)
    for line in args.services.readlines():
        logger.debug("line: '{}'".format(line.strip()))
        service_name, repo_url = json.loads(line)
        full_name = full_name_from_url(repo_url)
        row = [service_name, full_name]
        try:
            row.extend(status_reports[full_name])
        except KeyError:
            row.append("Missing data for repo '{}'".format(full_name))
        print(",".join(row))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument("--debug", help="Enter pdb on problem", action="store_true")
    parser.add_argument("--services", help="input json file", type=argparse.FileType())
    parser.add_argument("csv_files", help="repo status csv files", nargs="+")
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    try:
        rc = main()
    except (KeyboardInterrupt, BrokenPipeError):
        rc = 2
    raise SystemExit(rc)
