# GitHub-Audit
Collection of Tools &amp; Procedures for double checking GitHub configurations

## Targeted threats

The set of tools is primarily focussed on detecting deltras from our
[guidelines](checklist.md). The current list includes


### Checks via GUI

Executing these checks require manual input of the 2FA token.

- ``check_2fa_required.py`` to determine if an organization has been
  configured to require 2fa for all members & outside collaborators.


### Checks via API

These checks can be automated, if a PAT token is available.

- ``check_multiple_creds.py`` to determine if anyone associated with an
  org appear to have multiple deployed credentials.

- ``check_branch_protections.py`` to extract the information about
  protected branches. Outputs JSON file, which ``protection_report`` can
  summarize to csv. Import that into a spreadsheet, and play.
