const ALLOWED_TAGS = new Set(['P', 'DIV', 'BR', 'SPAN', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'UL', 'OL', 'LI', 'FONT', 'IMG'])
const SAFE_IMAGE = /^data:image\/(?:png|jpe?g|gif|webp);base64,[a-z0-9+/=\s]+$/i

export function sanitizeRichText(value: string | null | undefined) {
  if (!value) return ''
  const document = new DOMParser().parseFromString(value, 'text/html')
  for (const element of [...document.body.querySelectorAll('*')]) {
    if (!ALLOWED_TAGS.has(element.tagName)) {
      if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED'].includes(element.tagName)) element.remove()
      else element.replaceWith(...element.childNodes)
      continue
    }
    const color = element instanceof HTMLElement ? element.style.color : ''
    const fontColor = element.getAttribute('color') || ''
    const src = element.tagName === 'IMG' ? element.getAttribute('src') || '' : ''
    const alt = element.tagName === 'IMG' ? element.getAttribute('alt') || '' : ''
    for (const attribute of [...element.attributes]) element.removeAttribute(attribute.name)
    if (element.tagName === 'IMG') {
      if (!SAFE_IMAGE.test(src)) { element.remove(); continue }
      element.setAttribute('src', src)
      element.setAttribute('alt', alt.slice(0, 200))
    } else if (color || fontColor) {
      element.setAttribute('style', `color:${color || fontColor}`)
    }
  }
  return document.body.innerHTML
}

export function hasRichContent(value: string | null | undefined) {
  if (!value) return false
  const document = new DOMParser().parseFromString(value, 'text/html')
  return Boolean(document.body.textContent?.trim() || document.body.querySelector('img'))
}
