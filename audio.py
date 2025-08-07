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


