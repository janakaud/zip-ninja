#!/usr/bin/python

# display what will be downloaded/reused; by downloading only the source zipfile's metadata
dryrun = False

# point to an existing local IDEA CE zipfile, if available; script will get/reuse unmodified files from this without re-downloading them
local = None

# location where the resulting distro will be assembled
outdir = "/tmp/IDEA"

# latest IDEA CE zipfile URL; this JetBrains' Maven snapshot
file = "http://d2s4y8xcwt8bet.cloudfront.net/com/jetbrains/intellij/idea/ideaIC/LATEST-EAP-SNAPSHOT/ideaIC-LATEST-EAP-SNAPSHOT.zip"
# location where the "metadata" zipfile gets cached. DO NOT change this; if you do, core.py also must be changed accordingly
cd_file = "/tmp/" + file.replace("/", "_").replace(":", "_")


import sys
import os
from os.path import isdir, isfile, dirname
import io
import zipfile
import zlib

from httpzip import *


# few utils

# parses 4 little-endian bits into their corresponding integer value
def parse_int(bytes):
	return parse_short(bytes[0:2]) + (parse_short(bytes[2:4]) << 16)
def parse_short(bytes):
	return ord(bytes[0:1]) + (ord(bytes[1:2]) << 8)

def eprint(line):
	sys.stderr.write(line)
	sys.stderr.write("\n")
io.eprint = eprint

# print a list(ZipInfo)
def ls(kind, zipinfos):
	size = 0
	eprint("\n%s\n" % kind)
	for zi in zipinfos:
		size += zi.compress_size
		eprint(zi.filename)
	eprint("\nTotal %s: %d" % (kind, size))
	return size

# load a list of filenames from a file, skipping commented ("#...") lines
def loadlist(fname):
	valid = filter(lambda r: len(r) > 1 and not (r.startswith("#")), open(fname).readlines())
	return map(lambda n: n.replace("\n", ""), valid)


# should we include a given zip filepath in final output?
def accept(name):
	#TODO proper way to detect dir entry
	if name.endswith("/"):
		return False

	for w in whitelist:
		if name.startswith(w):
			break
	else:
		return False

	for b in blacklist:
		if name.startswith(b):
			return False
	return True

# is this file already available in final output?
def is_extracted(zi):
	local = "%s/%s" % (outdir, zi.filename)
	return isfile(local) and zi.CRC == (zlib.crc32(open(local, "rb").read()) & 0xFFFFFFFF)


# process all entries in zip; check each against old zipfile and outdir content and invoke suitable action callback
def process(zip, old, ignore, reuse, download, redownload):
	# check where we can get each file for new archive
	for zi in zip.infolist():
		n = zi.filename
		if not accept(n):   # skip
			ignore(zi)
			continue

		if is_extracted(zi):    # already done
			ignore(zi)
			continue

		try:
			old_zi = old.getinfo(n)
			if old_zi.CRC == zi.CRC:    # same old content!
				reuse(zi)
			else:
				redownload(zi)  # content changed
		except KeyError:
			download(zi)    # fresh file


# dry-run; list and summarize size of ignored/reused/(re)downloaded files
def preview(zip, old):
	reuse = []
	download = []
	redownload = []
	ignore = []

	process(zip, old, ignore.append, reuse.append, download.append, redownload.append)

	ls("reuse", reuse)
	ls("ignore", ignore)
	dl = ls("download", download)
	dl += ls("redownload", redownload)
	eprint("\nTotal %d" % dl)



# driving code begins here

# holds each downloaded chunk for use in any re-runs; after completion, it is safe to delete this dir
tmpdir = "%s/DELETE--tmp" % outdir
if not isdir(tmpdir):
	os.makedirs(tmpdir)

# list of paths/files to include, and exclude (higher priority)
whitelist = loadlist("../data/intellij/whitelist.txt")
blacklist = loadlist("../data/intellij/blacklist.txt")

# fetch/load zipfile CD/metadata
if isfile(cd_file):
	eprint("Loading cached copy %s" % cd_file)
	cache = open(cd_file, "rb")
	zip = zipfile.ZipFile(cache)
	cache.seek(-6, 2)
	cd_start_bytes = cache.read(4)
	cd_start = parse_int(cd_start_bytes)
else:
	eprint("Fetching EOCD %s" % file)
	#TODO refactor core, make reusable without args
	io.head = head
	io.fetch = fetch
	sys.argv = ['', file]   # list mode
	from core import zip, cd_start

# load old IDEA zip if specified
if (local):
	eprint("Loading local/old file %s" % local)
	old = zipfile.ZipFile(open(local, "rb"))
else:
	old = zipfile.ZipFile("%s/DELETE--dummy.zip" % outdir, "w") # empty


# early exit if dry-run
if dryrun:
	preview(zip, old)
	sys.exit(0)


# download flow

# to be extracted from old zip 
reuse = []
# data chunks to be downloaded from remote zip, for new/missing files
chunks = []

# start, end and contained files for each DL chunk
prev_start = 0
prev_end = 0
prev_files = []

dl_size = 0

# compute contiguous chunks to download (each may contain multiple files)
def download(zi):
	global outdir, dl_size, chunks, prev_start, prev_end, prev_files

	# already downloaded? (on resume from failure)
	if is_extracted(zi):
		return

	# NOTE: end values have 1 extra byte
	# ideally we should get name_len/extra_len from the file header inside zip body; we compute them here to avoid extra RTT
	name_len = len(zi.filename)
	extra_len = 0

	start = cd_start + zi.header_offset
	data_start = start + 30 + name_len + extra_len
	end = data_start + zi.compress_size
	# assuming entries are in increasing offset order; grow existing DL window or initiate new window
	if start != prev_end:
		chunks.append([prev_start, prev_end, prev_files])
		dl_size += prev_end - prev_start
		prev_start = start
		prev_files = []
	prev_end = end
	prev_files.append([zi, data_start - prev_start])	# (file, offset inside chunk)

def redownload(zi):
	download(zi)


# analyze zip, decide files to reuse and chunks to download
process(zip, old, lambda zi: None, lambda zi: reuse.append(old.getinfo(zi.filename)), download, redownload)

# extract reused files from old zip
eprint("Reusing %d" % len(reuse))
old.extractall(outdir, reuse)

if len(chunks) == 0:
	eprint("All up to date")
	sys.exit(0)

# drop first chunk; download() adds a dummy 0-0
chunks.pop(0)

# add last chunk; download() misses it
chunks.append([prev_start, prev_end, prev_files])
dl_size += prev_end - prev_start


eprint("Downloading %d over %d chunks" % (dl_size, len(chunks)))
# download chunks, split each into contained files
for seg in chunks:
	size = seg[1] - seg[0]  # (end + 1) - start - 1
	# cache DL data for reuse/reruns
	cached = "%s/%s-%s" % (tmpdir, seg[0], seg[1])
	if isfile(cached):
		data = open(cached, "rb").read()
	else:
		data = fetch(file, seg[0], size, str(list(map(lambda entry: entry[0].filename, seg[2]))))
		with open(cached, "wb") as datafile:
			datafile.write(data)

	# extract each file included in this chunk
	for entry in seg[2]:
		zi = entry[0]
		blob = data[entry[1] : (entry[1] + zi.compress_size - 1)]

		if zi.compress_type == zipfile.ZIP_DEFLATED:
			blob = zlib.decompressobj(-zlib.MAX_WBITS).decompress(blob)
		# decompression sometimes produces smaller files; extend them
		lendiff = zi.file_size - len(blob)
		if lendiff < 0: # larger than expected
			eprint("%s expected %d, decomp. %d" % (zi.filename, zi.file_size, len(blob)))
		elif lendiff > 0:
			eprint("%s missing %d, expanding to %d" % (zi.filename, lendiff, zi.file_size))
			blob += b"0" * lendiff

		path = "%s/%s" % (outdir, zi.filename)
		parent = dirname(path)
		if not isdir(parent):
			os.makedirs(parent)
		with open(path, "wb") as outfile:
			outfile.write(blob)

# create a dummy 'tips' JAR; we skipped original as it's big and useless, but its inner XML is mandatory for IDE launch
tips = zipfile.ZipFile("%s/lib/mock--tips.jar" % outdir, "w")
tips.writestr("META-INF/tips-intellij-idea-community.xml",
				'<idea-plugin><extensions defaultExtensionNs="com.intellij"></extensions></idea-plugin>')
