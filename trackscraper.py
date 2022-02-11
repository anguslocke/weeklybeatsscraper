import os
from html.parser import HTMLParser

import music_tag
import requests

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda sequence: (i for i in sequence)


class TrackListScraper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tracks = []
        self._opentags = []
        self._listitem = None
        self._itemdepth = 0
        # Key bits of data are identified by certain signatures of tags,
        #   some of which with certain attributes.
        self.signatures = {
            "title": (
                ("div", {"class": "item-subject"}),
                ("h3", {}),
                ("a", {}),
            ),
        }
        self.converters = {}

    def scrape(self, url, params=None):
        before = len(self.tracks)
        r = requests.get(url, params)
        self.feed(r.text)
        return len(self.tracks) > before

    def _depth(self):
        return len(self._opentags)

    def should_ignore(self, tag):
        # Input tags seem to not be closed sometimes.
        return tag in ["input"]

    def handle_starttag(self, tag, attrs):
        if self.should_ignore(tag):
            return
        attrs = dict(attrs)
        self._opentags.append((tag, attrs))
        if tag == "div" and attrs.get("class", "").startswith("main-item"):
            # Track list item start
            if self._listitem is not None:
                raise ValueError(
                    "Unclosed track list item at {}?".format(self.getpos())
                )
            self._listitem = {"id": attrs["id"]}
            self._itemdepth = self._depth()

    def handle_endtag(self, tag):
        if self.should_ignore(tag):
            return
        if self._depth() == 0 or tag != self._opentags[-1][0]:
            raise ValueError("Mismatch tag '{}' at {}".format(tag, self.getpos()))
        self._opentags.pop()
        if self._depth() < self._itemdepth:
            # TODO: validate track info
            self.tracks.append(self._listitem)
            self._listitem = None
            self._itemdepth = 0

    def handle_data(self, data: str) -> None:
        if self._listitem is None:
            return
        # Check if we match any of the target signatures.
        for thing, conditions in self.signatures.items():
            for tag, test in zip(self._opentags[-len(conditions) :], conditions):
                if test[0] != tag[0]:
                    break
                for attr in test[1]:
                    if attr not in tag[1] or tag[1][attr] != test[1][attr]:
                        break
                else:
                    # Everything checked out.
                    continue
                # If we got here, an attribute mismatched.
                break
            else:
                # No mismatches!
                self._listitem[thing] = self.converters.get(thing, str)(data)


class TrackLinkScraper(TrackListScraper):
    def __init__(self):
        super().__init__()
        self.signatures.update(
            {
                "url": (("div", {"class": "player-play play-list"}),),
                "artist": (
                    ("p", {}),
                    ("span", {"class": "item-starter"}),
                    ("cite", {}),
                ),
            }
        )
        # To be called when we match the signature above
        def extract_track_url(_):
            onclick = self._opentags[-1][1]["onclick"]
            # looks like
            # "setPlaylistItem('https://weeklybeats.s3.amazonaws.com/music/2022/wangus_weeklybeats-2022_1_wheats-thics-[sic].m4a');..."
            return onclick.split("'")[1]

        self.converters.update(
            {
                "url": extract_track_url,
            }
        )


def scrapeWeekTracks(week, year=2022):
    scraper = TrackLinkScraper()
    for i in range(1, 10):
        if not scraper.scrape(
            "https://weeklybeats.com/music",
            params={"p": i, "o": "title", "s": "tag:week {} {}".format(week, year)},
        ):
            break
    return scraper.tracks


def downloadTracks(tracks, destination, album=None):
    for track in tqdm(tracks):
        r = requests.get(track["url"])
        file_path = os.path.join(destination, track["url"].split("/")[-1])
        with open(file_path, "wb+") as g:
            g.write(r.content)
        f = music_tag.load_file(file_path)
        f["title"] = track["title"]
        f["artist"] = track["artist"]
        if album is not None:
            f["album"] = album
        f.save()
