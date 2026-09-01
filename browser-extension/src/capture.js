const MAX_CAPTURE_CHARS = 2_000_000;
const MAX_IMAGES = 1000;
const MAX_LINKS = 2000;

export async function captureCurrentPage() {
  const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  if (!tab?.id) {
    throw browserError('NO_ACTIVE_TAB', '没有可抓取的当前标签页');
  }
  if (!isSupportedPageURL(tab.url || '')) {
    throw browserError('UNSUPPORTED_PAGE', '浏览器内部页、商店页和扩展页不支持抓取');
  }
  try {
    const [execution] = await chrome.scripting.executeScript({
      target: {tabId: tab.id, allFrames: false},
      func: extractPageInTab,
      args: [MAX_CAPTURE_CHARS, MAX_IMAGES, MAX_LINKS],
    });
    if (!execution?.result) {
      throw browserError('CAPTURE_EMPTY', '页面没有返回可抓取内容');
    }
    return {
      untrusted_browser_content: true,
      ...execution.result,
    };
  } catch (error) {
    if (error?.code) throw error;
    throw browserError(
      'SITE_PERMISSION_REQUIRED',
      '当前站点尚未授权。请点击 LazyMind Browser 扩展并授权当前站点。',
      {cause: String(error?.message || error)},
    );
  }
}

export function isSupportedPageURL(rawURL) {
  try {
    const parsed = new URL(rawURL);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function originPattern(rawURL) {
  const parsed = new URL(rawURL);
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw browserError('UNSUPPORTED_PAGE', '当前页面不支持站点授权');
  }
  return `${parsed.origin}/*`;
}

function browserError(code, message, details) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  return error;
}

async function extractPageInTab(maxChars, maxImages, maxLinks) {
  const cleanText = (value) => String(value || '')
    .replace(/\u0000/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const limitations = [];
  const body = document.body;
  let visibleText = cleanText(body?.innerText || '');

  for (const frame of document.querySelectorAll('iframe')) {
    try {
      if (!frame.contentDocument) {
        limitations.push('cross_origin_iframe_not_captured');
        continue;
      }
      const frameText = cleanText(frame.contentDocument.body?.innerText || '');
      if (frameText) visibleText += `\n\n${frameText}`;
    } catch {
      limitations.push('cross_origin_iframe_not_captured');
    }
  }

  const articleCandidate = document.querySelector(
    'article, main, [role="main"], [itemprop="articleBody"]',
  );
  let articleText = cleanText(articleCandidate?.innerText || '');
  if (!articleText && body) {
    const clone = body.cloneNode(true);
    clone.querySelectorAll(
      'script, style, noscript, template, nav, footer, header, aside, form',
    ).forEach((node) => node.remove());
    articleText = cleanText(clone.textContent || '');
  }

  const imagesAll = Array.from(document.images);
  const linksAll = Array.from(document.querySelectorAll('a[href]'));
  if (imagesAll.length > maxImages) limitations.push('images_truncated');
  if (linksAll.length > maxLinks) limitations.push('links_truncated');

  const totalChars = visibleText.length;
  const encoder = new TextEncoder();
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(visibleText));
  const sha256 = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
  const truncated = totalChars > maxChars;
  if (truncated) {
    limitations.push('visible_text_truncated_at_transport_limit');
    visibleText = visibleText.slice(0, maxChars);
  }
  if (articleText.length > maxChars) {
    limitations.push('article_text_truncated_at_transport_limit');
    articleText = articleText.slice(0, maxChars);
  }

  return {
    schema_version: '1',
    capture_id: crypto.randomUUID(),
    tab: {
      url: location.href,
      origin: location.origin,
      title: document.title,
      captured_at: new Date().toISOString(),
    },
    content: {
      article_text: articleText,
      visible_text: visibleText,
      lang: document.documentElement.lang || navigator.language || '',
      total_chars: totalChars,
      returned_chars: visibleText.length,
      truncated,
      sha256,
    },
    images: imagesAll.slice(0, maxImages).map((image) => ({
      alt: cleanText(image.alt),
      src: image.currentSrc || image.src || '',
    })),
    links: linksAll.slice(0, maxLinks).map((link) => ({
      text: cleanText(link.innerText || link.getAttribute('aria-label') || ''),
      href: link.href,
    })),
    limitations: Array.from(new Set(limitations)),
  };
}
