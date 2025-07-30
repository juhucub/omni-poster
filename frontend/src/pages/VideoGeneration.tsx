// src/pages/VideoGenerationPage.tsx
import React, { Suspense } from 'react';
import { useAuthGuard } from '../components/video-gen/useAuthGuard.tsx';        // ← guard hook
import { useVideoUpload } from '../api/video_service.ts';    // ← upload hook

const FileUploader   = React.lazy(() => import('../components/media-uploader/FileUploader'));
const MetadataForm   = React.lazy(() => import('../components/video-gen/MetadataForm'));
const ProgressBar    = React.lazy(() => import('../components/video-gen/ProgressBar'));
const PreviewPlayer  = React.lazy(() => import('../components/video-gen/PreviewPlayer'));
const GenerateButton = React.lazy(() => import('../components/video-gen/GenerateButton'));

const VideoGenerationPage: React.FC = () => {
  // 1) Redirect to /login if not authenticated
  useAuthGuard();

  // 2) Pull everything from your custom hook, not your service fn
  const {
    file,
    setFile,
    metadata,
    setMetadata,
    options,
    setOptions,
    uploadProgress,
    previewUrl,
    generateVideo,    // ← now this is from the hook
    isGenerating,
    error,
  } = useVideoUpload(); 

  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <h1 className="text-3xl font-extrabold mb-8">Video Generation</h1>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* LEFT: Uploader + Form */}
        <section className="flex-1 space-y-8">
          <Suspense fallback={<div>Loading uploader…</div>}>
            <FileUploader
              file={file}
              onFileSelect={setFile}
              maxSize={500 * 1024 * 1024}
              accept="video/*"
            />
          </Suspense>

          <Suspense fallback={<div>Loading metadata form…</div>}>
            <MetadataForm metadata={metadata} onChange={setMetadata} />
          </Suspense>

          <section className="bg-white p-4 rounded-2xl shadow-sm">
            <label htmlFor="resolution" className="block text-sm font-medium text-gray-700">
              Resolution
            </label>
            <select
              id="resolution"
              value={options.resolution}
              onChange={e => setOptions({ ...options, resolution: e.target.value as any })}
              className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 
                         focus:ring-indigo-500 focus:border-indigo-500"
            >
              <option value="720p">1280×720 (HD)</option>
              <option value="1080p">1920×1080 (Full HD)</option>
              <option value="4k">3840×2160 (4K)</option>
            </select>
          </section>
        </section>

        {/* RIGHT: Preview + Actions */}
        <aside className="flex-1 space-y-8">
          <div className="bg-white p-4 rounded-2xl shadow-sm">
            <h2 className="text-xl font-semibold mb-4">Preview</h2>
            {previewUrl ? (
              <Suspense fallback={<div>Loading preview…</div>}>
                <PreviewPlayer src={previewUrl} />
              </Suspense>
            ) : (
              <p className="text-gray-500">Preview will appear here once ready.</p>
            )}
          </div>

          {uploadProgress > 0 && (
            <Suspense fallback={<div>Loading progress bar…</div>}>
              <ProgressBar progress={uploadProgress} />
            </Suspense>
          )}

          <div className="flex items-center space-x-4">
            <Suspense fallback={<button className="btn-loading">Loading…</button>}>
              <GenerateButton onClick={generateVideo} disabled={isGenerating || !file} />
            </Suspense>
            <button
              onClick={() => {/* download logic */}}
              className="px-4 py-2 bg-green-600 text-white rounded-lg shadow 
                         hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
              disabled={!previewUrl}
            >
              Download
            </button>
            <button
              onClick={() => {/* schedule logic */}}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg shadow 
                         hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              Schedule
            </button>
          </div>

          {error && <p className="text-red-600">{error}</p>}
        </aside>
      </div>
    </main>
  );
};

export default VideoGenerationPage;
