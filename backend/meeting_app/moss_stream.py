import re
import time


def caption_text(raw,after_ms=0):
    if after_ms:
        markers=list(re.finditer(r'\[(\d+(?:\.\d+)?)\]\s*\[S\d+\]',raw))
        raw=''.join(raw[match.start():markers[index+1].start() if index+1<len(markers) else len(raw)]
                    for index,match in enumerate(markers) if float(match[1])*1000>=after_ms)
    text=re.sub(r'\[(?:\d+(?:\.\d+)?|S\d+)\]','',raw)
    text=re.sub(r'\[(?:\d*\.?\d*|S\d*)$','',text)
    return text.rstrip('\ufffd').strip()


class CaptionStreamer:
    """Transformers token stream, kept separate from the final timestamped result."""
    def __init__(self,tokenizer,callback,after_ms=0):
        self.tokenizer=tokenizer;self.callback=callback;self.after_ms=after_ms
        self.prompt=True;self.tokens=[];self.last='';self.emitted=0

    def put(self,value):
        if self.prompt:self.prompt=False;return
        self.tokens.extend(value.reshape(-1).tolist())
        self.emit()

    def emit(self,force=False):
        text=caption_text(self.tokenizer.decode(self.tokens,skip_special_tokens=True),self.after_ms)
        now=time.monotonic()
        if text!=self.last and (force or now-self.emitted>=.15):
            self.callback(text);self.last=text;self.emitted=now

    def end(self):self.emit(True)
