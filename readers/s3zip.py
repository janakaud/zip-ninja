#!/usr/bin/python

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
	io.eprint("Fetching bytes %d-%d from %s on %s as %s" % (start, end, key, bucket, reason))

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


io.head = head
io.fetch = fetch
import core