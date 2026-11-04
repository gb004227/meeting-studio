from pathlib import Path
import threading
import numpy as np


def model_directory(settings):
    return Path(settings['moss_path']).parent/'auxiliary'/'paraformer-streaming'


def models_ready(settings):
    directory=model_directory(settings)
    return all((directory/name).is_file() for name in ('encoder.int8.onnx','decoder.int8.onnx','tokens.txt','ready.json'))


class LocalCaptionModel:
    def __init__(self,directory):
        import sherpa_onnx
        self.directory=Path(directory)
        self.lock=threading.Lock()
        self.recognizer=sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=str(self.directory/'tokens.txt'),encoder=str(self.directory/'encoder.int8.onnx'),
            decoder=str(self.directory/'decoder.int8.onnx'),num_threads=2,sample_rate=16000,feature_dim=80,
            enable_endpoint_detection=True,rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.0,rule3_min_utterance_length=15,
        )

    def session(self):return LocalCaptionSession(self)


class LocalCaptionSession:
    def __init__(self,model):
        self.model=model;self.stream=model.recognizer.create_stream()
        self.samples=0;self.start_ms=0

    def accept(self,pcm=b'',final=False,offset_ms=None):
        with self.model.lock:
            recognizer=self.model.recognizer
            samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
            if offset_ms is not None:self.samples=offset_ms*16
            self.samples+=len(samples)
            if len(samples):self.stream.accept_waveform(16000,samples)
            if final:
                self.stream.accept_waveform(16000,np.zeros(9600,dtype=np.float32))
                self.stream.input_finished()
            while recognizer.is_ready(self.stream):recognizer.decode_stream(self.stream)
            text=recognizer.get_result(self.stream).strip()
            endpoint=final or recognizer.is_endpoint(self.stream)
            result={'text':text,'endpoint':endpoint,'start_ms':self.start_ms,'end_ms':self.samples//16}
            if endpoint and not final:
                recognizer.reset(self.stream);self.start_ms=self.samples//16
            return result
