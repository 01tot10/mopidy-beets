from __future__ import unicode_literals

import logging
import urllib

from mopidy import backend, models
from mopidy.models import SearchResult


logger = logging.getLogger(__name__)


class BeetsLibraryProvider(backend.LibraryProvider):

    root_directory = models.Ref.directory(uri="beets:library",
                                          name='Beets library')

    def __init__(self, *args, **kwargs):
        super(BeetsLibraryProvider, self).__init__(*args, **kwargs)
        self.remote = self.backend.beets_api

    def _find_exact(self, query=None, uris=None):
        if not query:
            # Fetch all artists (browse library)
            return SearchResult(
                uri='beets:search',
                tracks=self.remote.get_artists())
        else:
            results = []
            if 'artist' in query:
                results.append(self.remote.get_tracks_by_artist(
                        query['artist'][0]))
            if 'album' in query:
                results.append(self.remote.get_tracks_by_title(
                        query['album'][0]))
            if len(results) > 1:
                # return only albums that match all restrictions
                results_set = set(results.pop(0))
                while results:
                    results_set.intersection_update(set(results.pop(0)))
                tracks = list(results_set)
            elif len(results) == 1:
                tracks = results[0]
            else:
                tracks = []
        return SearchResult(uri='beets:tracks', tracks=tracks)

    def browse(self, uri):
        def quoting(text):
            return urllib.quote(text.encode("utf-8"))

        def unquoting(text):
            return urllib.unquote(text.encode("ascii")).decode("utf-8")

        def get_uri_path(*args):
            return ":".join([self.root_directory.uri] + list(args))

        # ignore the first two tokens
        current_path = uri.split(":", 2)[-1]
        if uri == self.root_directory.uri:
            directories = {"albums-by-artist": "Albums by Artist"}
            return [models.Ref.directory(uri=get_uri_path(uri_suffix),
                                         name=label)
                    for uri_suffix, label in directories.items()]
        elif current_path == "albums-by-artist":
            # list all artists with albums
            album_artists = self.remote.get_sorted_album_artists()
            return [models.Ref.directory(uri=get_uri_path("albums-by-artist",
                                                          quoting(artist)),
                                         name=artist)
                    for artist in album_artists]
        elif current_path.startswith("albums-by-artist:"):
            artist = unquoting(current_path.split(":", 1)[1])
            albums_of_artist = self.remote.get_albums_by_artist(artist)
            albums_of_artist.sort(key=(lambda item: item["albumartist_sort"]))
            return [models.Ref.directory(uri=get_uri_path("album",
                                                          str(album["id"])),
                                         name=album["album"])
                    for album in albums_of_artist]
        elif current_path.startswith("album:"):
            album_id = int(current_path.split(":", 1)[1])
            tracks_of_album = self.remote.get_tracks_by_album_id(album_id)
            tracks_of_album.sort(key=(lambda item: item.track_no))
            return [models.Ref.track(uri=track.uri, name=track.name)
                    for track in tracks_of_album]
        else:
            logger.error('Invalid browse URI: %s / %s', uri, current_path)
            return []

    def search(self, query=None, uris=None, exact=False):
        logger.debug('Query "%s":' % query)
        if not self.remote.has_connection:
            return []

        if not query:
            # Fetch all data(browse library)
            return SearchResult(uri='beets:search',
                                tracks=self.remote.get_tracks())

        self._validate_query(query)
        search_list = []
        for (field, val) in query.iteritems():
            if field == "any":
                search_list.append(val[0])
            elif field == "album":
                search_list.append(("album", val[0]))
            elif field == "artist":
                search_list.append(("artist", val[0]))
            elif field == "track_name":
                search_list.append(("title", val[0]))
            elif field == "date":
                # TODO: there is no "date" in beets - just "day", "month"
                #       and "year". Determine the format of "date" and
                #       define a suitable date format string?
                search_list.append(("date", val[0]))
            else:
                logger.info("Ignoring unknown query key: %s", field)
        logger.debug('Search query "%s":' % search_list)
        tracks = self.remote.get_tracks_by(search_list, exact, [])
        uri = '-'.join([item if isinstance(item, str) else "=".join(item)
                        for item in search_list])
        return SearchResult(uri='beets:search-' + uri, tracks=tracks)

    def lookup(self, uri):
        # TODO: verify if we should do the same for Albums
        track_id = uri.split(";")[1]
        logger.debug('Beets track id for "%s": %s' % (track_id, uri))
        track = self.remote.get_track(track_id, True)
        return [track] if track else []

    def _validate_query(self, query):
        for values in query.values():
            if not values:
                raise LookupError('Missing query')
            for value in values:
                if not value:
                    raise LookupError('Missing query')
