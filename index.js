// dsh-voice · 让 AI 有声音：带情绪说话 + 唱歌
//
// 工具：
//   voice_speak  —— 把文字用声音说出来（情绪/音色可调），可本机播放
//   voice_sing   —— 把文字按旋律唱出来（逐字变调 + 拼接）
//   voice_status —— 查看引擎与运行状态
//
// 后端：本机 Python + ChatTTS（自然、有情感，需 GPU/模型缓存）或 edge-tts（快速、无需模型）。
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { execFile, spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

export const name = 'dsh-voice'
export const inject = ['tools']

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SCRIPT = path.join(__dirname, 'lib', 'voice.py')

const textOf = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }]

function resolveDataDir(config) {
  if (typeof config.dataDir === 'string' && config.dataDir.trim()) return path.resolve(config.dataDir.trim())
  return path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'dsh-voice')
}

export function apply(ctx, config = {}) {
  const pythonPath = config.pythonPath || 'E:\\SD-WebUI-Forge\\venv\\Scripts\\python.exe'
  const ffmpegPath = config.ffmpegPath || 'E:\\tools\\ffmpeg\\ffmpeg-master-latest-win64-gpl\\bin\\ffmpeg.exe'
  const ffplayPath = config.ffplayPath || path.join(path.dirname(ffmpegPath), 'ffplay.exe')
  const dataDir = resolveDataDir(config)
  const modelHome = config.modelHome || 'C:\\Users\\Lenovo\\.dsh\\tts-models'
  const defaultEngine = (config.engine || 'auto').toLowerCase()
  const outDir = path.join(dataDir, 'out')
  try {
    fs.mkdirSync(outDir, { recursive: true })
  } catch {}

  function runVoice(request, timeoutMs = 180000) {
    return new Promise((resolve, reject) => {
      const payload = {
        ...request,
        outDir,
        ffmpeg: ffmpegPath,
        hfHome: modelHome,
        engine: request.engine || defaultEngine,
      }
      execFile(
        pythonPath,
        [SCRIPT, JSON.stringify(payload)],
        { timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024, windowsHide: true },
        (err, stdout, stderr) => {
          if (err) {
            const detail = String(stderr || err.message || '').trim().slice(-600)
            return reject(new Error('语音合成失败：' + detail))
          }
          const line = String(stdout || '').trim().split('\n').filter(Boolean).pop() || '{}'
          try {
            resolve(JSON.parse(line))
          } catch {
            reject(new Error('语音输出无法解析：' + line.slice(-300)))
          }
        },
      )
    })
  }

  function playFile(file) {
    try {
      const proc = spawn(ffplayPath, ['-nodisp', '-autoexit', '-loglevel', 'quiet', file], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      })
      proc.unref()
      return true
    } catch {
      return false
    }
  }

  const EMOTIONS = ['calm', 'happy', 'sad', 'shy', 'angry', 'excited']
  const VOICES = ['default', 'soft', 'bright', 'sharp']

  const voiceStatus = {
    name: 'voice_status',
    description:
      '查看 dsh-voice 的语音引擎状态：Python、edge-tts、ChatTTS 模型缓存、ffmpeg/ffplay 是否可用，输出目录与最近生成的文件。',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: { schema: { type: 'object' }, render: (a, v) => textOf(v) },
    async execute() {
      const exists = (p) => {
        try {
          return fs.existsSync(p)
        } catch {
          return false
        }
      }
      let recent = []
      try {
        recent = fs
          .readdirSync(outDir)
          .filter((f) => /\.(mp3|wav)$/i.test(f))
          .map((f) => ({ name: f, mtime: fs.statSync(path.join(outDir, f)).mtimeMs }))
          .sort((a, b) => b.mtime - a.mtime)
          .slice(0, 5)
          .map((f) => f.name)
      } catch {}
      return {
        dataDir,
        outDir,
        engine: defaultEngine,
        python: { path: pythonPath, exists: exists(pythonPath) },
        ffmpeg: { path: ffmpegPath, exists: exists(ffmpegPath) },
        ffplay: { path: ffplayPath, exists: exists(ffplayPath) },
        chatttsModel: { path: modelHome, exists: exists(modelHome) },
        emotions: EMOTIONS,
        voices: VOICES,
        recent,
      }
    },
  }

  const voiceSpeak = {
    name: 'voice_speak',
    description:
      '把一段文字用声音说出来，可指定情绪与音色。情绪会影响语速、音高与断句（calm/happy/sad/shy/angry/excited）；音色可选 default/soft/bright/sharp。' +
      '默认用 ChatTTS（自然、有情感，需本机模型缓存）生成，失败时自动回退 edge-tts。生成 mp3 保存到数据目录；play=true 时在本机播放（ffplay）。',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: '要说出来的文字' },
        emotion: { type: 'string', enum: EMOTIONS, description: '情绪：calm 平静 / happy 开心 / sad 难过 / shy 害羞 / angry 生气 / excited 兴奋' },
        voice: { type: 'string', enum: VOICES, description: '音色：default / soft 温柔 / bright 明亮 / sharp 尖锐' },
        play: { type: 'boolean', description: '生成后是否在本机播放（默认 false）' },
        engine: { type: 'string', enum: ['auto', 'chattts', 'edge'], description: '引擎（默认沿配置 auto）' },
      },
      required: ['text'],
    },
    output: { schema: { type: 'object' }, render: (a, v) => textOf(v) },
    async execute(args = {}) {
      const text = typeof args.text === 'string' ? args.text.trim().slice(0, 2000) : ''
      if (!text) return { ok: false, reason: 'text 不能为空' }
      const emotion = EMOTIONS.includes(args.emotion) ? args.emotion : 'calm'
      const voice = VOICES.includes(args.voice) ? args.voice : 'default'
      try {
        const result = await runVoice({ mode: 'speak', text, emotion, voice, engine: args.engine })
        if (result.ok && args.play && result.file) result.played = playFile(result.file)
        return result
      } catch (e) {
        return { ok: false, reason: String(e?.message || e) }
      }
    },
  }

  const voiceSing = {
    name: 'voice_sing',
    description:
      '把一段文字（歌词）唱出来：逐字按旋律变调（edge-tts 按音高逐字合成）再拼接成一首短曲。旋律可选 star（小星星）/ birthday（生日快乐）/ gentle（温柔）/ funny（搞怪）。' +
      '生成 mp3 保存到数据目录；play=true 时在本机播放。',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: '要唱的文字（建议 8~24 个字，越短越像一小段旋律）' },
        melody: { type: 'string', enum: ['star', 'birthday', 'gentle', 'funny'], description: '旋律风格（默认 star）' },
        voice: { type: 'string', enum: VOICES, description: '音色（默认 default）' },
        play: { type: 'boolean', description: '生成后是否在本机播放（默认 false）' },
      },
      required: ['text'],
    },
    output: { schema: { type: 'object' }, render: (a, v) => textOf(v) },
    async execute(args = {}) {
      const text = typeof args.text === 'string' ? args.text.trim().slice(0, 200) : ''
      if (!text) return { ok: false, reason: 'text 不能为空' }
      const melody = ['star', 'birthday', 'gentle', 'funny'].includes(args.melody) ? args.melody : 'star'
      const voice = VOICES.includes(args.voice) ? args.voice : 'default'
      try {
        const result = await runVoice({ mode: 'sing', text, melody, voice })
        if (result.ok && args.play && result.file) result.played = playFile(result.file)
        return result
      } catch (e) {
        return { ok: false, reason: String(e?.message || e) }
      }
    },
  }

  for (const def of [voiceStatus, voiceSpeak, voiceSing]) {
    ctx.effect(() => ctx.tools.register(def), `dsh-voice.${def.name}()`)
  }
}
