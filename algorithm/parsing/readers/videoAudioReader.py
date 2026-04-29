from pathlib import Path
from typing import List, Optional, cast

from lazyllm.thirdparty import fsspec
from lazyllm.tools.rag.doc_node import DocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase


class VideoAudioReader(LazyLLMReaderBase):
    __lazyllm_registry_disable__ = True

    def __init__(
        self, model_version: str = 'base', return_trace: bool = True,
        time_segment: bool = False, time_interval: int = 15
    ) -> None:
        super().__init__(return_trace=return_trace)
        self._model_version = model_version
        self._time_segment = time_segment
        self._time_interval = time_interval

        try:
            import whisper
        except ImportError as exc:
            raise ImportError('Please install OpenAI whisper model `pip install openai-whisper` to use the model') from exc

        model = whisper.load_model(self._model_version)
        self._parser_config = {'model': model}

    def _load_data(
        self, file: Path,
        fs: Optional['fsspec.AbstractFileSystem'] = None
    ) -> List[DocNode]:
        import whisper

        if not isinstance(file, Path):
            file = Path(file)

        video_input = False
        if file.suffix.lower() == '.mp4':
            try:
                from pydub import AudioSegment
            except ImportError as exc:
                raise ImportError('Please install pydub `pip install pydub`') from exc

            if fs:
                with fs.open(file, 'rb') as f:
                    video = AudioSegment.from_file(f, format='mp4')
            else:
                video = AudioSegment.from_file(file, format='mp4')

            video_input = True
            audio = video
            video_file_path = file
            file = Path(str(file)[:-4] + '.mp3')
            audio.export(file, format='mp3')

        model = cast(whisper.Whisper, self._parser_config['model'])

        if self._time_segment:
            result = model.transcribe(str(file), word_timestamps=True)
            return self._merge_segments(result['segments'], file, video_input, video_file_path if video_input else None)

        result = model.transcribe(str(file))
        transcript = result['text']
        metadata = {
            'start_time': 0,
            'end_time': float('inf'),
            'audio_file_path': str(file),
        }
        if video_input:
            metadata['video_file_path'] = str(video_file_path)
        return [DocNode(text=transcript, metadata=metadata)]

    def _merge_segments(
        self, segments, file: Path, video_input: bool = False,
        video_file_path: Optional[Path] = None
    ) -> List[DocNode]:
        nodes = []
        merged_text = []
        merged_start = None
        merged_end = None

        def _build_node(start_time, end_time, texts):
            metadata = {
                'start_time': start_time,
                'end_time': end_time,
                'audio_file_path': str(file),
            }
            if video_input and video_file_path is not None:
                metadata['video_file_path'] = str(video_file_path)
            return DocNode(text=''.join(texts), metadata=metadata)

        for segment in segments:
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text']

            if merged_start is None:
                merged_start = start_time
                merged_end = end_time
                merged_text.append(text)
                continue

            if end_time - merged_start < self._time_interval:
                merged_end = end_time
                merged_text.append(text)
                continue

            nodes.append(_build_node(merged_start, merged_end, merged_text))
            merged_start = start_time
            merged_end = end_time
            merged_text = [text]

        if merged_start is not None:
            nodes.append(_build_node(merged_start, merged_end, merged_text))

        return nodes


__all__ = ['VideoAudioReader']
