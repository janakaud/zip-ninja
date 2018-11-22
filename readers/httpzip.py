#!/usr/bin/python

import io
import requests


def fetch(file, start, len, reason):
	end = start + len - 1
	io.eprint("Fetching bytes %d-%d from %s as %s" % (start, end, file, reason))
	return requests.get(file, headers={"Range": "bytes=%d-%d" % (start, end)}).content

def head(file):
	headers = requests.head(file).headers
	if headers["Accept-Ranges"] != "bytes":
		sys.stderr.write("Server doesn't support ranged GETs!\nCtrl+C if you wish to stop, any other key to continue...\n")
		raw_input()
	return int(headers["Content-Length"])


io.head = head
io.fetch = fetch
import core