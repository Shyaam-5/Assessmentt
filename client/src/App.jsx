import { useState, useEffect, createContext, useContext, Component } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Login from './pages/Login'
import StudentPortal from './pages/StudentPortal'
import MentorPortal from './pages/MentorPortal'
import AdminPortal from './pages/AdminPortal'
import ScanMobilePage from './prescan/pages/ScanMobilePage'
import ScanDesktopPage from './prescan/pages/ScanDesktopPage'

// Error Boundary to catch React runtime errors
class ErrorBoundary extends Component {
    constructor(props) { super(props); this.state = { hasError: false, error: null } }
    static getDerivedStateFromError(error) { return { hasError: true, error } }
    componentDidCatch(error, info) { console.error('ErrorBoundary caught:', error, info) }
    render() {
        if (this.state.hasError) {
            return (<div style={{ padding: 40, background: '#1e1e2e', color: '#ff6b6b', minHeight: '100vh', fontFamily: 'monospace' }}>
                <h1>Something went wrong</h1>
                <pre style={{ whiteSpace: 'pre-wrap', color: '#ffa07a' }}>{this.state.error?.message}</pre>
                <pre style={{ whiteSpace: 'pre-wrap', color: '#888', fontSize: 12 }}>{this.state.error?.stack}</pre>
                <button onClick={() => this.setState({ hasError: false, error: null })} style={{ marginTop: 20, padding: '10px 20px', background: '#4a4a6a', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer' }}>Try Again</button>
            </div>)
        }
        return this.props.children
    }
}

// Create Auth Context
export const AuthContext = createContext(null)
export const ThemeContext = createContext(null)

export const useAuth = () => useContext(AuthContext)
export const useTheme = () => useContext(ThemeContext)

// Protected Route Component
function ProtectedRoute({ children, allowedRoles }) {
    const { user } = useAuth()

    if (!user) {
        return <Navigate to="/login" replace />
    }

    if (allowedRoles && !allowedRoles.includes(user.role)) {
        return <Navigate to={`/${user.role}`} replace />
    }

    return children
}

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api'

function App() {
    const [user, setUser] = useState(null)
    const [theme, setTheme] = useState(() => {
        const saved = localStorage.getItem('theme')
        if (saved) return saved
        // Auto-detect system preference
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    })
    const [loading, setLoading] = useState(true)
    const navigate = useNavigate()

    useEffect(() => {
        // Check for saved user session and verify with backend
        const verifySession = async () => {
            try {
                const savedUser = localStorage.getItem('currentUser')
                if (savedUser && savedUser !== 'undefined') {
                    const parsedUser = JSON.parse(savedUser)

                    // Verify with backend
                    const response = await fetch(`${API_BASE}/auth/verify`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ userId: parsedUser.id })
                    })

                    if (response.ok) {
                        const data = await response.json()
                        setUser(data.user)
                        localStorage.setItem('currentUser', JSON.stringify(data.user))
                    } else {
                        console.warn('Session invalid or expired')
                        localStorage.removeItem('currentUser')
                        setUser(null)
                    }
                }
            } catch (error) {
                console.error('Session verification failed:', error)
                localStorage.removeItem('currentUser')
                setUser(null)
            } finally {
                setLoading(false)
            }
        }

        verifySession()
    }, [])

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme)
        localStorage.setItem('theme', theme)
    }, [theme])

    const login = async (email, password) => {
        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            })

            const data = await response.json()

            if (!response.ok) {
                throw new Error(data.error || 'Login failed')
            }

            setUser(data.user)
            localStorage.setItem('currentUser', JSON.stringify(data.user))

            // Navigate to appropriate portal based on role
            navigate(`/${data.user.role}`)

            return { success: true }
        } catch (error) {
            return { success: false, error: error.message }
        }
    }

    const logout = () => {
        setUser(null)
        localStorage.removeItem('currentUser')
        navigate('/login')
    }

    const toggleTheme = () => {
        setTheme(prev => prev === 'light' ? 'dark' : 'light')
    }

    if (loading) {
        return (
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                background: 'var(--bg-secondary)'
            }}>
                <div className="loading-spinner"></div>
            </div>
        )
    }

    return (
        <AuthContext.Provider value={{ user, login, logout }}>
            <ThemeContext.Provider value={{ theme, toggleTheme }}>
                <ErrorBoundary>
                <Routes>
                    <Route path="/login" element={
                        user ? <Navigate to={`/${user.role}`} replace /> : <Login />
                    } />

                    <Route path="/student/*" element={
                        <ProtectedRoute allowedRoles={['student']}>
                            <StudentPortal />
                        </ProtectedRoute>
                    } />

                    <Route path="/mentor/*" element={
                        <ProtectedRoute allowedRoles={['mentor']}>
                            <MentorPortal />
                        </ProtectedRoute>
                    } />

                    <Route path="/admin/*" element={
                        <ProtectedRoute allowedRoles={['admin']}>
                            <AdminPortal />
                        </ProtectedRoute>
                    } />

                    {/* Environment scan routes (public — token-based auth for mobile) */}
                    <Route path="/scan/mobile" element={<ScanMobilePage />} />
                    <Route path="/scan/desktop" element={
                        <ProtectedRoute allowedRoles={['student', 'mentor', 'admin']}>
                            <ScanDesktopPage />
                        </ProtectedRoute>
                    } />

                    <Route path="/" element={
                        user ? <Navigate to={`/${user.role}`} replace /> : <Navigate to="/login" replace />
                    } />

                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
                </ErrorBoundary>
            </ThemeContext.Provider>
        </AuthContext.Provider>
    )
}

export default App
