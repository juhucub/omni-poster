import React, { useState, ChangeEvent, FormEvent, useContext } from 'react';
import axios from 'axios';
import { AuthContext } from '../context/AuthContext.tsx';


//Allowed MIME types and size limits
const ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm'];
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/wav'];
const MAX_FILE_SIZE = 50 * (2**20); // 50 MB

interface MediaUploaderProps {
    onUploadSuccess: (file: File) => void;
    //FIXME: onUploadError?: (error: string) => void;
}

const MediaUploader: React.FC<MediaUploaderProps> = ({ onUploadSuccess }) => {
    //Local compontent state
    const [videoFile, setVideoFile] = useState<File | null>(null);
    const [audioFile, setAudioFile] = useState<File | null>(null);
    const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loader, setLoading] = useState<boolean>(false);
    useContext(AuthContext);
    //validate a selcted file against allowed types and size
    const validateFile = (file: File, allowedTypes: string[]) => {
        if(!allowedTypes.includes(file.type)) {
            return `Invalid file type: ${file.type}`;
        }
        if(file.size > MAX_FILE_SIZE) {
            return `File size exceeds the limit of ${MAX_FILE_SIZE / (2**20)} MB Limit`;
        }
        return null;
    };

    //Handlers for input change
    const handleVideoChange = (e: ChangeEvent<HTMLInputElement>) => {
        setError(null);
        const file = e.target.files?.[0];
        if(!file) { return; }
        const validationError = validateFile(file, ALLOWED_VIDEO_TYPES);
            if(validationError) {
                setError(validationError);
                return;
            } 
            setVideoFile(file);
    };

    const handleAudioChange = (e: ChangeEvent<HTMLInputElement>) => {
        setError(null);
        const file = e.target.files?.[0];
        if(!file) { return; }
        const validationError = validateFile(file, ALLOWED_AUDIO_TYPES);
            if(validationError) {
                setError(validationError);
                return;
            } 
            setAudioFile(file);
    };

    const handleThumbnailChange = (e: ChangeEvent<HTMLInputElement>) => {
        setError(null);
        const file = e.target.files?.[0];
        if(!file) { return; }
        const validationError = validateFile(file, ALLOWED_IMAGE_TYPES);
            if(validationError) {
                setError(validationError);
                return;
            } 
        setThumbnailFile(file);
    };

    //Submit handler for the form: POSTs to backend /upload 
    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError(null);

        if(!videoFile || !audioFile) {
            setError('Both Audio and Video files are required.');
            return;
        }

        const formData = new FormData();
        formData.append('video', videoFile);
        formData.append('audio', audioFile);
        if(thumbnailFile) formData.append('thumbnail', thumbnailFile);
        
        try{
            setLoading(true);
            const response = await axios.post('/upload', formData, {
                headers: {  'Content-Type': 'multipart/form-data' },
                withCredentials: true,      //include cookies for CSRF/auth
            });
            const { project_id } = response.data;
            onUploadSuccess(project_id);
        } catch (err: any) {
            //Handle err status codes that we know
            if(err.response?.status == 415) {
                setError('Unsupported file type.');
            } else if(err.response?.status == 500) {
                setError('Server error saving files.');
            } else {
                setError('An unexpected error occurred.');
            } 
        } finally {
            setLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-white rounded shadow">
            <h2 className="text-xl font-semibold">Upload Media</h2>

            {/*Video input */}
            <div>
                <label className="block text-sm font-medium">Video File</label>
                <input 
                    type="file" 
                    accept={ALLOWED_VIDEO_TYPES.join(', ')} 
                    onChange={handleVideoChange} 
                    className="mt-1 block w-full text-sm"
                    required
                />
            </div>
            {/*Audio input */}
            <div>
                <label className="block text-sm font-medium">Audio File</label>
                <input 
                    type="file" 
                    accept={ALLOWED_AUDIO_TYPES.join(', ')} 
                    onChange={handleAudioChange} 
                    className="mt-1 block w-full text-sm"
                    required
                />
            </div>

            {/*Error Message */}
            {error && <p className="test-red-600 text-sm">{error}</p>}

            {/*Submit button*/}
            <button 
                type="submit" 
                disabled={loader}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
                {loader ? 'Uploading...' : 'Upload & Generate'}
            </button>
        </form>
    );
};

export default MediaUploader;
// This component handles media uploads, validates files, and submits them to the backend.
