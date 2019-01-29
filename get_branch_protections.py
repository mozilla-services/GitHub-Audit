#!/usr/bin/env python
"""
    Gather & locally cache data needed to determing compliance with branch
    protection guidelines
"""
import argparse
import backoff
import copy
import json
import logging
import os
import socket
import time

from agithub.GitHub import GitHub
import tinydb

help_epilog = """
Data will stored in a TinyDB (json) file, named '{org}.db.json'.

WARNING: Remove any prior '{org}.db.json' file prior to execution. There is
         currently a bad bug prevening updating an existing database.
"""

DEBUG = False
CREDENTIALS_FILE = ".credentials"


class AG_Exception(Exception):
    pass


# TinyDB utility functions
def db_setup(org_name):
    """ HACK
    setup db per org as org_name.db
    setup global queries into it
    """
    db_filename = "{}.db.json".format(org_name)
    try:
        file_stat = os.stat(db_filename)
        if file_stat.st_size > 0:
            logger.warn("Updating '%s' may not work.", db_filename)
    except OSError:
        # okay if file doesn't exist
        pass
    try:
        db = tinydb.TinyDB(db_filename)
        global last_table
        last_table = db.table("GitHub")
    except Exception:
        # something very bad. provide some info
        logger.error("Can't create/read db for '{}'".format(org_name))
        raise
    return db


def db_teardown(db):
    global last_table
    last_table = None
    db.close()


def equals_as_lowercase(db_value, key):
    # Do case insensitive test
    return db_value.lower() == key.lower()


def add_media_types(headers):
    """
    Add in the media type to get node_ids (v4) returned
    """
    if "Accept" in headers:
        headers["Accept"] += ", application/vnd.github.jean-grey-preview+json"
    else:
        headers["Accept"] = "application/vnd.github.jean-grey-preview+json"


# agithub utility functions
@backoff.on_exception(backoff.expo, exception=socket.gaierror, max_tries=15)
def retry_call(func, *args, **kwargs):
    # wrapper to allow backoff
    return func(*args, **kwargs)


def ag_call(*args, **kwargs):
    """
    Support old calling convention
    """
    _, body = ag_call_with_rc(*args, **kwargs)
    return body


def ag_call_with_rc(
    func, *args, expected_rc=None, new_only=True, headers=None, no_cache=False, **kwargs
):
    """
    Wrap AGitHub calls with basic error detection and caching in TingDB

    Not smart, and hides any error information from caller.
    But very convenient. :)
    """
    if not headers:
        headers = {}
    add_media_types(headers)
    last = {}
    url = func.keywords["url"]
    doc = {"url": url}
    if new_only and last_table is not None:
        try:
            last = last_table.search(tinydb.where("url") == url)[0]["when"]
        except IndexError:
            pass
        # prefer last modified, as more readable, but neither guaranteed
        # https://developer.github.com/v3/#conditional-requests
        if "last-modified" in last:
            headers["If-Modified-Since"] = last["last-modified"]
        elif "etag" in last:
            headers["If-None-Match"] = last["etag"]
    # Insert our (possibly modified) headers
    real_headers = kwargs.setdefault("headers", {})
    real_headers.update(headers)

    if expected_rc is None:
        expected_rc = [200, 304]
    rc, body = retry_call(func, *args, **kwargs)
    # If we have new information, we want to use it (and store it unless
    # no_cache is true)
    # If we are told our existing info is ok, or there's an error, use the
    # stored info
    if rc == 200:
        doc["rc"] = rc
        doc["body"] = body
    elif rc in (202, 204, 304):
        logger.debug("can't handle {} for {}, using older data".format(rc, url))
        body = doc.get("body", [])
    # Handle repo rename/removal corner cases
    elif rc == 301:
        logger.error("Permanent Redirect for '{}'".format(url))
        # TODO: do something better, like switch to using id's
        # for now, act like nothing is there
        body = doc.get("body", [])
    elif rc == 404 and rc not in expected_rc:
        logger.debug("No longer available or access denied: {}".format(url))
        # TODO: Figure out what to do here. Maybe it's just that message, but
        # maybe need to delete from DB before next run
        body = doc.get("body", [])
        # don't throw on this one
        expected_rc.append(404)
    logger.debug("{} for {}".format(rc, url))
    if (not no_cache) and new_only and last_table is not None:
        h = {k.lower(): v for k, v in gh.getheaders()}
        for x in "etag", "last-modified":
            if x in h:
                last[x] = h[x]
        doc.update({"body": body, "rc": rc, "when": last})
        last_table.upsert(doc, tinydb.where("url") == url)

    # Ignore 204s here -- they come up for many "legit" reasons, such as
    # repositories with no code.
    if rc not in expected_rc + [204]:
        if DEBUG:
            import pudb

            pudb.set_trace()  # noqa: E702
        else:
            logger.error("{} for {}".format(rc, url))
            raise AG_Exception
    return rc, body


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
        # We don't expect to need to get multiple pages for items we cache in
        # the db (we don't handle that). So holler if it appears to be that
        # way, even if only one page is returned.
        if not orig_kwargs.get("no_cache", False):
            logger.error(
                "Logic error: multi page query with db cache"
                " url: '{}', page {}".format(func.keywords["url"], kwargs["page"])
            )

        # fix up to get next page, without changing query set
        kwargs["page"] += 1
        kwargs["new_only"] = False


# JSON support routines
class BytesEncoder(json.JSONEncoder):
    # When reading from the database, an empty value will sometimes be returned
    # as an empty bytes array. Convert to empty string.
    def default(self, obj):
        if isinstance(obj, bytes):
            if not bool(obj):
                return ""
        return self.super(obj)


def get_github_client():
    def get_token():
        token = ""
        with open(CREDENTIALS_FILE, "r") as cf:
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
    body = ag_call(gh.rate_limit.get, no_cache=True)
    return body


def ratelimit_remaining():
    body = ratelimit_dict()
    return body["resources"]["core"]["remaining"]


def wait_for_ratelimit(min_karma=25, msg=None):
    while gh:
        rc, payload = ag_call_with_rc(gh.rate_limit.get, no_cache=True)
        calls_remaining = payload["resources"]["core"]["remaining"]
        if calls_remaining < min_karma:
            core = payload["resources"]["core"]
            now = time.time()
            nap = max(core["reset"] - now, 3.0)
            if nap > 3500:
                status = "FAIL"
            else:
                status = "pass"
            logger.error(
                f"{status} time calc: remaining: {calls_remaining}, karma: {min_karma}"
            )
            logger.error(
                f"               reset: {core['reset']}, now: {now}, nap: {nap}"
            )
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


class DeferredRetryQueue:
    """
    Some data isn't ready on first probe, and will return an HTTP result code
    indicating that. Queue those up for later execution.

    Can only be used on calls that do not process the body immediately.
    """

    def __init__(self, retry_codes=None):
        try:
            iter(retry_codes)
        except TypeError:
            # add additional context to error
            raise TypeError("Need a list for 'rc_codes'")
        self.retry_codes = retry_codes
        self.queue = []

    def call_with_retry(self, method, *args, **kwargs):
        """
        Make the call - add to retry queue if rc code matches
        """
        rc, _ = ag_call_with_rc(method, *args, **kwargs)
        if rc in self.retry_codes:
            logger.debug(
                f"Data not ready - deferring call for {method.keywords['url']}"
            )
            self.add_retry(method)

    def add_retry(self, method, max_retries=5, **kwargs):
        """
        add a method (url) to retry later
        """
        retriable = {
            "method": method,
            "max_retries": max_retries,
            "last_time": time.time(),
        }
        self.queue.append(retriable)

    def retry_waiting(self):
        """
        Walk queue, retry each call, retry again if get 202

        If still not successful, return member to queue
        """
        needs_retry = self.queue
        self.queue = []
        retry = 0
        while needs_retry:
            retry += 1
            remaining = needs_retry
            needs_retry = []
            for r in remaining:
                now = time.time()
                not_before = r["last_time"] + 5 * retry
                if not_before > now:
                    nap_seconds = int(not_before - now) + 1
                    logger.info(f"waiting {nap_seconds:d} before retry")
                    time.sleep(int(not_before - now) + 1)
                rc, _ = ag_call_with_rc(r["method"], expected_rc=[200, 202])
                if rc in self.retry_codes:
                    # still not ready
                    if retry < r["max_retries"]:
                        needs_retry.append(r)
                    else:
                        # put back on queue, since not finished
                        self.add_retry(**r)
                        url = r["method"].keywords["url"]
                        logger.warning(f"No data after {retry} retries for {url}")
                else:
                    logger.info(
                        f"Data retrieved on retry {retry} for {r['method'].keywords['url']}"
                    )


def harvest_repo(repo):
    full_name = repo["full_name"]
    name = repo["name"]
    owner = repo["owner"]
    default_branch = repo["default_branch"]
    protected_count = len(
        list(
            ag_get_all(
                gh.repos[full_name].branches.get, protected="true", no_cache=True
            )
        )
    )
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
        record = None  # branch_results.get(tinydb.where('repo') == full_name)
        if branch and record:
            fresh_details = details
            details = record.get("branch", {})
            details.update(fresh_details)
        # always look deeper
        logger.debug(
            "Raw data for %s: %s",
            default_branch,
            json.dumps(branch, indent=2, cls=BytesEncoder),
        )
        protection = ag_call(
            gh.repos[full_name].branches[default_branch].protection.get,
            expected_rc=[200, 304, 404],
        )
        logger.debug(
            "Protection data for %s: %s",
            default_branch,
            json.dumps(protection, indent=2, cls=BytesEncoder),
        )
        signatures = ag_call(
            gh.repos[full_name]
            .branches[default_branch]
            .protection.required_signatures.get,
            headers={"Accept": "application/vnd.github" ".zzzax-preview+json"},
            expected_rc=[200, 304, 404],
        )
        logger.debug(
            "Signature data for %s: %s",
            default_branch,
            json.dumps(signatures, indent=2, cls=BytesEncoder),
        )
        # just get into database. No other action for now
        hooks = list(ag_get_all(gh.repos[full_name].hooks.get, no_cache=True))
        for hook in hooks:
            ag_call(gh.repos[full_name].hooks[hook["id"]].get)
        logger.debug("Hooks for %s: %s (%s)", full_name, len(hooks), repr(hooks))
        method = gh.repos[full_name].stats.commit_activity.get
        org_queue.call_with_retry(method, expected_rc=[200, 202])
        # the subfields might not have had changes, so don't blindly update
        if branch:
            details.update({"default_protected": bool(branch["protected"])})
        if protection:
            details.update({"protections": protection})
        if signatures:
            details.update({"signatures": signatures})
    except AG_Exception:
        # Assume no branch so add no data
        pass
    return {repo["full_name"]: details}


def harvest_org(org_name):
    def repo_fetcher():
        logger.debug("Using API for repos")
        for repo in ag_get_all(gh.orgs[org_name].repos.get, no_cache=True):
            # TODO: not sure yieldingj correct 'repo' here
            # hack - we can't cache on get_all, so redo repo query here
            ag_call(gh.repos[repo["full_name"]].get)
            yield repo
            wait_for_ratelimit()

    logger.debug("Working on org '%s'", org_name)
    org_data = {}
    try:
        ag_call(gh.orgs[org_name].get)
    except AG_Exception:
        logger.error("No such org '%s'", org_name)
        return org_data
    for repo in repo_fetcher():
        repo_data = harvest_repo(repo)
        org_data.update(repo_data)
    # process any pending
    org_queue.retry_waiting()
    return org_data


def get_my_orgs():
    orgs = []
    for response in ag_get_all(gh.user.orgs.get, no_cache=True):
        orgs.append(response["login"])
    return orgs


def process_orgs(args=None, collected_as=None):
    logger.info(
        "Gathering branch protection data." " (calls remaining %s).",
        ratelimit_remaining(),
    )
    if not args:
        args = {}
    if not collected_as:
        collected_as = "<unknown>"
    if args.all_orgs:
        orgs = get_my_orgs()
    else:
        orgs = args.orgs
    file_suffix = ".db.json"
    results = {}
    for org in orgs:
        # org allowed to be specified as db filename, so strip suffix if there
        if org.endswith(file_suffix):
            org = org[: -len(file_suffix)]
            # avoid foot gun of doubled suffixes from prior runs
            if org.endswith(file_suffix):
                logger.warn("Skipping org {}".format(org))
                continue
        logger.info(
            "Starting on org %s." " (calls remaining %s).", org, ratelimit_remaining()
        )
        global org_queue
        # Accept (assumed transitory) GitHub glitch codes as retry requests
        org_queue = DeferredRetryQueue(retry_codes=[202, 403, 502])
        try:
            db = None
            db = db_setup(org)
            # global branch_results
            # branch_results = db.table('branch_results')
            # wait_for_ratelimit()
            if args.repo:
                logger.info("Only processing repo %s", args.repo)
                repo = ag_call(gh.repos[org][args.repo].get)
                if repo:
                    org_data = harvest_repo(repo)
                else:
                    logger.fatal(f"no repo {args.repo} in org {org}")
                    raise ValueError
            else:
                org_data = harvest_org(org)
            org_queue.retry_waiting()
            results.update(org_data)
        finally:
            if db is not None:
                meta_data = {"collected_as": collected_as, "collected_at": time.time()}
                db.table("collection_data").insert({"meta": meta_data})
                db_teardown(db)
    logger.info(
        "Finished gathering branch protection data" " (calls remaining %s).",
        ratelimit_remaining(),
    )
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
    results = {"collected_as": collected_as, "collected_at": time.time()}
    results.update(data)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=help_epilog)
    parser.add_argument("orgs", help="Organization", nargs="*")
    parser.add_argument("--all-orgs", help="Check all orgs", action="store_true")
    parser.add_argument("--repo", help="Only check for this repo")
    parser.add_argument(
        "--debug", help="Debug log level and enter pdb on problem", action="store_true"
    )
    args = parser.parse_args()
    if args.repo and "/" in args.repo:
        parser.error("Do not specify org in value of --repo")
    elif args.all_orgs and len(args.orgs) > 0:
        parser.error("Can't specify --all-orgs & positional args")
    elif len(args.orgs) == 0 and not args.all_orgs:
        parser.error("Must specify at least one org (or use --all-orgs)")
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("backoff").setLevel(logging.DEBUG)
    return args


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    # setup backoff logging
    logging.getLogger("backoff").addHandler(logging.StreamHandler())
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
    except Exception as e:
        import traceback

        traceback.print_exc()
        if os.environ.get("DEBUGGER", False):
            import pudb

            pudb.set_trace()
        # stack dump already printed, just exit
        raise SystemExit(1)
