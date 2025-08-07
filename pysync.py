__author__ = "forrest, benward"
__copyright__ = "Copyright 2021, BFF.fm"
__credits__ = ["Forrest Guest", "Ben Ward"]
__version__ = "1.6"
__status__ = "Production"

# basic os functions
import os, sys

# logging
import logging
from logging.handlers import RotatingFileHandler

# scheduling imports
import time
import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# connecting to the website - get next show
import urllib.request

# utilities for writing output files
import shutil

# json parsing - get next show
import json

# yaml parsing - config
import yaml

# MP3 tag editing
from mutagen.id3 import ID3NoHeaderError, ID3v1SaveOptions
from mutagen.id3 import ID3, TIT2, TALB, TPE1

from slack_sdk.webhook import WebhookClient

import audio

# TODO: configuration file
# TODO: email on directory creation (new show - won't play)
# TODO: daemonize
# TODO: Auto Rerun (second to last show in podcast RSS)

LOGGER = logging.getLogger()

# TODO -- move global config object into something that is passed around to make testing easier
CONFIG = {}


def build_slack_message(text, icon=None, detail=None):
    message = ''

    if (icon is not None):
        message = message + icon + " "

    message = message + text

    if (detail is not None and detail):
        message = message + "\n" + "> " + str(detail)

    return message

# slack integration - Use this for #alerts (failures only)
def notify_slack_alerts(message):
    if not bool(CONFIG["enable_slack"]):
        return
    alerts_url = CONFIG["alerts_url"]
    webhook = WebhookClient(alerts_url)
    LOGGER.debug('SLACK ALERT: ' + message)
    response = webhook.send(text=message)
    notify_slack_monitor(message)
    return

# slack integration - Use this for #monitor-automation (both failures and successes)
def notify_slack_monitor(message):
    if not bool(CONFIG["enable_slack"]):
        return
    monitor_url = CONFIG["monitor_url"]
    webhook = WebhookClient(monitor_url)
    LOGGER.debug('SLACK MON: ' + message)
    response = webhook.send(text=message)
    return

def possibly_download_broadcast(broadcast):
    """ Given a dictionary of data representing a broadcast, possibly download the mp3 associated with it.

    See "retrieve_upcoming_broadcast_metadata" function below for example structure of these broadcast dicts

    Reasons we wouldn't download:

    - There is no media metadata associated with it
    - The file already exists and it's the same file we expect
    - There is otherwise some failure in the downloading mechanism

    Once we download the broadcast, we:

    - Overwrite the existing mp3 tag based on the show information in the broadcast
    """

    # Config params
    destination_folder = CONFIG["destination_folder"]

    show_title = broadcast['Show']['title']
    start_time = broadcast['start']

    # We'll check if this show is starting imminently when decided whether to report/log missing MP3s
    showtime = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    now_plus_60 = datetime.datetime.now() + datetime.timedelta(minutes=60)

    remote_path = ""

    show_id = broadcast['show_id']
    LOGGER.debug("Processing show: " + show_id)

    title = broadcast['title']
    LOGGER.debug("Broadcast title: " + title)

    # Look for attached media
    show_media = broadcast['media']
    for media in show_media:
        subtype = media.get('subtype', 'no key found')
        LOGGER.debug("Media subtype: " + subtype)
        if subtype == 'mp3':
            LOGGER.debug("found an mp3: ")
            remote_path = media['url']
            LOGGER.debug("Remote Path: " + remote_path)
    if not remote_path:
        LOGGER.debug("Show {} does not have an MP3 attached.".format(show_id))
        # Report to Slack if starting-soon show doesn't have an MP3. Otherwise, process silently.
        if (showtime <= now_plus_60):
            notify_slack_monitor(build_slack_message("_{}_ at {} does not have an MP3 attached. Expecting live broadcast.".format(show_title, start_time), ":mute:"))
        return

    # Get show info for MP3 tags:
    show_info = broadcast['Show']
    LOGGER.debug(show_info)

    album = show_info['title']
    LOGGER.debug("Show Name (album): " + album)

    short_name = show_info['short_name']
    LOGGER.debug("Short Name (local folder): " + short_name)

    # iterate through hosts
    LOGGER.debug("trying to get hosts")
    hosts = show_info['hosts']
    host_list = []
    for host in hosts:
        LOGGER.debug("Found a host")
        host_list.append(host['display_name'])

    if len(host_list) == 0:
        LOGGER.debug("No host data in API response, use show name as artist tag placeholder")
        artist = album
    elif len(host_list) > 1:
        LOGGER.debug("making a list of hosts for Artist field")
        artist = ','.join(host_list)
    else:
        LOGGER.debug("Only one host")
        artist = host_list[0]

    LOGGER.debug("Hosts (artist): " + artist)

    # construct filename
    metadata_filename = os.path.join(destination_folder, short_name, short_name + ".json")
    local_filename = os.path.join(destination_folder, short_name, short_name + "-newest.mp3")
    local_directory = os.path.dirname(local_filename)

    LOGGER.debug('Local Filename: ' + local_filename)
    LOGGER.debug('Local metadata filename: ' + metadata_filename)

    # create directories, if needed
    if not os.path.exists(local_directory):
        LOGGER.warning('Had to make directory ' + local_directory)
        notify_slack_alerts(build_slack_message("New show warning, no local directory existed.", ":warning:", "Created `{}`. You should verify that this was expected.".format(local_directory)))
        os.makedirs(local_directory)

    # If we already have an MP3 for this show, check if it matches the new data
    if os.path.exists(local_filename) and os.path.exists(metadata_filename):

        LOGGER.debug("Local MP3 for show exists. Opening sidecar metadata to compare source.")
        with open(metadata_filename, 'r') as metadata_file:
            source_metadata = json.load(metadata_file)

        # Uploaded objects are trusted to be immutable due to CDN caching, so we only need to compare the file name
        previous_path = source_metadata['url']
        if previous_path == remote_path:
            LOGGER.debug("Local file source matches remote URL. No download required. {}".format(remote_path))
            LOGGER.debug("Previously downloaded at: {}".format(source_metadata['download_time']))
            notify_slack_monitor(build_slack_message(
                "_{}_ already downloaded and cued for {}".format(show_title, start_time),
                ":white_check_mark:",
                "File was previously downloaded at `{}`".format(source_metadata['download_time'])
            ))
            return
        else:
            LOGGER.debug("Local file source name ({}) different from remote ({}); file has changed: Download new file.".format(previous_path, remote_path))

    # If the existing file doesn't match the remote file
    notify_slack_monitor(build_slack_message(
        "Downloading next {} broadcast: _{}_ at {}".format(show_title, title, start_time),
        ":arrow_down:",
        "Downloading `{}` to `{}`".format(remote_path, local_filename)
    ))

    # Download file
    LOGGER.info("Downloading " + remote_path + " to " + local_filename)
    # todo/possible bug: forcing int conversion, need to handle exceptions
    retry_count = int(CONFIG["retry_count"])
    for i in range(retry_count):
        try:
            with urllib.request.urlopen(remote_path) as response, open(local_filename, 'wb') as out_file:
                expected_bytes = response.headers.get('content-length')
                shutil.copyfileobj(response, out_file)

            actual_bytes = os.path.getsize(local_filename)

            if (int(actual_bytes) != int(expected_bytes)):
                message = "Download size did not match: {} bytes saved, expected {} bytes".format(actual_bytes, expected_bytes)

                LOGGER.debug(message)
                notify_slack_monitor(build_slack_message(message, ":abacus:"))
                raise RuntimeError(message)

            # Record metadata before any local modification can occur
            with open(metadata_filename, 'w') as metadata_file:
                json.dump({
                    "url": remote_path,
                    "download_time": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "filesize": expected_bytes
                }, metadata_file)
            LOGGER.debug("Wrote metadata sidecar: {}".format(metadata_filename))

        except Exception as e:
            if i < retry_count - 1: # i is zero indexed
                LOGGER.debug("Download attempt {} failed. {}".format(i + 1, e))
                notify_slack_monitor(build_slack_message(
                    "Download attempt failed, {}/{}".format(i, retry_count),
                    ":warning:",
                    e))
                continue
            else:
                LOGGER.debug("Download completely failed. {}".format(i, e))
                notify_slack_alerts(build_slack_message(
                    "Downloading `{}` failed: `{}`. ".format(remote_path, e),
                    ":bangbang:",
                    "Recording of {} must be manually cued to `{}` before *{}*".format(show_title, local_filename, start_time)
                ))
                return
        break

    if os.path.exists(local_filename):
        LOGGER.info("download complete.")
        notify_slack_monitor(build_slack_message(
            "Download successful. _{}_ cued for {}".format(show_title, start_time),
            ":white_check_mark:",
            "Automation will broadcast `{}`".format(local_filename)
        ))

        # TODO -- Add logic here to pad file if it's a length that would cause problems

        set_mp3_tag(local_filename, artist, album, title)
        inspect_track_length(local_filename)

    else:
        LOGGER.info("download completed, but local file not available: {}".format(local_filename))
        notify_slack_alerts(build_slack_message(
            "Local file `{}` is not available after download.".format(local_filename),
            ":bangbang:",
            "{} recording `{}` must be manually cued to `{}` before *{}*".format(show_title, remote_path, local_filename, start_time)
        ))
    return

def set_mp3_tag(local_filename, artist, album, title):
    # set mp3 tags
    LOGGER.debug("Adding mp3 tag")
    try:
        tags = ID3(local_filename)
    except ID3NoHeaderError:
        LOGGER.debug("Adding ID3 header")
        tags = ID3()

    LOGGER.debug("Removing tags")
    tags.delete(local_filename)

    LOGGER.debug("Constructing tag")
    tags["TIT2"] = TIT2(encoding=3, text=title) # title
    tags["TALB"] = TALB(encoding=3, text=album) # album
    tags["TPE1"] = TPE1(encoding=3, text=artist) # artist

    LOGGER.debug("Saving tags")
    # v1=2 switch forces ID3 v1 tag to be written
    tags.save(
        filename=local_filename,
        v1=ID3v1SaveOptions.CREATE,
        v2_version=4
    )

def inspect_track_length(local_filename):
    track_length = audio.get_audio_duration_minutes_from_file(local_filename)
    LOGGER.info(f"Track is {track_length} minutes long")
    if audio.length_is_close_to_thirty_minute_boundary(track_length):
        LOGGER.info(f"Track is close to the 30 minute boundary zone!")



# main function
def fetch_upcoming():
    LOGGER.name = 'bff.download_files'
    LOGGER.info("Starting process")

    notify_slack_monitor(build_slack_message("Automation checking for new recorded shows...", ":eyes:"))

    station_url = CONFIG["station_url"]
    key = CONFIG["key"]

    broadcast_metadata = retrieve_upcoming_broadcast_metadata(station_url, key)

    if broadcast_metadata:
        LOGGER.debug("{} upcoming broadcasts returned by Creek API".format(len(broadcast_metadata)))
        # Process every upcoming broadcast and cue the download file if new:
        for broadcast in broadcast_metadata:
            possibly_download_broadcast(broadcast)
    else:
        LOGGER.debug("No upcoming broadcast returned by Creek")
        notify_slack_monitor(build_slack_message("There is no upcoming broadcast published in Creek", ":shrug:"))

    LOGGER.info("Finished process")
    LOGGER.name = __name__

def retrieve_upcoming_broadcast_metadata(station_url, key):
    """ Retrieves a json response from creek that we parse into a list of dictionaries.

    Example format of this is like below -- note some have attached media, and some don't.

    [
        {
            "id": "48469",
            "title": "Heartbeats 8/4",
            "start": "2025-08-04 16:00:00",
            "text": "",
            "show_id": "612",
            "url": "http://bff.fm/broadcasts/48469",
            "Show": {
                "id": "612",
                "title": "Heartbeats FM",
                "short_name": "heartbeats-fm",
                "short_description": "HEARTBEATS is a series of live shows in the Bay Area that spotlights artists and focuses on immersive and rousing electronic dance music. \r\nReach out if you'd like to spin at one of our events. If not then enjoy the tunes.\r\n",
                "full_description": "(Future Funk, City Pop, Nu-Disco, Bay House, Retro Internationale.) HEARTBEATS is a series of live shows in the Bay Area that spotlights artists and focuses on immersive and rousing dance music. This channel will serve as a bulletin board for those events as well as a mood board for your Monday groove. I want to expose YOU, the listener, to a new kind of slapper. Reach out if you'd like to spin at one of our events.&nbsp;If not then enjoy the tunes.",
                "url": "http://bff.fm/shows/heartbeats-fm",
                "Image": null,
                "image": false,
                "airtime_rule": null,
                "hosts": [],
                "airtimes": [],
                "categories": [],
                "group": null,
                "meta": []
            },
            "media": [
                {
                    "id": "146898",
                    "title": "bff_Aug4.mp3",
                    "description": "",
                    "type": "audio",
                    "subtype": "mp3",
                    "file": "heartbeats-fm/1754321122YDBQjwjv-bff_Aug4.mp3",
                    "url": "https://a.bff.fm/audio/heartbeats-fm/1754321122YDBQjwjv-bff_Aug4.mp3",
                    "meta": []
                }
            ],
            "User": null,
            "Image": null,
            "tracks": []
        },
        {
            "id": "48422",
            "title": "PICKLEPLANET #156 ERIC PT 3",
            "start": "2025-08-04 18:00:00",
            "text": "HES BACK BABY THE BIRTHDAY KING BRINGING THE BANGERS",
            "show_id": "507",
            "url": "http://bff.fm/broadcasts/48422",
            "Show": {
                "id": "507",
                "title": "PICKLEPLANET",
                "short_name": "pickleplanet",
                "short_description": "pickle licious tracks sprinkled with new stuff, local stuff and all the things that make up my chaos brainz ",
                "full_description": "pickle licious tracks sprinkled with new stuff, local stuff and all the things that make up my chaos brainz.",
                "url": "http://bff.fm/shows/pickleplanet",
                "Image": null,
                "image": false,
                "airtime_rule": null,
                "hosts": [],
                "airtimes": [],
                "categories": [],
                "group": null,
                "meta": []
            },
            "media": [],
            "User": null,
            "Image": null,
            "tracks": []
        }
    ]
    """

    # download json
    upcoming_url = "api/broadcasts/upcoming?key="
    full_upcoming_url = station_url + upcoming_url + key
    LOGGER.debug("Upcoming broadcast URL: " + full_upcoming_url)

    # Get next broadcast from Creek:
    try:
        response = urllib.request.urlopen(full_upcoming_url)
    except Exception as e:
        LOGGER.debug("Error: Failed to read from Creek upcoming broadcasts API.")
        notify_slack_alerts(build_slack_message("Automation could not connect to Creek upcoming broadcast API `{}`".format(upcoming_url), ":bangbang:", e))
        return None

    # Attempt to parse as JSON - do this in separate steps for clearer debugging
    try:
        str_response = response.read().decode('utf-8')
        broadcasts = json.loads(str_response)
    except Exception as e:
        LOGGER.debug("Error: Creek upcoming broadcasts API response could not be parsed.")
        notify_slack_alerts(":bangbang: Automation failed to parse Creek upcoming broadcast response `{}{}`\n\n> `{}`".format(station_url, upcoming_url, e))
        return None

    #LOGGER.debug("string response: " + str_response)
    #LOGGER.debug("json response: ")
    #LOGGER.debug(broadcasts)

    return broadcasts


def configure_logs(logger, config):
    # prep logging system
    log_path = config["log_path"]
    log_file_name = config["log_name"]
    log_level = config["log_level"]

    log_format = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    logger.setLevel(log_level)

    # log to file
    log_file_handler = RotatingFileHandler(
        filename="{0}/{1}.log".format(log_path, log_file_name),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=20
    )
    log_file_handler.setFormatter(log_format)
    logger.addHandler(log_file_handler)

    # log to console
    log_console_handler = logging.StreamHandler()
    log_console_handler.setFormatter(log_format)
    logger.addHandler(log_console_handler)


if __name__ == '__main__':
    # MAIN PROCESS

    with open('pysync-config.yml', 'r') as f:
        CONFIG = yaml.load(f, Loader=yaml.SafeLoader)
        if not CONFIG:
            raise Exception("No configuration found")

    configure_logs(LOGGER, CONFIG)

    LOGGER.info("Program Start")

    if(len(sys.argv) > 1):
        if(sys.argv[1] == "now"):
            LOGGER.info("now switch passed, running once and exiting.")
            fetch_upcoming()
            sys.exit(0)

    # background scheduler is part of apscheduler class
    scheduler = BackgroundScheduler()
    # add a cron based (clock) scheduler for every 30 minutes, 20 minutes past
    scheduler.add_job(fetch_upcoming, 'cron', minute='20,50')
    scheduler.start()

    LOGGER.info('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()  # Not strictly necessary if daemonic mode is enabled but should be done if possible

    LOGGER.info("Program Stop")
