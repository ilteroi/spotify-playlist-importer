#generic python stuff
import re, sys, argparse, logging
from pathlib import Path
from datetime import datetime
from collections import namedtuple
from tabnanny import verbose

#external dependencies
import m3u8
import spotipy
import spotipy.util as util
from thefuzz import fuzz, process

#internal dependencies
from spotifyCredentials import *

trackNameScheme = re.compile("([^-]+)-+([^-\(\[]+)(.*)")

#first we try to find the long title if that fails try with the short title
TrackInfo3 = namedtuple("TrackInfo",['artist','title','titleExt'])
TrackInfo2 = namedtuple("TrackInfo",['artist','title'])

def ireplace(text, old, new):
    idx = 0
    while idx < len(text):
        index_l = text.lower().find(old.lower(), idx)
        if index_l == -1:
            return text
        text = text[:index_l] + new + text[index_l + len(old):]
        idx = index_l + len(new) 
    return text

def trackInfo3FromTrackname(name: str) -> TrackInfo3:
    #drop some useless characters and words
    name = ireplace(name,"."," ")
    name = ireplace(name,"_"," ")
    name = ireplace(name,"&"," ")
    name = ireplace(name," and "," ")
    name = ireplace(name," the "," ")
    name = ireplace(name," ft."," ")
    name = ireplace(name," ft "," ")
    name = ireplace(name," feat."," ")
    name = ireplace(name," rmx"," ")
    name = ireplace(name," remix"," ")
    name = ireplace(name," official"," ")

    result = trackNameScheme.match(name)
    if result:
        #artist, title, all the rest
        return TrackInfo3(result.group(1).strip(), result.group(2).strip(), result.group(3).strip())
    else:
        logging.error("could not parse track ---> %s" % name)
        pass

def trackInfo2Long(fullInfo: TrackInfo3) -> TrackInfo2:
    return TrackInfo2( artist=fullInfo.artist, title=f'{fullInfo.title} {fullInfo.titleExt}' )

def trackInfo2Short(fullInfo: TrackInfo3) -> TrackInfo2:
    return TrackInfo2( artist=fullInfo.artist, title=fullInfo.title )

def trackInfo2FromMatch(match) -> TrackInfo2:
    return TrackInfo2( artist=match['artists'][0]['name'], title=match['name'])

def matchQualityEditDistance(found: TrackInfo2, expected: TrackInfo2):
    #everything lower case
    a1 = found.artist.lower()
    t1 = found.title.lower()
    a2 = expected.artist.lower()
    t2 = expected.title.lower()

    #very basic scoring based on artist / title similarity
    partial_q = min( fuzz.partial_ratio(a1,a2), fuzz.partial_ratio(t1,t2) )
    full_q = min( fuzz.ratio(a1,a2), fuzz.ratio(t1,t2) )
    q = (partial_q*2 + full_q)//3

    logging.debug("searching for \"%s -- %s\", score is %d for \"%s -- %s\"" % (expected.artist,expected.title,q,found.artist,found.title))
    return q

def matchQualityTokenDistance(found: TrackInfo2, expected: TrackInfo2):
    #see how many common words we have
    a = f'{found.artist} {found.title}'
    b = f'{expected.artist} {expected.title}'

    #token_set_ratio seems better than set_sort_ratio
    q = fuzz.token_set_ratio(a,b)

    #ignore useless versions unless explictly expected
    if a.lower().find("live")>=0 and b.lower().find("live")<0:
        return 0
    if a.lower().find("karaoke")>=0 and b.lower().find("karaoke")<0:
        return 0

    logging.debug("searching for \"%s\", score is %d for \"%s\"" % (b,q,a))
    return q

def lookupSpotifyTrackID(sp, trackInfo2: TrackInfo2, maxMatches: int, minMatchQuality: int):
    #search for everything at once, seems to work better than f'artist:{trackInfo2.artist} track:{trackInfo2.title}'
    query = f'{trackInfo2.artist} {trackInfo2.title}'

    #get multiple responses since the first isn't always accurate
    results = sp.search(q=query, offset=0, limit=max(maxMatches*2,6), type='track', market=None)

    #avoid repetitions (sort by release date so we avoid compilations and live recordings if we have the choice)
    matches = results['tracks']['items']
    matches.sort(key=lambda x: x['album']['release_date'])
    knownTracks = set()
    uniqueMatches = []
    for x in matches:
        if trackInfo2FromMatch(x) not in knownTracks:
            uniqueMatches.append(x)
            knownTracks.add(trackInfo2FromMatch(x))

    #do our own scoring on top of what spotify does
    resultsWithScore = [(matchQualityTokenDistance(trackInfo2FromMatch(match),trackInfo2),match) for match in uniqueMatches]
    resultsWithScore.sort(key=lambda x: x[0], reverse=True)

    #keep the best N
    goodResults = [x for x in resultsWithScore[:maxMatches] if x[0]>=minMatchQuality]

    if not goodResults and resultsWithScore:
        bestMatch = trackInfo2FromMatch(resultsWithScore[0][1])
        logging.info("best match for track \"%s -- %s\" was \"%s -- %s\" with score %d" % (trackInfo2.artist,trackInfo2.title,bestMatch.artist,bestMatch.title,resultsWithScore[0][0]))

    return [x[1]['id'] for x in goodResults]

def getSpotifyTrackIDs(sp, trackInfos, maxMatches, minMatchQuality):
    allTrackIDs = []
    for trackInfo3 in trackInfos:
        #sometimes parsing fails
        if trackInfo3 is None:
            continue

        #first search for the long title (if we have one)
        if trackInfo3.titleExt:
            trackIDs = lookupSpotifyTrackID(sp, trackInfo2Long(trackInfo3), maxMatches, minMatchQuality)
            if trackIDs:
                allTrackIDs.append(trackIDs)
                continue

        #try the short title if long did not work
        trackIDs = lookupSpotifyTrackID(sp, trackInfo2Short(trackInfo3), maxMatches, minMatchQuality)
        if trackIDs:
            allTrackIDs.append(trackIDs)
            continue

        logging.error("no good matches for track %s -- %s." % (trackInfo3.artist,trackInfo3.title))

    return allTrackIDs

def initSpotipy(spotifyUsername,spotifyClientId,spotifyClientSecret):
    scope = 'playlist-modify-public playlist-modify-private'
    token = util.prompt_for_user_token(spotifyUsername,scope,client_id=spotifyClientId,client_secret=spotifyClientSecret,redirect_uri='http://localhost:8888') 
    return spotipy.Spotify(auth=token)

def makeNewPlaylist(sp,spotifyUsername,trackIDs,playlistName,isPublic):
    #create new playlist
    fullname = f'{playlistName} from {datetime.now():%Y-%m-%d %H:%M:%S%z}'
    newPlaylist = sp.user_playlist_create(spotifyUsername, name=fullname, public=isPublic)

    #populate playlist in one go (but not more than 100 at a time)
    flatlist = list([item for sublist in trackIDs for item in sublist])
    for i in range(0, len(flatlist), 100):
        sp.playlist_add_items(newPlaylist['id'], flatlist[i:i + 100])
 
    #check result
    content = sp.playlist_tracks(newPlaylist['id'])
    print("success: new playlist has %d entries!" % content['total'])
    return 0

def tracksFromFolder(path: str):
    files = Path(path).glob('*')
    sortedFiles = sorted(files,key=lambda x: x.stat().st_mtime)
    return [i.stem for i in sortedFiles if i.is_file()]

def tracksFromPlaylist(path: str):
    playlist = m3u8.load(path)
    return [Path(item).stem for item in playlist.files]

def main(args) -> int:
    logging.basicConfig( level=logging.INFO if args.verbose else logging.WARNING )

    #get our input tracks
    p = Path(args.input)
    tracks = []
    if p.is_file():
        tracks = tracksFromPlaylist(args.input)
    elif p.is_dir():
        tracks = tracksFromFolder(args.input)

    if not tracks:
        logging.critical("invalid or empty input ---> %s" % args.input)
        return 1

    #connect to spotify
    sp = initSpotipy(spotifyUsername,spotifyClientId,spotifyClientSecret)
    if not sp:
        logging.critical("failed to connect to spotify. check auth data!")
        return 1

    #try to identify our new tracks
    trackInfos = [trackInfo3FromTrackname(t) for t in tracks]
    allTrackIDs = getSpotifyTrackIDs(sp, trackInfos, args.maxmatches, args.quality)
    if not allTrackIDs:
        logging.critical("did not find any matching tracks")
        return 1

    #do the magic
    if args.dryrun:
        print("dry run finished! found matches for %.2f%% of inputs." % ( 100*len(allTrackIDs)/len(tracks) ) )
        return 0
    else:
        return makeNewPlaylist(sp,spotifyUsername,allTrackIDs,args.output,True if args.public else False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'make a spotify playlist from local files')
    parser.add_argument('input', help='folder or m3u playlist containing tracks to be imported')
    parser.add_argument('output', help='what should the new playlist be called in spotify')
    parser.add_argument('-m', '--maxmatches', type=int, help='how many matches to add for each track, default 1', default=1, choices=range(1, 4))
    parser.add_argument('-q', '--quality', type=int, help='how close should the matches be. default 70', default=70, choices=range(10, 101, 10))
    parser.add_argument('-d', '--dryrun', help='just try to parse and look up ids, do not create playlist', default=False, action='store_true')
    parser.add_argument('-p', '--public', help='make the resulting playlist public. default is private', default=False, action='store_true')
    parser.add_argument('-v', '--verbose', help='show additional log messages', default=False, action='store_true')
    parser.add_argument('-a', '--all', help='include matches which have live or karaoke in the name', default=False, action='store_true')
    sys.exit(main(parser.parse_args()))