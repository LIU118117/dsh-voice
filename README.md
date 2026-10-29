# dsh-voice

让 AI 有声音：**带情绪说话 + 唱歌**。

一个 DeepSeek Harness（Cordis）插件，注册 3 个工具：

| 工具 | 作用 |
| --- | --- |
| `voice_speak` | 把文字用声音说出来，可指定情绪（平静/开心/难过/害羞/生气/兴奋）与音色（default/soft/bright/sharp），可本机播放 |
| `voice_sing` | 把文字（歌词）唱出来：逐字按旋律变调再拼接，旋律可选 star/birthday/gentle/funny |
| `voice_status` | 查看引擎、路径、模型缓存与最近生成的文件 |

## 引擎

- **ChatTTS**（默认）：本机 GPU 推理，语气自然、有停顿和情感；需要模型缓存（`modelHome`）与 Python 环境里的 `ChatTTS` 包。
- **edge-tts**：无需本地模型，快速稳定；ChatTTS 不可用时自动回退。
- **唱歌**：使用 edge-tts 逐字合成 + 按旋律音高变调，再 ffmpeg 拼接（趣味向）。

## 安装

本插件是 Host-only bundle。把目录作为 `install_bundle` 的 target：

```
plugin_manager  install_bundle  <本目录绝对路径>
```

安装后工具列表出现 `voice_speak` / `voice_sing` / `voice_status` 即成功。

## 使用示例

```
voice_speak  text="今天也要开心呀。"  emotion="happy"  voice="soft"  play=true
voice_speak  text="才、才不是为了你才这样说呢……"  emotion="shy"  voice="default"
voice_sing   text="一闪一闪亮晶晶"  melody="star"  play=true
```

生成的文件保存在 `<dataDir>/out/`（默认 `<DSH_HOME>/dsh-voice/out/`）。

## 配置

行配置见 `cordis.patch.yml`：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `pythonPath` | `E:\SD-WebUI-Forge\venv\Scripts\python.exe` | 运行 voice.py 的 Python（需 edge-tts；ChatTTS 可选） |
| `ffmpegPath` | `E:\tools\ffmpeg\...\bin\ffmpeg.exe` | 转码 |
| `ffplayPath` | 同目录 `ffplay.exe` | 本机播放 |
| `modelHome` | `C:\Users\Lenovo\.dsh\tts-models` | ChatTTS 模型缓存（HF_HOME） |
| `engine` | `auto` | auto / chattts / edge |
| `dataDir` | 空 | 输出目录，空 = `<DSH_HOME>/dsh-voice` |

## 依赖

- Python 3.10+，`pip install edge-tts`；用 ChatTTS 还需 `pip install ChatTTS` 与约 1GB 模型缓存（首次加载自动从 HF 镜像下载）。
- ffmpeg / ffplay（用于转码与播放）。

## 隐私

语音合成在本机完成（ChatTTS 完全离线；edge-tts 仅把待合成文本发给微软语音服务，不上传其他数据）。生成音频只保存在本机数据目录。

## License

MIT
