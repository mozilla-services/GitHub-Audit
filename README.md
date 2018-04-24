# GitHub-Audit
Collection of Tools &amp; Procedures for double checking GitHub configurations

## Targeted threats

The set of tools is primarily focussed on detecting deltas from our
[guidelines](checklist.md). 

## Installation & Usage

These tools are best run in a python 3 virtual environment. Both ``pip``
and [``pipenv``](https://github.com/pypa/pipenv) configuration of the
virtualenv are supported.

### Checks via GUI

Executing these checks require manual input of the 2FA token. 

**Non-python Prerequisites**

- Install Firefox :)
- Install the latest version of
  [geckodriver](https://github.com/mozilla/geckodriver/releases) in your
  path.
- Set environment variables, then export them as follows:
  - ``GH_LOGIN`` <- the GitHub login with owner access to the orgs to be
    examined
  - ``GH_PASSWORD`` <- the password for ``GH_LOGIN``

**Scripts**

- [``check_2fa_required.py``](check_2fa_required.py) to determine if an organization has been
  configured to require 2fa for all members & outside collaborators.


### Checks via API

These checks can be automated, if a PAT token is available.

- ``check_multiple_creds.py`` to determine if anyone associated with an
  org appear to have multiple deployed credentials.
