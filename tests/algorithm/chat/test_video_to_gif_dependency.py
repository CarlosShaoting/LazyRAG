from lazymind.chat.engine.tools import multimodal


def test_video_to_gif_returns_dependency_error_when_ffmpeg_is_missing(monkeypatch):
    monkeypatch.setattr(multimodal.shutil, 'which', lambda _name: None)

    result = multimodal.video_to_gif('/tmp/generated-video.mp4')

    assert result['success'] is False
    assert result['error']['type'] == 'MissingDependency'
    assert 'FFMPEG_DEPENDENCY_MISSING' in result['error']['reason']
    assert result['meta'] == {
        'dependency': 'ffmpeg',
        'settings_path': '/model-providers/tools#ffmpeg-dependency',
        'fallback': 'video',
    }
