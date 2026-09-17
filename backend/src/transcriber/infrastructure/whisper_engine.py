class FasterWhisperEngine:
    def __init__(self, settings):
        # ML imports happen only when constructing the worker adapter.
        from faster_whisper import WhisperModel
        from huggingface_hub import snapshot_download
        import logging
        logging.getLogger(__name__).info("Loading pinned CPU model")
        path = snapshot_download(settings.model_id, revision=settings.model_revision,
                                 cache_dir=settings.model_cache, allow_patterns=['*.json', '*.bin', '*.txt'])
        self.model = WhisperModel(path, device='cpu', compute_type='int8', cpu_threads=settings.cpu_threads)

    def transcribe(self, audio):
        segments, _ = self.model.transcribe(str(audio), language='en', beam_size=5,
                                            vad_filter=True, condition_on_previous_text=False)
        return ' '.join(s.text.strip() for s in segments).strip()
