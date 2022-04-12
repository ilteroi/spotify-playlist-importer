# spotify playlist importer

this python script takes a set of files from your local disk or an m3u playlist, tries to find the closest matching tracks on spotify and creates a playlist from them.

the naming scheme for the files is assumed to be "artist - title (optional).ext", but this is easily be adapted via regex. currently only filenames are evaluated, metadata tags are ignored.

## setup

* you need to register a spotify app at https://developer.spotify.com/dashboard/ first. do not forget to add localhost:8888 as a valid redirect URL!
* the credentials must be provided in a file called spotifyCredentials.py (spotipy also supports environment variables but this is not used right now).
* install dependencies with pip (thefuzz, spotipy, m3u8)

## usage

call it like this:

    spotifyPlaylistImport.py [-h] [--dryrun] [--public] [--verbose] [--maxmatches N] [--quality Q] input output

some hints:

* input can be a playlist file (with a defined order) or a folder with individual files (ordered by mtime).
* output is the name of the playlist in spotify. the current date and time will be appended.
* since spotify search results can be weird, we try to do our own ranking and use the best N hits with a quality better than Q.
* by default search hits which have "live" or "karaoke" in the name are ignored!
* do a dry-run first to see which tracks can be processed an which cannot