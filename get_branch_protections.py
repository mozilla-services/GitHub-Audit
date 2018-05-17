#!/usr/bin/env python
"""
    Report on branches that don't match protection guidelines
"""
_epilog = """
"""
import argparse  # noqa: E402
import collections  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from agithub.GitHub import GitHub  # noqa: E402
import tinydb  # noqa: E402

DEBUG = False
CREDENTIALS_FILE = '.credentials'


class AG_Exception(Exception):
    pass


# TinyDB utility functions
def db_setup(org_name):
    ''' HACK
    setup db per org as org_name.db
    setup global queries into it
    '''
    db = tinydb.TinyDB('{}.db.json'.format(org_name))
    global last_table
    last_table = db.table("last_table")
    return db


def db_teardown(db):
    global last_table
    last_table = None
    global branch_results
    branch_results = None
    db.close()


def update_or_insert(table, key, key_value, payload):
    updated_docs = table.update(payload, tinydb.where(key) == key_value)
    if not updated_docs:
        # not in, so insert
        table.insert(payload)


def equals_as_lowercase(db_value, key):
    # Do case insensitive test
    return db_value.lower() == key.lower()


# agithub utility functions
def ag_call(func, *args, expected_rc=None, new_only=True, headers=None,
            **kwargs):
    """
    Wrap AGitHub calls with basic error detection.

    Not smart, and hides any error information from caller.
    But very convenient. :)
    """
    if not headers:
        headers = {}
    last = {}
    url = func.keywords['url']
    if new_only and last_table is not None:
        try:
            # TODO: need to grab most recent (sort desc by when)
            last = last_table.search(tinydb.where('url') == url)[0]['when']
        except IndexError:
            pass
        # prefer last modified, as more readable, but neither guaranteed
        # https://developer.github.com/v3/#conditional-requests
        if 'last-modified' in last:
            headers['If-Modified-Since'] = last['last-modified']
        elif 'etag' in last:
            headers['If-None-Match'] = last['etag']
        real_headers = kwargs.setdefault('headers', {})
        real_headers.update(headers)

    if expected_rc is None:
        expected_rc = [200, 304, ]
    rc, body = func(*args, **kwargs)
    # Handle repo rename/removal corner cases
    if rc == 301:
        logger.error("Permanent Redirect for '{}'".format(url))
        # TODO: do something better, like switch to using id's
        # for now, act like nothing is there
        return []
    elif rc == 404 and rc not in expected_rc:
        logger.error("No longer available or access denied: {}".format(url))
        # TODO: Figure out what to do here. Maybe it's just that message, but
        # maybe need to delete from DB before next run
        return []
    if rc == 304:
        logger.debug("304 for {}".format(url))
    else:
        logger.debug("{} for {}".format(rc, url))
    if new_only and last_table is not None:
        h = {k.lower(): v for k, v in gh.getheaders()}
        for x in 'etag', 'last-modified':
            if x in h:
                last[x] = h[x]
        update_or_insert(last_table, 'url', url, {'url': url, 'when': last})

    if rc not in expected_rc:
        if DEBUG:
            import pudb; pudb.set_trace()  # noqa: E702
        else:
            raise AG_Exception
    return body


def ag_get_all(func, *orig_args, **orig_kwargs):
    """
    Generator for multi-page GitHub responses

    It hacks the "page" query parameter to each call to get the next page. This
    is Not a general solution - it does not follow the links in the headers
    like a good client should.
    """
    kwargs = copy.deepcopy(orig_kwargs)
    args = copy.deepcopy(orig_args)
    kwargs["page"] = 1
    while True:
        body = ag_call(func, *args, **kwargs)
        if len(body) >= 1:
            for elem in body:
                yield elem
        else:
            break
        # fix up to get next page, without changing query set
        kwargs["page"] += 1
        kwargs['new_only'] = False


# JSON support routines
class BytesEncoder(json.JSONEncoder):
    # When reading from the database, an empty value will sometimes be returned
    # as an empty bytes array. Convert to empty string.
    def default(self, obj):
        if isinstance(obj, bytes):
            if not bool(obj):
                return ''
        return self.super(obj)


def get_github_client():
    def get_token():
        token = ''
        with open(CREDENTIALS_FILE, 'r') as cf:
            cf.readline()  # skip first line
            token = cf.readline().strip()
        return token

    token = get_token()
    #  gh = github3.login(token=token)
    gh = GitHub(token=token)
    gh.generateAuthHeader()
    return gh


def ratelimit_dict():
    #  return gh.ratelimit_remaining
    body = ag_call(gh.rate_limit.get)
    return body


def ratelimit_remaining():
    body = ratelimit_dict()
    return body["resources"]["core"]["remaining"]


def wait_for_ratelimit(min_karma=25, msg=None):
    while gh:
        payload = ag_call(gh.rate_limit.get)
        if payload["resources"]["core"]["remaining"] < min_karma:
            core = payload['resources']['core']
            now = time.time()
            nap = max(core['reset'] - now, 0.1)
            logger.info("napping for %s seconds", nap)
            if msg:
                logger.info(msg)
            time.sleep(nap)
        else:
            break


logger = logging.getLogger(__name__)

Pseudo_code = """
    for all orgs
        for all repos
            for all branches
                ouput default branch protection
"""


# SHH, globals, don't tell anyone
gh = None
last_table = None
branch_results = None


def harvest_repo(repo):
    full_name = repo["full_name"]
    name = repo["name"]
    owner = repo["owner"]
    default_branch = repo["default_branch"]
    protected_count = len(list(ag_get_all(gh.repos[full_name].branches.get,
                                          protected='true')))
    details = {
        "owner": owner,
        "name": name,
        "default_branch": default_branch,
        "protected_branch_count": protected_count,
    }
    # if repo is empty, branch retrieval will fail with 404
    try:
        branch = ag_call(gh.repos[full_name].branches[default_branch].get)
        # Yechity
        # branches are almost always updated, since they contain the latest
        # commit information. However, branch protection data may not be
        # updated, and we want to keep those values from last time.
        # Which means we always have to read the old record, and use the values
        # from there - without overwriting the current data.
        # TODO: normalize to not aggregating data
        # no changes since last time
        logger.debug("Getting payload from db")
        record = branch_results.get(tinydb.where('repo') == full_name)
        if branch and record:
            fresh_details = details
            details = record.get('branch', {})
            details.update(fresh_details)
        # always look deeper
        logger.debug("Raw data for %s: %s", default_branch,
                     json.dumps(branch, indent=2, cls=BytesEncoder))
        protection = ag_call(gh.repos[full_name]
                             .branches[default_branch].protection.get,
                             expected_rc=[200, 304, 404])
        logger.debug("Protection data for %s: %s", default_branch,
                     json.dumps(protection, indent=2, cls=BytesEncoder))
        signatures = ag_call(gh.repos[full_name]
                             .branches[default_branch]
                             .protection.required_signatures.get,
                             headers={"Accept":
                                      "application/vnd.github"
                                      ".zzzax-preview+json"},
                             expected_rc=[200, 304, 404])
        logger.debug("Signature data for %s: %s", default_branch,
                     json.dumps(signatures, indent=2, cls=BytesEncoder))
        # the subfields might not have had changes, so don't blindly update
        if branch:
            details.update({"default_protected":
                           bool(branch["protected"])})
        if protection:
            details.update({"protections": protection})
        if signatures:
            details.update({"signatures": signatures})
        update_or_insert(branch_results, 'repo', full_name,
                         {'repo': full_name, 'branch': details})
    except AG_Exception:
        # Assume no branch so add no data
        pass
    return {repo["full_name"]: details}


def harvest_org(org_name):
    def repo_fetcher():
        if org:
            logger.debug("Using API for repos")
            for repo in ag_get_all(gh.orgs[org_name].repos.get):
                yield repo
                wait_for_ratelimit()
        else:
            logger.debug("Using DB for repos")
            query = tinydb.Query()
            for db_doc in branch_results.search(query.branch.owner.login.test(equals_as_lowercase, org_name)):
                repo = db_doc['branch']
                repo['full_name'] = db_doc['repo']
                logger.debug("DB Repo: {}".format(db_doc['repo']))
                yield repo

    logger.debug("Working on org '%s'", org_name)
    org_data = {}
    try:
        org = ag_call(gh.orgs[org_name].get)
    except AG_Exception:
        logger.error("No such org '%s'", org_name)
        return org_data
    for repo in repo_fetcher():
        repo_data = harvest_repo(repo)
        org_data.update(repo_data)
    return org_data


def process_orgs(args=None, collected_as=None):
    logger.info("Gathering branch protection data."
                " (calls remaining %s).", ratelimit_remaining())
    if not args:
        args = {}
    if not collected_as:
        collected_as = '<unknown>'
    results = {}
    for org in args.org:
        try:
            db = db_setup(org)
            global branch_results
            branch_results = db.table('branch_results')
            wait_for_ratelimit()
            if args.repo:
                logger.info("Only processing repo %s", args.repo)
                repo = ag_call(gh.repos[org][args.repo].get)
                org_data = harvest_repo(repo)
            else:
                org_data = harvest_org(org)
            results.update(org_data)
        finally:
            meta_data = {
                "collected_as": collected_as,
                "collected_at": time.time(),
            }
            db.table('collection_data').insert({'meta': meta_data})
            db_teardown(db)
    logger.info("Finshed gathering branch protection data"
                " (calls remaining %s).", ratelimit_remaining())
    return results


def main(driver=None):
    args = parse_args()
    global gh
    gh = get_github_client()
    wait_for_ratelimit()
    body = ag_call(gh.user.get)
    collected_as = body["login"]
    logger.info("Running as {}".format(collected_as))
    data = process_orgs(args, collected_as=collected_as)
    results = {
        "collected_as": collected_as,
        "collected_at": time.time(),
    }
    results.update(data)
    if args.print:
        print(json.dumps(results, indent=2, cls=BytesEncoder))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=_epilog)
    parser.add_argument("org", help='Organization',
                        default=['mozilla-services'],
                        nargs='*')
    parser.add_argument('--repo', help='Only check for this repo')
    parser.add_argument('--debug', help='Enter pdb on problem',
                        action='store_true')
    parser.add_argument('--print', help='print huge json mess',
                        action='store_true')
    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s: %(message)s')
    logging.getLogger('github3').setLevel(logging.WARNING)
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
