import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

import FormatBrowser from './FormatBrowser';
import { FALLBACK_CONTENT_FORMATS, findFormat } from './formatBrowserData';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe('FormatBrowser', () => {
  it('renders all seven reusable format presets', () => {
    const container = document.createElement('div');
    const root = createRoot(container);

    act(() => {
      root.render(
        <FormatBrowser
          formats={FALLBACK_CONTENT_FORMATS}
          selectedFormatId="educational_short"
          onSelect={() => undefined}
        />
      );
    });

    expect(FALLBACK_CONTENT_FORMATS).toHaveLength(7);
    for (const format of FALLBACK_CONTENT_FORMATS) {
      expect(container.textContent).toContain(format.display_name);
      expect(container.textContent).toContain(format.best_use_case);
    }

    act(() => {
      root.unmount();
    });
  });

  it('calls onSelect with the chosen format', () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    const selected = [];

    act(() => {
      root.render(
        <FormatBrowser
          formats={FALLBACK_CONTENT_FORMATS}
          selectedFormatId="educational_short"
          onSelect={(format) => selected.push(format.id)}
        />
      );
    });

    const podcastButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Podcast Clip')
    );
    expect(podcastButton).toBeTruthy();

    act(() => {
      podcastButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(selected).toEqual(['podcast_clip']);
    expect(findFormat(FALLBACK_CONTENT_FORMATS, 'podcast_clip')?.display_name).toBe('Podcast Clip');

    act(() => {
      root.unmount();
    });
  });
});
