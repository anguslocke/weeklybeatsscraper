from html.parser import HTMLParser

import requests


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
        r = requests.get(url, params)
        self.feed(r.text)

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
