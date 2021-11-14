#!/usr/bin/python

import io
import re
import requests


def update_cookies(cookie, set_cookie):
	# split at ", ", trim to first ";" marks, join, and do regex match (eliminate dates)
	news = re.findall(r"\S+=\S+;", "; ".join(map(lambda c: c[:c.find(";")], set_cookie.split(", "))))

	for c in news:
		name = c[:c.find("=")]
		pos = cookie.find(name)
		if pos >= 0:	# replace
			end = cookie.find(";", pos)
			if end < 0:
				end = len(cookie)
			cookie = cookie[:pos] + c[:c.find(";")] + cookie[end:]
		else:	# append
			if len(cookie) > 0:
				cookie += "; "
			cookie += c[:c.find(";")]

	return cookie

def header_print(headers):
	return "\n".join(map(lambda k: "%s: %s" % (k, headers.get(k)), headers.keys()))


def fetch(file, start, len, reason, headers={}):
	end = start + len - 1
	io.eprint("Fetching bytes %d-%d from %s as %s" % (start, end, file, reason))
	ranged = headers.copy()
	ranged.update({"Range": "bytes=%d-%d" % (start, end)})
	return requests.get(file, headers=ranged).content

def head(file, headers={}):
	res = requests.head(file, headers=headers)

	if res.status_code in [301, 302, 303, 307]:
		next = res.headers.get("Location")
		old_cookies = headers.get("Cookie")
		new_cookies = res.headers.get("Set-Cookie")
		if old_cookies and new_cookies:
			headers.update({"Cookie": update_cookies(old_cookies, new_cookies)})
		pause(res, 'Redirecting to %s, headers\n%s\n' % (next, header_print(headers)))
		return head(next, headers)

	if res.status_code not in [200, 206]:
		pause(res, "Unexpected response code %d!" % res.status_code)
	if res.headers.get("Accept-Ranges") != "bytes":
		pause(res, "Server doesn't seem to support ranged GETs!")
	return (
		file,
		int(res.headers.get("Content-Length"))
	)

def pause(res, msg):
	io.eprint('HTTP code %d, headers\n%s\n' % (res.status_code, header_print(res.headers)))
	io.eprint(msg)
	io.eprint("Ctrl+C if you wish to stop, any other key to continue...")
	raw_input()


io.head = head
io.fetch = fetch
import core
