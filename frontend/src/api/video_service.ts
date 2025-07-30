import API from './client.ts';
import type { Metadata, VideoOptions } from '../models.tsx';

export async function useVideoUpload(
  file: File,
  metadata: Metadata,
  options: VideoOptions,
  onProgress: (pct: number) => void
): Promise<{ previewUrl: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', metadata.title);
  form.append('description', metadata.description);
  form.append('tags', metadata.tags.join(','));
  form.append('resolution', options.resolution);

  const { data } = await API.post<{ previewUrl: string }>(
    '/video/generate',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: e => {
        if (e.total) onProgress(Math.round((e.loaded * 100) / e.total));
      },
    }
  );
  return data;
}
