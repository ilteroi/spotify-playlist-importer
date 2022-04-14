# spotify playlist importer

this python script takes a set of files from your local disk or an m3u playlist, tries to find the closest matching tracks on spotify and creates a playlist from them.

the naming scheme for the files is assumed to be "artist - title (optional).ext", but this is easily be adapted via regex. currently only filenames are evaluated, metadata tags are ignored.

the spotify search results can be annoying because there is no easy way to exclude live versions, karaoke versions etc. To work around that any search hits which have "live" or "karaoke" in the name are ignored unless the local track has it too.

## setup

* you need to register a spotify app at https://developer.spotify.com/dashboard/ first. do not forget to add localhost:8888 as a valid redirect URL!
* the credentials must be provided in a file called spotifyCredentials.py (spotipy also supports environment variables but this is not used right now).
* install dependencies with pip (thefuzz, spotipy)

## usage

call it like this:

    spotifyPlaylistImport.py [-h] [--dryrun] [--public] [--verbose] [--maxmatches N] [--quality Q] input output

some hints:

* input can be a text file (with titles in a defined order) or a folder with individual files (ordered by mtime).
* the playlist file should use UTF-8 encoding. M3U format is expected but any list of filename works. lines with # are considered comments.
* output is the name of the playlist in spotify. the current date and time will be appended.
* since spotify search results can be weird, we try to do our own ranking and use the best N hits with a quality better than Q.
* do a dry-run first to see which tracks can be processed an which cannot