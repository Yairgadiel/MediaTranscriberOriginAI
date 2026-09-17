export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface TranscriptionJob {
  id: string
  status: JobStatus
  stage: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  expires_at: string | null
  duration_seconds: number | null
  text: string | null
  error: { code: string; message: string } | null
  status_url: string
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function responseError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  const message = typeof detail === 'string' ? detail : detail?.message
  return new ApiError(message || `Request failed (${response.status})`, response.status)
}

export async function submit(file: File, signal?: AbortSignal): Promise<TranscriptionJob> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/transcriptions', { method: 'POST', body, signal })
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<TranscriptionJob>
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<TranscriptionJob> {
  const response = await fetch(`/api/transcriptions/${jobId}`, { signal })
  if (response.status === 404) throw new ApiError('This transcription is no longer available. It may have expired or the service restarted. Please start a new upload.', 404)
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<TranscriptionJob>
}
