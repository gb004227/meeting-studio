from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .config import DEFAULTS,resolve_local_paths


def uid(prefix=''):
    return prefix + uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'meetings.sqlite3'
        with self.connection() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meetings(
              id TEXT PRIMARY KEY,title TEXT,mode TEXT,engine TEXT,status TEXT,
              created_at TEXT,updated_at TEXT,duration_ms INTEGER DEFAULT 0,
              audio_path TEXT,filename TEXT,error TEXT DEFAULT '',current_version TEXT,
              hotwords TEXT DEFAULT '',auto_minutes INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS speakers(
              id TEXT PRIMARY KEY,meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              name TEXT,color INTEGER,name_revision INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS bindings(
              meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              namespace TEXT,label TEXT,speaker_id TEXT REFERENCES speakers(id),
              PRIMARY KEY(meeting_id,namespace,label));
            CREATE TABLE IF NOT EXISTS versions(
              id TEXT PRIMARY KEY,meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              kind TEXT,status TEXT,parent_id TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS segments(
              version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,id TEXT,
              engine_key TEXT,speaker_id TEXT,start_ms INTEGER,end_ms INTEGER,text TEXT,
              edited INTEGER DEFAULT 0,PRIMARY KEY(version_id,id),UNIQUE(version_id,engine_key));
            CREATE TABLE IF NOT EXISTS minutes(
              id TEXT PRIMARY KEY,meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              source_version TEXT,kind TEXT,payload TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS tasks(
              id TEXT PRIMARY KEY,meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              kind TEXT,state TEXT,stage TEXT,payload TEXT,error TEXT DEFAULT '',created_at TEXT,updated_at TEXT);
            CREATE TABLE IF NOT EXISTS edits(
              id INTEGER PRIMARY KEY,meeting_id TEXT REFERENCES meetings(id) ON DELETE CASCADE,
              entity_id TEXT,before_value TEXT,after_value TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS speaker_vectors(
              speaker_id TEXT PRIMARY KEY REFERENCES speakers(id) ON DELETE CASCADE,vector TEXT,samples INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS speaker_aliases(
              old_id TEXT PRIMARY KEY REFERENCES speakers(id) ON DELETE CASCADE,
              target_id TEXT REFERENCES speakers(id) ON DELETE CASCADE);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connection() as db:
            return resolve_local_paths(DEFAULTS | {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')})

    def save_settings(self, values):
        with self.connection() as db:
            for key, value in values.items():
                if key in DEFAULTS:
                    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def create_meeting(self, title, mode, engine, hotwords='', auto_minutes=True):
        mid = uid('m_')
        with self.connection() as db:
            db.execute('INSERT INTO meetings(id,title,mode,engine,status,created_at,updated_at,hotwords,auto_minutes) VALUES(?,?,?,?,?,?,?,?,?)',
                       (mid, title.strip() or '未命名会议', mode, engine, 'ready', now(), now(), hotwords, int(auto_minutes)))
        return mid

    def update_meeting(self, mid, **values):
        allowed = {'title','status','duration_ms','audio_path','filename','error','current_version'}
        if not values or not values.keys() <= allowed:
            raise ValueError('不支持的会议字段')
        with self.connection() as db:
            db.execute('UPDATE meetings SET '+','.join(k+'=?' for k in values)+',updated_at=? WHERE id=?', [*values.values(), now(), mid])

    def list_meetings(self):
        with self.connection() as db:
            rows = db.execute('SELECT m.*, (SELECT COUNT(*) FROM speakers WHERE meeting_id=m.id AND id NOT IN (SELECT old_id FROM speaker_aliases)) speaker_count FROM meetings m ORDER BY created_at DESC').fetchall()
            return [dict(r) for r in rows]

    def meeting(self, mid):
        with self.connection() as db:
            row = db.execute('SELECT * FROM meetings WHERE id=?', (mid,)).fetchone()
            if row is None:
                raise KeyError('会议不存在')
            m = dict(row)
            m['speakers'] = [dict(r) for r in db.execute('SELECT * FROM speakers WHERE meeting_id=? ORDER BY color,id', (mid,))]
            m['segments'] = [dict(r) for r in db.execute('SELECT * FROM segments WHERE version_id=? ORDER BY start_ms,end_ms', (m['current_version'],))]
            m['versions'] = [dict(r) for r in db.execute('SELECT * FROM versions WHERE meeting_id=? ORDER BY created_at DESC', (mid,))]
            minutes = db.execute('SELECT * FROM minutes WHERE meeting_id=? ORDER BY created_at DESC LIMIT 1', (mid,)).fetchone()
            m['minutes'] = (dict(minutes) | {'data':json.loads(minutes['payload']), 'stale':minutes['source_version'] != m['current_version']}) if minutes else None
            if m['minutes']:
                del m['minutes']['payload']
            aliases={r['old_id']:r['target_id'] for r in db.execute('SELECT a.* FROM speaker_aliases a JOIN speakers s ON s.id=a.old_id WHERE s.meeting_id=?',(mid,))}
            m['speakers']=[p for p in m['speakers'] if p['id'] not in aliases]
            for segment in m['segments']:
                segment['speaker_id']=aliases.get(segment['speaker_id'],segment['speaker_id'])
            if m['minutes']:
                for action in m['minutes']['data'].get('action_items',[]):
                    sid=action.get('owner_speaker_id')
                    action['owner_speaker_id']=aliases.get(sid,sid)
            m['tasks'] = [dict(r) for r in db.execute('SELECT id,kind,state,stage,error,created_at,updated_at FROM tasks WHERE meeting_id=? ORDER BY created_at DESC', (mid,))]
            return m

    def new_version(self, mid, kind, parent=None, copy_segments=False, activate=True):
        vid = uid('tv_')
        with self.connection() as db:
            db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)', (vid,mid,kind,'working',parent,now()))
            if parent and copy_segments:
                db.execute('INSERT INTO segments SELECT ?,id,engine_key,speaker_id,start_ms,end_ms,text,edited FROM segments WHERE version_id=?', (vid,parent))
            if activate:
                db.execute('UPDATE meetings SET current_version=?,updated_at=? WHERE id=?', (vid,now(),mid))
        return vid

    def publish(self, vid):
        with self.connection() as db:
            db.execute("UPDATE versions SET status='published' WHERE id=?", (vid,))

    def activate_version(self, mid, vid):
        with self.connection() as db:
            if not db.execute('SELECT 1 FROM versions WHERE id=? AND meeting_id=?', (vid,mid)).fetchone():
                raise KeyError('转写版本不存在')
        self.update_meeting(mid, current_version=vid)

    def _speaker(self, db, mid, namespace, label, start, end, previous_version, embedding=None,prefer_embedding=False):
        if label is None or str(label) in ('', '-1', 'unknown'):
            return None
        label = str(label)
        binding = db.execute('SELECT speaker_id FROM bindings WHERE meeting_id=? AND namespace=? AND label=?', (mid,namespace,label)).fetchone()
        if binding:
            if embedding: self._save_vector(db,binding['speaker_id'],embedding)
            return binding['speaker_id']
        sid=self._match_vector(db,mid,embedding) if embedding else None
        acoustic_gallery=prefer_embedding and embedding and db.execute('SELECT 1 FROM speaker_vectors v JOIN speakers s ON s.id=v.speaker_id WHERE s.meeting_id=? LIMIT 1',(mid,)).fetchone()
        # Match the SAME utterance across overlapping requests, not label order.
        matches = db.execute('''SELECT speaker_id,SUM(MIN(end_ms,?)-MAX(start_ms,?)) AS overlap
          FROM segments WHERE version_id=? AND speaker_id IS NOT NULL AND start_ms<? AND end_ms>?
          GROUP BY speaker_id ORDER BY overlap DESC''', (end,start,previous_version,end,start)).fetchall() if previous_version else []
        if not sid and not acoustic_gallery and matches and matches[0]['overlap'] >= max(500,(end-start)*0.65) and (len(matches)<2 or matches[0]['overlap']>2*matches[1]['overlap']):
            sid = matches[0]['speaker_id']
        if sid:
            alias=db.execute('SELECT target_id FROM speaker_aliases WHERE old_id=?',(sid,)).fetchone()
            if alias: sid=alias['target_id']
        if not sid:
            sid = uid('spk_')
            index = db.execute('SELECT COUNT(*) FROM speakers WHERE meeting_id=?',(mid,)).fetchone()[0]
            db.execute('INSERT INTO speakers VALUES(?,?,?,?,?)', (sid,mid,f'说话人 {index+1}',index,0))
        db.execute('INSERT INTO bindings VALUES(?,?,?,?)', (mid,namespace,label,sid))
        if embedding: self._save_vector(db,sid,embedding)
        return sid

    def _match_vector(self,db,mid,embedding):
        import numpy as np
        vector=np.asarray(embedding,dtype=float)
        scores=[]
        for row in db.execute('SELECT v.* FROM speaker_vectors v JOIN speakers s ON s.id=v.speaker_id WHERE s.meeting_id=? AND s.id NOT IN (SELECT old_id FROM speaker_aliases)',(mid,)):
            other=np.asarray(json.loads(row['vector']),dtype=float)
            if len(vector)!=len(other): continue
            score=float(vector@other/max(float(np.linalg.norm(vector)*np.linalg.norm(other)),1e-9))
            scores.append((score,row['speaker_id']))
        scores.sort(reverse=True)
        if scores and scores[0][0]>=0.78 and (len(scores)<2 or scores[0][0]-scores[1][0]>=0.1): return scores[0][1]
        return None

    def _save_vector(self,db,sid,embedding):
        import numpy as np
        vector=np.asarray(embedding,dtype=float)
        norm=float(np.linalg.norm(vector))
        if not norm: return
        vector=vector/norm
        old=db.execute('SELECT * FROM speaker_vectors WHERE speaker_id=?',(sid,)).fetchone()
        count=1
        if old:
            count=min(old['samples']+1,20)
            previous=np.asarray(json.loads(old['vector']),dtype=float)
            if len(previous)!=len(vector): return
            vector=(previous*(count-1)+vector)/count
        db.execute('INSERT OR REPLACE INTO speaker_vectors VALUES(?,?,?)',(sid,json.dumps(vector.tolist()),count))

    def add_segments(self, mid, vid, segments, namespace, previous_version=None):
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM versions WHERE id=? AND meeting_id=? AND status='working'",(vid,mid)).fetchone():
                return
            for segment in segments:
                start, end = int(segment['start_ms']), int(segment['end_ms'])
                text = str(segment.get('text','')).strip()
                if not text or end<=start or start<0:
                    continue
                sid = self._speaker(db,mid,namespace,segment.get('speaker'),start,end,previous_version,segment.get('embedding'),segment.get('prefer_embedding',False))
                engine_key = str(segment.get('key', f'{namespace}:{start}'))
                existing = db.execute('SELECT id,edited FROM segments WHERE version_id=? AND engine_key=?',(vid,engine_key)).fetchone()
                if existing:
                    if not existing['edited']:
                        db.execute('UPDATE segments SET speaker_id=?,start_ms=?,end_ms=?,text=? WHERE version_id=? AND id=?',(sid,start,end,text,vid,existing['id']))
                else:
                    from difflib import SequenceMatcher
                    duplicates=db.execute('SELECT * FROM segments WHERE version_id=? AND start_ms BETWEEN ? AND ? AND end_ms>?',(vid,start-1000,start+1000,start)).fetchall()
                    if any(r['speaker_id']==sid and SequenceMatcher(None,r['text'],text).ratio()>=0.92 and min(r['end_ms'],end)-max(r['start_ms'],start)>0.6*min(end-start,r['end_ms']-r['start_ms']) for r in duplicates):
                        continue
                    db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(vid,uid('seg_'),engine_key,sid,start,end,text,0))

    def rename_speaker(self, mid, sid, name):
        name = name.strip()
        if not name or len(name)>60:
            raise ValueError('姓名请填写 1～60 个字符')
        with self.connection() as db:
            old = db.execute('SELECT name FROM speakers WHERE id=? AND meeting_id=?',(sid,mid)).fetchone()
            if not old: raise KeyError('说话人不存在')
            db.execute('UPDATE speakers SET name=?,name_revision=name_revision+1 WHERE id=?',(name,sid))
            db.execute('INSERT INTO edits(meeting_id,entity_id,before_value,after_value,created_at) VALUES(?,?,?,?,?)',(mid,sid,old['name'],name,now()))

    def create_speaker(self,mid,name):
        self.meeting(mid)
        sid=uid('spk_')
        with self.connection() as db:
            count=db.execute('SELECT COUNT(*) FROM speakers WHERE meeting_id=?',(mid,)).fetchone()[0]
            db.execute('INSERT INTO speakers VALUES(?,?,?,?,?)',(sid,mid,name.strip() or f'说话人 {count+1}',count,0))
        return sid

    def merge_speakers(self,mid,source,target):
        meeting=self.meeting(mid)
        people={p['id'] for p in meeting['speakers']}
        if source==target or source not in people or target not in people:
            raise ValueError('请选择该会议中的两位不同说话人')
        with self.connection() as db:
            db.execute('UPDATE speaker_aliases SET target_id=? WHERE target_id=?',(target,source))
            db.execute('INSERT INTO speaker_aliases VALUES(?,?)',(source,target))
            db.execute('UPDATE bindings SET speaker_id=? WHERE meeting_id=? AND speaker_id=?',(target,mid,source))
            db.execute('INSERT INTO edits(meeting_id,entity_id,before_value,after_value,created_at) VALUES(?,?,?,?,?)',(mid,source,'merge',target,now()))

    def edit_minutes(self,mid,summary):
        if not isinstance(summary,list) or not all(isinstance(s,str) for s in summary):
            raise ValueError('会议总结格式不正确')
        meeting=self.meeting(mid)
        if not meeting['minutes']: raise KeyError('暂无纪要')
        payload=meeting['minutes']['data']
        payload['summary']=[s.strip() for s in summary if s.strip()]
        return self.save_minutes(mid,meeting['minutes']['source_version'],payload,'human')

    def edit_segment(self, mid, segment_id, text=None, speaker_id=None, change_speaker=False):
        m = self.meeting(mid)
        vid = m['current_version']
        version = next(v for v in m['versions'] if v['id']==vid)
        if version['status']=='published':
            vid = self.new_version(mid,'human',vid,True)
        with self.connection() as db:
            segment = db.execute('SELECT * FROM segments WHERE version_id=? AND id=?',(vid,segment_id)).fetchone()
            if segment is None: raise KeyError('分段不存在')
            if change_speaker and speaker_id and not db.execute('SELECT 1 FROM speakers WHERE id=? AND meeting_id=?',(speaker_id,mid)).fetchone():
                raise ValueError('说话人不属于该会议')
            db.execute('UPDATE segments SET text=?,speaker_id=?,edited=1 WHERE version_id=? AND id=?',
                       (segment['text'] if text is None else text.strip(),speaker_id if change_speaker else segment['speaker_id'],vid,segment_id))
            db.execute('INSERT INTO edits(meeting_id,entity_id,before_value,after_value,created_at) VALUES(?,?,?,?,?)',(mid,segment_id,json.dumps(dict(segment)),json.dumps({'text':text,'speaker_id':speaker_id}),now()))
        if version['status']=='published': self.publish(vid)

    def save_minutes(self, mid, vid, payload, kind):
        minute_id = uid('mv_')
        with self.connection() as db:
            db.execute('INSERT INTO minutes VALUES(?,?,?,?,?,?)',(minute_id,mid,vid,kind,json.dumps(payload,ensure_ascii=False),now()))
        return minute_id

    def edit_action(self, mid, aid, values):
        m = self.meeting(mid)
        minute = m['minutes']
        if not minute: raise KeyError('暂无行动项')
        payload = minute['data']
        item = next((a for a in payload.get('action_items',[]) if a['id']==aid),None)
        if item is None: raise KeyError('行动项不存在')
        allowed = {'task','owner_speaker_id','owner_mentioned_as','due_date','status','deliverable'}
        if not values.keys()<=allowed: raise ValueError('不支持的行动项字段')
        if values.get('owner_speaker_id') and values['owner_speaker_id'] not in {p['id'] for p in m['speakers']}:
            raise ValueError('负责人不属于该会议')
        item.update(values)
        item['source'] = 'human'
        self.save_minutes(mid,minute['source_version'],payload,'human')

    def new_task(self, mid, kind, payload):
        tid=uid('task_')
        with self.connection() as db:
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',(tid,mid,kind,'queued','等待处理',json.dumps(payload),'',now(),now(),))
        return tid

    def task_update(self, tid, **values):
        if not values.keys()<={'state','stage','error'}: raise ValueError('任务字段不合法')
        with self.connection() as db:
            db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in values)+',updated_at=? WHERE id=?',[*values.values(),now(),tid])

    def pending_tasks(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM tasks WHERE state IN ('queued','running') ORDER BY created_at")]

    def delete(self, mid):
        with self.connection() as db:
            db.execute('DELETE FROM meetings WHERE id=?',(mid,))
