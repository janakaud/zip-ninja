#!/usr/bin/python

import io
import requests


def fetch(file, start, len, reason):
	end = start + len - 1
	io.eprint("Fetching bytes %d-%d from %s as %s" % (start, end, file, reason))
	return requests.get(file, headers={"Range": "bytes=%d-%d" % (start, end)}).content

def head(file):
	res = requests.head(file)
	if res.status_code not in [200, 206]:
		pause('HTTP code ' + res.status_code)
	if res.headers.get("Accept-Ranges") != "bytes":
		pause("Server doesn't support ranged GETs!")
	return int(res.headers.get("Content-Length"))

def pause(msg):
	io.eprint(msg)
	io.eprint("Ctrl+C if you wish to stop, any other key to continue...")
	raw_input()


io.head = head
io.fetch = fetch
import core