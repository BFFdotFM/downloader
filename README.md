# downloader
Tool to download upcoming shows to the automation computer

It will check every 20 and 50 minutes past the hour to see if a show is coming up in the next ten minutes, then downloads the show into a local folder.  You also need to set up your automation to load the correct file.  Best results in RadioDJ are to set up the file as a variable length file and just set an event to start the show.  This means you'll have to maintain the schedules in creek as well as RadioDJ.

It's meant to be used for prerecorded shows and the 'variable length file' filetype of RadioDJ (http://radiodj.ro)

Installation instructions:

    Install Python 3 (tested against 3.5 on windows)
    Install modules
        pip install apscheduler mutagen pyyaml slack_sdk

You'll need to go into creek for your station and download the private key.

Log in as a station admin, then:
Tools > Settings > Integration > Scroll down to bottom > Secret Key

Manually edit the script to include this key.

It should be left open in a command window, just double click python-sync.py to begin
