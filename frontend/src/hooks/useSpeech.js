import { useCallback, useEffect, useRef, useState } from 'react'

// Browser speech (Web Speech API). Chrome/Edge on Android and desktop support recognition;
// other browsers fall back to typing.
const Recognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

export const SPEECH_LOCALES = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }

export const speechInputSupported = Boolean(Recognition)

/** Push-to-talk speech recognition. `onFinal` receives the recognised text. */
export function useSpeechInput(language, onFinal) {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recognition = useRef(null)
  const finalHandler = useRef(onFinal)

  useEffect(() => {
    finalHandler.current = onFinal
  }, [onFinal])

  const stop = useCallback(() => recognition.current?.stop(), [])

  const start = useCallback(() => {
    if (!Recognition) return
    const rec = new Recognition()
    rec.lang = SPEECH_LOCALES[language] ?? 'en-IN'
    rec.interimResults = true
    rec.continuous = false
    let finalText = ''
    rec.onresult = (event) => {
      let partial = ''
      for (const result of event.results) {
        if (result.isFinal) finalText += result[0].transcript
        else partial += result[0].transcript
      }
      setInterim(partial || finalText)
    }
    rec.onerror = (event) => {
      // not-allowed: mic permission denied; network/audio-capture: device or service problem
      if (event.error !== 'no-speech' && event.error !== 'aborted') setError(event.error)
    }
    rec.onend = () => {
      setListening(false)
      setInterim('')
      if (finalText.trim()) finalHandler.current(finalText.trim())
    }
    setError('')
    recognition.current = rec
    rec.start()
    setListening(true)
  }, [language])

  useEffect(() => () => recognition.current?.abort(), [])

  return { supported: speechInputSupported, listening, interim, error, start, stop }
}

/** Read text aloud in the session language, if the device has a suitable voice. */
export function speak(text, language) {
  if (!('speechSynthesis' in window) || !text) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  const locale = SPEECH_LOCALES[language] ?? 'en-IN'
  const voices = window.speechSynthesis.getVoices()
  // Marathi voices are rare; a Hindi voice reads Devanagari acceptably
  const voice =
    voices.find((v) => v.lang === locale) ??
    voices.find((v) => v.lang.startsWith(locale.slice(0, 2))) ??
    (language === 'mr' ? voices.find((v) => v.lang.startsWith('hi')) : undefined)
  if (voice) utterance.voice = voice
  utterance.lang = voice?.lang ?? locale
  window.speechSynthesis.speak(utterance)
}

export function stopSpeaking() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}
