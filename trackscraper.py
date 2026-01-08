import argparse
import multiprocessing as mp
import os
import re
import unicodedata

import mutagen
import requests
from bs4 import BeautifulSoup
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4
from mutagen.id3 import ID3, TCMP, USLT
from mutagen.mp3 import EasyMP3

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
                track[thing] = str(
                    self.converters.get(thing, lambda t: t.string)(result[0])
                )
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


def scrape_week_tracks(week, year=2024):
    """
    Grab all the tracks for a specified week (probably spans multiple pages)
    """
    scraper = TrackLinkScraper()
    for i in range(1, 10):
        if not scraper.scrape(
            "https://weeklybeats.com/music",
            params={
                "p": i,
                "o": "title",
                "y": year,
                "s": "tag:week {} {}".format(week, year),
                # filter = none?
                "f": 8,
            },
        ):
            break
    return scraper.tracks


def get_track_description(track):
    r = requests.get(track["page"])
    b = BeautifulSoup(r.text, features="html.parser")
    try:
        description = b.head.find_all("meta", property="og:description")[0].attrs[
            "content"
        ]
    except IndexError:
        with open(f'/tmp/dump-{track["url"].split("/")[-1]}', "w+") as g:
            g.write(r.text)
        return
    # Newline and unicode compatibility normalization
    description = "\n".join(unicodedata.normalize("NFKD", description).splitlines())
    track["description"] = description


def scrape_track_descriptions(tracks, parallel=False):
    """
    Grab all the track descriptions.
    """
    if parallel:
        with mp.Pool(50) as p, tqdm(total=len(tracks)) as progress:
            for _ in p.imap_unordered(get_track_description, tracks, 2):
                progress.update()
    else:
        for track in tqdm(tracks):
            get_track_description(track)


def download_track(track, destination, album=None, force_download=False):
    """
    Download a particular track and update metadata with title/artist/album.
    """
    file_path = os.path.join(destination, track["url"].split("/")[-1])
    if not os.path.exists(file_path) or force_download:
        r = requests.get(track["url"])
        with open(file_path, "wb+") as g:
            g.write(r.content)

    # TODO: split out downloading and metadataing
    # TODO: on errors, try changing extension
    #   or better, check filetype?

    # tbh idk why these are necessary
    EasyID3.RegisterTextKey("lyrics", "USLT")
    EasyID3.RegisterTextKey("compilation", "TCMP")
    EasyMP4.RegisterTextKey("lyrics", "\xa9lyr")
    EasyMP4.RegisterTextKey("compilation", "cpil")

    try:
        f = mutagen.File(file_path, easy=True)
        # Only used for some checks I don't know how to make on Easy.
        hard = mutagen.File(file_path)
    except Exception:
        print(f"Error loading metadata '{file_path}'")
        return

    # breakpoint()
    # TODO: less hacky
    if isinstance(f, EasyMP3):
        reload_description = "USLT::XXX" not in hard
    elif isinstance(f, EasyMP4):
        reload_description = "\xa9lyr" not in hard
    else:
        reload_description = "lyrics" not in f
    if reload_description:
        get_track_description(track)
        f["lyrics"] = track["description"]

    f["title"] = track["title"]
    f["artist"] = track["artist"]
    f["albumartist"] = "Various Artists"
    f["compilation"] = "1"

    # personal preference: i don't want these
    for tag in ("tracknumber", "totaltracks", "artwork", "album"):
        f.pop(tag, None)

    if album is not None:
        f["album"] = album
    f.save()


def download_tracks(tracks, destination, album=None, force_download=False):
    for track in tqdm(tracks, maxinterval=1):
        try:
            download_track(track, destination, album, force_download)
        except Exception as e:
            print(f"Error downloading '{track}'")
            print(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download WeeklyBeats week tracks.")
    parser.add_argument(
        "-w", "--week", type=int, default=None, help="Week number to download."
    )
    parser.add_argument(
        "-y",
        "--year",
        type=int,
        default=2024,
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

    if args.week is None:
        try:
            args.week = int(args.destination.split("-")[-1])
            assert args.week >= 1 and args.week <= 52
        except:
            raise ValueError("ya gotta specify a week")

    print(f"Scraping tracks for week {args.week}...")
    tracks = scrape_week_tracks(args.week, args.year)
    print("Downloading new tracks (and descriptions) and updating metadata...")
    download_tracks(
        tracks,
        args.destination,
        "WB {} wk {}".format(args.year, args.week),
        args.force_download,
    )
