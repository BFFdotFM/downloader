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

__author__ = 'forrest'


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
        message = message + "\n\n" + "> " + str(detail)

    return message

# slack integration - Use this for #alerts (failures only)
def notify_slack_alerts(message):
    alerts_url = config["alerts_url"]
    webhook = WebhookClient(alerts_url)
    logger.debug('SLACK ALERT: ' + message)
    response = webhook.send(text=message)
    notify_slack_monitor(message)
    return

# slack integration - Use this for #monitor-automation (both failures and successes)
def notify_slack_monitor(message):
    monitor_url = config["monitor_url"]
    webhook = WebhookClient(monitor_url)
    logger.debug('SLACK MON: ' + message)
    response = webhook.send(text=message)
    return

# main function
def download_files(force_download=False):
    logger.name = 'bff.download_files'
    logger.info("Starting process")
    notify_slack_monitor("Starting download process")

    # Config params
    destination_folder = config["destination_folder"]
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
        show_title = broadcasts[0]['Show']['title']
        start_time = broadcasts[0]['start']
        logger.debug("Upcoming broadcast {} at {}".format(show_title, start_time))

    # time calculation
    showtime = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    now_plus_10 = datetime.datetime.now() + datetime.timedelta(minutes=10)
    # initialize possibly empty value
    remote_path = ""
    # if the show will start in the next 10 minutes
    if (showtime <= now_plus_10) or (force_download):
        logger.debug("Found a show that will start in 10 minutes")

        show_id = broadcasts[0]['show_id']
        logger.debug("show id: " + show_id)

        title = broadcasts[0]['title']
        logger.debug("Title: " + title)

        show_media = broadcasts[0]['media']
        for media in show_media:
            subtype = media.get('subtype', 'no key found')
            logger.debug("Media subtype: " + subtype)
            if subtype == 'mp3':
                logger.debug("found an mp3: ")
                remote_path = media['url']
                logger.debug("Remote Path: " + remote_path)

        if not remote_path:
            notify_slack_monitor(build_slack_message("_{}_ at {} does not have an MP3 attached. Expecting live broadcast.".format(show_title, start_time), ":mute:"))
            return

        # Get show info for MP3 tags:
        show_info = broadcasts[0]['Show']
        logger.debug(show_info)

        album = show_info['title']
        logger.debug("Show Name (album): " + album)

        short_name = show_info['short_name']
        logger.debug("Short Name (local folder): " + short_name)

        notify_slack_monitor("Found a show that will begin in ten minutes: " + short_name)

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
        local_filename = os.path.join(destination_folder, short_name, short_name + "-newest.mp3")
        logger.debug('Local Filename: ' + local_filename)
        notify_slack_monitor("Found a file: " + remote_path + " to be downloaded to " + local_filename)

        # create directories, if needed
        local_directory = os.path.dirname(local_filename)
        if not os.path.exists(local_directory):
            logger.warning('Had to make directory ' + local_directory)
            notify_slack_alerts("New show warning, this directory did not exist: " + local_directory)
            os.makedirs(local_directory)

        if remote_path:
            # download file
            logger.info("Downloading " + remote_path + " to " + local_filename)
            retry_count = config["retry_count"]
            for i in range(retry_count):
                try:
                    with urllib.request.urlopen(remote_path) as response, open(local_filename, 'wb') as out_file:
                        shutil.copyfileobj(response, out_file)
                except:
                    if i < tries - 1: # i is zero indexed
                        notify_slack_alerts("Download failed, attempt #" + i)
                        continue
                    else:
                        notify_slack_alerts("Download failed too many times, someone will have to manually download " + remote_path + " to " + local_filename)
                        raise
                break
            
            logger.info("download complete.")
            notify_slack_monitor("Downloaded file " + local_filename)
        else:
            logger.warn("No file was attached to the broadcast!")
            notify_slack_alerts("No valid MP3 file was attached to the broadcast for : " + local_directory)

        # add mp3 tags
        if os.path.exists(local_filename):
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
            # title
            tags["TIT2"] = TIT2(encoding=3, text=title)
            # album
            tags["TALB"] = TALB(encoding=3, text=album)
            # artist
            tags["TPE1"] = TPE1(encoding=3, text=artist)

            logger.debug("Saving tags")
            # v1=2 switch forces ID3 v1 tag to be written
            tags.save(filename=local_filename,
                      v1=ID3v1SaveOptions.CREATE,
                      v2_version=4)

    else:
        # show time is not 10 minutes or less from now
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            show_delta = showtime - datetime.datetime.now()
            s = show_delta.seconds
            days, hour_rem = divmod(s, 86400)
            hours, remainder = divmod(hour_rem, 3600)
            minutes, seconds = divmod(remainder, 60)
            show_delta_string = "{0} days, {1} hours, {2} minutes, {3} seconds".format(days, hours, minutes, seconds)
            short_name = broadcasts[0]['Show']['short_name']
            logger.debug("Next show (" + short_name + ") in " + show_delta_string + ", not running download step yet")

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
            download_files(True)
            sys.exit(0)

    # background scheduler is part of apscheduler class
    scheduler = BackgroundScheduler()
    # add a cron based (clock) scheduler for every 30 minutes, 20 minutes past
    scheduler.add_job(download_files, 'cron', minute='20,50')
    scheduler.start()

    logger.info('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()  # Not strictly necessary if daemonic mode is enabled but should be done if possible

    logger.info("Program Stop")
    
