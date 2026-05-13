# OmniPoster System Design Graph

**Vision:** OmniPoster is a reusable AI content pipeline that turns scripts, character voices, backgrounds, and layout presets into polished short-form videos ready for posting.

---

## 1. Final Vision System Map

```mermaid
flowchart TD
  A[Creator Idea] --> B[Script / Dialogue]
  B --> C[Speaker Assignment]
  C --> D[Voice Profiles]
  C --> E[Video Layout Preset]
  D --> F[Voice Generation]
  E --> G[Preview Composer]
  F --> H[Audio Segments]
  G --> I[Visual Preview]
  H --> J[Final Render]
  I --> J
  J --> K[Exported Short-Form Video]
  K --> L[Metadata]
  L --> M[Schedule / Publish]
  M --> N[Upload History / Analytics]

  D --> D1[Reference Audio]
  D --> D2[Speaker Image]
  D --> D3[Voice Recipe]
  D --> D4[Golden Samples]

  E --> E1[Background]
  E --> E2[Character PNG Placement]
  E --> E3[Chat Bubble Style]
  E --> E4[Platform Aspect Ratio]
```

---

## 2. Product Flow

```mermaid
flowchart LR
  A[Dashboard] --> B[Create Project]
  B --> C[Script Editor]
  C --> D[Assign Speakers]
  D --> E[Select Background]
  E --> F[Configure Preview]
  F --> G[Generate Voice Segments]
  G --> H[Render Video]
  H --> I[Review Output]
  I --> J[Download]
  I --> K[Schedule Post]
  I --> L[Regenerate Changed Parts]

  L --> G
  L --> F
```

---

## 3. Backend Architecture

```mermaid
flowchart TD
  UI[React Frontend] --> API[FastAPI Backend]

  API --> AUTH[Auth / Session Layer]
  API --> PROJECTS[Projects API]
  API --> VOICES[Voice Lab API]
  API --> VIDEO[Video Lab API]
  API --> JOBS[Generation Jobs API]
  API --> ARTIFACTS[Artifact Serving API]

  PROJECTS --> DB[(Postgres)]
  VOICES --> DB
  VIDEO --> DB
  JOBS --> DB

  VOICES --> STORAGE[(Media Storage)]
  VIDEO --> STORAGE
  ARTIFACTS --> STORAGE

  JOBS --> REDIS[(Redis Queue)]
  REDIS --> WORKERS[Worker Pool]
```

---

## 4. Worker Architecture

```mermaid
flowchart TD
  REDIS[(Redis Queue)] --> ORCH[Job Orchestrator]

  ORCH --> SCRIPT[Script Parser]
  ORCH --> VOICE[Voice Worker]
  ORCH --> PREVIEW[Preview Worker]
  ORCH --> RENDER[Render Worker]

  SCRIPT --> SEGMENTS[Speaker Segments]

  SEGMENTS --> VOICE
  VOICE --> CACHE[Audio Cache]
  VOICE --> WAVS[Segment WAV Artifacts]

  PREVIEW --> PREVIEWSTATE[Persisted Preview State]
  PREVIEWSTATE --> RENDER
  WAVS --> RENDER

  RENDER --> FFMPEG[FFmpeg Composer]
  FFMPEG --> FINAL[Final MP4]
  FINAL --> ARTIFACTS[Stored Render Artifacts]
  ARTIFACTS --> DB[(Job Metadata)]
```

---

## 5. Full MVP Boundary

```mermaid
flowchart TD
  subgraph MVP[Minimum Viable Product]
    A[Create Project]
    B[Paste / Generate Script]
    C[Assign Voice Profiles]
    D[Select Background]
    E[Persistent Video Preview]
    F[Generate Segment WAVs]
    G[Render Final Video]
    H[Download Final MP4]
    I[View Job History]
  end

  A --> B --> C --> D --> E --> F --> G --> H
  G --> I

  subgraph RequiredReliability[Required Reliability Features]
    R1[Final Audio Matches Segment WAVs]
    R2[Preview Matches Render]
    R3[Artifacts Are Inspectable]
    R4[Failed Jobs Are Debuggable]
    R5[Unchanged Audio/Visuals Are Cached]
  end

  F --> R1
  E --> R2
  G --> R3
  I --> R4
  F --> R5
```

---

## 6. MVP Feature Checklist

```mermaid
flowchart LR
  A[MVP Done] --> B[Voice Lab Works]
  A --> C[Video Lab Works]
  A --> D[Preview Persists]
  A --> E[Render Pipeline Works]
  A --> F[Artifacts Work]

  B --> B1[Upload Reference Audio]
  B --> B2[Store Voice Profile]
  B --> B3[Show Speaker Image]
  B --> B4[Generate Preview WAV]

  C --> C1[Select Script]
  C --> C2[Select Speakers]
  C --> C3[Select Background]
  C --> C4[Configure Layout]

  D --> D1[Background Visible]
  D --> D2[Character PNGs Visible]
  D --> D3[Bubble Font Adjustable]
  D --> D4[Character Size Adjustable]

  E --> E1[Generate Segment Audio]
  E --> E2[Compose Video]
  E --> E3[Attach Correct Audio]
  E --> E4[Export MP4]

  F --> F1[Segment WAV Links]
  F --> F2[Final MP4 Link]
  F --> F3[Job Metadata]
  F --> F4[Error Logs]
```

---

## 7. Core Data Model

```mermaid
erDiagram
  USER ||--o{ PROJECT : owns
  PROJECT ||--o{ SCRIPT : contains
  PROJECT ||--o{ GENERATION_JOB : creates
  PROJECT ||--o{ PREVIEW_STATE : stores

  VOICE_PROFILE ||--o{ REFERENCE_AUDIO : has
  VOICE_PROFILE ||--o{ VOICE_RECIPE : uses
  VOICE_PROFILE ||--o{ SPEAKER_IMAGE : displays

  SCRIPT ||--o{ SCRIPT_SEGMENT : splits_into
  SCRIPT_SEGMENT }o--|| VOICE_PROFILE : assigned_to

  GENERATION_JOB ||--o{ AUDIO_ARTIFACT : produces
  GENERATION_JOB ||--o{ VIDEO_ARTIFACT : produces
  GENERATION_JOB ||--o{ JOB_LOG : records

  PREVIEW_STATE }o--|| BACKGROUND_ASSET : selects
  PREVIEW_STATE }o--o{ SPEAKER_IMAGE : places
```

---

## 8. Optimization Strategy

```mermaid
flowchart TD
  A[Optimization Goal] --> B[Accuracy]
  A --> C[Speed]
  A --> D[Repeatability]

  B --> B1[Validate Reference Audio]
  B --> B2[Calibrate Voice Recipes]
  B --> B3[Compare Preview WAV vs Segment WAV vs Final Audio]

  C --> C1[Cache Voice Segments]
  C --> C2[Avoid Reloading Models Per Segment]
  C --> C3[Reuse Preview State]
  C --> C4[Render Only Changed Parts]

  D --> D1[Reusable Voice Profiles]
  D --> D2[Reusable Backgrounds]
  D --> D3[Reusable Layout Presets]
  D --> D4[Reusable Metadata Templates]
```
