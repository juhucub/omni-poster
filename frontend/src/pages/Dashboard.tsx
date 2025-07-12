import React, { useState } from 'react';
import MediaUploader from '../components/MediaUploader';
import VideoPreview from '../components/VideoPreview';
import MetadataForm from '../components/MetaDataForm';
import PlatformSelector from '../components/PlatformSelector';
import SchedulePicker from '../components/SchedulePicker';
import UploadHistoryTable from '../components/UploadHistoryTable';
import axios from 'axios';

/**
 * Dashboard
 * Orchestrates the upload flow: asset upload -> preview -> metadata -> platforms -> schedule
 * and displays upload history.
 */
const Dashboard: React.FC = () => {
  // Core flow states
  const [projectId, setProjectId] = useState<string>('');
  const [metadataSaved, setMetadataSaved] = useState<boolean>(false);
  const [metadata, setMetadata] = useState<{ title: string; tags: string[]; hashtags: string[] } | null>(null);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [scheduledTime, setScheduledTime] = useState<string>('');
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [scheduleSuccess, setScheduleSuccess] = useState<boolean>(false);

  // Handle asset upload success
  const handleUploadSuccess = (pid: string) => {
    setProjectId(pid);
  };

  // Handle metadata saved
  const handleMetadataComplete = (data: { title: string; tags: string[]; hashtags: string[] }) => {
    setMetadata(data);
    setMetadataSaved(true);
  };

  // Handle final schedule submission
  const handleSchedule = async (iso: string) => {
    setScheduleError(null);
    try {
      // Endpoint to schedule job combining project, metadata, platforms, and time
      await axios.post(
        '/schedule',
        { project_id: projectId, platforms, scheduled_time: iso },
        { withCredentials: true }
      );
      setScheduledTime(iso);
      setScheduleSuccess(true);
    } catch (err: any) {
      setScheduleError('Failed to schedule upload. Please try again.');
    }
  };

  return (
    <div className="space-y-8 p-8">
      {/* Upload Section */}
      {!projectId && <MediaUploader onUploadSuccess={handleUploadSuccess} />}

      {/* Preview Section */}
      {projectId && (
        <VideoPreview projectId={projectId} />
      )}

      {/* Metadata Section */}
      {projectId && !metadataSaved && (
        <MetadataForm projectId={projectId} onComplete={handleMetadataComplete} />
      )}

      {/* Platform Selection */}
      {metadataSaved && (
        <PlatformSelector
          initialSelected={[]}
          onChange={selected => setPlatforms(selected)}
        />
      )}

      {/* Schedule Picker & Submit */}
      {metadataSaved && (
        <div className="space-y-4">
          <SchedulePicker onSchedule={handleSchedule} />
          {scheduleError && <p className="text-red-600">{scheduleError}</p>}
          {scheduleSuccess && <p className="text-green-600">Upload scheduled for {new Date(scheduledTime).toLocaleString()}</p>}
        </div>
      )}

      {/* Upload History */}
      <div>
        <h2 className="text-2xl font-semibold">Upload History</h2>
        <UploadHistoryTable />
      </div>
    </div>
  );
};

export default Dashboard;
