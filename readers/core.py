import sys
import zlib
import zipfile
import io


# parses 4 little-endian bits into their corresponding integer value
def parse_int(bytes):
	return ord(bytes[0]) + (ord(bytes[1]) << 8) + (ord(bytes[2]) << 16) + (ord(bytes[3]) << 24)

def eprint(line):
	sys.stderr.write(line)
	sys.stderr.write("\n")
io.eprint = eprint


# actual logic begins here

if len(sys.argv) < 2:
	eprint("Usage: %s <URL> [<pathname of file to be extracted>]" % sys.argv[0])
	sys.exit(2)

file = sys.argv[1]
extractee = sys.argv[2] if len(sys.argv) > 2 else None

# try to read the cached copy, fetch and cache CD + EOCD on failure
tmpfile = "/tmp/" + file.replace("/", "_")
try:
	cache = open(tmpfile, "r")
	zip = zipfile.ZipFile(cache)
	cache.seek(-6, 2)
	cd_start_bytes = cache.read(4)
	cd_start = parse_int(cd_start_bytes)
	eprint("Loaded cached copy " + tmpfile)

except:
	# fetch total size, and fetch the last 22 bytes (end-of-central-directory record)
	size = io.head(file)
	eocd = io.fetch(file, size - 22, 22, "end of central directory (EOCD)")

	"""
	TODO if eocd[21] > 0 it probably has a trailing comment,
	in which case we'll have to incrementally search for the beginning of EOCD or CD
	"""

	# start offset and size of the central directory (CD)
	cd_start = parse_int(eocd[16:20])
	cd_size = parse_int(eocd[12:16])

	# fetch CD, append EOCD, and open as zipfile!
	cd = io.fetch(file, cd_start, cd_size, "central directory (CD)")
	zipdata = cd + eocd
	open(tmpfile, "w").write(zipdata)

	eprint("Opening %d CD and %d EOCD as zipfile" % (len(cd), len(eocd)))
	zip = zipfile.ZipFile(io.BytesIO(zipdata))

eprint("")
for zi in zip.filelist:
	if not extractee:
		print "%19s %8d %8d %s %s" % (("%4d-%2d-%2d %2d:%2d:%2d" % zi.date_time), zi.compress_size, zi.file_size, zi.filename, zi.comment)

	elif zi.filename == extractee:

		# local file header starting at file name length + file content
		# (so we can reliably skip file name and extra fields)

		# in our "mock" zipfile, `header_offset`s are negative (probably because the leading content is missing)
		# so we have to add to it the CD start offset (`cd_start`) to get the actual offset

		file_head = io.fetch(file, cd_start + zi.header_offset + 26, 4, "%s file header" % extractee)
		name_len = ord(file_head[0]) + (ord(file_head[1]) << 8)
		extra_len = ord(file_head[2]) + (ord(file_head[3]) << 8)

		content = io.fetch(file, cd_start + zi.header_offset + 30 + name_len + extra_len, zi.compress_size, "%s file content" % extractee)
		eprint("")

		if zi.compress_type == zipfile.ZIP_DEFLATED:
			print zlib.decompressobj(-15).decompress(content)
		else:
			print content
		break