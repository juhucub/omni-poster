import { test as base, expect } from '@playwright/test';
import type { Page, Route, TestInfo } from '@playwright/test';

const allowedOrigins = new Set([
  'http://localhost:3000',
  'http://127.0.0.1:3000',
  'ws://localhost:3000',
  'ws://127.0.0.1:3000',
]);

const allowedSchemes = ['about:', 'data:', 'blob:'];

const isAllowedBrowserUrl = (rawUrl: string) => {
  if (allowedSchemes.some((scheme) => rawUrl.startsWith(scheme))) {
    return true;
  }

  try {
    const parsed = new URL(rawUrl);
    return allowedOrigins.has(parsed.origin);
  } catch {
    return false;
  }
};

const blockUnexpectedRequest = async (route: Route, blockedUrls: string[]) => {
  const url = route.request().url();
  if (isAllowedBrowserUrl(url)) {
    await route.continue();
    return;
  }

  blockedUrls.push(url);
  console.error(`[localhost-only] blocked browser request: ${url}`);
  await route.abort('blockedbyclient');
};

const attachBlockedUrls = async (testInfo: TestInfo, blockedUrls: string[]) => {
  await testInfo.attach('localhost-only-blocked-requests', {
    body: blockedUrls.length ? blockedUrls.join('\n') : 'none',
    contentType: 'text/plain',
  });
};

export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use, testInfo) => {
    const blockedUrls: string[] = [];

    await page.route('**/*', async (route) => {
      await blockUnexpectedRequest(route, blockedUrls);
    });

    await page.routeWebSocket('**/*', async (webSocket) => {
      const url = webSocket.url();
      if (isAllowedBrowserUrl(url)) {
        webSocket.connectToServer();
        return;
      }
      blockedUrls.push(url);
      console.error(`[localhost-only] blocked browser websocket: ${url}`);
      await webSocket.close({ code: 1008, reason: 'Blocked by localhost-only fixture' });
    });

    await use(page);
    await attachBlockedUrls(testInfo, blockedUrls);

    expect(blockedUrls, `Blocked non-localhost browser request(s):\n${blockedUrls.join('\n')}`).toEqual([]);
  },
});

export { expect };
