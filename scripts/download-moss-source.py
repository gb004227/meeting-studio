from pathlib import Path
import io
import urllib.request
import zipfile

root=Path(__file__).resolve().parents[1]/'vendor'/'moss'
with urllib.request.urlopen('https://codeload.github.com/OpenMOSS/MOSS-Transcribe-Diarize/zip/refs/heads/main',timeout=90) as response:
    raw=response.read()
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    for entry in archive.infolist():
        parts=Path(entry.filename).parts[1:]
        if not parts: continue
        target=root.joinpath(*parts).resolve()
        if not target.is_relative_to(root.resolve()): raise ValueError('Unsafe archive member')
        if entry.is_dir(): target.mkdir(parents=True,exist_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(entry))
print('Official MOSS source is ready.')
