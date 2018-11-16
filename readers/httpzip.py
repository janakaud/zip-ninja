#!/usr/bin/python

import io
import requests


def fetch(file, start, len, reason):
	end = start + len - 1
	io.eprint("Fetching bytes %d-%d from %s as %s" % (start, end, file, reason))
	return requests.get(file, headers={"Range": "bytes=%d-%d" % (start, end)}).content

def head(file):
	return int(requests.head(file).headers["Content-Length"])


io.head = head
io.fetch = fetch
import core