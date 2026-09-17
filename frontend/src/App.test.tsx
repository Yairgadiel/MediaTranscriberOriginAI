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
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('hello world')).toBeTruthy()
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
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(screen.getByText('Status: queued')).toBeTruthy()
    expect(window.localStorage.getItem('media-transcriber.active-job')).toBe('a'.repeat(32))
  })
})
