# 第三方组件与模型来源

听会的原始应用源码与第三方组件分别适用各自权利声明。公开仓库本身不改变第三方模型、运行库和依赖的许可。

## MOSS-Transcribe-Diarize

- 权重与模型卡：https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize
- 上游源码：https://github.com/OpenMOSS/MOSS-Transcribe-Diarize
- 上游标注许可：Apache License 2.0。
- 本版本权重修订：`10304d926740cf5a5cee05a268086e3265197910`。
- 权重 SHA-256：`9a0ceb4ab7330357db3ff583dba8d83625d5b733b00e1d55d6970e11b07026c4`。
- 发布程序保留上游的 `MOSS-LICENSE.txt`。模型包保留 Apache 2.0 许可文本。原始权重未作修改。

## Paraformer 流式字幕模型

- ONNX 模型来源：https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en
- 上游模型卡标注许可：Apache License 2.0。
- 修订：`8e40c43232a1c5c66c82111efc5820d3accca11b`。
- 模型卡指向的原始模型：https://www.modelscope.cn/models/damo/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8404-online/summary
- 本项目使用已经导出的量化 ONNX 文件，未重新训练或修改权重。

## CAM++ 说话人模型

- ONNX 转换文件来源：https://huggingface.co/csukuangfj/speaker-embedding-models
- 文件：`3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx`。
- 修订：`0743f301363dec56491a490f6d6cbc9d67f9a3bf`。
- 原模型及说明：https://modelscope.cn/models/iic/speech_campplus_sv_zh-cn_16k-common
- FunASR 模型卡：https://huggingface.co/funasr/campplus ，标注 Apache License 2.0。
- 计算框架与更多说明：https://github.com/modelscope/3D-Speaker
- SHA-256：`f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11`。
- ONNX 镜像仓库未单独提供模型卡；本项目保留转换来源和原模型的许可说明，不将框架许可替换为另一个许可。

## 运行环境

- Electron、React、sherpa-onnx、PyTorch、Transformers、FFmpeg 和 Python 等组件的许可文件随对应组件保留，依赖版本可在源代码清单及运行环境的包元数据中查看。
- Microsoft C++ 运行库来自构建机 Visual Studio x64 可再分发目录，采用应用目录本地部署。相关文件清单保留在程序包的 `第三方许可/MSVC-Redist.txt`；其使用与分发遵循 Microsoft 对这些组件的许可条件。
- 豆包云端与外部 AI 文本模型服务需要使用者自己的账号和凭据，服务条款由相应提供方决定。
