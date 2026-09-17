import json
import os
import signal
import subprocess
import sys
import tempfile
import wave
from transcriber.domain.models.job import JobError
from transcriber.domain.contracts import MediaProcessor

SUPPORTED_CONTAINERS = frozenset({'wav', 'mp3', 'mov', 'mp4', 'm4a', 'matroska', 'webm'})
SUPPORTED_AUDIO_CODECS = frozenset({'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le', 'mp3', 'aac', 'opus', 'vorbis'})
# Informational only: HTTP MIME headers are untrusted; ffprobe container/codec checks enforce support.
SUPPORTED_MEDIA_MIME_TYPES = frozenset({
    'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/webm',
    'video/mp4', 'video/webm', 'video/x-matroska',
})

class FFmpegMediaProcessor(MediaProcessor):
    def __init__(self, settings):
        self.settings = settings

    def _run(self, args, timeout):
        # A fresh launcher sets Linux parent-death protection before exec.
        command = [sys.executable, '-m', 'transcriber.adapters.process_launcher', str(os.getpid()), *args]
        # Probe selects one stream; launcher also caps stdout file size at 64 KiB.
        with tempfile.TemporaryFile() as output, subprocess.Popen(
            command, stdout=output, stderr=subprocess.DEVNULL, start_new_session=True
        ) as process:
            try:
                process.wait(timeout=timeout)
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
            if process.returncode:
                raise JobError('invalid_media', 'The media could not be decoded. Use a supported audio or video file.')
            output.seek(0)
            return output.read(65536)

    def normalize(self, source, destination):
        try:
            raw = self._run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
                             '-select_streams', 'a:0',
                             '-show_entries', 'format=format_name:stream=codec_type,codec_name',
                             '-of', 'json', str(source)], min(30, self.settings.decode_timeout))
            probe = json.loads(raw)
            containers = set(probe.get('format', {}).get('format_name', '').split(','))
            if not containers & SUPPORTED_CONTAINERS:
                raise JobError('unsupported_media', 'Use WAV, MP3, M4A, MP4, or WebM media.')
            audio = [s for s in probe.get('streams', []) if s.get('codec_type') == 'audio']
            if not audio:
                raise JobError('no_audio', 'The video has no audio track.')
            if audio[0].get('codec_name') not in SUPPORTED_AUDIO_CODECS:
                raise JobError('unsupported_codec', 'The first audio track uses an unsupported codec.')
            self._run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-protocol_whitelist', 'file',
                       '-threads', '1', '-i', str(source), '-map', '0:a:0', '-vn', '-sn', '-dn',
                       '-t', str(self.settings.max_duration_seconds + 1), '-ac', '1', '-ar', '16000',
                       '-c:a', 'pcm_s16le', '-threads', '1', '-y', str(destination)], self.settings.decode_timeout)
            with wave.open(str(destination)) as wav:
                duration = wav.getnframes() / wav.getframerate()
            if duration > self.settings.max_duration_seconds:
                raise JobError('media_too_long', 'The recording exceeds the configured duration limit.')
            if duration <= 0:
                raise JobError('empty_audio', 'The audio track contains no samples.')
            return duration
        except subprocess.TimeoutExpired as exc:
            raise JobError('decode_timeout', 'Media decoding exceeded its time limit.') from exc
        except (json.JSONDecodeError, wave.Error) as exc:
            raise JobError('invalid_media', 'The media could not be decoded.') from exc
