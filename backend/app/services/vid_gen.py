# backend/app/services/video_generation.py
import os
import logging
import uuid
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import HTTPException, status
from moviepy import CompositeVideoClip

logger = logging.getLogger(__name__)

class VideoGenerationService:
    """Service for combining video and audio files."""
    
    def __init__(self, output_dir: str = "./generated_videos"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Check if moviepy is available
        try:
            import moviepy
            self.moviepy_available = True
            logger.info("MoviePy is available for video processing")
        except ImportError:
            self.moviepy_available = False
            logger.warning("MoviePy not available - install with: pip install moviepy")
    
    def generate_video(
        self, 
        video_path: str, 
        audio_path: str, 
        thumbnail_path: Optional[str] = None,
        project_id: str = None
    ) -> Dict[str, Any]:
        """
        Combine video and audio files, optionally add thumbnail overlay.
        
        Args:
            video_path: Path to video file (can include file:// prefix)
            audio_path: Path to audio file (can include file:// prefix)
            thumbnail_path: Optional path to thumbnail image
            project_id: Project identifier
            
        Returns:
            Dict with output path and metadata
        """
        if not self.moviepy_available:
            # Fallback to simple file copy for testing
            return self._generate_video_fallback(
                video_path, audio_path, thumbnail_path, project_id
            )
        
        try:
            from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip
            
            # Clean file paths (remove file:// prefix if present)
            clean_video_path = self._clean_file_path(video_path)
            clean_audio_path = self._clean_file_path(audio_path)
            clean_thumbnail_path = self._clean_file_path(thumbnail_path) if thumbnail_path else None
            
            # Validate input files exist
            if not os.path.exists(clean_video_path):
                raise FileNotFoundError(f"Video file not found: {clean_video_path}")
            if not os.path.exists(clean_audio_path):
                raise FileNotFoundError(f"Audio file not found: {clean_audio_path}")
            
            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{project_id or uuid.uuid4()}_{timestamp}.mp4"
            output_path = self.output_dir / output_filename
            
            logger.info(f"Starting video generation: {output_filename}")
            start_time = time.time()
            
            # Load video and audio clips
            logger.info(f"Loading video from: {clean_video_path}")
            video_clip = VideoFileClip(clean_video_path)
            
            logger.info(f"Loading audio from: {clean_audio_path}")
            audio_clip = AudioFileClip(clean_audio_path)
            
            # Set audio to video (this will replace the original audio)
            final_video = video_clip.set_audio(audio_clip)
            
            # Add thumbnail overlay if provided
            if clean_thumbnail_path and os.path.exists(clean_thumbnail_path):
                logger.info(f"Adding thumbnail overlay from: {clean_thumbnail_path}")
                final_video = self._add_thumbnail_overlay(final_video, clean_thumbnail_path)
            
            # Export final video with optimized settings
            logger.info(f"Exporting video to: {output_path}")
            final_video.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                verbose=False,
                logger=None,  # Suppress moviepy logs
                preset='medium',  # Balance between speed and quality
                ffmpeg_params=['-crf', '23']  # Good quality-to-size ratio
            )
            
            processing_time = time.time() - start_time
            
            # Cleanup clips to free memory
            video_clip.close()
            audio_clip.close()
            final_video.close()
            
            # Get file info
            file_size = output_path.stat().st_size
            duration = self._get_video_duration(str(output_path))
            
            logger.info(
                f"Video generation completed: {output_filename} "
                f"({file_size / (1024*1024):.1f}MB, {processing_time:.1f}s)"
            )
            
            return {
                "output_path": f"file://{output_path.absolute()}",
                "filename": output_filename,
                "size_bytes": file_size,
                "duration_seconds": duration,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            logger.error(f"Video generation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Video generation failed: {str(e)}"
            )
    
    def _generate_video_fallback(
        self, 
        video_path: str, 
        audio_path: str, 
        thumbnail_path: Optional[str],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Fallback method when MoviePy is not available.
        Just copies the video file and returns metadata.
        """
        import shutil
        
        try:
            clean_video_path = self._clean_file_path(video_path)
            
            if not os.path.exists(clean_video_path):
                raise FileNotFoundError(f"Video file not found: {clean_video_path}")
            
            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{project_id or uuid.uuid4()}_{timestamp}_fallback.mp4"
            output_path = self.output_dir / output_filename
            
            logger.warning("Using fallback video generation (copying original video)")
            
            # Copy original video file
            shutil.copy2(clean_video_path, output_path)
            
            # Get file info
            file_size = output_path.stat().st_size
            
            return {
                "output_path": f"file://{output_path.absolute()}",
                "filename": output_filename,
                "size_bytes": file_size,
                "duration_seconds": 0.0,  # Unknown without moviepy
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "processing_time_seconds": 0.1,
                "note": "Fallback mode: original video copied without audio processing"
            }
            
        except Exception as e:
            logger.error(f"Fallback video generation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Video generation failed: {str(e)}"
            )
    
    def _clean_file_path(self, file_path: str) -> str:
        """Remove file:// prefix and convert to absolute path."""
        if not file_path:
            return file_path
        
        # Remove file:// prefix if present
        clean_path = file_path.replace("file://", "")
        
        # Convert to absolute path
        return os.path.abspath(clean_path)
    
    def _add_thumbnail_overlay(self, video_clip, thumbnail_path: str):
        """Add thumbnail as overlay at the beginning."""
        try:
            from moviepy import ImageClip
            
            # Verify thumbnail exists
            if not os.path.exists(thumbnail_path):
                logger.warning(f"Thumbnail file not found: {thumbnail_path}")
                return video_clip
            
            # Create thumbnail clip (show for first 3 seconds)
            thumbnail_clip = (ImageClip(thumbnail_path)
                            .set_duration(min(3, video_clip.duration))  # Don't exceed video duration
                            .resize(height=100)  # Small overlay
                            .set_position(('right', 'top'))
                            .set_start(0))
            
            # Composite with main video
            return CompositeVideoClip([video_clip, thumbnail_clip])
            
        except Exception as e:
            logger.warning(f"Thumbnail overlay failed: {e}")
            return video_clip
        
def get_video_generation_service() -> VideoGenerationService:
    """
    FastAPI dependency factory for VideoGenerationService.
    """
    return VideoGenerationService()