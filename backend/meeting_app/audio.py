from pathlib import Path
import subprocess
import wave
import imageio_ffmpeg


def convert_audio(source: Path, destination: Path, start=None, duration=None, opus=False):
    args = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
    if start is not None: args += ['-ss',str(start)]
    args += ['-i',str(source), '-vn','-ac','1','-ar','16000']
    if duration is not None: args += ['-t',str(duration)]
    args += ['-c:a','libopus','-b:a','24k'] if opus else ['-c:a','pcm_s16le']
    args += [str(destination)]
    result = subprocess.run(args,capture_output=True,timeout=1800,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('音频解码失败，请检查文件是否完整或换用 WAV/MP3 格式。')


def duration_ms(path: Path):
    with wave.open(str(path),'rb') as audio:
        return round(audio.getnframes()*1000/audio.getframerate())


def read_pcm(path: Path):
    with wave.open(str(path),'rb') as audio:
        return audio.readframes(audio.getnframes())
