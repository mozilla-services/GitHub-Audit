# GitHub-Audit
Collection of Tools &amp; Procedures for double checking GitHub configurations

## Targeted threats

The set of tools is primarily focussed on detecting deltras from our
[guidelines](checklist.md). The current list includes


### Checks via API

These checks can be automated, if a PAT token is available. The PAT
token should be on the second line of a file named ``.credentials`` in
the current directory.

- ``check_multiple_creds.py`` to determine if anyone associated with an
  org appear to have multiple deployed credentials.

- ``get_branch_protections.py`` * to extract the information about
  protected branches. Outputs JSON file, which
  ``report_branch_status.py`` can summarize to csv. Import that into a
  spreadsheet, and play.

- ``term_search.py`` search orgs or repos for a specific term, such as
  an API token name. Outputs list of repos that do have the term (per
  GitHub's index, which can be out of date).
