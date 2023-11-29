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

# TODO: configuration file
# TODO: email on directory creation (new show - won't play)
# TODO: daemonize
# TODO: Auto Rerun (second to last show in podcast RSS)

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
    if not bool(config["enable_slack"]):
        return
    alerts_url = config["alerts_url"]
    webhook = WebhookClient(alerts_url)
    logger.debug('SLACK ALERT: ' + message)
    response = webhook.send(text=message)
    notify_slack_monitor(message)
    return

# slack integration - Use this for #monitor-automation (both failures and successes)
def notify_slack_monitor(message):
    if not bool(config["enable_slack"]):
        return
    monitor_url = config["monitor_url"]
    webhook = WebhookClient(monitor_url)
    logger.debug('SLACK MON: ' + message)
    response = webhook.send(text=message)
    return

def possibly_download_broadcast(broadcast):

    # Config params
    destination_folder = config["destination_folder"]

    show_title = broadcast['Show']['title']
    start_time = broadcast['start']

    # We'll check if this show is starting imminently when decided whether to report/log missing MP3s
    showtime = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    now_plus_60 = datetime.datetime.now() + datetime.timedelta(minutes=60)

    remote_path = ""

    show_id = broadcast['show_id']
    logger.debug("Processing show: " + show_id)

    title = broadcast['title']
    logger.debug("Broadcast title: " + title)

    # Look for attached media
    show_media = broadcast['media']
    for media in show_media:
        subtype = media.get('subtype', 'no key found')
        logger.debug("Media subtype: " + subtype)
        if subtype == 'mp3':
            logger.debug("found an mp3: ")
            remote_path = media['url']
            logger.debug("Remote Path: " + remote_path)
    if not remote_path:
        logger.debug("Show {} does not have an MP3 attached.".format(show_id))
        # Report to Slack if starting-soon show doesn't have an MP3. Otherwise, process silently.
        if (showtime <= now_plus_60):
            notify_slack_monitor(build_slack_message("_{}_ at {} does not have an MP3 attached. Expecting live broadcast.".format(show_title, start_time), ":mute:"))
        return

    # Get show info for MP3 tags:
    show_info = broadcast['Show']
    logger.debug(show_info)

    album = show_info['title']
    logger.debug("Show Name (album): " + album)

    short_name = show_info['short_name']
    logger.debug("Short Name (local folder): " + short_name)

    # iterate through hosts
    logger.debug("trying to get hosts")
    hosts = show_info['hosts']
    host_list = []
    for host in hosts:
        logger.debug("Found a host")
        host_list.append(host['display_name'])

    if len(host_list) == 0:
        logger.debug("No host data in API response, use show name as artist tag placeholder")
        artist = album
    elif len(host_list) > 1:
        logger.debug("making a list of hosts for Artist field")
        artist = ','.join(host_list)
    else:
        logger.debug("Only one host")
        artist = host_list[0]

    logger.debug("Hosts (artist): " + artist)

    # construct filename
    metadata_filename = os.path.join(destination_folder, short_name, short_name + ".json")
    local_filename = os.path.join(destination_folder, short_name, short_name + "-newest.mp3")
    local_directory = os.path.dirname(local_filename)

    logger.debug('Local Filename: ' + local_filename)
    logger.debug('Local metadata filename: ' + metadata_filename)

    # create directories, if needed
    if not os.path.exists(local_directory):
        logger.warning('Had to make directory ' + local_directory)
        notify_slack_alerts(build_slack_message("New show warning, no local directory existed.", ":warning:", "Created `{}`. You should verify that this was expected.".format(local_directory)))
        os.makedirs(local_directory)

    # If we already have an MP3 for this show, check if it matches the new data
    if os.path.exists(local_filename) and os.path.exists(metadata_filename):

        logger.debug("Local MP3 for show exists. Opening sidecar metadata to compare source.")
        with open(metadata_filename, 'r') as metadata_file:
            source_metadata = json.load(metadata_file)

        # Uploaded objects are trusted to be immutable due to CDN caching, so we only need to compare the file name
        previous_path = source_metadata['url']
        if previous_path == remote_path:
            logger.debug("Local file source matches remote URL. No download required. {}".format(remote_path))
            logger.debug("Previously downloaded at: {}".format(source_metadata['download_time']))
            notify_slack_monitor(build_slack_message(
                "_{}_ already downloaded and cued for {}".format(show_title, start_time),
                ":white_check_mark:",
                "File was previously downloaded at `{}`".format(source_metadata['download_time'])
            ))
            return
        else:
            logger.debug("Local file source name ({}) different from remote ({}); file has changed: Download new file.".format(previous_path, remote_path))

    # If the existing file doesn't match the remote file
    notify_slack_monitor(build_slack_message(
        "Downloading next {} broadcast: _{}_ at {}".format(show_title, title, start_time),
        ":arrow_down:",
        "Downloading `{}` to `{}`".format(remote_path, local_filename)
    ))

    # Download file
    logger.info("Downloading " + remote_path + " to " + local_filename)
    # todo/possible bug: forcing int conversion, need to handle exceptions
    retry_count = int(config["retry_count"])
    for i in range(retry_count):
        try:
            with urllib.request.urlopen(remote_path) as response, open(local_filename, 'wb') as out_file:
                expected_bytes = response.headers.get('content-length')
                shutil.copyfileobj(response, out_file)

            actual_bytes = os.path.getsize(local_filename)

            if (int(actual_bytes) != int(expected_bytes)):
                message = "Download size did not match: {} bytes saved, expected {} bytes".format(actual_bytes, expected_bytes)

                logger.debug(message)
                notify_slack_monitor(build_slack_message(message, ":abacus:"))
                raise RuntimeError(message)

            # Record metadata before any local modification can occur
            with open(metadata_filename, 'w') as metadata_file:
                json.dump({
                    "url": remote_path,
                    "download_time": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "filesize": expected_bytes
                }, metadata_file)
            logger.debug("Wrote metadata sidecar: {}".format(metadata_filename))

        except Exception as e:
            if i < retry_count - 1: # i is zero indexed
                logger.debug("Download attempt {} failed. {}".format(i + 1, e))
                notify_slack_monitor(build_slack_message(
                    "Download attempt failed, {}/{}".format(i, retry_count),
                    ":warning:",
                    e))
                continue
            else:
                logger.debug("Download completely failed. {}".format(i, e))
                notify_slack_alerts(build_slack_message(
                    "Downloading `{}` failed: `{}`. ".format(remote_path, e),
                    ":bangbang:",
                    "Recording of {} must be manually cued to `{}` before *{}*".format(show_title, local_filename, start_time)
                ))
                return
        break

    if os.path.exists(local_filename):
        logger.info("download complete.")
        notify_slack_monitor(build_slack_message(
            "Download successful. _{}_ cued for {}".format(show_title, start_time),
            ":white_check_mark:",
            "Automation will broadcast `{}`".format(local_filename)
        ))

        # set mp3 tags
        logger.debug("Adding mp3 tag")
        try:
            tags = ID3(local_filename)
        except ID3NoHeaderError:
            logger.debug("Adding ID3 header")
            tags = ID3()

        logger.debug("Removing tags")
        tags.delete(local_filename)

        logger.debug("Constructing tag")
        tags["TIT2"] = TIT2(encoding=3, text=title) # title
        tags["TALB"] = TALB(encoding=3, text=album) # album
        tags["TPE1"] = TPE1(encoding=3, text=artist) # artist

        logger.debug("Saving tags")
        # v1=2 switch forces ID3 v1 tag to be written
        tags.save(filename=local_filename,
                  v1=ID3v1SaveOptions.CREATE,
                  v2_version=4)
    else:
        logger.info("download completed, but local file not available: {}".format(local_filename))
        notify_slack_alerts(build_slack_message(
            "Local file `{}` is not available after download.".format(local_filename),
            ":bangbang:",
            "{} recording `{}` must be manually cued to `{}` before *{}*".format(show_title, remote_path, local_filename, start_time)
        ))
    return

# main function
def fetch_upcoming():
    logger.name = 'bff.download_files'
    logger.info("Starting process")

    notify_slack_monitor(build_slack_message("Automation checking for new recorded shows...", ":eyes:"))

    # Config params
    station_url = config["station_url"]
    key = config["key"]

    # download json
    upcoming_url = "api/broadcasts/upcoming?key="
    full_upcoming_url = station_url + upcoming_url + key
    logger.debug("Upcoming broadcast URL: " + full_upcoming_url)

    # Get next broadcast from Creek:
    try:
        response = urllib.request.urlopen(full_upcoming_url)
    except Exception as e:
        logger.debug("Error: Failed to read from Creek upcoming broadcasts API.")
        notify_slack_alerts(build_slack_message("Automation could not connect to Creek upcoming broadcast API `{}`".format(upcoming_url), ":bangbang:", e))
        return

    # Attempt to parse as JSON - do this in separate steps for clearer debugging
    try:
        str_response = response.read().decode('utf-8')
        broadcasts = json.loads(str_response)
    except Exception as e:
        logger.debug("Error: Creek upcoming broadcasts API response could not be parsed.")
        notify_slack_alerts(":bangbang: Automation failed to parse Creek upcoming broadcast response `{}{}`\n\n> `{}`".format(station_url, upcoming_url, e))
        return

    #logger.debug("string response: " + str_response)
    #logger.debug("json response: ")
    #logger.debug(broadcasts)

    if not broadcasts:
        logger.debug("No upcoming broadcast returned by Creek")
        notify_slack_monitor(build_slack_message("There is no upcoming broadcast published in Creek", ":shrug:"))
        return
    else:
        logger.debug("{} upcoming broadcasts returned by Creek API".format(len(broadcasts)))

    # Process every upcoming broadcast and cue the download file if new:
    for broadcast in broadcasts:
        possibly_download_broadcast(broadcast)

    logger.info("Finished process")
    logger.name = __name__


if __name__ == '__main__':
    # MAIN PROCESS

    with open('pysync-config.yml', 'r') as f:
        config = yaml.load(f)

    # prep logging system
    log_path = config["log_path"]
    log_file_name = config["log_name"]
    log_level = config["log_level"]

    log_format = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # log to file
    log_file_handler = RotatingFileHandler(filename="{0}/{1}.log".format(log_path, log_file_name),
                                           maxBytes=10 * 1024 * 1024,  # 10 MB
                                           backupCount=20)
    log_file_handler.setFormatter(log_format)
    logger.addHandler(log_file_handler)

    # log to console
    log_console_handler = logging.StreamHandler()
    log_console_handler.setFormatter(log_format)
    logger.addHandler(log_console_handler)

    logger.info("Program Start")

    if(len(sys.argv) > 1):
        if(sys.argv[1] == "now"):
            logger.info("now switch passed, running once and exiting.")
            fetch_upcoming()
            sys.exit(0)

    # background scheduler is part of apscheduler class
    scheduler = BackgroundScheduler()
    # add a cron based (clock) scheduler for every 30 minutes, 20 minutes past
    scheduler.add_job(fetch_upcoming, 'cron', minute='20,50')
    scheduler.start()

    logger.info('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()  # Not strictly necessary if daemonic mode is enabled but should be done if possible

    logger.info("Program Stop")
