import sys
import argparse
import zlib
import zipfile
import io


# parses 4 little-endian bits into their corresponding integer value
def parse_int(bytes):
	return parse_short(bytes[0:2]) + (parse_short(bytes[2:4]) << 16)
def parse_short(bytes):
	return ord(bytes[0:1]) + (ord(bytes[1:2]) << 8)

def eprint(line):
	sys.stderr.write(line)
	sys.stderr.write("\n")
io.eprint = eprint

def waitkey():
	try:
		raw_input()
	except NameError:
		input()
io.waitkey = waitkey

if sys.platform.startswith('win'):
    import os, msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

def dump(data):
	if hasattr(sys.stdout, 'buffer'):
		sys.stdout.buffer.write(data)
	else:
		sys.stdout.write(data)

def flatname(name):
	return name.replace('/', '_').replace(':', '_').replace('?', '_')


parser = argparse.ArgumentParser(description='List/extract contents of a remote zipfile without full download')
parser.add_argument('url', metavar='<location>', type=str, help='URL pointing to the remote zipfile')
parser.add_argument('--extract', '-x', metavar='<filepath>', type=str, help='pathname of file to be extracted')
parser.add_argument('--extract-length', '-xl', metavar='<head-length>', type=int, help='get only this many bytes from extractee')
parser.add_argument('--length', '-l', metavar='<content-length>', type=int, help='content-length of zipfile (if known)')
parser.add_argument('--print-central-directory-size', '-pcds', action='store_true',
	help='just print size of Central Directory (CD) and exit')
parser.add_argument('--fresh', '-r', action='store_true',
	help='fetch freshly from remote; overwrite locally cached (meta)data')
parser.add_argument('--headers', '-H', nargs='*', metavar='<headers>', type=str, default=[],
	help='extra headers ("key: value") to include in requests; authorization, cookies, etc')
args = parser.parse_args()

# actual logic begins here

file = args.url
extractee = args.extract
conlen = args.length

headers = {}
for h in args.headers:
	colon = h.index(':')
	headers[h[:colon]] = h[(colon + 1):].strip()

# try to read the cached copy, fetch and cache CD + EOCD on failure
tmpfile = "/tmp/" + flatname(file)
try:
	if args.fresh:
		raise IOError('Fresh fetch requested')

	cache = open(tmpfile, 'rb')
	zip = zipfile.ZipFile(cache)
	cache.seek(-6, 2)
	cd_start_bytes = cache.read(4)
	cd_start = parse_int(cd_start_bytes)
	eprint("Loaded cached copy " + tmpfile)

	if args.print_central_directory_size:
		cache.seek(-8, 1)
		print(parse_int(cache.read(4)))
		sys.exit(0)

except (IOError, zipfile.BadZipFile):
	# fetch total size, and fetch the last 22 bytes (end-of-central-directory record)
	# if head results in a redirect, we'll get back a new file (URL/path) as well
	(file, size) = io.head(file, headers) if conlen is None else long(conlen)
	eocd = io.fetch(file, size - 22, 22, "end of central directory (EOCD)", headers)

	"""
	TODO if eocd[21] > 0 it probably has a trailing comment,
	in which case we'll have to incrementally search for the beginning of EOCD or CD
	"""

	# start offset and size of the central directory (CD)
	cd_start = parse_int(eocd[16:20])
	cd_size = parse_int(eocd[12:16])

	if args.print_central_directory_size:
		open(tmpfile + "_eocd", 'wb').write(eocd)
		print(cd_size)
		sys.exit(0)

	# fetch CD, append EOCD, and open as zipfile!
	cd = io.fetch(file, cd_start, cd_size, "central directory (CD)")
	zipdata = cd + eocd
	open(tmpfile, 'wb').write(zipdata)

	eprint("Opening %d CD and %d EOCD as zipfile" % (len(cd), len(eocd)))
	zip = zipfile.ZipFile(io.BytesIO(zipdata))

eprint("")
for zi in zip.filelist:
	if not extractee:
		print("%19s %8d %8d %s %s" % (("%4d-%2d-%2d %2d:%2d:%2d" % zi.date_time), zi.compress_size, zi.file_size, zi.filename, zi.comment))

	elif zi.filename == extractee:

		# local file header starting at file name length + file content
		# (so we can reliably skip file name and extra fields)

		# in our "mock" zipfile, `header_offset`s are negative (probably because the leading content is missing)
		# so we have to add to it the CD start offset (`cd_start`) to get the actual offset

		# extra_len is usually zero but no guarantee; so we fetch header to be safe
		file_head = io.fetch(file, cd_start + zi.header_offset + 26, 4, "%s file header" % extractee)
		name_len = parse_short(file_head[0:2])
		extra_len = parse_short(file_head[2:4])
		"""
		name_len = len(zi.filename)
		extra_len = 0 if zi.file_size == 0 else 20
		"""
		dl_len = zi.compress_size if args.extract_length is None else args.extract_length

		content = io.fetch(file, cd_start + zi.header_offset + 30 + name_len + extra_len, dl_len, "%s file content" % extractee)
		eprint("")

		if zi.compress_type == zipfile.ZIP_DEFLATED:
			dump(zlib.decompressobj(-zlib.MAX_WBITS).decompress(content))
		else:
			dump(content)
		break
