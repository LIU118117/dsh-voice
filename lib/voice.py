#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dsh-voice 语音引擎：ChatTTS / edge-tts 双后端 + 唱歌模式。

调用方式：
  python voice.py '{"mode":"speak","text":"...","emotion":"happy","voice":"default","outDir":"...","ffmpeg":"...","hfHome":"..."}'
  python voice.py '{"mode":"sing","text":"一闪一闪亮晶晶","melody":"star","outDir":"...","ffmpeg":"...","hfHome":"..."}'

输出：stdout 打印一行 JSON：{"ok":true,"engine":"chattts|edge","file":"...","duration":1.2}
"""
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REQUEST = json.loads(sys.argv[1])

EMOTIONS = {
    'calm':    {'rate': '+0%',  'pitch': '+0Hz',  'speed': '[speed_5]', 'refine': '[oral_1][laugh_0][break_2]'},
    'happy':   {'rate': '+6%',  'pitch': '+4Hz',  'speed': '[speed_6]', 'refine': '[oral_2][laugh_1][break_1]'},
    'sad':     {'rate': '-10%', 'pitch': '-6Hz',  'speed': '[speed_4]', 'refine': '[oral_1][laugh_0][break_5]'},
    'shy':     {'rate': '-6%',  'pitch': '-2Hz',  'speed': '[speed_4]', 'refine': '[oral_2][laugh_0][break_4]'},
    'angry':   {'rate': '+10%', 'pitch': '-8Hz',  'speed': '[speed_7]', 'refine': '[oral_2][laugh_0][break_1]'},
    'excited': {'rate': '+12%', 'pitch': '+8Hz',  'speed': '[speed_7]', 'refine': '[oral_2][laugh_1][break_1]'},
}

VOICES = {
    'default': {'seed': 1234, 'edge': 'zh-CN-XiaoxiaoNeural'},
    'soft':    {'seed': 777,  'edge': 'zh-CN-XiaoxiaoNeural'},
    'bright':  {'seed': 2222, 'edge': 'zh-CN-XiaoyiNeural'},
    'sharp':   {'seed': 3333, 'edge': 'zh-CN-XiaoxiaoNeural'},
}

NOTES = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23, 'G4': 392.00,
    'A4': 440.00, 'B4': 493.88, 'C5': 523.25, 'D5': 587.33, 'E5': 659.25,
    'F5': 698.46, 'G5': 783.99,
}
MELODIES = {
    'star':    ['C4', 'C4', 'G4', 'G4', 'A4', 'A4', 'G4', 'F4', 'F4', 'E4', 'E4', 'D4', 'D4', 'C4'],
    'birthday':['G4', 'G4', 'A4', 'G4', 'C5', 'B4', 'G4', 'G4', 'A4', 'G4', 'D5', 'C5'],
    'gentle':  ['C4', 'D4', 'E4', 'G4', 'E4', 'D4', 'C4', 'D4', 'E4', 'A4', 'G4', 'E4', 'D4'],
    'funny':   ['C4', 'E4', 'G4', 'C5', 'G4', 'E4', 'C4', 'G4', 'E4', 'C5', 'G4', 'C4'],
}

OUT = Path(REQUEST['outDir'])
OUT.mkdir(parents=True, exist_ok=True)
FFMPEG = REQUEST.get('ffmpeg') or 'ffmpeg'
FFPROBE = str(Path(FFMPEG).with_name('ffprobe.exe')) if os.name == 'nt' else 'ffprobe'


def emit(result):
    print(json.dumps(result, ensure_ascii=False), flush=True)


def duration_of(file_path):
    try:
        probe = subprocess.run(
            [FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        return round(float(probe.stdout.strip()), 2)
    except Exception:
        return None


def ffmpeg_to_mp3(src, dst):
    subprocess.run(
        [FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', str(src),
         '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-codec:a', 'libmp3lame', '-q:a', '4', str(dst)],
        check=True, capture_output=True, timeout=120,
    )


def speak_edge(text, emotion, voice):
    emo = EMOTIONS.get(emotion, EMOTIONS['calm'])
    v = VOICES.get(voice, VOICES['default'])
    out = OUT / ('speak_edge_%d.mp3' % os.getpid())
    cmd = [sys.executable, '-m', 'edge_tts', '--voice', v['edge'],
           '--rate=%s' % emo['rate'], '--pitch=%s' % emo['pitch'],
           '--text', text, '--write-media', str(out)]
    if voice == 'sharp':
        cmd.insert(cmd.index('--rate=%s' % emo['rate']) + 1, '--rate=+9%')
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return out


def speak_chattts(text, emotion, voice):
    os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
    os.environ.setdefault('HF_HOME', REQUEST.get('hfHome') or str(Path.home() / '.cache' / 'dsh-voice'))
    import numpy as np
    import torch
    import ChatTTS

    emo = EMOTIONS.get(emotion, EMOTIONS['calm'])
    seed = VOICES.get(voice, VOICES['default'])['seed']
    chat = ChatTTS.Chat()
    chat.load(source='huggingface', compile=False, device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'))
    torch.manual_seed(seed)
    spk = chat.sample_random_speaker()
    params = ChatTTS.Chat.InferCodeParams(
        prompt=emo['speed'], temperature=0.25, top_P=0.6, top_K=18,
        manual_seed=seed + len(text), spk_emb=spk, show_tqdm=False,
    )
    refine = ChatTTS.Chat.RefineTextParams(prompt=emo['refine'], show_tqdm=False)
    wavs = chat.infer([text], params_infer_code=params, params_refine_text=refine)
    wav = wavs[0]
    if isinstance(wav, torch.Tensor):
        wav = wav.detach().cpu().numpy()
    wav = np.squeeze(np.asarray(wav))
    wav16 = (np.clip(wav, -1.0, 1.0) * 32767).astype(np.int16)
    tmp_wav = Path(tempfile.gettempdir()) / ('dsh_voice_%d.wav' % os.getpid())
    with wave.open(str(tmp_wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(wav16.tobytes())
    out = OUT / ('speak_chattts_%d.mp3' % os.getpid())
    ffmpeg_to_mp3(tmp_wav, out)
    try:
        tmp_wav.unlink()
    except Exception:
        pass
    return out


def do_speak():
    text = (REQUEST.get('text') or '').strip()
    if not text:
        emit({'ok': False, 'error': 'text 不能为空'})
        return
    emotion = REQUEST.get('emotion') or 'calm'
    voice = REQUEST.get('voice') or 'default'
    engine = (REQUEST.get('engine') or 'auto').lower()
    errors = []
    if engine in ('auto', 'chattts'):
        try:
            out = speak_chattts(text, emotion, voice)
            emit({'ok': True, 'engine': 'chattts', 'file': str(out), 'duration': duration_of(out)})
            return
        except Exception as exc:
            errors.append('chattts: %s' % exc)
    if engine in ('auto', 'edge'):
        try:
            out = speak_edge(text, emotion, voice)
            emit({'ok': True, 'engine': 'edge', 'file': str(out), 'duration': duration_of(out)})
            return
        except Exception as exc:
            errors.append('edge: %s' % exc)
    emit({'ok': False, 'error': '；'.join(errors) or '没有可用的语音引擎'})


def do_sing():
    text = (REQUEST.get('text') or '').strip()
    melody_name = REQUEST.get('melody') or 'star'
    melody = MELODIES.get(melody_name, MELODIES['star'])
    voice = REQUEST.get('voice') or 'default'
    v = VOICES.get(voice, VOICES['default'])
    base = NOTES['C4']
    chars = [c for c in text if c.strip() and c not in '，。！？、…「」“”‘’（）()《》,.!?;: ']
    chars = chars[:24]
    if not chars:
        emit({'ok': False, 'error': '歌词里没有可唱的字'})
        return
    clips = []
    try:
        for i, ch in enumerate(chars):
            note = melody[i % len(melody)]
            offset = int(round(NOTES[note] - base))
            clip = OUT / ('sing_%d_%02d.mp3' % (os.getpid(), i))
            cmd = [sys.executable, '-m', 'edge_tts', '--voice', v['edge'],
                   '--rate=+0%', '--pitch=%+dHz' % offset,
                   '--text', ch, '--write-media', str(clip)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            clips.append(clip)
        list_file = OUT / ('sing_%d_list.txt' % os.getpid())
        with open(list_file, 'w', encoding='utf-8') as fh:
            for clip in clips:
                fh.write("file '%s'\n" % str(clip).replace('\\', '/'))
        out = OUT / ('sing_%d.mp3' % os.getpid())
        subprocess.run(
            [FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
             '-i', str(list_file), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-codec:a', 'libmp3lame', '-q:a', '4', str(out)],
            check=True, capture_output=True, timeout=180,
        )
        for clip in clips:
            try:
                clip.unlink()
            except Exception:
                pass
        try:
            list_file.unlink()
        except Exception:
            pass
        emit({'ok': True, 'engine': 'edge-sing', 'file': str(out), 'duration': duration_of(out), 'melody': melody_name, 'chars': len(chars)})
    except Exception as exc:
        emit({'ok': False, 'error': '唱歌失败: %s' % exc})


MODE = REQUEST.get('mode')
try:
    if MODE == 'speak':
        do_speak()
    elif MODE == 'sing':
        do_sing()
    else:
        emit({'ok': False, 'error': '未知 mode: %s' % MODE})
except Exception as exc:
    emit({'ok': False, 'error': '异常: %s' % exc})
