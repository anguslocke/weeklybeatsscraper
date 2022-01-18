import json
import os
import sys
from html.parser import HTMLParser

import requests


class HTMLTrackParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tracks = []
        self._opentags = []
        self._listitem = None
        self._itemdepth = 0

    def _depth(self):
        return len(self._opentags)

    def _to_be_ignored(self, tag):
        # Input tags seem to not be closed sometimes.
        return tag in ["input"]

    def handle_starttag(self, tag, attrs):
        if self._to_be_ignored(tag):
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
        if self._to_be_ignored(tag):
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
        # These key bits of data are identified by certain structures of tags,
        #   some of which with certain attributes.
        signatures = {
            "title": (
                ("div", {"class": "item-subject"}),
                ("h3", {}),
                ("a", {}),
            ),
            "week": (
                ("li", {"class": "info-views"}),
                ("strong", {}),
            ),
            "comments": (
                ("li", {"class": "info-replies"}),
                ("strong", {}),
            ),
        }
        converters = {"week": lambda s: int(s.split()[1]), "comments": int}
        # Check if we match any of the target signatures.
        for thing, conditions in signatures.items():
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
                self._listitem[thing] = converters.get(thing, str)(data)


def fetch_tracks(username="wangus"):
    r = requests.get("https://weeklybeats.com/" + username)
    w = HTMLTrackParser()
    w.feed(r.text)
    return w.tracks


def save_record(tracks, path):
    with open(path, "w+") as g:
        json.dump(tracks, g)


def load_record(path):
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return json.load(f)


def check_new_comments(tracks, record):
    new_comments = {}

    def week_indexed(a):
        return {i["week"]: i for i in a}

    tracks, record = map(week_indexed, (tracks, record))
    for week in tracks:
        if week not in record:
            continue
        new_comment_count = tracks[week]["comments"] - record[week]["comments"]
        if new_comment_count != 0:
            new_comments[week] = new_comment_count
    return new_comments


def fetch_new_comments(record_path, username="wangus"):
    tracks = fetch_tracks()
    record = load_record(record_path)
    new_comments = check_new_comments(tracks, record)
    save_record(tracks, record_path)
    return new_comments


if __name__ == "__main__":
    # new_comments = fetch_new_comments(sys.argv[1])
    new_comments = {}
    print("cool")
    if new_comments:
        for week in new_comments:
            print("Week {}: {:+} comments")
