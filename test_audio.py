import tempfile

import audio



def test_get_audio_duration():

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp:
        audio.generate_silence(temp.name, 10)
        length_of_track = audio.get_audio_duration_minutes_from_file(temp.name)
        assert length_of_track == 10.0


def test_extend_file():

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp1:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as temp2:
            audio.generate_silence(temp1.name, 10)
            audio.generate_silence(temp2.name, 3)

            combined_tracks = audio.extend_mp3_with_other_file(temp1.name, temp2.name)

            length_of_track = audio.get_audio_duration_minutes(combined_tracks)
            assert length_of_track == 13.0

