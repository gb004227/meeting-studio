"""Isolated inference worker. JSON lines on stdout; library logs on stderr."""
import contextlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from meeting_app.moss_format import generate_with_format_retry
from meeting_app.moss_stream import CaptionStreamer
from meeting_app.speaker_audio import enough_speech_for_embedding

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
protocol_output=sys.stdout
os.environ.setdefault('HF_HUB_OFFLINE','1')
os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
model=None; processor=None; cam=None; model_signature=None


def attach_embeddings(segments,audio_path,model_path):
    global cam
    import numpy as np
    import soundfile as sf
    import torch
    from funasr import AutoModel
    torch.set_num_threads(min(4,os.cpu_count() or 2))
    embedding_path=Path(model_path).parent/'auxiliary'/'camplusplus'
    if not embedding_path.exists():raise ValueError('本地说话人辅助模型未安装，请运行安装本地模型。')
    if cam is None:cam=AutoModel(model=str(embedding_path),device='cpu',disable_update=True,disable_pbar=True)
    with sf.SoundFile(audio_path) as audio:
        for segment in segments:
            if segment['end_ms']-segment['start_ms']<1500:continue
            start=max(0,int(segment['start_ms']*audio.samplerate/1000))
            end=min(len(audio),int(segment['end_ms']*audio.samplerate/1000))
            if end<=start:continue
            audio.seek(start);clip=audio.read(end-start,dtype='float32')
            if not enough_speech_for_embedding(clip,audio.samplerate):continue
            answer=cam.generate(input=clip,fs=audio.samplerate,disable_pbar=True)
            vector=answer[0].get('spk_embedding') if answer else None
            if vector is not None:
                if hasattr(vector,'cpu'):vector=vector.detach().cpu().numpy()
                segment['embedding']=np.asarray(vector).reshape(-1).tolist()
    return segments


def run(job):
    global model,processor,cam,model_signature
    timings={};started=time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        if job.get('task')=='speaker_embeddings':
            return {'segments':attach_embeddings(job['segments'],job['audio_path'],job['model_path']),'truncated':False}
        import numpy as np
        import soundfile as sf
        waveform,rate=sf.read(job['audio_path'],dtype='float32')
        if not len(waveform) or float(np.max(np.abs(waveform)))<=1e-6:
            return {'segments':[],'raw_text':'','truncated':False}
        import torch
        from transformers import AutoModelForCausalLM,AutoProcessor
        from moss_transcribe_diarize import parse_transcript
        from moss_transcribe_diarize.inference_utils import build_transcription_messages,generate_transcription,resolve_device,DEFAULT_PROMPT
        timings['imports']=round(time.monotonic()-started,3)
        torch.set_num_threads(min(4,os.cpu_count() or 2))
        device=resolve_device(job.get('device','cpu'))
        dtype=torch.bfloat16 if device.type=='cuda' and torch.cuda.is_bf16_supported() else (torch.float16 if device.type=='cuda' else torch.float32)
        signature=(str(Path(job['model_path']).resolve()),str(device),str(dtype))
        if model is None or signature!=model_signature:
            model=AutoModelForCausalLM.from_pretrained(job['model_path'],trust_remote_code=True,dtype=dtype,attn_implementation='sdpa',local_files_only=True).to(device).eval()
            processor=AutoProcessor.from_pretrained(job['model_path'],trust_remote_code=True,local_files_only=True)
            model_signature=signature
        timings['model_ready']=round(time.monotonic()-started,3)
        # The CPU integration loses timestamps with custom hotword prompts.
        # Use the official standard instruction for a dependable transcript.
        prompt=DEFAULT_PROMPT
        def input_ready(tokens):timings['inputs_ready']=round(time.monotonic()-started,3)
        def generate(instruction):
            print('MOSS generation started; standard prompt='+str(instruction==DEFAULT_PROMPT),file=sys.stderr,flush=True)
            inference_model=model
            if job.get('stream'):
                def caption(text):
                    if text and 'first_caption' not in timings:timings['first_caption']=round(time.monotonic()-started,3)
                    print(json.dumps({'job_id':job['job_id'],'event':'partial','partial':text},ensure_ascii=False),file=protocol_output,flush=True)
                caption('')
                observer=CaptionStreamer(processor.tokenizer,caption,job.get('partial_after_ms',0))
                def streaming_generate(**kwargs):
                    kwargs['streamer']=observer
                    return model.generate(**kwargs)
                inference_model=SimpleNamespace(parameters=model.parameters,generation_config=model.generation_config,generate=streaming_generate)
            answer=generate_transcription(inference_model,processor,build_transcription_messages(job['audio_path'],instruction),max_new_tokens=job.get('max_new_tokens',4096),do_sample=False,device=device,dtype=dtype,input_callback=input_ready)
            print('MOSS generation finished; tokens='+str(answer.get('generated_tokens',0)),file=sys.stderr,flush=True)
            return answer
        result,parsed,initial=generate_with_format_retry(generate,parse_transcript,prompt,DEFAULT_PROMPT)
        timings['generation_done']=round(time.monotonic()-started,3)
        segments=[{'start_ms':round(s.start*1000),'end_ms':round(s.end*1000),'speaker':s.speaker,'text':s.text} for s in parsed]
        embedding_path=Path(job['model_path']).parent/'auxiliary'/'camplusplus'
        if job.get('embeddings') and embedding_path.exists():
            try:
                attach_embeddings(segments,job['audio_path'],job['model_path'])
            except Exception as error:
                print('Speaker component unavailable:',type(error).__name__,file=sys.stderr)
        return {'segments':segments,'raw_text':result['text'],'initial_raw_text':initial,'format_retry':initial is not None,
                'truncated':result.get('generated_tokens',0)>=job.get('max_new_tokens',4096),'timings':timings}


if __name__=='__main__':
    for line in sys.stdin:
        try:
            job=json.loads(line)
            started=time.monotonic()
            result=run(job)
            print(json.dumps({'job_id':job['job_id'],'ok':True,'elapsed':time.monotonic()-started,**result},ensure_ascii=False),flush=True)
        except Exception as error:
            print(json.dumps({'job_id':locals().get('job',{}).get('job_id'),'ok':False,'error':f'{type(error).__name__}: {str(error)[:400]}'},ensure_ascii=False),flush=True)
