import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getJob, submit, type TranscriptionJob } from './api'

const storageKey = 'media-transcriber.active-job'
const terminal = (job: TranscriptionJob) => job.status === 'completed' || job.status === 'failed'
const pollingRetryDelayMs = 2_000
const pollingRetryMaxDelayMs = 5_000

const retryDelay = (attempt: number) => Math.min(
  pollingRetryDelayMs * (2 ** (attempt - 1)), pollingRetryMaxDelayMs,
)

export function useTranscription() {
  const [job, setJob] = useState<TranscriptionJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const pollTimer = useRef<number | null>(null)
  const request = useRef<AbortController | null>(null)
  const pollFailures = useRef(0)

  const stop = useCallback(() => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current)
    pollTimer.current = null
    request.current?.abort()
    request.current = null
  }, [])

  const refresh = useCallback(async (jobId: string) => {
    request.current?.abort()
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current)
    pollTimer.current = null
    const controller = new AbortController()
    request.current = controller
    try {
      const next = await getJob(jobId, controller.signal)
      setJob(next)
      setError(null)
      pollFailures.current = 0
      if (terminal(next)) window.localStorage.removeItem(storageKey)
    } catch (cause) {
      if ((cause as Error).name !== 'AbortError') {
        if (cause instanceof ApiError && cause.status === 404) {
          stop()
          window.localStorage.removeItem(storageKey)
          setJob(null)
          setError(cause.message)
          return
        }
        pollFailures.current += 1
        if (pollFailures.current >= 3) {
          stop()
          window.localStorage.removeItem(storageKey)
          setJob(null)
          setError('We could not refresh the transcription status after three attempts. Please start a new upload or refresh the page.')
          return
        }
        setError((cause as Error).message || 'Unable to refresh status. Retrying shortly.')
        pollTimer.current = window.setTimeout(() => void refresh(jobId), retryDelay(pollFailures.current))
      }
    }
  }, [stop])

  useEffect(() => {
    const jobId = window.localStorage.getItem(storageKey)
    if (jobId) void refresh(jobId)
    return stop
  }, [refresh, stop])

  useEffect(() => {
    if (!job || terminal(job)) return
    pollTimer.current = window.setTimeout(() => void refresh(job.id), 2000)
    return () => {
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [job, refresh])

  const upload = useCallback(async (file: File) => {
    stop()
    pollFailures.current = 0
    setUploading(true)
    setError(null)
    try {
      const next = await submit(file)
      setJob(next)
      window.localStorage.setItem(storageKey, next.id)
    } catch (cause) {
      setError((cause as Error).message || 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
    }
  }, [stop])

  const reset = useCallback(() => {
    stop()
    pollFailures.current = 0
    window.localStorage.removeItem(storageKey)
    setJob(null)
    setError(null)
  }, [stop])

  return { job, error, uploading, upload, refresh, reset }
}
