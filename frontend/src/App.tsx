import { FormEvent, useState } from 'react'
import { useTranscription } from './useTranscription'
import './styles.css'

function download(text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'transcript.txt'
  link.click()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const { job, error, uploading, upload, refresh, reset } = useTranscription()
  const active = uploading || (job && !['completed', 'failed'].includes(job.status))
  const submit = (event: FormEvent) => { event.preventDefault(); if (file) void upload(file) }

  return <main>
    <section className="panel" aria-labelledby="title">
      <p className="eyebrow">ASYNC AUDIO TRANSCRIPTION</p>
      <h1 id="title">Media Transcriber</h1>
      <p className="intro">Upload one media file. Files can be up to 4 GiB and audio can be up to one hour. Results are temporary.</p>
      <form onSubmit={submit}>
        <label htmlFor="media">Media file</label>
        <input id="media" type="file" accept="audio/*,video/*" disabled={Boolean(active)} onChange={event => setFile(event.target.files?.[0] || null)} />
        {file && <p className="file">{file.name}</p>}
        <button type="submit" disabled={!file || Boolean(active)}>{uploading ? 'Uploading…' : 'Upload and transcribe'}</button>
      </form>
      {job && <section className={`status ${job.status}`} aria-live="polite">
        <strong>{job.status === 'completed' ? 'Transcription complete' : job.status === 'failed' ? 'Transcription failed' : `Status: ${job.stage || job.status}`}</strong>
        {!['completed', 'failed'].includes(job.status) && <button className="text-button" type="button" onClick={() => void refresh(job.id)}>Refresh now</button>}
        <button className="text-button" type="button" onClick={reset}>New upload</button>
      </section>}
      {error && <p className="error" role="alert">{error}</p>}
      {job?.error && <p className="error" role="alert">{job.error.message}</p>}
      {job?.status === 'completed' && <section className="result" aria-labelledby="transcript-heading">
        <div><h2 id="transcript-heading">Transcript</h2><span>{job.duration_seconds ? `${Math.round(job.duration_seconds)} seconds of media` : ''}</span></div>
        <pre>{job.text || 'No speech was detected.'}</pre>
        <button type="button" onClick={() => navigator.clipboard.writeText(job.text || '')}>Copy text</button>
        <button type="button" onClick={() => download(job.text || '')}>Download .txt</button>
      </section>}
    </section>
  </main>
}
