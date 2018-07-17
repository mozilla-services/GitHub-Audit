========================
Mozilla Specific Scripts
========================

The scripts in this directory are likely not useful to anyone outside
the Firefox Security Operations team. Some of the scripts reference
private material (i.e. they will fail if you run them).

What's here
===========

In alphabetical order

full_to_email
-------------

Reformats the output of "report-by-service" to allow easy import into
Google Doc Spreadsheets for manipulation before emailing.

get_repos.sh
------------

Hack to get repositories grouped by the services they support. From
internal JSON sources.

report-by-service
-----------------

Wrapper script to generate reports sorted the way we want.

Typical Usage
=============

Data Collection
---------------

To gather the needed data, you can use the Makefile targets for most steps::

    make -f moz_scripts/Makefile full       # can take over 4 hours

Now cd into the directory given in the output from the last make invocation.
Verify that the commit looks sane (I usually do ``git log -n1 --stat``), then
push from there.

Filing Issues
-------------

You can automatically file issues for repos that appear to be out of compliance.

To file (or reopen) issues about "protected" status not being set:

    1. Download the `latest report`_ as CSV

    2. Move the file to the parent directory, and rename to
           ``consolidated.csv``.

    3. Run a sanity check::

        make -f moz_scripts/Makefile preview_new_issues

    4. Generate the issues::

        make -f moz_scripts/Makefile open_protected_issues

Review the output for ERROR messages. Failure to open an issue with status 410
likely means the repository is a fork that does not have issues enabled. An
alternate way of informing the team will be needed.

.. _latest report: https://sql.telemetry.mozilla.org/api/queries/60714/results/5413247.csv

Notes
=====

Athena Support
--------------

The modern data flow is to upload the collected data to S3 for processing via
Athena. For Athena to parse the JSON, DDL must be supplied or refreshed any time
the data significantly changes.

If there are any significant changes to the data, the DDL will need to be
regnerated and the Athena tables recreated. See `these instructions`_.

.. _these instructions: https://github.com/mozilla-services/foxsec-tools/tree/master/metrics/utils



Updating the current reports is now a two step process: obtain the data (done
via automation), then manually send any needed emails
