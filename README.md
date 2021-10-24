# Downloader

BFF.fm's tool to download upcoming broadcasts to the automation computer. It's meant to be used for prerecorded shows and the 'variable length file' filetype of RadioDJ (http://radiodj.ro)

It will check every 20 and 50 minutes past the hour and review the list of upcoming shows from Creek. It then downloads the broadcast into a local folder with a fixed filename, corresponding to the automation system scheduler. It records the source filename, and will not download the source remote file twice. Remote filenames are considered immutable, so if a broadcast recording is changed, the MP3 filename must change.

You need to set up your automation to load the correct file. Best results in RadioDJ are to set up the file as a variable length file and just set an event to start the show.  This means you'll have to maintain the schedules in Creek as well as RadioDJ.

## Installation instructions:

1. Install Python 3 (tested against 3.5 on windows)
2. Install modules

    pip install apscheduler mutagen pyyaml slack_sdk

You'll need to go into Creek for your station and download the API key.

1. Log in as a station admin, then:
2. Tools > Settings > Integration > Scroll down to bottom > Secret Key

Edit the `pysync-config.yml` configuration file to reflect this key.

### To enable Slack notifications

1. Set `enable_slack` to true in `pysync-config.yml`
2. Go to Slack's developer portal and create an app, add webhooks for the channel(s) you want to post to and add them to the config file.

It should be left open in a command window, just double click python-sync.py to begin
