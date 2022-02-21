import argparse
import os
import re
import unicodedata

import music_tag
import requests
from bs4 import BeautifulSoup

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda sequence: (i for i in sequence)


class TrackListScraper:
    """
    Parses WB page contents for track lists (works for searches, profiles, etc).
    The structure of HTML tags (and perhaps the values of their attributes)
    is used to identify bits of content, and converter functions can
    parse or cast the data to relevant formats.
    """

    def __init__(self):
        self.tracks = []
        # Key bits of data are identified by certain signatures of tags,
        #   some of which with certain attributes.
        self.signatures = {
            "title": (
                ("div", {"class": ["item-subject"]}),
                ("h3", {}),
                ("a", {}),
            ),
        }
        self.converters = {}

    def scrape(self, url, params=None):
        """Convenience function to scrape tracks from a URL + query params"""
        before = len(self.tracks)
        r = requests.get(url, params)
        self.feed(r.text)
        return len(self.tracks) > before

    def _signature_key_match(self, tag, key, verbose=False):
        """
        Checks a BeautifulSoup tag against a signature item (name, plus attrs).
        """
        if verbose:
            print("checking for {}".format(key))
        if tag.name != key[0]:
            if verbose:
                print("  mismatch name {} != {}".format(tag.name, key[0]))
            return False
        for attr in key[1]:
            if not tag.has_attr(attr):
                if verbose:
                    print("  absent " + attr)
                return False
            value = key[1][attr]
            if value and value != tag[attr]:
                if verbose:
                    print("  mismatch {} != {}".format(tag[attr], value))
                return False
        return True

    def _signature_match_function(self, sig):
        """
        Returns a function that checks a tag against the specified signature.
        (name/attrs of tag itself, and looking back to any relevant parents)
        """

        def signature_match(tag):
            if not self._signature_key_match(tag, sig[-1]):
                return False
            for parent, key in zip(tag.parents, sig[-2::-1]):
                if not self._signature_key_match(parent, key):
                    return False
            return True

        return signature_match

    def feed(self, contents):
        b = BeautifulSoup(contents, features="html.parser")
        track_tags = b.find_all("div", class_=re.compile("^main-item"))
        for track_tag in track_tags:
            track = {}
            # Find signatured things in track tag contents
            for thing, sig in self.signatures.items():
                result = track_tag.find_all(self._signature_match_function(sig))
                if len(result) != 1:
                    print("Bad '{}' signature: found {}?".format(thing, len(result)))
                track[thing] = self.converters.get(thing, lambda t: t.string)(result[0])
            # TODO: validate track info
            self.tracks.append(track)


class TrackLinkScraper(TrackListScraper):
    """
    Pull the track download URL and the artist name too.
    """

    def __init__(self):
        super().__init__()
        self.signatures.update(
            {
                "url": (("div", {"class": ["player-play", "play-list"]}),),
                "page": (
                    ("div", {"class": ["item-subject"]}),
                    ("h3", {}),
                    ("a", {}),
                ),
                "artist": (
                    ("p", {}),
                    ("span", {"class": ["item-starter"]}),
                    ("cite", {}),
                ),
            }
        )
        # To be called when we match the signature above
        def extract_track_url(tag):
            # "onclick" attr looks like
            # "setPlaylistItem('https://weeklybeats.s3.amazonaws.com/music/2022/wangus_weeklybeats-2022_1_wheats-thics-[sic].m4a');..."
            return tag.attrs["onclick"].split("'")[1]

        def extract_page_url(tag):
            return tag.attrs["href"]

        self.converters.update(
            {
                "page": extract_page_url,
                "url": extract_track_url,
            }
        )


def scrape_week_tracks(week, year=2022):
    """
    Grab all the tracks for a specified week (probably spans multiple pages)
    """
    scraper = TrackLinkScraper()
    for i in range(1, 10):
        if not scraper.scrape(
            "https://weeklybeats.com/music",
            params={"p": i, "o": "title", "s": "tag:week {} {}".format(week, year)},
        ):
            break
    return scraper.tracks


def get_track_description(page_url):
    r = requests.get(page_url)
    b = BeautifulSoup(r.text, features="html.parser")
    description = b.head.find_all("meta", property="og:description")[0].attrs["content"]
    # Newline and unicode compatibility normalization
    description = "\n".join(unicodedata.normalize("NFKD", description).splitlines())
    return description


def scrape_track_descriptions(tracks):
    """
    Grab all the track descriptions.
    """
    for track in tqdm(tracks):
        track["description"] = get_track_description(track["page"])


def download_track(track, destination, album=None, force_download=False):
    """
    Download a particular track and update metadata with title/artist/album.
    """
    file_path = os.path.join(destination, track["url"].split("/")[-1])
    if not os.path.exists(file_path) or force_download:
        r = requests.get(track["url"])
        with open(file_path, "wb+") as g:
            g.write(r.content)
    f = music_tag.load_file(file_path)
    f["title"] = track["title"]
    f["artist"] = track["artist"]
    f["compilation"] = True
    f["albumartist"] = "Various Artists"
    # Use the lyrics field to include the original description.
    if "lyrics" not in f:
        f["lyrics"] = get_track_description(track["page"])
    for tag in ("tracknumber", "totaltracks"):
        # I'm having trouble getting music-tag to unset track numbers on some files. This is OK?
        f[tag] = 0
    # Personal preference; remove artwork
    f["artwork"] = []
    f.remove_tag("album")
    if album is not None:
        f["album"] = album
    f.save()


def download_tracks(tracks, destination, album=None, force_download=False):
    for track in tqdm(tracks):
        download_track(track, destination, album, force_download)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download WeeklyBeats week tracks.")
    parser.add_argument(
        "-w", "--week", type=int, required=True, help="Week number to download."
    )
    parser.add_argument(
        "-y",
        "--year",
        type=int,
        default=2022,
        help="Year to download. Default %(default)s",
    )
    parser.add_argument(
        "-f",
        "--force-download",
        action="store_true",
        help="Download all tracks (normally we skip already-downloaded)",
    )
    parser.add_argument("destination", help="Destination directory.")
    args = parser.parse_args()

    print("Scraping tracks...")
    tracks = scrape_week_tracks(args.week, args.year)
    print("Downloading new tracks (and descriptions) and updating metadata...")
    download_tracks(
        tracks,
        args.destination,
        "WB {} wk {}".format(args.year, args.week),
        args.force_download,
    )
