import numpy as np
from pathlib import Path
import threading
import wave


def speaker_model_path(settings):
    return Path(settings['moss_path']).parent/'auxiliary'/'camplusplus'/'3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx'


class SpeakerModel:
    def __init__(self,path):
        import sherpa_onnx
        self.path=Path(path);self.lock=threading.Lock()
        config=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path),num_threads=1,provider='cpu')
        self.extractor=sherpa_onnx.SpeakerEmbeddingExtractor(config)

    def attach(self,path,segments):
        result=[dict(segment) for segment in segments]
        with self.lock,wave.open(str(path),'rb') as audio:
            rate=audio.getframerate()
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2:raise ValueError('Speaker input must be mono PCM16')
            for segment in result:
                start=max(0,round(segment['start_ms']*rate/1000))
                end=min(audio.getnframes(),round(segment['end_ms']*rate/1000))
                if end-start<rate*1.5:continue
                audio.setpos(start)
                clip=np.frombuffer(audio.readframes(end-start),dtype='<i2').astype(np.float32)/32768
                if not enough_speech_for_embedding(clip,rate):continue
                stream=self.extractor.create_stream()
                stream.accept_waveform(sample_rate=rate,waveform=clip)
                stream.input_finished()
                if self.extractor.is_ready(stream):segment['embedding']=self.extractor.compute(stream)
        return result


def enough_speech_for_embedding(clip,rate):
    """Do not treat a short word plus trailing silence as a reliable voice sample."""
    samples=np.asarray(clip,dtype=np.float32).reshape(-1)
    size=max(1,round(rate*.02))
    count=len(samples)//size
    if not count:return False
    frames=samples[:count*size].reshape(count,size)
    energy=np.sqrt(np.mean(frames**2,axis=1))
    threshold=max(.006,float(energy.max())*.12)
    return int(np.count_nonzero(energy>=threshold))*.02>=1.2
