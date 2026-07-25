import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import Subscription from './pages/Subscription'
import TodayMenu from './pages/TodayMenu'
import Complaints from './pages/Complaints'

import CatererDashboard from './pages/caterer/CatererDashboard'
import CatererMenu from './pages/caterer/CatererMenu'
import CatererRequests from './pages/caterer/CatererRequests'
import CatererComplaints from './pages/caterer/CatererComplaints'
import CatererScan from './pages/caterer/CatererScan'

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token')
  return token ? children : <Navigate to="/login" />
}

function CatererRoute({ children }) {
  const token = localStorage.getItem('token')
  const role = localStorage.getItem('role')
  if (!token) return <Navigate to="/login" />
  if (role !== 'caterer' && role !== 'admin') return <Navigate to="/" />
  return children
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route path="/" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
        <Route path="/subscription" element={<PrivateRoute><Subscription /></PrivateRoute>} />
        <Route path="/menu" element={<PrivateRoute><TodayMenu /></PrivateRoute>} />
        <Route path="/complaints" element={<PrivateRoute><Complaints /></PrivateRoute>} />

        <Route path="/caterer" element={<CatererRoute><CatererDashboard /></CatererRoute>} />
        <Route path="/caterer/menu" element={<CatererRoute><CatererMenu /></CatererRoute>} />
        <Route path="/caterer/requests" element={<CatererRoute><CatererRequests /></CatererRoute>} />
        <Route path="/caterer/complaints" element={<CatererRoute><CatererComplaints /></CatererRoute>} />
        <Route path="/caterer/scan" element={<CatererRoute><CatererScan /></CatererRoute>} />
      </Routes>
    </BrowserRouter>
  )
}

export default App