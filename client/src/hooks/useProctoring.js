/**
 * Proctoring hooks for GlobalTestInterface.
 * Extracted from the monolithic component for modularity.
 *
 * Modes:
 *   standard     — timer + basic tab-switch warning only
 *   enhanced     — tab tracking, fullscreen, copy/paste/DevTools block, multi-monitor
 *   ai_proctored — everything in enhanced + camera/audio, TF.js detection, behavior tracking
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import socketService from '@/services/socketService'

const MAX_VIOLATIONS = 10

// ── Tab & Window Tracking ────────────────────────────────────────
export function useTabTracking(enabled, maxSwitches, onViolation) {
    const [tabSwitches, setTabSwitches] = useState(0)
    const tabRef = useRef(0)

    useEffect(() => {
        if (!enabled) return
        const onVisChange = () => {
            if (document.hidden) {
                tabRef.current += 1
                setTabSwitches(tabRef.current)
                onViolation?.('tab_switch', tabRef.current)
            }
        }
        const onBlur = () => {
            tabRef.current += 1
            setTabSwitches(tabRef.current)
            onViolation?.('window_blur', tabRef.current)
        }
        document.addEventListener('visibilitychange', onVisChange)
        window.addEventListener('blur', onBlur)
        return () => {
            document.removeEventListener('visibilitychange', onVisChange)
            window.removeEventListener('blur', onBlur)
        }
    }, [enabled, onViolation])

    return { tabSwitches, tabSwitchesRef: tabRef }
}

// ── Fullscreen Enforcement ───────────────────────────────────────
export function useFullscreen(enabled, submittedRef) {
    useEffect(() => {
        if (!enabled) return
        const enterFS = () => {
            if (!submittedRef?.current && !document.fullscreenElement) {
                document.documentElement.requestFullscreen?.().catch(() => {})
            }
        }
        enterFS()
        const onFSChange = () => {
            if (!document.fullscreenElement && !submittedRef?.current) {
                setTimeout(enterFS, 300)
            }
        }
        document.addEventListener('fullscreenchange', onFSChange)
        return () => document.removeEventListener('fullscreenchange', onFSChange)
    }, [enabled, submittedRef])
}

// ── Copy/Paste & DevTools Block ──────────────────────────────────
export function useCopyPasteBlock(enabled) {
    const [copyPasteAttempts, setCopyPasteAttempts] = useState(0)
    const cpRef = useRef(0)

    useEffect(() => {
        if (!enabled) return
        const block = (e) => { e.preventDefault(); cpRef.current += 1; setCopyPasteAttempts(cpRef.current) }
        const blockCtx = (e) => e.preventDefault()
        const blockKeys = (e) => {
            if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && 'IJC'.includes(e.key.toUpperCase())) ||
                (e.ctrlKey && e.key === 'u') || e.key === 'PrintScreen') {
                e.preventDefault()
            }
        }
        document.addEventListener('copy', block)
        document.addEventListener('paste', block)
        document.addEventListener('contextmenu', blockCtx)
        document.addEventListener('keydown', blockKeys)
        return () => {
            document.removeEventListener('copy', block)
            document.removeEventListener('paste', block)
            document.removeEventListener('contextmenu', blockCtx)
            document.removeEventListener('keydown', blockKeys)
        }
    }, [enabled])

    return { copyPasteAttempts, copyPasteRef: cpRef }
}

// ── Multi-Monitor Detection ──────────────────────────────────────
export function useMultiMonitorDetection(enabled) {
    const [multipleMonitorCount, setCount] = useState(0)

    useEffect(() => {
        if (!enabled) return
        const check = () => {
            const isExt = window.screen?.isExtended
            const wOff = Math.abs(window.screenX) > 10 || Math.abs(window.screenY) > 50
            const avail = window.screen && (window.screen.availWidth > window.screen.width * 1.5)
            if (isExt || wOff || avail) setCount(c => c + 1)
        }
        const id = setInterval(check, 15000)
        check()
        return () => clearInterval(id)
    }, [enabled])

    return { multipleMonitorCount }
}

// ── Camera & Object Detection (AI-Proctored only) ────────────────
export function useCamera(enabled) {
    const videoRef = useRef(null)
    const canvasRef = useRef(null)
    const [mediaStream, setMediaStream] = useState(null)
    const [videoEnabled, setVideoEnabled] = useState(false)
    const [audioEnabled, setAudioEnabled] = useState(false)
    const [cameraBlocked, setCameraBlocked] = useState(false)
    const [cameraBlockedCount, setCameraBlockedCount] = useState(0)
    const [cameraAccessDenied, setCameraAccessDenied] = useState(false)
    const camBlockRef = useRef(0)
    const camCheckRef = useRef(null)

    const initializeCamera = useCallback(async () => {
        try {
            // Enumerate devices and pick the first local webcam to avoid
            // Windows defaulting to a connected mobile device camera
            const devices = await navigator.mediaDevices.enumerateDevices()
            const webcam = devices.find(d => d.kind === 'videoinput' && d.deviceId)
            const videoConstraints = webcam?.deviceId
                ? { deviceId: { exact: webcam.deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
                : { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
            const stream = await navigator.mediaDevices.getUserMedia({
                video: videoConstraints,
                audio: true
            })
            setMediaStream(stream)
            setVideoEnabled(true)
            setAudioEnabled(true)
            setCameraAccessDenied(false)
            if (videoRef.current) videoRef.current.srcObject = stream
            return true
        } catch {
            setCameraAccessDenied(true)
            return false
        }
    }, [])

    // Camera obstruction check via canvas brightness
    useEffect(() => {
        if (!enabled || !mediaStream) return
        const checkBlocked = () => {
            const video = videoRef.current
            const canvas = canvasRef.current
            if (!video || !canvas || video.videoWidth === 0) return
            const ctx = canvas.getContext('2d')
            canvas.width = 64; canvas.height = 48
            ctx.drawImage(video, 0, 0, 64, 48)
            const data = ctx.getImageData(0, 0, 64, 48).data
            let total = 0
            for (let i = 0; i < data.length; i += 4) total += data[i] + data[i + 1] + data[i + 2]
            const avg = total / (data.length / 4 * 3)
            if (avg < 15) {
                setCameraBlocked(true)
                camBlockRef.current += 1
                setCameraBlockedCount(camBlockRef.current)
            } else {
                setCameraBlocked(false)
            }
        }
        camCheckRef.current = setInterval(checkBlocked, 5000)
        return () => clearInterval(camCheckRef.current)
    }, [enabled, mediaStream])

    const stopCamera = useCallback(() => {
        if (mediaStream) mediaStream.getTracks().forEach(t => t.stop())
        if (camCheckRef.current) clearInterval(camCheckRef.current)
    }, [mediaStream])

    return {
        videoRef, canvasRef, mediaStream, videoEnabled, audioEnabled,
        cameraBlocked, cameraBlockedCount, cameraAccessDenied,
        camBlockRef, initializeCamera, stopCamera,
    }
}

export function useObjectDetection(enabled, videoRef) {
    const [phoneDetectionCount, setPhoneCount] = useState(0)
    const [faceMissingCount, setFaceMissing] = useState(0)
    const phoneRef = useRef(0)
    const faceRef = useRef(0)
    const modelRef = useRef(null)

    useEffect(() => {
        if (!enabled) return
        let mounted = true
        let intervalId = null
        // Cooldown to prevent rapid-fire duplicate alerts
        let lastPhoneAlert = 0
        const PHONE_COOLDOWN_MS = 8000

        const loadAndDetect = async () => {
            try {
                const tf = await import('@tensorflow/tfjs')
                await tf.ready()
                const cocoSsd = await import('@tensorflow-models/coco-ssd')
                modelRef.current = await cocoSsd.load({ base: 'lite_mobilenet_v2' })
                if (!mounted) return
                console.log('✅ Object detection model loaded for proctoring')

                // Fast detection interval (1.5s) matching ProctoredCodeEditor
                intervalId = setInterval(async () => {
                    if (!videoRef.current || videoRef.current.readyState < 2 || !modelRef.current) return
                    try {
                        const preds = await modelRef.current.detect(videoRef.current)

                        // Broader device detection matching ProctoredCodeEditor:
                        // cell phone, laptop, book, remote — all count as suspicious
                        const deviceClasses = ['cell phone', 'laptop', 'book', 'remote']
                        const hasDevice = preds.some(p => deviceClasses.includes(p.class) && p.score > 0.4)
                        const hasFace = preds.some(p => p.class === 'person' && p.score > 0.4)

                        if (hasDevice) {
                            const now = Date.now()
                            if (now - lastPhoneAlert > PHONE_COOLDOWN_MS) {
                                lastPhoneAlert = now
                                phoneRef.current += 1
                                setPhoneCount(phoneRef.current)
                            }
                        }
                        if (!hasFace) { faceRef.current += 1; setFaceMissing(faceRef.current) }
                    } catch { /* ignore detection errors */ }
                }, 1500)
            } catch (err) { console.error('Object detection model load failed:', err) }
        }

        loadAndDetect()
        return () => { mounted = false; if (intervalId) clearInterval(intervalId) }
    }, [enabled, videoRef])

    return { phoneDetectionCount, faceMissingCount, phoneRef, faceRef }
}

// ── Behavior Tracking (AI-Proctored) ─────────────────────────────
export function useBehaviorTracking(enabled, userId, testId) {
    const behaviorSessionId = useRef(`beh-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`)
    const eventsBuffer = useRef([])
    const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:3000') + '/api'

    const flush = useCallback(async () => {
        if (eventsBuffer.current.length === 0) return
        const batch = [...eventsBuffer.current]
        eventsBuffer.current = []
        try {
            await fetch(`${API_BASE}/behavior-agent/events`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: behaviorSessionId.current, userId, testId, events: batch }),
            })
        } catch { /* ignore flush errors */ }
    }, [userId, testId, API_BASE])

    useEffect(() => {
        if (!enabled) return
        const track = (type) => (e) => {
            eventsBuffer.current.push({
                type, ts: Date.now(),
                x: e.clientX || e.pageX || 0, y: e.clientY || e.pageY || 0,
            })
        }
        const onMove = track('mouse_move')
        const onScroll = track('scroll')
        const onFocus = track('focus')
        const onBlurEv = track('blur')

        // Throttle mouse moves
        let lastMove = 0
        const throttledMove = (e) => { if (Date.now() - lastMove > 2000) { lastMove = Date.now(); onMove(e) } }

        document.addEventListener('mousemove', throttledMove)
        document.addEventListener('scroll', onScroll)
        window.addEventListener('focus', onFocus)
        window.addEventListener('blur', onBlurEv)

        const flushId = setInterval(flush, 30000)
        return () => {
            document.removeEventListener('mousemove', throttledMove)
            document.removeEventListener('scroll', onScroll)
            window.removeEventListener('focus', onFocus)
            window.removeEventListener('blur', onBlurEv)
            clearInterval(flushId)
            flush()
        }
    }, [enabled, flush])

    return { behaviorSessionId, flushBehaviorEvents: flush }
}

// ── Agent Termination Listener ───────────────────────────────────
export function useAgentTermination(enabled, userId, sessionId, onTerminate) {
    const [agentTerminated, setAgentTerminated] = useState(false)
    const [terminateReason, setTerminateReason] = useState('')

    useEffect(() => {
        if (!enabled) return
        // Use socketService directly (matches ProctoredCodeEditor pattern)
        socketService.connect()
        if (userId && sessionId) socketService.joinStudentSession(userId, sessionId)
        socketService.onAgentTerminate((data) => {
            console.error('[ProctorAgent] TEST TERMINATED BY AGENT:', data)
            setAgentTerminated(true)
            setTerminateReason(data?.reason || 'Test terminated by proctor.')
            onTerminate?.(data)
        })
        return () => socketService.removeListener('agent_terminate')
    }, [enabled, userId, sessionId, onTerminate])

    return { agentTerminated, terminateReason }
}

export { MAX_VIOLATIONS }
