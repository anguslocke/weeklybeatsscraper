import json
import os
import sys

import trackscraper


class WeekCommentsScraper(trackscraper.TrackListScraper):
    """
    Additionally parse the week number and the current comment count.
    """

    def __init__(self):
        super().__init__()
        self.signatures.update(
            {
                "week": (
                    ("li", {"class": "info-views"}),
                    ("strong", {}),
                ),
                "comments": (
                    ("li", {"class": "info-replies"}),
                    ("strong", {}),
                ),
            }
        )
        self.converters.update(
            {
                "week": lambda s: int(s.split()[1]),
                "comments": int,
            }
        )


def fetch_tracks(username="wangus"):
    """Fetch a user's track listing"""
    # TODO: does this paginate eventually?
    w = WeekCommentsScraper()
    w.scrape("https://weeklybeats.com/" + username)
    return w.tracks


def save_record(tracks, path):
    """Save a comment count record to a file."""
    with open(path, "w+") as g:
        json.dump(tracks, g)


def load_record(path):
    """Load a comment count record from a file (or empty if file doesn't exist yet)"""
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return json.load(f)


def check_new_comments(tracks, record):
    """
    Compare comment counts to an existing record and return which have new comments.
    Ignores previously unrecorded tracks
    """
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
    """
    Fetch new comment count for the specified username,
    assess which tracks have new comments,
    and update the record.
    """
    tracks = fetch_tracks()
    record = load_record(record_path)
    new_comments = check_new_comments(tracks, record)
    save_record(tracks, record_path)
    return new_comments


if __name__ == "__main__":
    new_comments = fetch_new_comments(sys.argv[1])
    print("cool")
    if new_comments:
        for week in new_comments:
            print("Week {}: {:+} comments".format(week, new_comments[week]))
