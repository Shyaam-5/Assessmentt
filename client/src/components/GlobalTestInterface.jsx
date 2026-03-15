import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Clock, ChevronLeft, ChevronRight, Send, CheckCircle, Sparkles, Play, FileText, Code, Database, Lightbulb, Target, ChevronDown, ChevronUp } from 'lucide-react'
import Editor from '@monaco-editor/react'
import axios from 'axios'
import CodeOutputPreview from '@/components/CodeOutputPreview'
import SQLValidator from '@/components/SQLValidator'
import SQLVisualizer from '@/components/SQLVisualizer'
import SQLDebugger from '@/components/SQLDebugger'
import proctoringSocketAdapter from '@/services/proctoringSocketAdapter'
import socketService from '@/services/socketService'
import { useTabTracking, useFullscreen, useCopyPasteBlock, useMultiMonitorDetection, useCamera, useObjectDetection, useFaceDetection, useBehaviorTracking, useAgentTermination, MAX_VIOLATIONS } from '@/hooks/useProctoring'
import { API_BASE, LANGUAGE_CONFIG, SECTION_META, seededShuffle, generateSeed, cleanCode } from './global-test/constants'
import TestSidebar from './global-test/TestSidebar'
import { ResultOverlay, SubmittingOverlay, CameraSetupOverlay, TerminationOverlay, CameraBlockedOverlay, WarningBanner } from './global-test/Overlays'

export default function GlobalTestInterface({ test, user, onClose, onComplete }) {
    // ── Core State ──
    const [answers, setAnswers] = useState({})
    const answersRef = useRef({})
    const [selectedLanguages, setSelectedLanguages] = useState({})
    const [currentSectionIndex, setCurrentSectionIndex] = useState(0)
    const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
    const [timeLeft, setTimeLeft] = useState((test.duration || 120) * 60)
    const timeLeftRef = useRef((test.duration || 120) * 60)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const submittedRef = useRef(false)
    const terminatedRef = useRef(false)
    const [showResult, setShowResult] = useState(false)
    const [result, setResult] = useState(null)
    const [showWarning, setShowWarning] = useState(false)
    const [warningMessage, setWarningMessage] = useState('')
    const [showCameraSetup, setShowCameraSetup] = useState(false)

    // Code editor state
    const [consoleOutput, setConsoleOutput] = useState({})
    const [customInputs, setCustomInputs] = useState({})
    const [activeTab, setActiveTab] = useState({})
    const [testResults, setTestResults] = useState({})
    const [isRunning, setIsRunning] = useState(false)
    const [isConsoleOpen, setIsConsoleOpen] = useState(false)
    const [consoleHeight, setConsoleHeight] = useState(250)
    const isResizingRef = useRef(false)
    const consoleResizeRef = useRef(null)
    const [hint, setHint] = useState('')
    const [loadingHint, setLoadingHint] = useState(false)
    const [sqlTool, setSqlTool] = useState('validator')

    // ── Proctoring Config ──
    const proctoring = test.proctoring || {}
    const mode = proctoring.mode || 'standard'
    const isEnhanced = mode === 'enhanced' || mode === 'ai_proctored'
    const isAI = mode === 'ai_proctored'
    const maxTabSwitches = proctoring.maxTabSwitches || test.maxTabSwitches || 3

    // ── Proctoring Hooks ──
    const onViolation = useCallback((type, count) => {
        setShowWarning(true)
        setWarningMessage(`⚠️ ${type === 'tab_switch' ? 'Tab switch' : 'Window blur'} detected! (${count}/${maxTabSwitches})`)
        setTimeout(() => setShowWarning(false), 3000)
        // Emit to live monitoring dashboard
        socketService.emitProctoringViolation(
            user?.id, user?.name || user?.email, type,
            count >= maxTabSwitches ? 'critical' : 'warning', null
        )
        // Log to backend proctoring table for Proctor Agent analysis
        try {
            fetch(`${API_BASE}/global-tests/${test.id}/log-proctoring`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sessionId: behaviorSessionId.current,
                    userId: user?.id,
                    eventType: type,
                    severity: count >= maxTabSwitches ? 'critical' : 'medium',
                    details: { count, maxTabSwitches },
                }),
            }).catch(() => {})
        } catch {}
        if (isEnhanced && count >= maxTabSwitches) {
            handleSubmit(true)
        }
    }, [maxTabSwitches, isEnhanced, user, test.id])

    const { tabSwitches, tabSwitchesRef } = useTabTracking(isEnhanced && proctoring.trackTabSwitches, maxTabSwitches, onViolation)
    useFullscreen(isEnhanced && proctoring.enforceFullscreen, submittedRef)
    const { copyPasteAttempts, copyPasteRef } = useCopyPasteBlock(isEnhanced && proctoring.disableCopyPaste)
    const { multipleMonitorCount } = useMultiMonitorDetection(isEnhanced)
    const { videoRef, canvasRef, mediaStream, videoEnabled, audioEnabled, cameraBlocked, cameraBlockedCount, cameraAccessDenied, camBlockRef, initializeCamera, stopCamera } = useCamera(isAI && proctoring.enableVideoAudio)
    const { phoneDetectionCount, faceMissingCount, phoneRef, faceRef } = useObjectDetection(isAI && proctoring.detectPhoneUsage, videoRef)
    const { noFaceCount, multipleFaceCount } = useFaceDetection(isAI && proctoring.enableVideoAudio, videoRef)
    const { behaviorSessionId, flushBehaviorEvents } = useBehaviorTracking(isAI, user?.id, test.id)

    const totalViolations = tabSwitches + copyPasteAttempts + cameraBlockedCount + phoneDetectionCount + faceMissingCount + multipleMonitorCount + noFaceCount + multipleFaceCount
    const totalViolationsRef = useRef(0)
    useEffect(() => { totalViolationsRef.current = totalViolations }, [totalViolations])

    const onTerminate = useCallback((data) => {
        if (submittedRef.current) return
        setTimeout(() => {
            handleSubmit(true)
            terminatedRef.current = true
        }, 3000)
    }, [])

    const { agentTerminated, terminateReason } = useAgentTermination(isAI, user?.id, behaviorSessionId.current, onTerminate)

    // Auto-terminate on max violations
    useEffect(() => {
        if (isEnhanced && totalViolations >= MAX_VIOLATIONS && !terminatedRef.current) {
            terminatedRef.current = true
            handleSubmit(true)
        }
    }, [totalViolations, isEnhanced])

    // Log face detection violations to backend
    useEffect(() => {
        if (noFaceCount > 0) {
            fetch(`${API_BASE}/global-tests/${test.id}/log-proctoring`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: behaviorSessionId.current, userId: user?.id, eventType: 'no_face', severity: 'high', details: { count: noFaceCount } }),
            }).catch(() => {})
        }
    }, [noFaceCount])

    useEffect(() => {
        if (multipleFaceCount > 0) {
            socketService.emitProctoringViolation(user?.id, user?.name || user?.email, 'multiple_faces', 'critical', null)
            fetch(`${API_BASE}/global-tests/${test.id}/log-proctoring`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: behaviorSessionId.current, userId: user?.id, eventType: 'multiple_faces', severity: 'critical', details: { count: multipleFaceCount } }),
            }).catch(() => {})
        }
    }, [multipleFaceCount])

    // ── Questions ──
    const allQuestions = useMemo(() => {
        const qs = []
        const bySection = test.questionsBySection || {}
        const sections = test.sectionConfig?.sections || Object.keys(SECTION_META).map(id => ({ id, enabled: true }))
        for (const sec of sections) {
            if (!sec.enabled) continue
            const secQs = bySection[sec.id] || []
            qs.push(...secQs.map(q => ({ ...q, section: sec.id })))
        }
        if (qs.length === 0 && test.questions) qs.push(...test.questions)
        return user?.id && test.id ? seededShuffle(qs, generateSeed(user.id, test.id)) : qs
    }, [test, user])

    const sectionsWithQuestions = useMemo(() => [...new Set(allQuestions.map(q => q.section))], [allQuestions])
    const sectionQuestions = useMemo(() => allQuestions.filter(q => q.section === sectionsWithQuestions[currentSectionIndex]), [allQuestions, sectionsWithQuestions, currentSectionIndex])
    const currentQ = sectionQuestions[currentQuestionIndex]
    const totalQuestions = allQuestions.length

    // Keep answersRef in sync
    useEffect(() => { answersRef.current = answers }, [answers])

    // ── Timer ──
    useEffect(() => {
        const id = setInterval(() => {
            setTimeLeft(t => {
                const next = t - 1
                timeLeftRef.current = next
                if (next <= 0) { handleSubmit(true); clearInterval(id) }
                return next
            })
        }, 1000)
        return () => clearInterval(id)
    }, [])

    // Show camera setup for AI mode
    useEffect(() => {
        if (isAI && proctoring.enableVideoAudio) setShowCameraSetup(true)
    }, [isAI, proctoring.enableVideoAudio])

    // ── Handlers ──
    const handleAnswerSelect = (qId, value) => setAnswers(prev => ({ ...prev, [qId]: value }))
    const handleLanguageChange = (qId, lang) => {
        setSelectedLanguages(prev => ({ ...prev, [qId]: lang }))
        if (!answers[qId]) setAnswers(prev => ({ ...prev, [qId]: LANGUAGE_CONFIG[lang]?.defaultCode || '' }))
    }

    const handleRunCode = async (qId, code, lang) => {
        setIsRunning(true)
        try {
            const res = await axios.post(`${API_BASE}/run`, { code: cleanCode(code), language: lang, input: customInputs[qId] || '' })
            setConsoleOutput(p => ({ ...p, [qId]: res.data.output || res.data.error || 'No output' }))
            if (!isConsoleOpen) setIsConsoleOpen(true)
            setActiveTab(p => ({ ...p, [qId]: 'output' }))
        } catch (e) {
            setConsoleOutput(p => ({ ...p, [qId]: e.response?.data?.error || 'Execution failed' }))
        } finally { setIsRunning(false) }
    }

    const handleGetHint = async () => {
        if (!currentQ) return
        setLoadingHint(true); setHint('')
        try {
            const res = await axios.post(`${API_BASE}/ai/hint`, { question: currentQ.question, language: selectedLanguages[currentQ.id] || 'Python', code: answers[currentQ.id] || '' })
            setHint(res.data.hint || 'No hint available.')
        } catch { setHint('Unable to generate hint.') }
        finally { setLoadingHint(false) }
    }

    const handleSubmit = async (auto = false) => {
        if (isSubmitting || terminatedRef.current) return
        if (!auto && totalQuestions > 0 && Object.keys(answers).length < totalQuestions) {
            if (!window.confirm(`You have ${totalQuestions - Object.keys(answers).length} unanswered. Submit anyway?`)) return
        }
        submittedRef.current = true
        setIsSubmitting(true)
        await flushBehaviorEvents()
        stopCamera()
        if (document.fullscreenElement) { try { await document.exitFullscreen() } catch {} }
        try {
            const timeSpent = (test.duration || 120) * 60 - timeLeftRef.current
            if (user && test) {
                proctoringSocketAdapter.emitSubmissionCompleted(user.id, user.name || user.email, test.id, test.title, null, 'success', Math.round((Object.keys(answersRef.current).length / totalQuestions) * 100))
            }
            const res = await axios.post(`${API_BASE}/global-tests/${test.id}/submit`, {
                studentId: user.id, answers: answersRef.current, selectedLanguages, timeSpent,
                tabSwitches: tabSwitchesRef.current, copyPasteAttempts: copyPasteRef.current,
                cameraBlockedCount: camBlockRef.current, phoneDetectionCount: phoneRef.current,
                faceMissingCount: faceRef.current, totalViolations: totalViolationsRef.current,
                multipleMonitorCount, proctoringEnabled: proctoring.enabled || false,
                behaviorSessionId: behaviorSessionId.current,
            })
            const sub = res.data.submission || res.data
            if (sub) { await new Promise(r => setTimeout(r, 200)); setIsSubmitting(false); onClose(); onComplete?.(sub) }
            else { setIsSubmitting(false); alert('Submitted but no result data. Please refresh.') }
        } catch (e) { setIsSubmitting(false); alert(e.response?.data?.error || 'Submit failed.') }
    }

    const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
    const nextQuestion = () => { if (currentQuestionIndex < sectionQuestions.length - 1) setCurrentQuestionIndex(i => i + 1); else if (currentSectionIndex < sectionsWithQuestions.length - 1) { setCurrentSectionIndex(currentSectionIndex + 1); setCurrentQuestionIndex(0) } }
    const prevQuestion = () => { if (currentQuestionIndex > 0) setCurrentQuestionIndex(i => i - 1); else if (currentSectionIndex > 0) { const prevLen = allQuestions.filter(q => q.section === sectionsWithQuestions[currentSectionIndex - 1]).length; setCurrentSectionIndex(currentSectionIndex - 1); setCurrentQuestionIndex(prevLen - 1) } }

    // ── Result overlay ──
    if (showResult && result) return <ResultOverlay result={result} onClose={onClose} onComplete={onComplete} />
    if (allQuestions.length === 0) return <div style={{ padding: '2rem', textAlign: 'center', color: 'white' }}>No questions available.<button onClick={onClose} style={{ marginLeft: '1rem', padding: '.5rem', cursor: 'pointer' }}>Close</button></div>

    const isSql = currentQ?.questionType === 'sql' || currentQ?.questionType === 'SQL' || currentQ?.language === 'SQL' || currentQ?.type === 'SQL'
    const isCoding = (currentQ?.questionType === 'coding' || currentQ?.type === 'coding' || !!currentQ?.language) && !isSql
    const currentLang = selectedLanguages[currentQ?.id] || (isSql ? 'SQL' : 'Python')
    const codeOrSql = (isCoding || isSql) ? (answers[currentQ?.id] ?? LANGUAGE_CONFIG[currentLang]?.defaultCode ?? '') : ''

    const samples = useMemo(() => {
        if (!currentQ) return { input: 'N/A', output: 'N/A' }
        if (currentQ.sampleInput !== undefined && currentQ.expectedOutput !== undefined) return { input: String(currentQ.sampleInput), output: String(currentQ.expectedOutput) }
        if (currentQ.testCases) {
            if (isSql) {
                let exp = 'N/A'
                if (Array.isArray(currentQ.testCases)) { const f = currentQ.testCases[0]; if (f) exp = f.expected_output || f.expectedOutput || 'N/A' }
                else exp = currentQ.testCases.expectedOutput || 'N/A'
                return { input: 'N/A', output: String(exp) }
            }
            const cases = Array.isArray(currentQ.testCases) ? currentQ.testCases : (currentQ.testCases.cases || [])
            const s = cases.find(c => !c.isHidden) || cases[0]
            if (s) return { input: String(s.input ?? s.sampleInput ?? '(empty)'), output: String(s.expected_output ?? s.expectedOutput ?? '(empty)') }
        }
        return { input: 'N/A', output: 'N/A' }
    }, [currentQ, isSql])

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'linear-gradient(135deg,#0f172a 0%,#1e1b4b 50%,#0f172a 100%)', zIndex: 9999, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <style>{`@keyframes pulse{0%,100%{opacity:.3;transform:scale(1)}50%{opacity:1;transform:scale(1.2)}}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            {showWarning && <WarningBanner message={warningMessage} />}
            {agentTerminated && <TerminationOverlay reason={terminateReason} />}
            {isSubmitting && <SubmittingOverlay />}
            {showCameraSetup && isAI && proctoring.enableVideoAudio && (
                <CameraSetupOverlay proctoring={proctoring} cameraAccessDenied={cameraAccessDenied} onCancel={onClose}
                    onAllow={async () => { const ok = await initializeCamera(); if (ok) setShowCameraSetup(false) }} />
            )}
            {cameraBlocked && isAI && proctoring.detectCameraBlocking && !showCameraSetup && <CameraBlockedOverlay count={cameraBlockedCount} />}

            {/* HEADER */}
            <header style={{ padding: '.75rem 2rem', borderBottom: '1px solid rgba(139,92,246,0.2)', background: 'linear-gradient(180deg,rgba(15,23,42,0.98),rgba(15,23,42,0.95))', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backdropFilter: 'blur(12px)', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', paddingRight: '1.5rem', borderRight: '1px solid rgba(139,92,246,0.2)' }}>
                        <Sparkles size={20} color="#8b5cf6" />
                        <span style={{ fontWeight: 700, fontSize: '1.1rem', background: 'linear-gradient(135deg,#8b5cf6,#6366f1)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Assessment</span>
                    </div>
                    <div style={{ display: 'flex', gap: '.5rem' }}>
                        {sectionsWithQuestions.map((sec, i) => {
                            const Icon = SECTION_META[sec]?.icon || FileText
                            const active = currentSectionIndex === i
                            return <button key={sec} onClick={() => { setCurrentSectionIndex(i); setCurrentQuestionIndex(0) }} style={{ padding: '.5rem 1rem', borderRadius: 10, border: active ? '1px solid rgba(139,92,246,0.5)' : '1px solid transparent', background: active ? 'linear-gradient(135deg,rgba(139,92,246,0.25),rgba(99,102,241,0.15))' : 'transparent', color: active ? '#a78bfa' : '#94a3b8', cursor: 'pointer', fontSize: '.85rem', fontWeight: active ? 600 : 500, display: 'flex', alignItems: 'center', gap: '.5rem', transition: 'all .2s' }}>
                                <Icon size={14} />{SECTION_META[sec]?.label || sec}
                            </button>
                        })}
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
                    {isEnhanced && <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.4rem .75rem', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8 }}><div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', animation: 'pulse 1.5s infinite' }} /><span style={{ fontSize: '.75rem', color: '#fca5a5', fontWeight: 600, letterSpacing: '.5px' }}>PROCTORED</span></div>}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.4rem .75rem', background: 'rgba(139,92,246,0.1)', borderRadius: 8, border: '1px solid rgba(139,92,246,0.2)' }}><CheckCircle size={14} color="#a78bfa" /><span style={{ color: '#a78bfa', fontSize: '.85rem', fontWeight: 600 }}>{Object.keys(answers).length}/{totalQuestions}</span></div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.5rem 1rem', background: timeLeft < 300 ? 'linear-gradient(135deg,rgba(239,68,68,0.2),rgba(220,38,38,0.1))' : 'linear-gradient(135deg,rgba(16,185,129,0.2),rgba(5,150,105,0.1))', borderRadius: 10, border: `1px solid ${timeLeft < 300 ? 'rgba(239,68,68,0.4)' : 'rgba(16,185,129,0.4)'}` }}>
                        <Clock size={16} color={timeLeft < 300 ? '#ef4444' : '#10b981'} />
                        <span style={{ fontVariantNumeric: 'tabular-nums', color: timeLeft < 300 ? '#fca5a5' : '#6ee7b7', fontWeight: 700, fontSize: '1rem' }}>{formatTime(timeLeft)}</span>
                    </div>
                </div>
            </header>

            {/* MAIN */}
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                <TestSidebar proctoring={proctoring} mode={mode} videoRef={videoRef} videoEnabled={videoEnabled} audioEnabled={audioEnabled}
                    tabSwitches={tabSwitches} maxTabSwitches={maxTabSwitches} cameraBlockedCount={cameraBlockedCount}
                    phoneDetectionCount={phoneDetectionCount} faceMissingCount={faceMissingCount} multipleMonitorCount={multipleMonitorCount}
                    totalViolations={totalViolations} sectionQuestions={sectionQuestions} currentQuestionIndex={currentQuestionIndex}
                    setCurrentQuestionIndex={setCurrentQuestionIndex} answers={answers} />

                {(!isCoding && !isSql) ? (
                    /* MCQ LAYOUT */
                    <div style={{ flex: 1, padding: '2rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', maxWidth: 900, margin: '0 auto', width: '100%' }}>
                        <div style={{ marginBottom: '1rem', fontSize: '1rem', color: '#8b5cf6', fontWeight: 600 }}>Question {currentQuestionIndex + 1} OF {sectionQuestions.length}</div>
                        <h2 style={{ fontSize: '1.25rem', color: 'white', lineHeight: 1.6, marginBottom: '2rem' }}>{currentQ?.question}</h2>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            {(currentQ?.options || []).map((opt, i) => (
                                <button key={i} onClick={() => handleAnswerSelect(currentQ.id, opt)} style={{ padding: '1.25rem', textAlign: 'left', borderRadius: 12, border: `1px solid ${answers[currentQ.id] === opt ? '#8b5cf6' : 'rgba(255,255,255,0.1)'}`, background: answers[currentQ.id] === opt ? 'rgba(139,92,246,0.1)' : 'rgba(255,255,255,0.02)', color: 'white', cursor: 'pointer', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '1rem', transition: 'all .2s' }}>
                                    <div style={{ width: 28, height: 28, borderRadius: '50%', border: '1px solid rgba(255,255,255,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '.8rem', background: answers[currentQ.id] === opt ? '#8b5cf6' : 'transparent' }}>{String.fromCharCode(65 + i)}</div>
                                    {opt}
                                </button>
                            ))}
                        </div>
                        <div style={{ marginTop: 'auto', paddingTop: '2rem', display: 'flex', justifyContent: 'space-between' }}>
                            <button onClick={prevQuestion} style={{ padding: '.75rem 1.5rem', borderRadius: 10, background: 'rgba(255,255,255,0.1)', border: 'none', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '.5rem' }}><ChevronLeft size={20} /> Previous</button>
                            <button onClick={nextQuestion} style={{ padding: '.75rem 1.5rem', borderRadius: 10, background: 'linear-gradient(135deg,#3b82f6,#6366f1)', border: 'none', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '.5rem' }}>Next <ChevronRight size={20} /></button>
                        </div>
                    </div>
                ) : (
                    /* CODING/SQL SPLIT LAYOUT */
                    <>
                        <div style={{ width: '35%', minWidth: 350, maxWidth: 450, borderRight: '1px solid #334155', display: 'flex', flexDirection: 'column', background: '#0f172a' }}>
                            <div style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem' }}>
                                        <div style={{ background: 'rgba(139,92,246,0.15)', padding: '.6rem', borderRadius: 10 }}><FileText size={20} color="#8b5cf6" /></div>
                                        <h3 style={{ margin: 0, color: 'white', fontSize: '1.2rem', fontWeight: 700 }}>Problem Statement</h3>
                                    </div>
                                </div>
                                <div style={{ color: '#94a3b8', lineHeight: 1.8, fontSize: '1rem' }}>{currentQ?.question}</div>

                                {isSql && (
                                    <div style={{ marginTop: '2rem' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.75rem', color: '#60a5fa' }}>
                                            <Database size={18} /><span style={{ fontWeight: 700, fontSize: '.9rem', textTransform: 'uppercase', letterSpacing: '.5px' }}>Database Schema</span>
                                        </div>
                                        <div style={{ background: '#0f172a', borderRadius: 12, border: '1px solid rgba(59,130,246,0.3)', overflow: 'hidden' }}>
                                            <pre style={{ margin: 0, padding: '1.25rem', fontSize: '.85rem', color: '#93c5fd', whiteSpace: 'pre-wrap', fontFamily: '"Fira Code",monospace', lineHeight: 1.6 }}>{currentQ.sqlSchema || currentQ.starterCode || 'No schema provided'}</pre>
                                        </div>
                                        {samples.output && samples.output !== 'N/A' && (
                                            <div style={{ marginTop: '1rem' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.75rem', color: '#10b981' }}>
                                                    <Target size={16} /><span style={{ fontWeight: 700, fontSize: '.85rem', textTransform: 'uppercase' }}>Expected Output</span>
                                                </div>
                                                <pre style={{ margin: 0, padding: '1rem', background: 'rgba(16,185,129,0.05)', borderRadius: 12, border: '1px solid rgba(16,185,129,0.2)', fontFamily: '"Fira Code",monospace', fontSize: '.85rem', color: '#4ade80', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{samples.output}</pre>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {!isSql && (
                                    <div style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                        <div><div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.75rem', color: '#94a3b8' }}><FileText size={16} /><span style={{ fontWeight: 700, fontSize: '.85rem', textTransform: 'uppercase' }}>Sample Input</span></div>
                                            <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 10, border: '1px solid #334155', fontFamily: '"Fira Code",monospace', fontSize: '.9rem', color: '#e2e8f0' }}>{samples.input}</div>
                                        </div>
                                        <div><div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.75rem', color: '#10b981' }}><CheckCircle size={16} /><span style={{ fontWeight: 700, fontSize: '.85rem', textTransform: 'uppercase' }}>Expected Output</span></div>
                                            <div style={{ background: 'rgba(16,185,129,0.05)', padding: '1rem', borderRadius: 10, border: '1px solid rgba(16,185,129,0.2)', fontFamily: '"Fira Code",monospace', fontSize: '.9rem', color: '#4ade80' }}>{samples.output}</div>
                                        </div>
                                    </div>
                                )}

                                <div style={{ marginTop: '2rem' }}>
                                    <button onClick={handleGetHint} disabled={loadingHint} style={{ width: '100%', padding: '.75rem', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)', color: '#fbbf24', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '.5rem' }}>
                                        <Lightbulb size={16} /> {loadingHint ? 'Loading...' : 'Get AI Hint'}
                                    </button>
                                    {hint && <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)', color: '#4ade80', borderRadius: 10, fontSize: '.9rem' }}>💡 {hint}</div>}
                                </div>
                            </div>
                        </div>

                        {/* CODE EDITOR */}
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'linear-gradient(180deg,#111827,#0f172a)' }}>
                            <div style={{ padding: '.65rem 1.25rem', borderBottom: '1px solid rgba(59,130,246,0.15)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'linear-gradient(180deg,rgba(31,41,55,0.6),rgba(31,41,55,0.3))' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}><Code size={14} color="#3b82f6" /><div style={{ color: '#94a3b8', fontSize: '.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Language</div></div>
                                    <select value={currentLang} onChange={e => handleLanguageChange(currentQ.id, e.target.value)} disabled={isSql}
                                        style={{ background: 'rgba(30,41,59,0.8)', color: '#f3f4f6', border: '1px solid rgba(59,130,246,0.3)', borderRadius: 8, padding: '.4rem .75rem', cursor: isSql ? 'default' : 'pointer', fontSize: '.85rem', outline: 'none' }}>
                                        {Object.keys(LANGUAGE_CONFIG).map(l => <option key={l} value={l} disabled={isSql && l !== 'SQL'}>{l}</option>)}
                                    </select>
                                </div>
                                {!isSql && <button onClick={() => handleRunCode(currentQ.id, codeOrSql, currentLang)} disabled={isRunning} style={{ padding: '.5rem 1.25rem', background: isRunning ? '#374151' : 'linear-gradient(135deg,#10b981,#059669)', border: 'none', borderRadius: 8, color: 'white', fontWeight: 600, cursor: isRunning ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '.6rem', fontSize: '.9rem' }}>
                                    {isRunning ? 'Running...' : <><Play size={16} fill="white" /> Run Code</>}
                                </button>}
                            </div>
                            <div style={{ flex: 1, position: 'relative', minHeight: 200 }}>
                                <Editor height="100%" defaultLanguage={isSql ? 'sql' : 'python'} language={LANGUAGE_CONFIG[currentLang]?.monacoLang || 'python'} theme="vs-dark" value={codeOrSql}
                                    onChange={v => setAnswers(prev => ({ ...prev, [currentQ.id]: v || '' }))} options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 16 } }} />
                            </div>
                            {/* CONSOLE AREA */}
                            <div ref={consoleResizeRef} style={{ height: !isConsoleOpen ? 40 : `${consoleHeight}px`, minHeight: isConsoleOpen ? 200 : 40, borderTop: '2px solid rgba(59,130,246,0.3)', background: 'linear-gradient(180deg,#0a0f1a,#020617)', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden' }}>
                                {!isConsoleOpen ? (
                                    <div onClick={() => setIsConsoleOpen(true)} style={{ flex: 1, display: 'flex', alignItems: 'center', padding: '0 1.5rem', cursor: 'pointer', background: 'linear-gradient(180deg,#0f172a,#1e293b)', gap: '.75rem', color: '#94a3b8', fontSize: '.85rem', justifyContent: 'space-between' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem' }}><ChevronUp size={16} color="#3b82f6" /> <span style={{ fontWeight: 600 }}>Console & Test Results</span></div>
                                    </div>
                                ) : isSql ? (
                                    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                                        <div style={{ padding: '.75rem 1.25rem', background: '#0f172a', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <div style={{ display: 'flex', gap: '1.25rem' }}>
                                                {['validator', 'visualizer', 'debugger'].map(t => <button key={t} onClick={() => setSqlTool(t)} style={{ padding: '.5rem .75rem', background: 'transparent', color: sqlTool === t ? '#3b82f6' : '#94a3b8', border: 'none', borderBottom: sqlTool === t ? '2px solid #3b82f6' : '2px solid transparent', cursor: 'pointer', fontSize: '.85rem', fontWeight: 600, textTransform: 'capitalize' }}>{t}</button>)}
                                            </div>
                                            <button onClick={() => setIsConsoleOpen(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><ChevronDown size={18} /></button>
                                        </div>
                                        <div style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}>
                                            {sqlTool === 'validator' && <SQLValidator query={codeOrSql} schemaContext={currentQ.sqlSchema || currentQ.starterCode} />}
                                            {sqlTool === 'visualizer' && <SQLVisualizer schema={currentQ.sqlSchema || currentQ.starterCode} />}
                                            {sqlTool === 'debugger' && <SQLDebugger query={codeOrSql} schema={currentQ.sqlSchema || currentQ.starterCode} />}
                                        </div>
                                    </div>
                                ) : (
                                    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                                        <div style={{ display: 'flex', borderBottom: '1px solid rgba(59,130,246,0.1)', justifyContent: 'space-between', paddingRight: '1rem' }}>
                                            <div style={{ display: 'flex' }}>
                                                {['input', 'output', 'tests'].map(tab => (
                                                    <button key={tab} onClick={() => setActiveTab(p => ({ ...p, [currentQ.id]: tab }))} style={{ padding: '1rem 1.5rem', background: (activeTab[currentQ.id] || 'input') === tab ? 'rgba(30,41,59,0.8)' : 'transparent', border: 'none', borderBottom: (activeTab[currentQ.id] || 'input') === tab ? '3px solid #3b82f6' : '3px solid transparent', color: (activeTab[currentQ.id] || 'input') === tab ? '#60a5fa' : '#94a3b8', cursor: 'pointer', fontSize: '.9rem', fontWeight: 600, textTransform: 'capitalize' }}>{tab}</button>
                                                ))}
                                            </div>
                                            <button onClick={() => setIsConsoleOpen(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><ChevronDown size={18} /></button>
                                        </div>
                                        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
                                            {(activeTab[currentQ.id] || 'input') === 'input' && <textarea value={customInputs[currentQ.id] || ''} onChange={e => setCustomInputs(p => ({ ...p, [currentQ.id]: e.target.value }))} placeholder="Enter custom input..." style={{ width: '100%', height: '100%', background: 'rgba(15,23,42,0.6)', color: '#e2e8f0', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 12, padding: '1.25rem', fontFamily: 'monospace', resize: 'none', outline: 'none', fontSize: '.9rem' }} />}
                                            {(activeTab[currentQ.id] || 'input') === 'output' && <div style={{ fontFamily: 'monospace', color: '#e2e8f0', fontSize: '.9rem', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{consoleOutput[currentQ.id] || 'No output yet. Run your code.'}</div>}
                                            {(activeTab[currentQ.id] || 'input') === 'tests' && <CodeOutputPreview problemId={currentQ.id} code={codeOrSql} language={currentLang} isGlobalTest onRunComplete={r => { if (r?.testResults) { const p = r.testResults.filter(x => x.passed).length; setTestResults(prev => ({ ...prev, [currentQ.id]: { passed: p, total: r.testResults.length } })); if (user && socketService) socketService.emitProgressUpdate(user.id, currentQ.id, Math.round((p / r.testResults.length) * 100), null) } }} />}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* FOOTER */}
            <div style={{ padding: '.75rem 2rem', borderTop: '1px solid rgba(139,92,246,0.2)', background: 'linear-gradient(180deg,rgba(15,23,42,0.98),rgba(15,23,42,0.95))', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backdropFilter: 'blur(12px)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span style={{ fontSize: '.85rem', color: '#64748b' }}>Question {allQuestions.indexOf(currentQ) + 1} of {totalQuestions}</span>
                    <div style={{ display: 'flex', gap: '.5rem' }}>
                        <button onClick={prevQuestion} style={{ padding: '.5rem 1rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: '#94a3b8', cursor: 'pointer', fontSize: '.85rem', display: 'flex', alignItems: 'center', gap: '.35rem' }}><ChevronLeft size={16} /> Prev</button>
                        <button onClick={nextQuestion} style={{ padding: '.5rem 1rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: '#94a3b8', cursor: 'pointer', fontSize: '.85rem', display: 'flex', alignItems: 'center', gap: '.35rem' }}>Next <ChevronRight size={16} /></button>
                    </div>
                </div>
                <button onClick={() => handleSubmit(false)} disabled={isSubmitting} style={{ padding: '.75rem 2rem', borderRadius: 12, border: 'none', background: isSubmitting ? '#374151' : 'linear-gradient(135deg,#8b5cf6,#6366f1)', color: 'white', fontWeight: 700, cursor: isSubmitting ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '.5rem', boxShadow: isSubmitting ? 'none' : '0 4px 20px rgba(139,92,246,0.4)', fontSize: '.95rem' }}>
                    <Send size={18} /> {isSubmitting ? 'Submitting...' : 'Submit Test'}
                </button>
            </div>

            <canvas ref={canvasRef} style={{ display: 'none' }} />
        </div>
    )
}
