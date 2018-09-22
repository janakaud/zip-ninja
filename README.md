# zip-ninja

Various hacks and manipulations on zip files

## readers/s3zip.py

Reads indexes and fetches specified entries from S3-hosted zip files, without downloading the whole archive, using standard Python `zipfile` APIs.
Uses `boto` for S3 access.
Prints listing and retrieved (and deflated, if applicable) entries to standard output.
