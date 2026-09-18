import subprocess
import wave
import errno

import pytest

from transcriber.config import Settings
from transcriber.domain.models.job import JobError
from transcriber.adapters.ffmpeg_processor import FFmpegMediaProcessor, TransientDecoderStartError


def pcm(path, seconds):
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0\0' * int(seconds * 16000))


def test_duration_boundary_and_invalid_media(tmp_path):
    processor = FFmpegMediaProcessor(Settings(max_duration_seconds=1))
    source, dest = tmp_path / 'source.wav', tmp_path / 'audio.wav'
    pcm(source, 1)
    assert processor.normalize(source, dest) == 1
    pcm(source, 1.01)
    with pytest.raises(JobError, match='duration limit'):
        processor.normalize(source, dest)
    source.write_bytes(b'not media')
    with pytest.raises(JobError) as exc:
        processor.normalize(source, dest)
    assert exc.value.code == 'invalid_media'


def test_no_audio_and_decoder_timeout(tmp_path, monkeypatch):
    source = tmp_path / 'silent.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=16x16:rate=1',
                    '-t', '1', '-c:v', 'mpeg4', str(source)], check=True)
    processor = FFmpegMediaProcessor(Settings())
    with pytest.raises(JobError) as exc:
        processor.normalize(source, tmp_path / 'out.wav')
    assert exc.value.code == 'no_audio'
    def timeout(*args):
        raise subprocess.TimeoutExpired('ffmpeg', 1)
    monkeypatch.setattr(processor, '_run', timeout)
    with pytest.raises(JobError) as exc:
        processor.normalize(source, tmp_path / 'out.wav')
    assert exc.value.code == 'decode_timeout'


def test_decoder_launch_resource_errors_are_classified_for_bounded_retry(monkeypatch):
    processor = FFmpegMediaProcessor(Settings())
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: (_ for _ in ()).throw(
        OSError(errno.EMFILE, 'too many open files')))
    with pytest.raises(TransientDecoderStartError):
        processor._run(['ffmpeg'], 1)

    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: (_ for _ in ()).throw(
        OSError(errno.ENOMEM, 'out of memory')))
    with pytest.raises(JobError) as exc:
        processor._run(['ffmpeg'], 1)
    assert exc.value.code == 'invalid_media'
