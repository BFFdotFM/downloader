import os
import tempfile

from pydub.generators import Sine

import audio


INSPECTABLE_OUPUT_FILENAME = "listen_to_me.mp3"
INSPECTABLE_PATH = os.path.join("resources", INSPECTABLE_OUPUT_FILENAME)


def test_get_audio_duration():
    """Test our helper can tell us audio duration"""

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp:
        audio.generate_silence(temp.name, 10)
        length_of_track = audio.get_audio_duration_minutes_from_file(temp.name)
        assert length_of_track == 10.0


def test_extend_file():
    """Test we can add two files together and get an expected length"""

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp1:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp2:
            audio.generate_silence(temp1.name, 10)
            audio.generate_silence(temp2.name, 3)

            combined_tracks = audio.extend_mp3_with_other_file(temp1.name, temp2.name)

            length_of_track = audio.get_audio_duration_minutes(combined_tracks)
            assert length_of_track == 13.0


def test_extend_file_with_inspectable_output():
    """Test we can add two files together in a way that leaves a file that a human can inspect to confirm
    the second file is actually added to the end of the first one =)"""

    tone1_freq = 440
    tone2_freq = 550

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp1:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp2:
            tone1 = Sine(tone1_freq).to_audio_segment(duration=2 * 1000 * 60)
            tone1.export(temp1.name, format="mp3")

            tone2 = Sine(tone2_freq).to_audio_segment(duration=1 * 1000 * 60)
            tone2.export(temp2.name, format="mp3")

            combined_tracks = audio.extend_mp3_with_other_file(temp1.name, temp2.name)

            length_of_track = audio.get_audio_duration_minutes(combined_tracks)
            assert length_of_track == 3

            # A human should be able to listen to this track and see the higher tone
            # lasts three minutes
            combined_tracks.export(INSPECTABLE_PATH, format="mp3")


def test_boundary_helper():

    assert audio.length_is_close_to_thirty_minute_boundary(27.5, close_mins=2) is False
    assert audio.length_is_close_to_thirty_minute_boundary(28.0, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(29.0, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(30.0) is True
    assert audio.length_is_close_to_thirty_minute_boundary(31.0, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(32.0, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(32.1, close_mins=2) is False

    assert audio.length_is_close_to_thirty_minute_boundary(57, close_mins=2) is False
    assert audio.length_is_close_to_thirty_minute_boundary(59, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(60) is True
    assert audio.length_is_close_to_thirty_minute_boundary(61, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(63, close_mins=2) is False

    assert audio.length_is_close_to_thirty_minute_boundary(117, close_mins=2) is False
    assert audio.length_is_close_to_thirty_minute_boundary(119, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(120) is True
    assert audio.length_is_close_to_thirty_minute_boundary(122, close_mins=2) is True
    assert audio.length_is_close_to_thirty_minute_boundary(123, close_mins=2) is False
