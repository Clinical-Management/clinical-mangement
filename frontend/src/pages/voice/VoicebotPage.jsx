import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  correctHistory,
  finishHistory,
  getPatientView,
  sendHistoryMessage,
  setHistoryLanguage,
  submitHistory,
} from '../../api/history'
import Logo from '../../components/Logo'
import { speak, stopSpeaking, useSpeechInput } from '../../hooks/useSpeech'

// Interface text in the patient's language. NOTE: have Hindi/Marathi reviewed by native speakers.
const UI = {
  en: {
    speak: 'Tap to speak', listening: 'Listening... tap to stop', type: 'Type your answer', send: 'Send',
    typeInstead: 'Type instead', speakInstead: 'Speak instead', done: "I'm done",
    reviewTitle: 'Please check your summary', looksRight: 'Looks right, send to doctor', fix: 'Correct something',
    fixHint: 'Tell us what to change', thanks: 'Thank you! Your history has been sent to the doctor. Please wait to be called.',
    urgentTitle: 'Please get help now', mute: 'Mute', unmute: 'Read aloud', thinking: 'One moment...',
    aiDown: "The assistant isn't available right now. Please tell the front desk; they will note your history.",
    micError: "The microphone isn't working. Please type your answer instead.", language: 'Language', auto: 'Auto',
  },
  hi: {
    speak: 'बोलने के लिए दबाएं', listening: 'सुन रहे हैं... रोकने के लिए दबाएं', type: 'अपना जवाब लिखें', send: 'भेजें',
    typeInstead: 'लिखकर बताएं', speakInstead: 'बोलकर बताएं', done: 'बस, हो गया',
    reviewTitle: 'कृपया अपना सारांश देखें', looksRight: 'सही है, डॉक्टर को भेजें', fix: 'कुछ बदलना है',
    fixHint: 'बताएं क्या बदलना है', thanks: 'धन्यवाद! आपकी जानकारी डॉक्टर को भेज दी गई है। कृपया अपनी बारी का इंतज़ार करें।',
    urgentTitle: 'कृपया तुरंत मदद लें', mute: 'आवाज़ बंद', unmute: 'पढ़कर सुनाएं', thinking: 'एक पल...',
    aiDown: 'सहायक अभी उपलब्ध नहीं है। कृपया रिसेप्शन पर बताएं, वे आपकी जानकारी लिख लेंगे।',
    micError: 'माइक्रोफ़ोन काम नहीं कर रहा। कृपया लिखकर जवाब दें।', language: 'भाषा', auto: 'अपने आप',
  },
  mr: {
    speak: 'बोलण्यासाठी दाबा', listening: 'ऐकत आहे... थांबवण्यासाठी दाबा', type: 'तुमचे उत्तर लिहा', send: 'पाठवा',
    typeInstead: 'लिहून सांगा', speakInstead: 'बोलून सांगा', done: 'झाले',
    reviewTitle: 'कृपया तुमचा सारांश तपासा', looksRight: 'बरोबर आहे, डॉक्टरांना पाठवा', fix: 'काही दुरुस्त करायचे आहे',
    fixHint: 'काय बदलायचे ते सांगा', thanks: 'धन्यवाद! तुमची माहिती डॉक्टरांना पाठवली आहे. कृपया तुमच्या वेळेची वाट पहा.',
    urgentTitle: 'कृपया लगेच मदत घ्या', mute: 'आवाज बंद', unmute: 'वाचून दाखवा', thinking: 'एक क्षण...',
    aiDown: 'सहाय्यक सध्या उपलब्ध नाही. कृपया रिसेप्शनला सांगा, ते तुमची माहिती लिहून घेतील.',
    micError: 'मायक्रोफोन काम करत नाही. कृपया उत्तर लिहून द्या.', language: 'भाषा', auto: 'आपोआप',
  },
}

const LANGUAGE_OPTIONS = [
  ['auto', null],
  ['en', 'English'],
  ['hi', 'हिन्दी'],
  ['mr', 'मराठी'],
]

function MicButton({ speech, label, listeningLabel, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={speech.listening ? speech.stop : speech.start}
      className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-full text-white shadow-lg transition disabled:opacity-50 ${
        speech.listening ? 'animate-pulse bg-red-600' : 'bg-brand-gradient hover:brightness-110'
      }`}
      aria-label={speech.listening ? listeningLabel : label}
    >
      <svg viewBox="0 0 24 24" className="h-9 w-9" fill="currentColor" aria-hidden="true">
        <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
      </svg>
    </button>
  )
}

/** Answer box used for both interview answers and summary corrections: voice and/or typing. */
function Composer({ t, language, voiceFirst, busy, onSend, placeholder }) {
  const [text, setText] = useState('')
  const [typing, setTyping] = useState(!voiceFirst)
  const speech = useSpeechInput(language, (spoken) => onSend(spoken, 'voice'))
  const showMic = voiceFirst && speech.supported && !typing && !speech.error

  const submit = (e) => {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim(), 'text')
    setText('')
  }

  return (
    <div className="space-y-2">
      {speech.error && <p className="text-center text-sm text-amber-700">{t.micError}</p>}
      {showMic ? (
        <div className="flex flex-col items-center gap-2">
          <MicButton speech={speech} label={t.speak} listeningLabel={t.listening} disabled={busy} />
          <p className="min-h-5 text-center text-sm text-slate-600">
            {speech.interim || (speech.listening ? t.listening : busy ? t.thinking : t.speak)}
          </p>
          <button type="button" className="text-sm text-brand-600 underline" onClick={() => setTyping(true)}>
            {t.typeInstead}
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex gap-2">
          <input
            autoFocus
            className="min-w-0 flex-1 rounded-full border border-slate-300 px-4 py-3 text-base focus:border-accent-600 focus:outline-none"
            placeholder={placeholder ?? t.type}
            value={text}
            disabled={busy}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="rounded-full bg-brand-gradient px-5 font-medium text-white disabled:opacity-60" disabled={busy || !text.trim()}>
            {t.send}
          </button>
          {voiceFirst && speech.supported && !speech.error && (
            <button type="button" className="text-sm text-brand-600 underline" onClick={() => setTyping(false)}>
              {t.speakInstead}
            </button>
          )}
        </form>
      )}
    </div>
  )
}

export default function VoicebotPage() {
  const { sessionId } = useParams()
  const [params] = useSearchParams()
  const token = params.get('token')

  const [session, setSession] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [muted, setMuted] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const bottom = useRef(null)
  const lastSpoken = useRef(null)

  const lang = session?.language ?? 'en'
  const t = UI[lang]
  const voiceFirst = session?.mode === 'voice'

  const run = useCallback(async (action) => {
    setBusy(true)
    setError('')
    try {
      setSession(await action())
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(detail?.code === 'ai_unavailable' ? 'ai' : (typeof detail === 'string' ? detail : detail?.message) || 'error')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    getPatientView(sessionId, token)
      .then(setSession)
      .catch((err) => setError(err.response?.data?.detail || 'This link is not valid.'))
  }, [sessionId, token])

  // Scroll to the newest message and read assistant turns aloud in voice mode
  const last = session?.transcript.at(-1)
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
    if (!last || last.role !== 'assistant' || lastSpoken.current === last.at) return
    lastSpoken.current = last.at
    if (voiceFirst && !muted) speak(last.text, last.language)
  }, [last, voiceFirst, muted])

  useEffect(() => stopSpeaking, [])

  if (!session) {
    return (
      <div className="grid min-h-screen place-items-center bg-brand-gradient p-6 text-center text-white">
        {error ? <p className="max-w-sm">{error}</p> : <p>Loading...</p>}
      </div>
    )
  }

  const send = (text, input) => {
    stopSpeaking()
    return run(() =>
      correcting
        ? correctHistory(sessionId, token, text, input).finally(() => setCorrecting(false))
        : sendHistoryMessage(sessionId, token, text, input),
    )
  }

  if (session.status === 'escalated') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-red-700 p-6 text-center text-white">
        <svg viewBox="0 0 24 24" className="h-16 w-16" fill="currentColor" aria-hidden="true">
          <path d="M12 2 1 21h22L12 2Zm1 15h-2v-2h2v2Zm0-4h-2V9h2v4Z" />
        </svg>
        <h1 className="text-3xl font-bold">{t.urgentTitle}</h1>
        <p className="max-w-lg text-xl leading-relaxed">{session.transcript.at(-1)?.text}</p>
      </div>
    )
  }

  if (session.status === 'submitted') {
    return (
      <div className="grid min-h-screen place-items-center bg-brand-gradient p-6 text-center text-white">
        <div className="space-y-4">
          <Logo light />
          <p className="max-w-md text-xl">{t.thanks}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-dvh flex-col bg-slate-50">
      <header className="flex items-center justify-between gap-2 bg-brand-gradient px-4 py-3 text-white">
        <Logo light compact />
        <div className="flex items-center gap-2 text-sm">
          <select
            aria-label={t.language}
            className="rounded-md bg-white/15 px-2 py-1.5 text-white [&>option]:text-slate-800"
            value={session.language_mode === 'auto' ? 'auto' : session.language}
            onChange={(e) => run(() => setHistoryLanguage(sessionId, token, e.target.value))}
          >
            {LANGUAGE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label ?? t.auto}
              </option>
            ))}
          </select>
          {voiceFirst && (
            <button
              className="rounded-md bg-white/15 px-2 py-1.5"
              onClick={() => {
                stopSpeaking()
                setMuted(!muted)
              }}
            >
              {muted ? t.unmute : t.mute}
            </button>
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-2xl space-y-3">
          {session.transcript.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'patient' ? 'justify-end' : 'justify-start'}`}>
              <p
                className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2.5 text-base leading-relaxed ${
                  m.role === 'patient' ? 'bg-brand-gradient text-white' : 'border border-slate-200 bg-white text-slate-800'
                }`}
              >
                {m.text}
              </p>
            </div>
          ))}

          {session.status === 'review' && (
            <section className="rounded-2xl border-2 border-accent-600 bg-white p-5">
              <h2 className="mb-2 text-lg font-semibold text-brand-700">{t.reviewTitle}</h2>
              <p className="whitespace-pre-line text-lg leading-relaxed text-slate-800">{session.patient_summary}</p>
              {voiceFirst && (
                <button className="mt-2 text-sm text-brand-600 underline" onClick={() => speak(session.patient_summary, lang)}>
                  {t.unmute}
                </button>
              )}
            </section>
          )}
          <div ref={bottom} />
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-4">
        <div className="mx-auto max-w-2xl space-y-3">
          {error && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-center text-sm text-amber-800">
              {error === 'ai' ? t.aiDown : error}
            </p>
          )}

          {session.status === 'review' && !correcting ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                className="flex-1 rounded-full bg-brand-gradient py-3.5 text-lg font-semibold text-white disabled:opacity-60"
                disabled={busy}
                onClick={() => run(() => submitHistory(sessionId, token))}
              >
                {t.looksRight}
              </button>
              <button
                className="flex-1 rounded-full border border-brand-200 py-3.5 text-lg font-medium text-brand-700"
                disabled={busy}
                onClick={() => setCorrecting(true)}
              >
                {t.fix}
              </button>
            </div>
          ) : (
            <>
              <Composer
                key={`${lang}-${correcting}`}
                t={t}
                language={lang}
                voiceFirst={voiceFirst}
                busy={busy}
                onSend={send}
                placeholder={correcting ? t.fixHint : undefined}
              />
              {session.status === 'in_progress' && session.transcript.length > 2 && (
                <button
                  className="w-full text-center text-sm text-slate-500 underline"
                  disabled={busy}
                  onClick={() => run(() => finishHistory(sessionId, token))}
                >
                  {t.done}
                </button>
              )}
            </>
          )}
        </div>
      </footer>
    </div>
  )
}
