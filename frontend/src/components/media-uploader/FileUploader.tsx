import React, { useCallback, useState, DragEvent } from 'react';

interface FileUploaderProps {
  file?: File;
  onFileSelect: (file: File) => void;
  maxSize: number;
  accept: string;
}

const FileUploader: React.FC<FileUploaderProps> = ({ file, onFileSelect, maxSize, accept }) => {
  const [error, setError] = useState<string | null>(null);

  const validateAndSelect = (f: File) => {
    if (!f.type.match(accept.replace('*', '.*'))) {
      setError('Unsupported file type.');
    } else if (f.size > maxSize) {
      setError(`File exceeds ${Math.round(maxSize / 1024 / 1024)} MB.`);
    } else {
      setError(null);
      onFileSelect(f);
    }
  };

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) {
      validateAndSelect(e.dataTransfer.files[0]);
    }
  }, []);

  return (
    <div>
      <label
        htmlFor="video-upload"
        className="block text-sm font-medium text-gray-700 mb-1"
      >
        Upload Video
      </label>
      <div
        onDragOver={e => e.preventDefault()}
        onDrop={onDrop}
        className="relative flex items-center justify-center h-40 border-2 border-dashed border-gray-300 rounded-lg bg-white hover:border-indigo-500 transition-colors"
        aria-label="File drop zone"
      >
        {!file ? (
          <div className="text-center text-gray-500">
            <p>Drag & drop a file here</p>
            <p>or</p>
            <button
              type="button"
              onClick={() => document.getElementById('video-upload')?.click()}
              className="mt-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              Browse
            </button>
          </div>
        ) : (
          <p className="text-gray-700">{file.name}</p>
        )}

        <input
          id="video-upload"
          type="file"
          accept={accept}
          className="hidden"
          onChange={e => {
            if (e.target.files?.[0]) validateAndSelect(e.target.files[0]);
          }}
        />
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
};

export default FileUploader;
