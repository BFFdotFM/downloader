# downloader
Tool to download upcoming shows to the automation computer

It will check every 20 and 50 minutes past the hour to see if a show is coming up in the next ten minutes, then downloads the show into a local folder.  You also need to set up your automation to load the correct file.  Best results in RadioDJ are to set up the file as a variable length file and just set an event to start the show.  This means you'll have to maintain the schedules in creek as well as RadioDJ.

Install Python 2.7 on the local computer.

You'll need to go into creek for your station and download the private key.

Log in as a station admin, then:
Tools > Settings > Integration > Scroll down to bottom > Secret Key

Manually edit the script to include this key.
