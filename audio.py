from typing import Optional

from pydub import AudioSegment


def generate_silence(output_path, minutes: int):
    duration_ms = minutes * 60 * 1000
    silence = AudioSegment.silent(duration=duration_ms)
    silence.export(output_path, format="mp3")


def get_audio_duration_minutes_from_file(file_path):
    audio = AudioSegment.from_file(file_path)
    return get_audio_duration_minutes(audio)


def get_audio_duration_minutes(audio: AudioSegment):
    duration_ms = len(audio)
    duration_minutes = duration_ms / (1000 * 60)
    return duration_minutes


def extend_mp3_with_other_file(base_path, additional_path):
    audio = AudioSegment.from_file(base_path)
    additional_audio = AudioSegment.from_file(additional_path)
    return audio + additional_audio


def length_is_close_to_thirty_minute_boundary(
    track_length_in_min: int, close_mins: int = 2
):
    """Looks at a track length and checks whether, when you round it to the closest 30 minutes,
    the track is within plus or minus `close_mins` to that length.

    We do this so that we can check whether 60, 90, or 120 minute shows are close to exactly their boundary.
    """

    moduloed_track_length = track_length_in_min % 30

    if moduloed_track_length <= close_mins or moduloed_track_length >= (
        30 - close_mins
    ):
        return True

    return False
