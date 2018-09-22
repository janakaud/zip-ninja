#!/usr/bin/python

import sys
import zlib
import zipfile
import io

import boto
from boto.s3.connection import OrdinaryCallingFormat


# hack to prevent repeated initialization of S3 client
_bucket = None
_key = None


def fetch(file, start, len, reason):
	global _key
	(bucket, key) = resolve(file)
	end = start + len - 1
	eprint("Fetching bytes %d-%d from %s on %s as %s" % (start, end, key, bucket, reason))

	init(bucket, key)
	return _key.get_contents_as_string(headers={"Range": "bytes=%d-%d" % (start, end)})

def head(file):
	global _key
	(bucket, key) = resolve(file)
	init(bucket, key)
	return _key.size

def resolve(file):
	if file.find("s3://") < 0:
		raise ValueError("Provided URL does not point to S3")
	return file[5:].split("/", 1)

def init(bucket, key):
	global _bucket, _key
	if not _bucket:
		# OrdinaryCallingFormat prevents certificate errors on bucket names with dots
		# https://stackoverflow.com/questions/51604689/read-zip-files-from-amazon-s3-using-boto3-and-python#51605244
		_bucket = boto.connect_s3(calling_format=OrdinaryCallingFormat()).get_bucket(bucket)
	if not _key:
		_key = _bucket.get_key(key)

"""
# for testing with a local file

import os

file = "/tmp/test.zip"

def fetch(file, start, len, reason):
	eprint("Fetching bytes %d-%d from %s as %s" % (start, start + len - 1, file, reason))
	f = open(file)
	f.read(start)
	return f.read(len)

def head(file):
	return os.path.getsize(file)
"""


# parses 4 little-endian bits into their corresponding integer value
def parse_int(bytes):
	return ord(bytes[0]) + (ord(bytes[1]) << 8) + (ord(bytes[2]) << 16) + (ord(bytes[3]) << 24)

def eprint(line):
	sys.stderr.write(line)
	sys.stderr.write("\n")



# actual logic begins here

if len(sys.argv) < 2:
	eprint("Usage: %s <S3 file URL> [<pathname of file to be extracted>]" % sys.argv[0])
	sys.exit(2)

file = sys.argv[1]
extractee = sys.argv[2] if len(sys.argv) > 2 else None

# fetch total size, and fetch the last 22 bytes (end-of-central-directory record)
size = head(file)
eocd = fetch(file, size - 22, 22, "end of central directory (EOCD)")

"""
TODO if eocd[21] > 0 it probably has a trailing comment,
in which case we'll have to incrementally search for the beginning of EOCD or CD
"""

# start offset and size of the central directory (CD)
cd_start = parse_int(eocd[16:20])
cd_size = parse_int(eocd[12:16])

# fetch CD, append EOCD, and open as zipfile!
cd = fetch(file, cd_start, cd_size, "central directory (CD)")
eprint("Opening %d CD and %d EOCD as zipfile" % (len(cd), len(eocd)))
zip = zipfile.ZipFile(io.BytesIO(cd + eocd))

eprint("")
for zi in zip.filelist:
	if not extractee:
		print "%19s %8d %8d %s %s" % (("%4d-%2d-%2d %2d:%2d:%2d" % zi.date_time), zi.compress_size, zi.file_size, zi.filename, zi.comment)

	elif zi.filename == extractee:

		# local file header starting at file name length + file content
		# (so we can reliably skip file name and extra fields)

		# in our "mock" zipfile, `header_offset`s are negative (probably because the leading content is missing)
		# so we have to add to it the CD start offset (`cd_start`) to get the actual offset

		file_head = fetch(file, cd_start + zi.header_offset + 26, 4, "%s file header" % extractee)
		name_len = ord(file_head[0]) + (ord(file_head[1]) << 8)
		extra_len = ord(file_head[2]) + (ord(file_head[3]) << 8)

		content = fetch(file, cd_start + zi.header_offset + 30 + name_len + extra_len, zi.compress_size, "%s file content" % extractee)
		eprint("")

		if zi.compress_type == zipfile.ZIP_DEFLATED:
			print zlib.decompressobj(-15).decompress(content)
		else:
			print content
		break