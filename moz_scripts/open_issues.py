#!/usr/bin/env python3
"""
Create issue in supplied org/repositories

We reopen an issue if it already exists
"""

import argparse
import copy
import logging
import time
import urllib.parse

from agithub.GitHub import GitHub
import yaml

help_epilog = """
Uses GitHub's search to find existing issues, then reopens or creates one as
appropriate.
"""

DEBUG = False
CREDENTIALS_FILE = ".credentials"
MESSAGES_FILE = "moz_scripts/messages.yaml"


class AG_Exception(Exception):
    pass


# agithub utility functions
def ag_call(
    func, *args, expected_rc=None, new_only=True, headers=None, no_cache=False, **kwargs
):
    """
    Wrap AGitHub calls with basic error detection

    Not smart, and hides any error information from caller.
    But very convenient. :)
    """

    def query_string():
        return urllib.parse.quote_plus(kwargs["q"])

    if not headers:
        headers = {}
    url = func.keywords["url"]
    # Insert our (possibly modified) headers
    real_headers = kwargs.setdefault("headers", {})
    real_headers.update(headers)

    if expected_rc is None:
        expected_rc = [200, 304]
    rc, body = func(*args, **kwargs)
    # If we have new information, we want to use it (and store it unless
    # no_cache is true)
    # If we are told our existing info is ok, or there's an error, use the
    # stored info
    # Handle repo rename/removal corner cases
    if rc == 301:
        logger.error("Permanent Redirect for '{}'".format(url))
        # TODO: do something better, like switch to using id's
        # for now, act like nothing is there
        body = []
    elif rc == 403 and rc not in expected_rc:
        # don't throw on this one, but do show query string
        # for search, there is a seperate rate limit we don't yet take into
        # account:
        #  https://developer.github.com/v3/search/#rate-limit
        logger.error("403 for query string '{}'".format(query_string()))
        logger.error("response: '{}'".format(repr(body)))
        expected_rc.append(rc)
    elif rc == 404 and rc not in expected_rc:
        logger.error("No longer available or access denied: {}".format(url))
        # TODO: Figure out what to do here. Maybe it's just that message, but
        # maybe need to delete from DB before next run
        body = []
        # don't throw on this one
        expected_rc.append(rc)
    elif rc == 422 and rc not in expected_rc:
        logger.error(f"Unprocessable Entity: {url} {query_string()}")
    logger.debug("{} for {}".format(rc, url))

    if rc not in expected_rc:
        if DEBUG:
            import pudb

            pudb.set_trace()  # noqa: E702
        else:
            logger.error("{} for {}".format(rc, url))
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
        # search results are ugly
        if isinstance(body, dict) and "items" in body and len(body["items"]) == 0:
            break
        elif not isinstance(body, list):
            yield body
        elif len(body) >= 1:
            for elem in body:
                yield elem
        else:
            break

        # fix up to get next page, without changing query set
        kwargs["page"] += 1
        kwargs["new_only"] = False


# GitHub API v3 support
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


def wait_for_ratelimit(min_karma=25, msg=None, usingSearch=False):
    def nap_if_needed(resource, min_karma, msg=None):
        napped = False
        if resource["remaining"] < min_karma:
            now = time.time()
            nap = max(resource["reset"] - int(now), 0) + 1
            logger.info("napping for %s seconds", nap)
            if msg:
                logger.info(msg)
            time.sleep(nap)
            napped = True
        return napped

    # repeat until good on all channels
    while gh:
        payload = ag_call(gh.rate_limit.get, no_cache=True)
        napped = nap_if_needed(payload["resources"]["core"], min_karma, msg)
        if usingSearch:
            napped = nap_if_needed(payload["resources"]["search"], 1, msg) or napped

        if not napped:
            break


# finally, our app!
logger = logging.getLogger(__name__)

Pseudo_code = """
    for each repo
        search for existing issue
        if none:
            create new issue with message
        else if issue closed:
            reopen with message
        else:
            add message
"""


# SHH, globals, don't tell anyone
gh = None
messages = None


class NoIssue(Exception):
    pass


def get_message(owner, repo, msg_id, **kwargs):
    """
    Return a fully expanded message body & title
    """
    template_values = {}
    template_values.update(locals())
    template_values.update(kwargs)
    title = messages["Messages"][msg_id]["title"].format(**template_values)
    message = messages["Messages"][msg_id]["message"].format(**template_values)

    return title, message


def find_existing_issue(owner, repo, term):
    """
    Generator for repositories containing term
    """
    q = term + " is:issue"
    q += " repo:{}/{}".format(owner, repo)
    kwargs = {"q": q}
    wait_for_ratelimit(usingSearch=True)
    try:
        for body in ag_get_all(gh.search.issues.get, **kwargs):
            if "items" not in body:
                # 403 or something we don't expect
                logger.error("Unexpected keys: {}".format(" ".join(body.keys())))
                continue
            issue_count = len(body["items"])
            logger.debug("items in body: {}".format(issue_count))
            if issue_count > 1:
                logger.error(
                    "Unexpected Issue Count {} for {}/{}".format(
                        issue_count, owner, repo
                    )
                )
            for match in body["items"]:
                state = match["state"]
                number = match["number"]
                return number, state
            wait_for_ratelimit(usingSearch=True)
    except AG_Exception:
        # We assume it's a bad repo, but let other repos process
        pass
    raise NoIssue


def update_issue(owner, repo, standard_id, issue, state):
    """
        Update an existing issue, and make sure it is not closed.

        ToDo: consider different message text when reopening
              maybe prepend "REOPENED: " to title?
    """
    logger.info(f"Reusing https://github.com/{owner}/{repo}/issues/{issue}")
    msg_id = next_message_id(standard_id, state)
    _, text = get_message(owner, repo, msg_id)
    # open bug in case it was closed
    payload = {"state": "open"}
    func = gh.repos[owner][repo].issues[issue].patch
    url = func.keywords["url"]
    logger.debug("Commenting on %(issue)s via %(url)s", locals())
    if DRY_RUN:
        # multiple calls, all debug info out already, so bail
        return
    status, _ = func(body=payload)
    if status in [422]:
        logger.error("Could not reopen %(url)s. Likely no write permission.", locals())
    # add comment
    payload = {"body": text}
    gh.repos[owner][repo].issues[issue].comments.post(body=payload)
    return


def next_message_id(standard_id, issue_state, force=False):
    """
        Compute correct message to issue
    """
    try:
        # load standard progression
        standard = [
            x for x in messages["Standards"] if str(x["standard number"]) == standard_id
        ][0]
        if force:
            key = "admin set"
        elif issue_state is None:
            key = "new message id"
        elif issue_state == "open":
            key = "still open message id"
        elif issue_state == "closed":
            key = "reopen message id"
        else:
            logger.error("Unknown bug state '{}'".format(issue_state))
            key = "new message id"

        next_id = standard[key]
        logger.debug(
            "Message id {} for std {}, state {}".format(
                next_id, standard_id, issue_state
            )
        )
    except (IndexError, KeyError):
        logger.error("YAML access error for std {}".format(standard_id))
        raise SystemExit
    return next_id


def create_issue(owner, repo, standard_id):
    """
        Create a new issue
    """
    logger.debug("Creating issue for {}/{}".format(owner, repo))
    msg_id = next_message_id(standard_id, None)
    title, text = get_message(owner, repo, msg_id)
    payload = {"title": title, "body": text}
    func = gh.repos[owner][repo].issues.post
    url = func.keywords["url"]
    logger.debug("Opening new issue via %(url)s", locals())
    if DRY_RUN:
        # multiple calls, all debug info out already, so bail
        return
    status, response_body = func(body=payload)
    if status not in [201]:
        logger.error("Issue not opened for %(url)s status %(status)s", locals())
    else:
        logger.info("Opened {}".format(response_body["html_url"]))


def load_messages(file_name):
    global messages
    messages = yaml.safe_load(open(file_name))


def main(driver=None):
    args = parse_args()
    std_id = args.id
    global gh
    gh = get_github_client()
    wait_for_ratelimit(usingSearch=True)
    body = ag_call(gh.user.get)
    collected_as = body["login"]
    logger.info(
        "Running as {} ({} API calls remaining)".format(
            collected_as, ratelimit_remaining()
        )
    )
    load_messages(args.message_file or MESSAGES_FILE)
    for repo_full_name in args.repos:
        logger.info("Starting on {}".format(repo_full_name))
        wait_for_ratelimit()
        owner, repo = repo_full_name.split("/")
        # Get message subject
        msg_id = next_message_id(std_id, None)
        subject, _ = get_message(None, None, msg_id)
        try:
            issue, state = find_existing_issue(owner, repo, subject)
            update_issue(owner, repo, std_id, issue, state)
        except NoIssue:
            create_issue(owner, repo, std_id)
    logger.info("Done with {} API calls remaining".format(ratelimit_remaining()))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, epilog=help_epilog)
    parser.add_argument(
        "repos", help="owner/repo to open issue on", nargs="+", metavar="org/repo"
    )
    parser.add_argument("--id", help="Message ID for new bugs (default 1)", default="1")
    parser.add_argument("--message-file", help="YAML file with messages")
    parser.add_argument("--debug", help="log at DEBUG level", action="store_true")
    parser.add_argument("--open-issues", help="Open issues", action="store_true")
    args = parser.parse_args()

    # validate repos are org/repo
    bad_args = [x for x in args.repos if x.count("/") != 1]
    if len(bad_args):
        parser.error("Bad '/' usage in repos: {}".format(", ".join(bad_args)))

    global DEBUG, DRY_RUN
    DRY_RUN = not args.open_issues
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    return args


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit
