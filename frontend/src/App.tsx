import { DragEvent, FormEvent, useState } from 'react'
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
  const [dragging, setDragging] = useState(false)
  const { job, error, uploading, upload, reset } = useTranscription()
  const terminal = Boolean(job && ['completed', 'failed'].includes(job.status))
  const active = uploading || Boolean(job && !terminal)
  const submit = (event: FormEvent) => { event.preventDefault(); if (file) void upload(file) }
  const chooseFile = (nextFile: File | null | undefined) => setFile(nextFile || null)
  const dropFile = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setDragging(false)
    if (!active) chooseFile(event.dataTransfer.files[0])
  }

  const statusCopy = job?.status === 'completed'
    ? 'Transcription complete'
    : job?.status === 'failed'
      ? 'Transcription failed'
      : `Status: ${job?.stage || job?.status}`

  return <main>
    <section className="panel" aria-labelledby="title">
      <header className="hero">
        <p className="eyebrow">ASYNC AUDIO TRANSCRIPTION</p>
        <h1 id="title">Media Transcriber</h1>
        <p className="intro">Upload one media file. Files can be up to 4 GiB and audio can be up to one hour. Results are temporary.</p>
      </header>
      <form onSubmit={submit}>
        <label
          className={`dropzone${dragging ? ' is-dragging' : ''}${active ? ' is-disabled' : ''}`}
          htmlFor="media"
          onDragEnter={event => { event.preventDefault(); if (!active) setDragging(true) }}
          onDragOver={event => event.preventDefault()}
          onDragLeave={event => { if (event.currentTarget === event.target) setDragging(false) }}
          onDrop={dropFile}
        >
          <input id="media" className="file-input" type="file" accept="audio/*,video/*" disabled={Boolean(active)} aria-label="Media file" onChange={event => chooseFile(event.target.files?.[0])} />
          <span className="upload-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M7 18.5h10a4 4 0 0 0 .4-7.98A5.5 5.5 0 0 0 6.8 9.1 4.7 4.7 0 0 0 7 18.5Z" /><path d="M12 8v7m0-7-2.5 2.5M12 8l2.5 2.5" /></svg>
          </span>
          <span className="dropzone-copy"><strong>{file ? file.name : 'Drag & drop media file here or click to browse'}</strong><small>{file ? 'Ready to transcribe' : 'Audio and video files · 4 GiB maximum'}</small></span>
        </label>
        <button className="primary-button" type="submit" disabled={!file || Boolean(active)}>
          {uploading && <span className="spinner" aria-hidden="true" />}
          {uploading ? 'Uploading…' : 'Upload and transcribe'}
        </button>
      </form>
      {uploading && <p className="activity-indicator" role="status"><span className="mini-spinner" aria-hidden="true" />Uploading your media…</p>}
      {job && <section className={`status ${job.status}`} aria-live="polite">
        <div className="status-heading">
          <span className="status-icon" aria-hidden="true">{job.status === 'completed' ? '✓' : job.status === 'failed' ? '!' : ''}</span>
          <div><span className="status-label">{job.status === 'completed' ? 'Ready' : job.status === 'failed' ? 'Action needed' : 'In progress'}</span><strong>{statusCopy}</strong>{!terminal && <span className="activity-indicator"><span className="mini-spinner" aria-hidden="true" />Checking status automatically</span>}</div>
        </div>
        {terminal && <div className="status-actions"><button className="ghost-button" type="button" onClick={reset}><span aria-hidden="true">＋</span> New upload</button></div>}
      </section>}
      {error && <p className="error" role="alert">{error}</p>}
      {job?.error && <p className="error" role="alert">{job.error.message}</p>}
      {job?.status === 'completed' && <section className="result" aria-labelledby="transcript-heading">
        <div><h2 id="transcript-heading">Transcript</h2><span>{job.duration_seconds ? `${Math.round(job.duration_seconds)} seconds of media` : ''}</span></div>
        <pre>{job.text || 'No speech was detected.'}</pre>
        <div className="result-actions"><button className="ghost-button" type="button" onClick={() => navigator.clipboard.writeText(job.text || '')}>Copy text</button><button className="ghost-button" type="button" onClick={() => download(job.text || '')}>Download .txt</button></div>
      </section>}
    </section>
  </main>
}
