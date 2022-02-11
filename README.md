# hello

If you're here, I'm assuming you know about WeeklyBeats.
https://weeklybeats.com

I wanted a way to batch download tracks, so I could listen offline.

You give the week number (and the year, though I haven't tried anything
other than default 2022), and it downloads all of that week's tracks,
and amends the metadata with title, artist, and "album title" of the
week number.

# dependencies

You gotta get Python 3 going yourself.
And you'll need modules:
* requests (fetch the info/tracks)
* music-tag (amend track metadata)
* tqdm (optional, just a lil progress bar)

and their dependencies.

The Pipfile is there if you use Pipenv like I do.

# usage

e.g. grab Week 5's tracks:
```
python trackscraper.py -w 5 path/to/destination/directory
```

# bonus

There's another script that I used to grab a peek at the comment counts.
I was going to set up something to send me a notification on new comments,
but I never got around to that part. Just the logic to fetch counts.

# bonus bonus

shameless plug https://weeklybeats.com/wangus
