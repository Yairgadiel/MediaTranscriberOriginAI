import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('transcription UI', () => {
  beforeEach(() => { window.localStorage.clear(); vi.restoreAllMocks(); vi.useFakeTimers() })
  const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve() })

  it('submits one file and renders a completed transcript', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'queued', stage: null, created_at: '', started_at: null, finished_at: null, expires_at: null, duration_seconds: null, text: null, error: null, status_url: '/api/transcriptions/x' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'completed', stage: null, created_at: '', started_at: null, finished_at: '', expires_at: '', duration_seconds: 3, text: 'hello world', error: null, status_url: '/api/transcriptions/x' }))))
    render(<App />)
    fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['x'], 'audio.mp3', { type: 'audio/mpeg' })] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and transcribe' }))
    await flush()
    expect(screen.getByText('Status: queued')).toBeTruthy()
    expect(screen.getByText('Checking status automatically')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /refresh now/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New upload' })).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('hello world')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'New upload' })).toBeTruthy()
  })

  it('stops polling after a terminal response', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'queued', stage: null, created_at: '', started_at: null, finished_at: null, expires_at: null, duration_seconds: null, text: null, error: null, status_url: '/api/transcriptions/x' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'completed', stage: null, created_at: '', started_at: null, finished_at: '', expires_at: '', duration_seconds: 3, text: 'hello world', error: null, status_url: '/api/transcriptions/x' }))))
    render(<App />)
    fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['x'], 'audio.mp3', { type: 'audio/mpeg' })] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and transcribe' }))
    await flush()
    expect(screen.getByText('Status: queued')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('hello world')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('retries a recoverable polling error without losing the active job', async () => {
    window.localStorage.setItem('media-transcriber.active-job', 'a'.repeat(32))
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'queued', stage: null, created_at: '', started_at: null, finished_at: null, expires_at: null, duration_seconds: null, text: null, error: null, status_url: '/api/transcriptions/x' }))))
    render(<App />)
    await flush()
    expect(screen.getByRole('alert').textContent).toContain('Request failed (503)')
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('Status: queued')).toBeTruthy()
    expect(window.localStorage.getItem('media-transcriber.active-job')).toBe('a'.repeat(32))
  })

  it('stops polling after three transient failures and gives a clear next step', async () => {
    window.localStorage.setItem('media-transcriber.active-job', 'a'.repeat(32))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    render(<App />)
    await flush()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(screen.getByRole('alert').textContent).toContain('after three attempts')
    expect(window.localStorage.getItem('media-transcriber.active-job')).toBeNull()
    expect(screen.getByRole('button', { name: 'Upload and transcribe' })).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('forgets an expired restored job after one polling 404', async () => {
    window.localStorage.setItem('media-transcriber.active-job', 'a'.repeat(32))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('', { status: 404 })))
    render(<App />)
    await flush()
    expect(screen.getByRole('alert').textContent).toContain('It may have expired or the service restarted. Please start a new upload.')
    expect(window.localStorage.getItem('media-transcriber.active-job')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('reveals New upload when a restored job has failed', async () => {
    window.localStorage.setItem('media-transcriber.active-job', 'a'.repeat(32))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'failed', stage: null, created_at: '', started_at: null, finished_at: '', expires_at: '', duration_seconds: null, text: null, error: { code: 'processing_failed', message: 'Unable to process media.' }, status_url: '/api/transcriptions/x' }))))
    render(<App />)
    await flush()
    expect(screen.getByText('Transcription failed')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'New upload' })).toBeTruthy()
    expect(screen.queryByText('Checking status automatically')).toBeNull()
  })

  it('shows a small upload indicator without an overlay while submission is pending', async () => {
    let resolveSubmission: ((response: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { resolveSubmission = resolve })))
    render(<App />)
    fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['x'], 'audio.mp3', { type: 'audio/mpeg' })] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and transcribe' }))
    await flush()
    expect(screen.getByRole('status').textContent).toContain('Uploading your media…')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    await act(async () => { resolveSubmission?.(new Response(JSON.stringify({ id: 'a'.repeat(32), status: 'queued', stage: null, created_at: '', started_at: null, finished_at: null, expires_at: null, duration_seconds: null, text: null, error: null, status_url: '/api/transcriptions/x' }), { status: 202 })) })
  })
})
