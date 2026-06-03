jest.mock('lucide-react', () => ({
  AlertTriangle: () => null,
  ArrowRight: () => null,
  CheckCircle2: () => null,
  ChevronDown: () => null,
  FileUp: () => null,
  PencilLine: () => null,
  RefreshCw: () => null,
  Save: () => null,
  Sparkles: () => null,
}));

import {
  deriveScriptViewModel,
  getSafeScriptDiagnostics,
} from './ProductionScriptSection';

const now = '2026-06-02T12:00:00.000Z';

const baseInput = {
  script: null,
  scriptDraft: '',
  scriptLines: [],
  generatedScript: null,
  isGenerating: false,
  scriptFailure: null,
  validationWarnings: [],
  renderReadiness: null,
  targetDurationSeconds: 45,
  generatedScriptHasHardWarnings: false,
};

const scriptRevision = {
  id: 3,
  parent_revision_id: null,
  raw_text: '<Host> Dogs celebrate every time you come home.\n<Guest> Cats are emotionally efficient.',
  parsed_lines: [
    {
      speaker: 'Host',
      text: 'Dogs celebrate every time you come home.',
      caption_text: 'Dogs celebrate every time you come home.',
      section: 'hook',
      line_id: 'line_001',
      order: 0,
    },
    {
      speaker: 'Guest',
      text: 'Cats are emotionally efficient.',
      caption_text: 'Cats are emotionally efficient.',
      section: 'body',
      line_id: 'line_002',
      order: 1,
    },
  ],
  characters: ['Host', 'Guest'],
  generated_script: null,
  source: 'manual',
  generation_provider: null,
  is_current: true,
  created_at: now,
};

const generatedScript = {
  id: 'gen_1',
  idea: 'Dogs vs cats',
  content_format_id: 'debate',
  platform: 'tiktok',
  target_duration_sec: 45,
  tone: 'sharp',
  audience: 'pet owners',
  speakers: [
    { id: 'host', label: 'Host', role: 'host', voice_profile_id: null, speaker_image_id: null },
    { id: 'guest', label: 'Guest', role: 'guest', voice_profile_id: null, speaker_image_id: null },
  ],
  lines: [
    {
      id: 'line_001',
      section: 'hook',
      speaker_id: 'host',
      speaker_label: 'Host',
      text: 'Dogs celebrate every time you come home.',
      caption_text: 'Dogs celebrate every time you come home.',
      estimated_duration_sec: 22,
    },
    {
      id: 'line_002',
      section: 'body',
      speaker_id: 'guest',
      speaker_label: 'Guest',
      text: 'Cats are emotionally efficient.',
      caption_text: 'Cats are emotionally efficient.',
      estimated_duration_sec: 30,
    },
  ],
  sections: ['hook', 'body'],
  caption_blocks: [],
  metadata_suggestions: {},
  total_estimated_duration_sec: 52,
  provider_metadata: {},
  validation_warnings: [],
};

describe('deriveScriptViewModel', () => {
  it('derives the empty state from missing script data', () => {
    const viewModel = deriveScriptViewModel(baseInput);

    expect(viewModel.state).toBe('empty');
    expect(viewModel.canProceed).toBe(false);
    expect(viewModel.lineCount).toBe(0);
    expect(viewModel.heroTitle).toBe('Generate the script.');
  });

  it('derives generating with pending timeline rows from a real pending request', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      isGenerating: true,
      scriptDraft: '<Host> Dogs celebrate every time you come home.',
      scriptLines: [scriptRevision.parsed_lines[0]],
    });

    expect(viewModel.state).toBe('generating');
    expect(viewModel.canProceed).toBe(false);
    expect(viewModel.timelineLines.some((line) => line.status === 'pending')).toBe(true);
  });

  it('derives generatedAccepted from accepted stable script lines', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      script: scriptRevision,
      scriptDraft: scriptRevision.raw_text,
      scriptLines: scriptRevision.parsed_lines,
    });

    expect(viewModel.state).toBe('generatedAccepted');
    expect(viewModel.canProceed).toBe(true);
    expect(viewModel.missingStableLineIds).toBe(0);
    expect(viewModel.captionReady).toBe(true);
  });

  it('derives generatedAccepted and budget warnings from a generated draft ready for acceptance', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      generatedScript,
      scriptDraft: scriptRevision.raw_text,
      scriptLines: [],
    });

    expect(viewModel.state).toBe('generatedAccepted');
    expect(viewModel.canAccept).toBe(true);
    expect(viewModel.warnings.join(' ')).toContain('exceeds 45s target');
  });

  it('derives failed from operation errors and sanitizes failure display text', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      scriptDraft: scriptRevision.raw_text,
      scriptLines: scriptRevision.parsed_lines,
      scriptFailure: 'Parser error on /Users/jacob/private/script.py: access_token=supersecret',
    });

    expect(viewModel.state).toBe('failed');
    expect(viewModel.failureReason).toContain('[path]');
    expect(viewModel.failureReason).not.toContain('supersecret');
  });

  it('adds warnings when manual lines lack stable IDs', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      scriptDraft: '<Host> Manual line',
      scriptLines: [{ speaker: 'Host', text: 'Manual line', order: 0 }],
    });

    expect(viewModel.state).toBe('generatedAccepted');
    expect(viewModel.missingStableLineIds).toBe(1);
    expect(viewModel.warnings.join(' ')).toContain('missing stable IDs');
  });
});

describe('getSafeScriptDiagnostics', () => {
  it('returns scoped diagnostics without leaking paths, tokens, or raw stack traces', () => {
    const viewModel = deriveScriptViewModel({
      ...baseInput,
      generatedScript,
      validationWarnings: ['access_token=supersecret near /Users/jacob/project/file.ts'],
    });
    const rows = getSafeScriptDiagnostics({
      providerMetadata: {
        provider_name: 'ollama',
        model: 'llama',
        fallback_used: true,
        fallback_reason: null,
        generation_duration_ms: 300,
        repair_attempted: true,
        prompt_char_count: 10,
        response_char_count: 20,
        timeout_seconds: 60,
        num_predict: null,
        num_ctx: null,
        ollama_total_duration: null,
        ollama_load_duration: null,
        ollama_prompt_eval_count: null,
        ollama_eval_count: null,
        failure_type: 'invalid_json at /Users/jacob/project/provider.py access_token=supersecret',
        diagnostics: {},
      },
      providerLabel: 'Ollama',
      viewModel,
      warnings: ['access_token=supersecret near /Users/jacob/project/file.ts'],
      renderReadiness: null,
    });

    const text = JSON.stringify(rows);
    expect(text).toContain('Ollama');
    expect(text).toContain('[path]');
    expect(text).not.toContain('/Users/jacob');
    expect(text).not.toContain('supersecret');
    expect(text).not.toContain('provider.py');
  });
});
