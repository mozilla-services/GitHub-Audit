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

Athena Support
--------------

The modern data flow is to upload the collected data to S3 for processing via
Athena. For Athena to parse the JSON, DDL must be supplied or refreshed any time
the data significantly changes.

Data Preparation
++++++++++++++++

The JSON data as collected is not in a format easily handled by Apache HIVE (the
DDL used by Athena). Fortunately, conversion can be simply handled by `jq`, and
the `Makefile` target `s3_prep` will handle that::

    make -f moz_scripts/Makefile s3_prep

Make note of the directory reported -- you'll need that below.

DDL Modification
++++++++++++++++

If there are any significant changes to the data, the DDL will need to be
regnerated and the Athena tables recreated.

A "significant change" is likely to occur when a new data type is collected. For
example, starting to collect repository hook data introduced additional elements
into the database.

.. note:: First time installation

    Apache ORC, includes tools to infer an acceptable HIVE DDL from
    (semi) arbitrary JSON. We use `org-tools`_, so you have to install that java
    program, and write a wrapper script named `orc-tools` that will invoke it
    properly.

The Apache tool writes a HIVE dialect that is slightly different from what
Athena supports. The differences were learned the hard way, and encapsulated in
a giant ``sed`` expression in the Makefile.

To generate new DDL, generate the S3 data (which will include any new JSON
object structures), and then::

    make -f moz_scripts/Makefile gen_ddl

The output will be in ``/tmp/schema.txt`` - you will need to manually paste that
into the Athena ``create table`` statement. Once you have the new tables
created, run some queries to ensure the new DDL is backward compatible (it
should be).

Upload Data
+++++++++++

You can now upload the data files (all the files in the directory given in the
first step) to the correct place on S3.

.. note:: Subject to Change

    The correct location is still not determined.

.. _org-tools: https://orc.apache.org/docs/java-tools.html

Legacy Data
-----------
Legacy data is that stored in the foxsec-results repo, and reported from there.

Updating the current reports is now a two step process: obtain the data, then
manually update the spreadsheet.

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

To file (or reopen) issues about "protected" status not being set::

    make -f moz_scripts/Makefile open_protected_issues

Review the output for ERROR messages. Failure to open an issue with status 410
likely means the repository is a fork that does not have issues enabled. An
alternate way of informing the team will be needed.

Report Processing
-----------------

There are 3 steps, covered in detail below:

    #. Add the current data (``consolidated.csv``) to a new sheet.
    #. Update the trend chart sheet(s).
    #. Update the latest pointer on the "README" sheet.

#.  Add the current data
    There is a lot of conditional formatting to be preserved, which makes the
    task a bit persnickety:

    #.  Make a duplicate of the most recent spreadsheet, then leave it alone!
    #.  With the original, delete the contents of cells A2 through F200 (or so --
        beyond the bottom of the current list). If you're pretty-darn-sure
        there haven't been any removals, you can skip this step.
    #.  Get the contents of the file ``consolidated.csv`` onto your clipboard.
    #.  Select the single cell A2, and paste.
    #.  Without changing the selection, from the menu, choose "Data" => "Split
        text to columns". Everything should auto format nicely.
    #.  Rename this sheet for the current date.
    #.  Go back to the duplicate sheet, and rename to the previous date. (I.e.
        remove the text "Copy of ".)

#.  Update the trend chart sheet(s).
    The trick here is to account for any additions or deletions in the
    repositories we monitor. (Note that this will need to be modified when we
    trend anything else.)

    #.  On the trend sheet, select columns B, C, & D, right click, and choose
        "Insert 3 left".
    #.  On the current data sheet, select column A, B, & C. Copy those columns.
    #.  Back on the trend sheet, select cell B1 and paste. Adjust column widths
        to see column B (service & repo name) text.
    #.  Delete column C (MFA compliance)
    #.  Starting from the top, find the first mismatch between columns A & B and
        adjust as follows to align them:

            #.  Note which column, A or B, needs cells added to restore alignment
            #.  If it is column A (new services or repositories in latest data):

                #.  select the rows between the first mismatch in column A up to,
                    but not including, the same value in column B.
                #.  right click and insert that many rows ABOVE
                #.  You'll now have a block of empty cells in columns B & C.
                    Select them, right click, and choose "Delete Cells" => "Shift
                    Up".
                #.  Copy/Paste from column B to fill in the blanks in column A.
                #.  Columns A & B should now have the same text.
            #.  If it is column B (fewer services or repositories in the latest
                data):

                #.  Make a block select selection in columns B & C between the
                    first mismatch in column B up to, but not including, the same
                    value in column A.
                #.  Right click and choose "Insert cells" => "Shift down".
                #.  Columns A & B should now have the same text.

        Repeat until you reach the bottom of the list.

    #.  Check that all rows with text in both column A and B have the same text.
    #.  Select column B (names from current data), and delete that column.
    #.  Select cell B1 and enter the current data's date.

#.  Update the latest pointer on the "README" sheet.
    If you followed the directions above about which sheet to insert the current
    data on, this is just a check. :)

    #.  Select the first sheet, "README".
    #.  Click on the link in cell B17 ("Latest Summary"). That should take you
        to the sheet with the current data. If it does, you're done!!! \\o/
    #.  If you need to modify the link:
            #.  Go to the current sheet
            #.  In the URL, select the text from "#gid=" to the end
            #.  Go back to the "README" sheet
            #.  Edit the formula in cell B17, and change the hyperlink
                function's first arguement to have the value you just copied.
