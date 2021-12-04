import time
from urllib.request import Request, urlopen, HTTPError
from urllib.parse import urlparse, quote
from .normalizer import ArtistNormalizer, AlbumNormalizer
from .deromanizer import DeRomanizer

QUERY_TEMPLATE = "https://itunes.apple.com/search?term=%s&media=music&entity=album"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36"
THROTTLED_WAIT_MINUTES = 30
THROTTLED_HTTP_CODES = [403, 429]

class AppleDownloader(object):
    def __init__(self, verbose):
        self.verbose = verbose
        self.artist_normalizer = ArtistNormalizer()
        self.album_normalizer = AlbumNormalizer()
        self.deromanizer = DeRomanizer()
        
    def _urlopen_safe(self, url):
        while True:
            try:
                q = Request(url)
                q.add_header("User-Agent", USER_AGENT)
                response = urlopen(q)
                return response.read()
            except HTTPError as e:
                if e.code in THROTTLED_HTTP_CODES:
                    # we've been throttled, time to sleep
                    domain = urlparse(url).netloc
                    print("WARNING: Request limit exceeded from %s, trying again in %d minutes..." % (domain, THROTTLED_WAIT_MINUTES))
                    time.sleep(THROTTLED_WAIT_MINUTES * 60)
                else:
                    raise e

    def _urlopen_text(self, url):
        try:
            return self._urlopen_safe(url).decode("utf8")
        except Exception as error:
            if ("certificate verify failed" in str(error)):
                print("ERROR: Python doesn't have SSL certificates installed, can't access " + url)
                print("Please run 'Install Certificates.command' from your Python installation directory.")
            else:
                print("ERROR: reading URL (%s): %s" % (url, str(error)))
            return ""

    def _download_from_url(self, image_url, dest_path):
        image_data = self._urlopen_safe(image_url)
        output = open(dest_path,'wb')
        output.write(image_data)
        output.close()
        print("Downloaded cover art: "  + dest_path)

    def _query(self, artist, album):
        query_term = "%s %s" % (artist, album)
        if album in artist:
            query_term = artist
        elif artist in album:
            query_term = album
        url = QUERY_TEMPLATE % quote(query_term)
        json = self._urlopen_text(url)
        if json:
            try:
                return eval(json)
            except:
                pass
        return {}

    def _get_data(self, meta):
        artist = self.artist_normalizer.normalize(meta.artist)
        album = self.album_normalizer.normalize(meta.album)
        info = self._query(artist, album)
        if not info or not info['resultCount']:
            # no result found, try replacing any roman numerals
            artist = self.deromanizer.convert_all(artist)
            album = self.deromanizer.convert_all(album)
            info = self._query(artist, album)
        return (artist, album, info)

    def download(self, meta, art_path):
        (meta_artist, meta_album, info) = self._get_data(meta)
        if info:
            try:
                art = ""
                # go through albums, use exact match or first contains match if no exacts found
                for album_info in reversed(info['results']):
                    artist = self.artist_normalizer.normalize(album_info['artistName'])
                    album = self.album_normalizer.normalize(album_info['collectionName'])
                    
                    if not meta_artist in artist:
                        continue
                    if not meta_album in album:
                        continue
                    
                    art = album_info['artworkUrl100'].replace('100x100bb','500x500bb')
                    if meta_album == album:
                        break # exact match found
                if art:
                    self._download_from_url(art, art_path)
                    return True
            except Exception as error:
                print("ERROR encountered when downloading for artist (%s) and album (%s)" % (meta_artist, meta_album))
                print(error)

        if self.verbose:
            print("Failed to find matching artist (%s) and album (%s)" % (meta_artist, meta_album))
        return False
